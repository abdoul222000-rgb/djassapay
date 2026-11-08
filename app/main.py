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
                email="djassapay9@gmail.com",
                store_name="Djassapay Officiel",
                store_slug="djassapay",
                bio="Plateforme e-commerce et encaissements sécurisés en Côte d'Ivoire.",
                logo_url="/static/images/djassapay_icon.svg",
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
        else:
            # S'assurer que le compte officiel a les coordonnées parfaites
            founder_merchant.phone = "0595094159"
            founder_merchant.email = "djassapay9@gmail.com"
            founder_merchant.wave_number = "0595094159"
            founder_merchant.pin_code = "7788"
            founder_merchant.store_name = "Djassapay Officiel"
            founder_merchant.store_slug = "djassapay"
            founder_merchant.logo_url = "/static/images/djassapay_icon.svg"
            db.commit()

        # S'assurer que Pav-225 shop est bien en mode gratuit STARTER (annulation test)
        for p_m in db.query(Merchant).all():
            if "pav" in (p_m.store_name or "").lower() or "pav" in (p_m.store_slug or "").lower():
                p_m.subscription_plan = "STARTER"
                p_m.subscription_status = "FREE"
                p_m.subscription_paid_amount = 0
        db.commit()

        # 1. Migration automatique schéma PostgreSQL : s'assurer que image_url et logo_url sont TEXT (support Base64 illimité)
        try:
            from sqlalchemy import text
            db.execute(text("ALTER TABLE products ALTER COLUMN image_url TYPE TEXT;"))
            db.execute(text("ALTER TABLE merchants ALTER COLUMN logo_url TYPE TEXT;"))
            db.commit()
            print("[Database Migration] products.image_url et merchants.logo_url vérifiés/convertis en TEXT.")
        except Exception as e:
            db.rollback()

        # 2. Suppression des zones et tarifs pré-remplis pour redonner la liberté totale aux vendeurs
        try:
            from app.routes.auth import ALL_CI_ZONES
            default_zone_names = {z[0] for z in ALL_CI_ZONES}
            for z in db.query(DeliveryZone).all():
                if z.name in default_zone_names:
                    db.delete(z)
            db.commit()
            print("[Database Migration] Zones pré-remplies supprimées avec succès pour redonner le plein contrôle aux vendeurs.")
        except Exception as e:
            db.rollback()

        # Nettoyage des anciennes photos IA de profil de vendeur
        for m in db.query(Merchant).all():
            if m.logo_url and ("photo-1544005313" in m.logo_url or "unsplash" in m.logo_url):
                m.logo_url = None
        db.commit()

        # 2. Restauration & Protection permanente des photos de tous les vendeurs
        import base64

        # Vraie photo authentique de Pav-225 (fournie directement par le vendeur)
        pav_real_path = "app/static/images/pav_real_complet.jpg"
        pav_suit_img = "/static/images/pav_real_complet.jpg"
        if os.path.exists(pav_real_path):
            with open(pav_real_path, "rb") as f:
                pav_suit_img = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"

        # Photo élégante ivoirienne pour Princesse Roxane
        roxane_path = "app/static/images/roxane_haut_sauter.jpg"
        roxane_top_img = "/static/images/roxane_haut_sauter.jpg"
        if os.path.exists(roxane_path):
            with open(roxane_path, "rb") as f:
                roxane_top_img = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"

        all_products = db.query(Product).all()
        for prod in all_products:
            m_name = (prod.merchant.store_name if prod.merchant else "").lower()
            m_slug = (prod.merchant.store_slug if prod.merchant else "").lower()
            title_lower = (prod.title or "").lower()
            img_url = prod.image_url or ""

            is_pav_store = ("pav" in m_name or "pav" in m_slug)
            is_roxane_store = ("roxane" in m_name or "roxane" in m_slug)

            # 1. Pav-225 shop UNIQUEMENT : sa VRAIE photo officielle certifiée (Complet 26 500 FCFA)
            if is_pav_store and (prod.price == 26500 or "complet" in title_lower):
                prod.image_url = pav_suit_img
                print(f"[Photo Restore] Pav-225 Complet restauré exclusivement pour Pav-225: {prod.title}")

            # 2. Princesse Roxane Shop UNIQUEMENT : sa photo officielle certifiée (Haut sauter)
            elif is_roxane_store and ("sauter" in title_lower or "haut" in title_lower or prod.price == 1000):
                if not img_url or not img_url.startswith("data:image/") or "photo-1523275335684" in img_url or "photo-1503342217505" in img_url or "unsplash" in img_url or prod.is_video:
                    prod.image_url = roxane_top_img
                    print(f"[Photo Restore] Princesse Roxane Haut sauter restauré : {prod.title}")

            # 3. NETTOYAGE STRICT : Si un autre vendeur a reçu par erreur la photo de Pav-225, la SUPPRIMER IMMÉDIATEMENT !
            elif not is_pav_store and (img_url == pav_suit_img or "/static/images/pav_real_complet.jpg" in img_url or (len(pav_suit_img) > 100 and pav_suit_img[:100] in img_url)):
                prod.image_url = "/static/images/product_placeholder.svg"
                print(f"[Photo Restore] Photo de Pav SUPPRIMÉE du produit '{prod.title}' (Vendeur: {prod.merchant.store_name if prod.merchant else 'Inconnu'})")

            # 4. Protection absolue des autres vendeurs : AUCUN écrasement de photo existante
            elif img_url.startswith("/static/uploads/"):
                local_fpath = os.path.join("app", img_url.lstrip("/"))
                if not os.path.exists(local_fpath):
                    prod.image_url = "/static/images/product_placeholder.svg"
                    print(f"[Photo Restore] Image réparée pour produit '{prod.title}' -> placeholder SVG")

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
Allow: /marketplace
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
            ("https://djassapay.onrender.com/marketplace", "daily", "0.9"),
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

# ==============================================================
# TÉLÉCHARGEMENT DIRECT DANS LA GALERIE (SMARTPHONE & PC)
# ==============================================================
@app.get("/telecharger/affiche-complete")
def download_affiche_complete():
    """Téléchargement direct forcé de l'affiche officielle complète avec marque et QR code."""
    fpath = "app/static/images/affiche_fondateur_campagne_officielle_hd.jpg"
    if os.path.exists(fpath):
        return FileResponse(fpath, media_type="image/jpeg", filename="affiche_fondateur_djassapay_complete.jpg")
    return Response(content="Affiche non trouvée", status_code=404)

@app.get("/telecharger/affiche-photo")
def download_affiche_photo():
    """Téléchargement direct forcé de la photo publicitaire épurée du fondateur."""
    fpath = "app/static/images/affiche_fondateur_pose_hd.jpg"
    if os.path.exists(fpath):
        return FileResponse(fpath, media_type="image/jpeg", filename="photo_fondateur_djassapay_pure.jpg")
    return Response(content="Photo non trouvée", status_code=404)

@app.get("/telecharger", response_class=HTMLResponse)
@app.get("/galerie", response_class=HTMLResponse)
def page_telechargement_galerie(request: Request):
    """Page dédiée optimisée smartphone pour enregistrer les 2 affiches directement dans la galerie Photos."""
    return templates.TemplateResponse("telecharger.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })
