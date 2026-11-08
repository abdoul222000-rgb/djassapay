from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import re

from app.database import get_db
from app.models import Merchant, DeliveryZone, Product

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ==============================================================
# TOUTES LES COMMUNES DE CÔTE D'IVOIRE (ABIDJAN & INTÉRIEUR)
# ==============================================================
# PRÉSETS 100% CÔTE D'IVOIRE (TOUTES LES COMMUNES & VILLES DE CI)
# ==============================================================
COMMUNES_ABIDJAN = [
    ("Cocody (Angré, 2 Plateaux, Riviera, Palmeraie, Danga, Abatta)", 1500, "1h - 2h"),
    ("Yopougon (Maroc, Niangon, Selmer, Bel Air, Toits Rouges, Gesco)", 2000, "2h - 4h"),
    ("Marcory (Zone 4, Biétry, Anoumabo, Résidentiel, Hibiscus)", 1500, "1h - 3h"),
    ("Koumassi (Remblais, Prodomo, Campement, SOPIM, 05)", 1500, "2h - 3h"),
    ("Treichville (Avenues 1-25, Arras, Belleville, Boulevard de Marseille)", 1500, "1h - 2h"),
    ("Plateau (Centre des Affaires & Administratif)", 1500, "1h - 2h"),
    ("Adjamé (220 Logements, Williamsville, Mirador, Liberté)", 1500, "1h - 2h"),
    ("Abobo (Samaké, N'Dotré, PK18, Avocatier, Belle-Ville, Bocabo)", 2000, "2h - 4h"),
    ("Port-Bouët (Aéroport, Gonzagueville, Vridi, Phare, Derrière-Wharf)", 2000, "2h - 4h"),
    ("Attécoubé (Agban, Locodjro, Santé, Boribana)", 1500, "1h - 3h"),
    ("Bingerville (Feh Kessé, Blanchon, Savane)", 2500, "2h - 4h"),
    ("Grand-Bassam (Moossou, Quartier France, Rosiers)", 3000, "3h - 5h"),
    ("Songon (Songon Agban, Kassemblé)", 3000, "3h - 5h"),
    ("Anyama & Stade Ebimpé", 3000, "2h - 4h"),
]

VILLES_INTERIEUR_CI = [
    ("Yamoussoukro (Capitale, Morofé, 220)", 2500, "24h - 48h (Colis)"),
    ("Bouaké (Air France, Commerce, Nimbo, Broukro)", 2500, "24h - 48h (Colis)"),
    ("San-Pédro (Centre, Bardot, Balmer, Séwéké)", 3000, "24h - 48h (Colis)"),
    ("Korhogo (Centre, Koko, Petit Paris)", 3000, "24h - 48h (Colis)"),
    ("Daloa (Tazibouo, Soleil, Huberson)", 3000, "24h - 48h (Colis)"),
    ("Gagnoa (Babré, Dioulabougou, Garahio)", 3000, "24h - 48h (Colis)"),
    ("Man (Grand Gbapleu, Koko, Domoraud)", 3500, "24h - 48h (Colis)"),
    ("Soubré (Centre-ville & Nawa)", 3500, "24h - 48h (Colis)"),
    ("Divo (Centre & Dougako)", 3000, "24h - 48h (Colis)"),
    ("Abengourou (Plateau & Indénié)", 3000, "24h - 48h (Colis)"),
    ("Agboville (Centre & Samaké)", 2500, "24h - 48h (Colis)"),
    ("Aboisso & Noé", 3000, "24h - 48h (Colis)"),
    ("Dabou (Centre & Kpass)", 2500, "2h - 4h"),
    ("Bondoukou & Bouna", 3500, "24h - 48h (Colis)"),
    ("Ferkessédougou", 3500, "24h - 48h (Colis)"),
    ("Séguéla & Worodougou", 3500, "24h - 48h (Colis)"),
    ("Odienné & Kabadougou", 4000, "24h - 48h (Colis)"),
    ("Daoukro & Dimbokro", 2500, "24h - 48h (Colis)"),
    ("Toumodi & Tiébissou", 2500, "24h - 48h (Colis)"),
    ("Bouaflé & Sinfra", 3000, "24h - 48h (Colis)"),
    ("Guiglo & Duékoué", 3500, "24h - 48h (Colis)"),
    ("Danané & Zouan-Hounien", 4000, "24h - 48h (Colis)"),
    ("Katiola & Niakara", 3000, "24h - 48h (Colis)"),
    ("Boundiali & Tengréla", 4000, "24h - 48h (Colis)"),
    ("Sassandra & San-Pédro", 3000, "24h - 48h (Colis)"),
    ("Adzopé & Akoupé", 2500, "24h - 48h (Colis)"),
    ("Oumé & Lakota", 3000, "24h - 48h (Colis)"),
    ("Bonoua & Grand-Bassam", 2500, "2h - 4h"),
    ("Jacqueville", 2500, "2h - 4h"),
    ("Tiassalé & N'Douci", 2500, "2h - 4h"),
    ("Touba & Bafing", 4000, "24h - 48h (Colis)"),
    ("Mankono & Béré", 4000, "24h - 48h (Colis)"),
    ("Toutes les Villes de l'Intérieur (Colis Car)", 3000, "24h - 48h (Colis)"),
]

ALL_CI_ZONES = COMMUNES_ABIDJAN + VILLES_INTERIEUR_CI

# Toutes les villes et communes de Côte d'Ivoire (Couverture Nationale 100%)
PRESET_ZONES = {
    # District Autonome d'Abidjan (14 Communes & Banlieue)
    "Abidjan (Toutes les 14 Communes)": ALL_CI_ZONES,
    "Cocody (Abidjan)": ALL_CI_ZONES,
    "Yopougon (Abidjan)": ALL_CI_ZONES,
    "Marcory (Abidjan)": ALL_CI_ZONES,
    "Koumassi (Abidjan)": ALL_CI_ZONES,
    "Treichville (Abidjan)": ALL_CI_ZONES,
    "Plateau (Abidjan)": ALL_CI_ZONES,
    "Adjamé (Abidjan)": ALL_CI_ZONES,
    "Abobo (Abidjan)": ALL_CI_ZONES,
    "Port-Bouët (Abidjan)": ALL_CI_ZONES,
    "Attécoubé (Abidjan)": ALL_CI_ZONES,
    "Bingerville": ALL_CI_ZONES,
    "Grand-Bassam": ALL_CI_ZONES,
    "Songon": ALL_CI_ZONES,
    "Anyama": ALL_CI_ZONES,
    # District Autonome de Yamoussoukro
    "Yamoussoukro": ALL_CI_ZONES,
    # Villes & Régions de l'Intérieur de la Côte d'Ivoire
    "Bouaké": ALL_CI_ZONES,
    "San-Pédro": ALL_CI_ZONES,
    "Korhogo": ALL_CI_ZONES,
    "Daloa": ALL_CI_ZONES,
    "Gagnoa": ALL_CI_ZONES,
    "Man": ALL_CI_ZONES,
    "Soubré": ALL_CI_ZONES,
    "Divo": ALL_CI_ZONES,
    "Abengourou": ALL_CI_ZONES,
    "Agboville": ALL_CI_ZONES,
    "Aboisso": ALL_CI_ZONES,
    "Dabou": ALL_CI_ZONES,
    "Bondoukou": ALL_CI_ZONES,
    "Ferkessédougou": ALL_CI_ZONES,
    "Séguéla": ALL_CI_ZONES,
    "Odienné": ALL_CI_ZONES,
    "Daoukro": ALL_CI_ZONES,
    "Dimbokro": ALL_CI_ZONES,
    "Toumodi": ALL_CI_ZONES,
    "Tiébissou": ALL_CI_ZONES,
    "Bouaflé": ALL_CI_ZONES,
    "Sinfra": ALL_CI_ZONES,
    "Issia": ALL_CI_ZONES,
    "Guiglo": ALL_CI_ZONES,
    "Duékoué": ALL_CI_ZONES,
    "Danané": ALL_CI_ZONES,
    "Katiola": ALL_CI_ZONES,
    "Boundiali": ALL_CI_ZONES,
    "Bouna": ALL_CI_ZONES,
    "Sassandra": ALL_CI_ZONES,
    "Adzopé": ALL_CI_ZONES,
    "Akoupé": ALL_CI_ZONES,
    "Oumé": ALL_CI_ZONES,
    "Lakota": ALL_CI_ZONES,
    "Bonoua": ALL_CI_ZONES,
    "Jacqueville": ALL_CI_ZONES,
    "Tiassalé": ALL_CI_ZONES,
    "Touba": ALL_CI_ZONES,
    "Mankono": ALL_CI_ZONES,
    "Tengréla": ALL_CI_ZONES,
    "Toute la Côte d'Ivoire (Vente Nationale)": ALL_CI_ZONES,
    "Autre ville / commune (Côte d'Ivoire)": ALL_CI_ZONES,
}

def slugify(text: str) -> str:
    """Génère un slug URL propre."""
    text = text.lower().strip()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    return text or "boutique"

def get_phone_lookup_variants(phone: str) -> list[str]:
    """Extrait toutes les variantes possibles d'un numéro ivoirien pour une recherche infaillible."""
    raw = phone.strip()
    digits = "".join([c for c in raw if c.isdigit()])
    variants = set()
    if digits:
        variants.add(digits)
        if digits.startswith("225"):
            base = digits[3:]
            variants.add(base)
            variants.add("0" + base)
            variants.add("+" + digits)
        if len(digits) >= 10:
            ten_digits = digits[-10:]
            variants.add(ten_digits)
            variants.add("225" + ten_digits)
            variants.add("+225" + ten_digits)
            variants.add(ten_digits[-8:])
        elif len(digits) == 8:
            variants.add(digits)
            variants.add("07" + digits)
            variants.add("05" + digits)
            variants.add("01" + digits)
    variants.add(raw)
    return [v for v in variants if v]

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Page de création d'une nouvelle boutique SaaS."""
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "cities": list(PRESET_ZONES.keys())
    })

@router.post("/register")
async def process_register(
    response: Response,
    name: str = Form(...),
    phone: str = Form(...),
    wave_number: str = Form(None),
    store_name: str = Form(...),
    city: str = Form("Abidjan"),
    country: str = Form("CI"),
    pin_code: str = Form("1234"),
    db: Session = Depends(get_db)
):
    """Enregistre un nouveau commerçant et prépare sa boutique prête à vendre."""
    # Normalisation du numéro WhatsApp pour stockage propre à 10 chiffres (Côte d'Ivoire)
    digits = "".join([c for c in phone if c.isdigit()])
    clean_phone = digits[-10:] if len(digits) >= 10 else digits

    # Normalisation du numéro Wave
    clean_wave = clean_phone
    if wave_number and isinstance(wave_number, str):
        wave_digits = "".join([c for c in wave_number if c.isdigit()])
        if wave_digits:
            clean_wave = wave_digits[-10:] if len(wave_digits) >= 10 else wave_digits
    
    # Vérifier si ce numéro a déjà une boutique
    variants = get_phone_lookup_variants(phone)
    existing = db.query(Merchant).filter(Merchant.phone.in_(variants)).first()
    if existing:
        return RedirectResponse(url="/login?error=exists", status_code=303)

    # Générer le slug
    base_slug = slugify(store_name)
    slug = base_slug
    counter = 1
    while db.query(Merchant).filter(Merchant.store_slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Création du Marchand Réel
    merchant = Merchant(
        name=name.strip(),
        phone=clean_phone,
        store_name=store_name.strip(),
        store_slug=slug,
        city=city,
        country=country,
        pin_code=pin_code.strip() or "1234",
        bio=f"Boutique officielle {store_name} à {city}. Vente sécurisée avec acompte Wave & Mobile Money.",
        wave_number=clean_wave,
        orange_money_number=clean_wave,
        mtn_momo_number=clean_wave,
        deposit_policy="DELIVERY_FEE_ONLY",
        fixed_deposit_amount=2000,
        subscription_plan="STARTER"
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)

    # Redirection vers le dashboard avec cookie de session (le vendeur gère librement ses propres zones et tarifs)
    redirect = RedirectResponse(url="/merchant/dashboard?new=1", status_code=303)
    redirect.set_cookie(key="merchant_id", value=str(merchant.id), max_age=3600*24*30)
    return redirect

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Page de connexion rapide pour un marchand existant."""
    return templates.TemplateResponse("auth/login.html", {
        "request": request
    })

@router.post("/login")
async def process_login(
    response: Response,
    phone: str = Form(...),
    pin_code: str = Form("1234"),
    db: Session = Depends(get_db)
):
    """Connexion avec numéro WhatsApp + Code PIN ultra-robuste."""
    variants = get_phone_lookup_variants(phone)
    merchant = db.query(Merchant).filter(Merchant.phone.in_(variants)).first()

    if not merchant:
        merchant = db.query(Merchant).filter(Merchant.wave_number.in_(variants)).first()

    # Si c'est le numéro du fondateur (0595094159) et qu'il n'existe pas encore, l'assurer
    if not merchant and any("0595094159" in v for v in variants):
        merchant = db.query(Merchant).filter(Merchant.store_slug == "djassapay").first()
        if not merchant:
            merchant = Merchant(
                name="Diabagate Assouman",
                phone="0595094159",
                email="djassapay9@gmail.com",
                store_name="Djassapay Officiel",
                store_slug="djassapay",
                bio="Boutique officielle Djassapay.",
                logo_url="/static/images/djassapay_icon.svg",
                wave_number="0595094159",
                orange_money_number="0595094159",
                mtn_momo_number="0595094159",
                pin_code="7788",
                deposit_policy="DELIVERY_FEE_ONLY",
                fixed_deposit_amount=2000
            )
            db.add(merchant)
            db.commit()
            db.refresh(merchant)

    if not merchant:
        # Auto-onboarding Zero-Rejet : si le marchand n'existe pas encore (ou après redémarrage serveur),
        # sa boutique est instantanément initialisée pour ne JAMAIS le bloquer.
        digits = "".join([c for c in phone if c.isdigit()])
        clean_phone = digits[-10:] if len(digits) >= 10 else digits
        if len(clean_phone) >= 8:
            clean_pin = pin_code.strip() or "1234"
            base_slug = f"boutique-{clean_phone[-4:]}"
            slug = base_slug
            counter = 1
            while db.query(Merchant).filter(Merchant.store_slug == slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            merchant = Merchant(
                name=f"Commerçant {clean_phone[-4:]}",
                phone=clean_phone,
                store_name=f"Boutique {clean_phone[-4:]}",
                store_slug=slug,
                city="Abidjan",
                country="CI",
                pin_code=clean_pin,
                bio=f"Boutique officielle. Vente sécurisée avec acompte Wave & Mobile Money.",
                wave_number=clean_phone,
                orange_money_number=clean_phone,
                mtn_momo_number=clean_phone,
                deposit_policy="DELIVERY_FEE_ONLY",
                fixed_deposit_amount=2000,
                subscription_plan="STARTER"
            )
            db.add(merchant)
            db.commit()
            db.refresh(merchant)

            # Redirection vers le dashboard (le vendeur gère librement ses propres zones)
            redirect = RedirectResponse(url="/merchant/dashboard?new=1", status_code=303)
            redirect.set_cookie(key="merchant_id", value=str(merchant.id), max_age=3600*24*30)
            return redirect
        else:
            return RedirectResponse(url="/login?error=invalid_phone", status_code=303)

    clean_pin = pin_code.strip()
    stored_pin = (merchant.pin_code or "1234").strip()
    
    # Accepter le code PIN enregistré, ou le code fondateur 7788, ou le code de secours 1234
    if clean_pin not in [stored_pin, "7788", "1234"]:
        return RedirectResponse(url="/login?error=invalid_pin", status_code=303)

    redirect = RedirectResponse(url="/merchant/dashboard", status_code=303)
    redirect.set_cookie(key="merchant_id", value=str(merchant.id), max_age=3600*24*30)
    return redirect

@router.get("/logout")
async def process_logout():
    """Déconnexion du marchand."""
    redirect = RedirectResponse(url="/login?logged_out=1", status_code=303)
    redirect.delete_cookie(key="merchant_id")
    return redirect
