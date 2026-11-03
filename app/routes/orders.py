from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, Merchant, PaymentStatusEnum, DeliveryStatusEnum
from app.services.whatsapp_service import (
    generate_customer_order_whatsapp, 
    generate_rider_dispatch_whatsapp
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/orders/{order_number}", response_class=HTMLResponse)
async def view_order(request: Request, order_number: str, db: Session = Depends(get_db)):
    """Page de suivi et de paiement de l'acompte pour le client."""
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()
    whatsapp_url = generate_customer_order_whatsapp(order, merchant)

    return templates.TemplateResponse("store/order_detail.html", {
        "request": request,
        "order": order,
        "merchant": merchant,
        "whatsapp_url": whatsapp_url
    })

@router.get("/delivery", response_class=HTMLResponse)
@router.get("/delivery/", response_class=HTMLResponse)
async def list_deliveries(request: Request, db: Session = Depends(get_db)):
    """
    Portail général des coursiers : affiche la liste de toutes les courses
    dont l'acompte a été réglé et qui sont en attente d'expédition ou en cours.
    """
    orders = db.query(Order).filter(
        Order.deposit_paid > 0
    ).order_by(Order.created_at.desc()).all()

    return templates.TemplateResponse("delivery/hub.html", {
        "request": request,
        "orders": orders
    })

@router.get("/delivery/search")
async def search_delivery(code: str = ""):
    """Redirige une recherche rapide de coursier vers la feuille de route."""
    clean_code = code.strip().upper()
    return RedirectResponse(url=f"/delivery/{clean_code}", status_code=303)

@router.get("/delivery/{order_number}", response_class=HTMLResponse)
async def view_delivery_slip(request: Request, order_number: str, db: Session = Depends(get_db)):
    """
    Feuille de route mobile pour le coursier / livreur à moto.
    Accessible directement depuis le lien WhatsApp reçu par le coursier.
    """
    clean_number = order_number.strip().upper()
    order = db.query(Order).filter(Order.order_number == clean_number).first()
    if not order:
        # Si la commande n'existe pas, redirection vers le hub avec message
        return RedirectResponse(url="/delivery?not_found=1", status_code=303)

    merchant = db.query(Merchant).filter(Merchant.id == order.merchant_id).first()

    return templates.TemplateResponse("delivery/slip.html", {
        "request": request,
        "order": order,
        "merchant": merchant
    })

@router.post("/delivery/{order_number}/complete")
async def complete_delivery(
    order_number: str,
    rider_name: str = Form(""),
    rider_phone: str = Form(""),
    db: Session = Depends(get_db)
):
    """Le livreur confirme que le colis a été livré et que le solde cash a été encaissé."""
    clean_number = order_number.strip().upper()
    order = db.query(Order).filter(Order.order_number == clean_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    order.delivery_status = DeliveryStatusEnum.DELIVERED.value
    order.payment_status = PaymentStatusEnum.FULLY_PAID.value
    if rider_name:
        order.delivery_rider_name = rider_name
    if rider_phone:
        order.delivery_rider_phone = rider_phone

    db.commit()
    return RedirectResponse(url=f"/delivery/{clean_number}?success=1", status_code=303)
