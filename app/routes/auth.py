from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import re

from app.database import get_db
from app.models import Merchant, DeliveryZone, Product

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Zones de livraison prédéfinies selon la ville choisie
PRESET_ZONES = {
    "Abidjan": [
        ("Cocody (Angré, Riviera, 2 Plateaux)", 1500, "1h - 3h"),
        ("Yopougon (Maroc, Selmer, Bel Air)", 2000, "2h - 4h"),
        ("Marcory & Zone 4 / Biétry", 1500, "1h - 3h"),
        ("Koumassi & Treichville", 1500, "2h - 3h"),
        ("Plateau & Adjamé", 1500, "1h - 2h"),
        ("Bingerville & Bassam", 2500, "3h - 5h"),
    ],
    "Dakar": [
        ("Plateau, Médina, Fann", 1500, "1h - 3h"),
        ("Almadies, Ngor, Yoff", 2000, "1h - 3h"),
        ("Ouakam, Mermoz, Sacré-Cœur", 1500, "1h - 2h"),
        ("Parcelles Assainies & Guédiawaye", 2000, "2h - 4h"),
        ("Pikine & Rufisque", 2500, "3h - 5h"),
    ],
    "Douala": [
        ("Akwa & Bonanjo (Centre-ville)", 1500, "1h - 2h"),
        ("Bonapriso & Bali", 1500, "1h - 3h"),
        ("Deido, Bépanda, Ndokoti", 2000, "2h - 4h"),
        ("Bonabéri & Yassa", 2500, "3h - 5h"),
    ],
    "Yaoundé": [
        ("Bastos & Centre administratif", 1500, "1h - 3h"),
        ("Biyem-Assi & Mendong", 2000, "2h - 4h"),
        ("Mvan & Nsam", 2000, "2h - 4h"),
        ("Ngoa-Ekélé & Melen", 1500, "1h - 3h"),
    ],
    "Bamako": [
        ("ACI 2000 & Hamdallaye", 1500, "1h - 3h"),
        ("Badalabougou & Badala Est", 1500, "1h - 3h"),
        ("Sébénikoro & Djicoroni", 2000, "2h - 4h"),
        ("Yirimadio & Faladié", 2500, "3h - 5h"),
    ],
    "Ouagadougou": [
        ("Ouaga 2000", 1500, "1h - 3h"),
        ("Centre-ville & Koulouba", 1500, "1h - 3h"),
        ("Patte d'Oie & Dassasgho", 2000, "2h - 4h"),
        ("Tampouy & Tanghin", 2000, "2h - 4h"),
    ]
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

    # Initialisation des zones de livraison adaptées à la ville
    city_zones = PRESET_ZONES.get(city, PRESET_ZONES["Abidjan"])
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
