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
    """Vérifie et initialise les données de démonstration au premier lancement."""
    db = SessionLocal()
    try:
        merchant = db.query(Merchant).first()
        if not merchant:
            demo_merchant = Merchant(
                name="Aïcha Traoré",
                phone="0708091011",
                email="aicha@glam-abidjan.ci",
                store_name="Glamour Abidjan",
                store_slug="glamour-abidjan",
                bio="Mode chic, robes tendances & accessoires haute qualité livrés partout à Abidjan & banlieues.",
                logo_url="https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=200&q=80",
                wave_number="0708091011",
                orange_money_number="0708091011",
                mtn_momo_number="0505060708",
                deposit_policy="DELIVERY_FEE_ONLY",
                fixed_deposit_amount=2000
            )
            db.add(demo_merchant)
            db.commit()
            db.refresh(demo_merchant)

            # Zones de livraison complètes en Côte d'Ivoire (Abidjan & Intérieur)
            from app.routes.auth import ALL_CI_ZONES
            zones = [
                DeliveryZone(merchant_id=demo_merchant.id, name=z[0], fee=z[1], estimated_time=z[2])
                for z in ALL_CI_ZONES
            ]
            db.add_all(zones)

            # Produits démo
            prods = [
                Product(
                    merchant_id=demo_merchant.id,
                    title="Robe Soirée Satin Émeraude",
                    description="Robe longue glamour en satin soyeux de qualité supérieure, idéale pour cérémonies et sorties chic.",
                    price=18500,
                    compare_at_price=25000,
                    image_url="https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=600&q=80",
                    stock=15
                ),
                Product(
                    merchant_id=demo_merchant.id,
                    title="Sac à Main Cuir Luxia Gold",
                    description="Sac cabas élégant avec finitions dorées premium. Résistant et raffiné.",
                    price=14000,
                    compare_at_price=18000,
                    image_url="https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&w=600&q=80",
                    stock=8
                ),
                Product(
                    merchant_id=demo_merchant.id,
                    title="Ensemble Tailleur Lin Ivoire",
                    description="Deux pièces veste et pantalon fluide en lin naturel respirant. Coupe moderne et décontractée.",
                    price=22000,
                    compare_at_price=28000,
                    image_url="https://images.unsplash.com/photo-1539109136881-3be0616acf4b?auto=format&fit=crop&w=600&q=80",
                    stock=12
                )
            ]
            db.add_all(prods)
            db.commit()
    finally:
        db.close()
