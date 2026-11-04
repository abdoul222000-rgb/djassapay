from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import httpx

from app.database import get_db
from app.config import settings
from app.models import Order, Merchant, PaymentStatusEnum
from app.services.payment_service import PaymentService
from app.services.whatsapp_service import auto_notify_deposit_confirmed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/payments/pay/{order_number}")
async def initiate_customer_payment(
    request: Request,
    order_number: str,
    db: Session = Depends(get_db)
):
    """
    Déclenche le paiement de l'acompte Anti-Lapin.
    - Si CinetPay est configuré : redirige vers le vrai CinetPay Checkout (Orange Money, Wave, MTN, Moov).
    - Sinon : bascule sur le simulateur interactif pour tester.
    """
    clean_number = order_number.strip().upper()
    order = db.query(Order).filter(Order.order_number == clean_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()

    # Vérifier si CinetPay Production est activé
    if settings.CINETPAY_API_KEY and settings.CINETPAY_SITE_ID:
        try:
            base_url = str(request.base_url).rstrip('/')
            if "onrender.com" in base_url and base_url.startswith("http://"):
                base_url = "https://" + base_url[7:]

            payload = {
                "apikey": settings.CINETPAY_API_KEY.strip(),
                "site_id": settings.CINETPAY_SITE_ID.strip(),
                "transaction_id": order.order_number,
                "amount": order.deposit_required,
                "currency": "XOF",
                "description": f"Acompte Anti-Lapin #{order.order_number} sur {merchant.store_name if merchant else 'DjassaPay'}",
                "notify_url": f"{base_url}/payments/webhook/cinetpay",
                "return_url": f"{base_url}/payments/return/cinetpay",
                "channels": "ALL",
                "customer_name": order.customer_name[:30] if order.customer_name else "Client",
                "customer_surname": "DjassaPay",
                "customer_phone_number": order.customer_phone
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api-checkout.cinetpay.com/v2/payment", json=payload)
                data = resp.json()

            if data.get("code") == "201" and data.get("data", {}).get("payment_url"):
                return RedirectResponse(url=data["data"]["payment_url"], status_code=303)
            else:
                print(f"[CinetPay API Response] {data}")
        except Exception as e:
            print(f"[CinetPay Initiation Error] {e}")

    # Fallback vers simulateur si pas encore configuré
    return RedirectResponse(url=f"/payments/simulate/{order.order_number}?method={order.payment_method}", status_code=303)

@router.get("/payments/simulate/{order_number}", response_class=HTMLResponse)
async def simulate_payment_page(
    request: Request, 
    order_number: str, 
    method: str = "WAVE", 
    db: Session = Depends(get_db)
):
    """
    Interface de paiement interactive (Wave, Orange Money, MTN MoMo).
    Permet de tester en direct le paiement de l'acompte Anti-Lapin.
    """
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()

    return templates.TemplateResponse("payments/simulate.html", {
        "request": request,
        "order": order,
        "merchant": merchant,
        "method": method.upper()
    })

@router.post("/payments/simulate/{order_number}/confirm")
async def confirm_simulated_payment(
    order_number: str,
    method: str = Form("WAVE"),
    db: Session = Depends(get_db)
):
    """Valide instantanément le paiement de l'acompte Anti-Lapin."""
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    order.payment_method = method.upper()
    PaymentService.mark_deposit_as_paid(order, db)

    # Déclencher les alertes WhatsApp automatiques au client et au marchand
    try:
        merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()
        if merchant:
            await auto_notify_deposit_confirmed(order, merchant)
    except Exception as e:
        print(f"[WhatsApp Deposit Trigger Error] {e}")

    return RedirectResponse(url=f"/orders/{order_number}?paid=1", status_code=303)

@router.post("/payments/webhook/wave")
async def wave_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook pour recevoir les confirmations réelles de l'API Wave."""
    try:
        data = await request.json()
        order_number = data.get("data", {}).get("client_reference")
        if order_number:
            order = db.query(Order).filter(Order.order_number == order_number).first()
            if order:
                PaymentService.mark_deposit_as_paid(order, db, transaction_ref=data.get("id"))
                return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"status": "ignored"})

@router.post("/payments/webhook/cinetpay")
async def cinetpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    URL de Notification IPN pour CinetPay.
    CinetPay envoie les données de validation du paiement Mobile Money / Wave.
    """
    try:
        form_data = await request.form()
        trans_id = form_data.get("cpm_trans_id") # Numéro de commande (ex: DJA-3E70A)
        trans_status = form_data.get("cpm_result") # "00" signifie succès chez CinetPay

        if trans_id:
            clean_order_number = trans_id.strip().upper()
            order = db.query(Order).filter(Order.order_number == clean_order_number).first()
            if order:
                if trans_status == "00" or not trans_status:
                    payment_method = form_data.get("payment_method", "MOBILE_MONEY")
                    order.payment_method = payment_method
                    PaymentService.mark_deposit_as_paid(order, db, transaction_ref=trans_id)
                return JSONResponse({"status": "success", "message": "Order updated"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"status": "received"})

@router.api_route("/payments/return/cinetpay", methods=["GET", "POST"])
async def cinetpay_return(request: Request):
    """
    URL de Retour CinetPay : là où le client est renvoyé après avoir payé.
    """
    # Si CinetPay renvoie le paramètre cpm_trans_id
    trans_id = request.query_params.get("cpm_trans_id")
    if not trans_id and request.method == "POST":
        try:
            form = await request.form()
            trans_id = form.get("cpm_trans_id")
        except Exception:
            pass

    if trans_id:
        return RedirectResponse(url=f"/orders/{trans_id}?paid=1", status_code=303)
    return RedirectResponse(url="/", status_code=303)
