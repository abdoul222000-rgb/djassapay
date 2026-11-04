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
# PRÉSETS 100% CÔTE D'IVOIRE (TOUTES LES COMMUNES & VILLES)
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
    ("Ferkessédougou", 3500, "24h - 48h (Colis)"),
    ("Bondoukou & Bouna", 3500, "24h - 48h (Colis)"),
    ("Toumodi & Tiébissou", 2500, "24h - 48h (Colis)"),
    ("Daoukro & Dimbokro", 2500, "24h - 48h (Colis)"),
    ("Séguéla & Worodougou", 3500, "24h - 48h (Colis)"),
    ("Odienné & Kabadougou", 4000, "24h - 48h (Colis)"),
]

ALL_CI_ZONES = COMMUNES_ABIDJAN + VILLES_INTERIEUR_CI

# Zones prédéfinies pour les boutiques en Côte d'Ivoire
PRESET_ZONES = {
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
    "Songon & Dabou": ALL_CI_ZONES,
    "Anyama": ALL_CI_ZONES,
    "Yamoussoukro": ALL_CI_ZONES,
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
}

def slugify(text: str) -> str:
    """Génère un slug URL propre."""
    text = text.lower().strip()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    return text or "boutique"

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
    store_name: str = Form(...),
    city: str = Form("Abidjan"),
    country: str = Form("CI"),
    pin_code: str = Form("1234"),
    db: Session = Depends(get_db)
):
    """Enregistre un nouveau commerçant et prépare sa boutique prête à vendre."""
    # Nettoyer téléphone
    clean_phone = "".join([c for c in phone if c.isdigit()])
    
    # Vérifier si ce numéro a déjà une boutique
    existing = db.query(Merchant).filter(Merchant.phone == clean_phone).first()
    if existing:
        return RedirectResponse(url="/login?error=exists", status_code=303)

    # Générer le slug
    base_slug = slugify(store_name)
    slug = base_slug
    counter = 1
    while db.query(Merchant).filter(Merchant.store_slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Création du Marchand
    merchant = Merchant(
        name=name.strip(),
        phone=clean_phone,
        store_name=store_name.strip(),
        store_slug=slug,
        city=city,
        country=country,
        pin_code=pin_code.strip() or "1234",
        bio=f"Boutique officielle {store_name} à {city}. Vente sécurisée avec acompte Wave & Mobile Money.",
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

    # Initialisation des zones de livraison adaptées à la ville (Côte d'Ivoire)
    city_zones = PRESET_ZONES.get(city, ALL_CI_ZONES)
    for z_name, fee, eta in city_zones:
        zone = DeliveryZone(
            merchant_id=merchant.id,
            name=z_name,
            fee=fee,
            estimated_time=eta
        )
        db.add(zone)

    # Ajouter 1 premier produit exemple pour que la boutique ne soit pas vide
    example_product = Product(
        merchant_id=merchant.id,
        title="Article de Bienvenue (Modèle)",
        description="Ceci est votre premier article de test. Vous pouvez le modifier ou le supprimer dans votre espace produits.",
        price=12000,
        compare_at_price=15000,
        image_url="https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80",
        stock=5
    )
    db.add(example_product)
    db.commit()

    # Redirection vers le dashboard avec cookie de session
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
    """Connexion avec numéro WhatsApp + Code PIN."""
    clean_phone = "".join([c for c in phone if c.isdigit()])
    merchant = db.query(Merchant).filter(
        (Merchant.phone == clean_phone) | (Merchant.phone == phone.strip())
    ).first()

    if not merchant:
        return RedirectResponse(url="/login?error=not_found", status_code=303)

    if merchant.pin_code and merchant.pin_code != pin_code.strip():
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
