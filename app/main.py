import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.routes import store, orders, payments, merchant, auth, admin, whatsapp
from app.models import Merchant, DeliveryZone, Product

# Création des tables de la base de données
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version="1.0.0"
)

templates = Jinja2Templates(directory="app/templates")

# Création du dossier static s'il n'existe pas
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routes PWA globales
@app.get("/manifest.json")
async def get_manifest():
    return FileResponse("app/static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
async def get_service_worker():
    return FileResponse("app/static/sw.js", media_type="application/javascript")

# Enregistrement des routes
app.include_router(store.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(merchant.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(whatsapp.router)

@app.on_event("startup")
def startup_populate_data():
    """Initialise le compte marchand officiel et supprime toute boutique démo."""
    db = SessionLocal()
    try:
        from app.routes.auth import ALL_CI_ZONES
        
        # Supprimer l'ancienne boutique démo Glamour Abidjan et ses faux produits
        old_demo = db.query(Merchant).filter(Merchant.store_slug == "glamour-abidjan").first()
        if old_demo:
            db.delete(old_demo)
            db.commit()

        # Vérifier ou créer le compte officiel du Fondateur
        founder_merchant = db.query(Merchant).filter(
            (Merchant.phone == "0595094159") | (Merchant.store_slug == "djassapay")
        ).first()

        if not founder_merchant:
            founder_merchant = Merchant(
                name="Diabagate Assouman",
                phone="0595094159",
                email="contact@djassapay.ci",
                store_name="Djassapay Officiel",
                store_slug="djassapay",
                bio="Plateforme e-commerce et encaissements sécurisés en Côte d'Ivoire.",
                logo_url="https://images.unsplash.com/photo-1556742049-0a67c5574f73?auto=format&fit=crop&w=200&q=80",
                wave_number="0595094159",
                orange_money_number="0595094159",
                mtn_momo_number="0595094159",
                moov_money_number="0100000000",
                pin_code="7788",
                deposit_policy="DELIVERY_FEE_ONLY",
                fixed_deposit_amount=2000
            )
            db.add(founder_merchant)
            db.commit()
            db.refresh(founder_merchant)

            # Zones de livraison complètes en Côte d'Ivoire (33 Communes & Villes)
            zones = [
                DeliveryZone(merchant_id=founder_merchant.id, name=z[0], fee=z[1], estimated_time=z[2])
                for z in ALL_CI_ZONES
            ]
            db.add_all(zones)
            db.commit()
        else:
            # S'assurer que le compte officiel a les coordonnées parfaites
            founder_merchant.phone = "0595094159"
            founder_merchant.wave_number = "0595094159"
            founder_merchant.pin_code = "7788"
            founder_merchant.store_name = "Djassapay Officiel"
            founder_merchant.store_slug = "djassapay"
            db.commit()
    finally:
        db.close()

# ==============================================================
# SEO & INDEXATION GOOGLE (ROBOTS.TXT & SITEMAP.XML)
# ==============================================================
from fastapi.responses import PlainTextResponse, Response

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    """Autorise Googlebot et les moteurs à indexer tout le site public."""
    return """User-agent: *
Allow: /
Allow: /register
Allow: /login
Allow: /pricing
Allow: /shop/
Disallow: /admin/
Disallow: /merchant/

Sitemap: https://djassapay.onrender.com/sitemap.xml
"""

@app.get("/sitemap.xml")
def sitemap_xml():
    """Génère la sitemap officielle XML pour Google Search Console."""
    db = SessionLocal()
    try:
        merchants = db.query(Merchant).all()
        urls = [
            ("https://djassapay.onrender.com/", "daily", "1.0"),
            ("https://djassapay.onrender.com/pricing", "weekly", "0.8"),
            ("https://djassapay.onrender.com/register", "monthly", "0.9"),
            ("https://djassapay.onrender.com/login", "monthly", "0.5"),
        ]
        for m in merchants:
            urls.append((f"https://djassapay.onrender.com/shop/{m.store_slug}", "daily", "0.8"))

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for loc, changefreq, priority in urls:
            xml += f"  <url>\n    <loc>{loc}</loc>\n    <changefreq>{changefreq}</changefreq>\n    <priority>{priority}</priority>\n  </url>\n"
        xml += "</urlset>"
        return Response(content=xml, media_type="application/xml")
    finally:
        db.close()
