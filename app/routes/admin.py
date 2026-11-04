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

FOUNDER_SESSION_TOKEN = "djassa_founder_auth_token_2026"

def is_founder_authenticated(request: Request) -> bool:
    """Vérifie si le cookie de session Fondateur est valide."""
    return request.cookies.get("founder_session") == FOUNDER_SESSION_TOKEN

@router.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request):
    """Redirection de la racine admin."""
    if is_founder_authenticated(request):
        return RedirectResponse(url="/admin/payouts", status_code=303)
    return RedirectResponse(url="/admin/login", status_code=303)

@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Portail d'authentification exclusif pour le Fondateur."""
    if is_founder_authenticated(request):
        return RedirectResponse(url="/admin/payouts", status_code=303)
    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "error": request.query_params.get("error")
    })

@router.post("/admin/login")
async def process_admin_login(pin: str = Form(...)):
    """Validation du code secret ou mot de passe Fondateur."""
    clean_pin = pin.strip()
    # Accepte soit le code PIN (par défaut 7788), soit le mot de passe de secours
    if clean_pin in [settings.FOUNDER_PIN, settings.FOUNDER_PASSWORD, "7788"]:
        redirect = RedirectResponse(url="/admin/payouts", status_code=303)
        redirect.set_cookie(
            key="founder_session",
            value=FOUNDER_SESSION_TOKEN,
            max_age=3600 * 24 * 30, # 30 jours
            httponly=True,
            samesite="lax"
        )
        return redirect
    return RedirectResponse(url="/admin/login?error=1", status_code=303)

@router.get("/admin/logout")
async def admin_logout():
    """Déconnexion et verrouillage de l'Espace Fondateur."""
    redirect = RedirectResponse(url="/admin/login?logged_out=1", status_code=303)
    redirect.delete_cookie(key="founder_session")
    return redirect

@router.get("/admin/payouts", response_class=HTMLResponse)
async def admin_payouts_page(request: Request, db: Session = Depends(get_db)):
    """Portail Fondateur : Réservé EXCLUSIVEMENT au Fondateur de la plateforme."""
    if not is_founder_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

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
    request: Request,
    founder_name: str = Form(...),
    founder_pin: str = Form("7788"),
    founder_wave_number: str = Form(""),
    founder_orange_money_number: str = Form(""),
    founder_mtn_momo_number: str = Form(""),
    commission_percentage: float = Form(1.5),
    wave_api_key: str = Form(""),
    wave_webhook_secret: str = Form(""),
    cinetpay_api_key: str = Form(""),
    cinetpay_site_id: str = Form("")
):
    """Met à jour les comptes de réception et le code secret du fondateur."""
    if not is_founder_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    settings.FOUNDER_NAME = founder_name
    settings.FOUNDER_PIN = founder_pin.strip() or "7788"
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

# 1. Sécurité Accès Fondateur
FOUNDER_PIN={settings.FOUNDER_PIN}
FOUNDER_PASSWORD={settings.FOUNDER_PASSWORD}

# 2. Vos Numéros Directs de Réception (Pour recevoir l'argent)
FOUNDER_NAME={founder_name}
FOUNDER_WAVE_NUMBER={founder_wave_number}
FOUNDER_ORANGE_MONEY_NUMBER={founder_orange_money_number}
FOUNDER_MTN_MOMO_NUMBER={founder_mtn_momo_number}
COMMISSION_PERCENTAGE={commission_percentage}

# 3. Clés API Wave Business (Optionnel au début, pour encaissements 100% automatiques)
WAVE_API_KEY={wave_api_key}
WAVE_WEBHOOK_SECRET={wave_webhook_secret}

# 4. Clés API CinetPay (Pour Orange Money, MTN, Moov, Wave dans 10 pays d'Afrique)
CINETPAY_API_KEY={cinetpay_api_key}
CINETPAY_SITE_ID={cinetpay_site_id}
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    return RedirectResponse(url="/admin/payouts?saved=1", status_code=303)
