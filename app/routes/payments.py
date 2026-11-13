from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import httpx

from app.database import get_db
from app.config import settings
from app.models import Order, Merchant, PaymentStatusEnum
from app.services.payment_service import PaymentService
from app.services.whatsapp_service import auto_notify_deposit_confirmed, generate_customer_order_whatsapp

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/payments/pay/{order_number}")
async def initiate_customer_payment(
    request: Request,
    order_number: str,
    db: Session = Depends(get_db)
):
    """
    Guichet de paiement 100% Côte d'Ivoire (Wave CI, Orange Money, MTN MoMo, Moov).
    Permet à la cliente de régler son acompte Anti-Lapin directement à la boutique.
    """
    clean_number = order_number.strip().upper()
    order = db.query(Order).filter(Order.order_number == clean_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()

    # Si Wave avec Clé API Wave Business configurée, rediriger vers Wave Checkout officiel
    if order.payment_method == "WAVE" and settings.WAVE_API_KEY:
        wave_res = PaymentService.initiate_wave_payment(order, merchant)
        if wave_res.get("payment_url") and not wave_res.get("is_simulation"):
            return RedirectResponse(url=wave_res["payment_url"], status_code=303)

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
    whatsapp_url = generate_customer_order_whatsapp(order, merchant)

    return templates.TemplateResponse("payments/simulate.html", {
        "request": request,
        "order": order,
        "merchant": merchant,
        "method": method.upper(),
        "whatsapp_url": whatsapp_url,
        "settings": settings
    })

@router.post("/payments/simulate/{order_number}/confirm")
async def confirm_simulated_payment(
    order_number: str,
    method: str = Form("WAVE"),
    transaction_ref: str = Form(""),
    db: Session = Depends(get_db)
):
    """Valide instantanément le paiement direct Wave / Mobile Money Côte d'Ivoire."""
    clean_number = order_number.strip().upper()
    order = db.query(Order).filter(Order.order_number == clean_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    order.payment_method = method.upper()
    ref = transaction_ref.strip() if transaction_ref else None
    PaymentService.mark_deposit_as_paid(order, db, transaction_ref=ref)

    # Déclencher les alertes WhatsApp automatiques au client et au marchand
    try:
        merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()
        if merchant:
            await auto_notify_deposit_confirmed(order, merchant)
    except Exception as e:
        print(f"[WhatsApp Deposit Trigger Error] {e}")

    return RedirectResponse(url=f"/orders/{order.order_number}?paid=1", status_code=303)

@router.post("/payments/webhook/wave")
async def wave_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook officiel Wave : Reçoit les confirmations réelles 24h/24 en toute autonomie.
    - Valide les acomptes de commande client.
    - Valide et active instantanément les abonnements PRO des vendeurs !
    """
    try:
        data = await request.json()
        client_ref = data.get("data", {}).get("client_reference", "")
        
        if client_ref:
            # 1. CAS ABONNEMENT PRO / BUSINESS MARCHANT (ex: SUB-15-PRO-1794182900)
            if client_ref.startswith("SUB-"):
                parts = client_ref.split("-")
                merchant_id = int(parts[1])
                target_plan = parts[2] if len(parts) > 2 else "PRO"
                
                merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
                if merchant:
                    merchant.subscription_plan = target_plan
                    merchant.subscription_status = "ACTIVE"
                    paid_amt = int(data.get("data", {}).get("amount", 6750))
                    merchant.subscription_paid_amount = (merchant.subscription_paid_amount or 0) + paid_amt
                    db.commit()
                    print(f"[Wave Webhook Autonome] Abonnement {target_plan} validé automatiquement pour {merchant.store_name} !")
                    return JSONResponse({"status": "success", "message": "Subscription activated"})

            # 2. CAS ACOMPTE ANTI-LAPIN COMMANDE CLIENT
            else:
                order = db.query(Order).filter(Order.order_number == client_ref).first()
                if order:
                    PaymentService.mark_deposit_as_paid(order, db, transaction_ref=data.get("id"))
                    print(f"[Wave Webhook Autonome] Acompte de commande {order.order_number} validé !")
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
