import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import Merchant, Order, PaymentStatusEnum

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/admin/payouts", response_class=HTMLResponse)
async def admin_payouts_page(request: Request, db: Session = Depends(get_db)):
    """Portail Fondateur : Gestion des comptes de réception et suivi des gains."""
    merchants = db.query(Merchant).all()
    orders = db.query(Order).all()

    # Calcul des gains du fondateur
    total_subscriptions = sum(m.subscription_paid_amount or 0 for m in merchants)
    total_sales_volume = sum(o.total_amount for o in orders if o.payment_status in [PaymentStatusEnum.DEPOSIT_PAID.value, PaymentStatusEnum.FULLY_PAID.value])
    total_deposits_volume = sum(o.deposit_paid for o in orders)
    platform_commissions = int((total_deposits_volume * settings.COMMISSION_PERCENTAGE) / 100)
    
    total_founder_earnings = total_subscriptions + platform_commissions

    return templates.TemplateResponse("admin/payouts.html", {
        "request": request,
        "settings": settings,
        "merchants": merchants,
        "total_subscriptions": total_subscriptions,
        "total_sales_volume": total_sales_volume,
        "platform_commissions": platform_commissions,
        "total_founder_earnings": total_founder_earnings
    })

@router.post("/admin/payouts")
async def update_admin_payouts(
    founder_name: str = Form(...),
    founder_wave_number: str = Form(""),
    founder_orange_money_number: str = Form(""),
    founder_mtn_momo_number: str = Form(""),
    commission_percentage: float = Form(1.5),
    wave_api_key: str = Form(""),
    wave_webhook_secret: str = Form(""),
    cinetpay_api_key: str = Form(""),
    cinetpay_site_id: str = Form("")
):
    """Met à jour les comptes de réception du fondateur et les enregistre dans .env."""
    settings.FOUNDER_NAME = founder_name
    settings.FOUNDER_WAVE_NUMBER = founder_wave_number
    settings.FOUNDER_ORANGE_MONEY_NUMBER = founder_orange_money_number
    settings.FOUNDER_MTN_MOMO_NUMBER = founder_mtn_momo_number
    settings.COMMISSION_PERCENTAGE = commission_percentage
    settings.WAVE_API_KEY = wave_api_key
    settings.WAVE_WEBHOOK_SECRET = wave_webhook_secret
    settings.CINETPAY_API_KEY = cinetpay_api_key
    settings.CINETPAY_SITE_ID = cinetpay_site_id

    # Sauvegarde dans le fichier .env
    env_content = f"""# ==============================================================
# CONFIGURATION DES COMPTES DU FONDATEUR (VOS COMPTES DE RÉCEPTION)
# ==============================================================
APP_NAME=DjassaPay
APP_ENV=development
SECRET_KEY={settings.SECRET_KEY}
DATABASE_URL={settings.DATABASE_URL}
BASE_URL={settings.BASE_URL}

# 1. Vos Numéros Directs de Réception (Pour recevoir l'argent)
FOUNDER_NAME={founder_name}
FOUNDER_WAVE_NUMBER={founder_wave_number}
FOUNDER_ORANGE_MONEY_NUMBER={founder_orange_money_number}
FOUNDER_MTN_MOMO_NUMBER={founder_mtn_momo_number}
COMMISSION_PERCENTAGE={commission_percentage}

# 2. Clés API Wave Business (Optionnel au début, pour encaissements 100% automatiques)
WAVE_API_KEY={wave_api_key}
WAVE_WEBHOOK_SECRET={wave_webhook_secret}

# 3. Clés API CinetPay (Pour Orange Money, MTN, Moov, Wave dans 10 pays d'Afrique)
CINETPAY_API_KEY={cinetpay_api_key}
CINETPAY_SITE_ID={cinetpay_site_id}
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    return RedirectResponse(url="/admin/payouts?saved=1", status_code=303)
