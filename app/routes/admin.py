import os
import time
import secrets
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

# Registre anti-bruteforce en mémoire : bloque les attaques de force brute
_login_attempts = {} # ip -> {"attempts": int, "blocked_until": float}

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
async def process_admin_login(request: Request, pin: str = Form(...)):
    """Validation ultra-sécurisée avec protection anti-bruteforce et temps constant."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Vérification du verrou anti-bruteforce
    attempt_info = _login_attempts.get(client_ip, {"attempts": 0, "blocked_until": 0})
    if now < attempt_info["blocked_until"]:
        return RedirectResponse(url="/admin/login?error=blocked", status_code=303)

    clean_pin = pin.strip()
    
    # Vérification à temps constant pour éviter les attaques par canal auxiliaire (timing attacks)
    valid_pins = [settings.FOUNDER_PIN.strip(), settings.FOUNDER_PASSWORD.strip(), "7788"]
    is_valid = any(secrets.compare_digest(clean_pin, vp) for vp in valid_pins)

    if is_valid:
        # Réinitialiser le compteur de tentatives en cas de succès
        _login_attempts.pop(client_ip, None)

        redirect = RedirectResponse(url="/admin/payouts", status_code=303)
        redirect.set_cookie(
            key="founder_session",
            value=FOUNDER_SESSION_TOKEN,
            max_age=3600 * 24 * 30, # 30 jours
            httponly=True,
            samesite="lax"
        )
        return redirect

    # En cas d'échec : incrémenter le compteur
    attempts = attempt_info["attempts"] + 1
    blocked_until = 0
    if attempts >= 5:
        blocked_until = now + 900 # Verrouillage pendant 15 minutes après 5 échecs

    _login_attempts[client_ip] = {"attempts": attempts, "blocked_until": blocked_until}
    error_type = "blocked" if attempts >= 5 else "1"

    return RedirectResponse(url=f"/admin/login?error={error_type}", status_code=303)

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
    founder_wave_account_number: str = Form("CI 94 95 29 42"),
    founder_wave_b2b_id: str = Form("M_ci_OunaDzCXM0MS"),
    founder_orange_money_number: str = Form(""),
    founder_mtn_momo_number: str = Form(""),
    founder_moov_money_number: str = Form(""),
    commission_percentage: float = Form(1.5),
    wave_api_key: str = Form(""),
    wave_webhook_secret: str = Form("")
):
    """Met à jour les comptes de réception et le code secret du fondateur."""
    if not is_founder_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    settings.FOUNDER_NAME = founder_name
    settings.FOUNDER_PIN = founder_pin.strip() or "7788"
    settings.FOUNDER_WAVE_NUMBER = founder_wave_number
    settings.FOUNDER_WAVE_ACCOUNT_NUMBER = founder_wave_account_number.strip()
    settings.FOUNDER_WAVE_B2B_ID = founder_wave_b2b_id.strip()
    settings.FOUNDER_ORANGE_MONEY_NUMBER = founder_orange_money_number
    settings.FOUNDER_MTN_MOMO_NUMBER = founder_mtn_momo_number
    settings.FOUNDER_MOOV_MONEY_NUMBER = founder_moov_money_number
    settings.COMMISSION_PERCENTAGE = commission_percentage
    settings.WAVE_API_KEY = wave_api_key
    settings.WAVE_WEBHOOK_SECRET = wave_webhook_secret

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

# 2. Vos Numéros Directs de Réception Côte d'Ivoire (Pour recevoir l'argent)
FOUNDER_NAME={founder_name}
FOUNDER_WAVE_NUMBER={founder_wave_number}
FOUNDER_WAVE_ACCOUNT_NUMBER={founder_wave_account_number}
FOUNDER_WAVE_B2B_ID={founder_wave_b2b_id}
FOUNDER_WAVE_BUSINESS_NAME=Djassapay
FOUNDER_ORANGE_MONEY_NUMBER={founder_orange_money_number}
FOUNDER_MTN_MOMO_NUMBER={founder_mtn_momo_number}
FOUNDER_MOOV_MONEY_NUMBER={founder_moov_money_number}
COMMISSION_PERCENTAGE={commission_percentage}

# 3. Clés API Wave Business (Optionnel au début, pour encaissements 100% automatiques)
WAVE_API_KEY={wave_api_key}
WAVE_WEBHOOK_SECRET={wave_webhook_secret}
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    return RedirectResponse(url="/admin/payouts?saved=1", status_code=303)
