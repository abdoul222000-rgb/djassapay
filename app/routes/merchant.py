import os
import io
import base64
import uuid
from PIL import Image, ImageOps
from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.config import settings
from app.models import Merchant, Product, DeliveryZone, Order, PaymentStatusEnum, DeliveryStatusEnum
from app.services.whatsapp_service import generate_rider_dispatch_whatsapp
from app.services.payment_service import PaymentService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

async def process_uploaded_media(media_file: UploadFile) -> str:
    """
    Traite le média uploadé par le commerçant :
    - Pour les photos : rotation EXIF automatique smartphone, redimensionnement max 900x900
      et compression JPEG haute fidélité stockée directement en Base64 Data URI dans PostgreSQL.
      Garantit que la photo NE SERA JAMAIS PERDUE lors des redémarrages de Render !
    - Pour les vidéos légères (< 3.5 Mo) : encodage Base64 direct.
    """
    if not media_file or not hasattr(media_file, "filename") or not media_file.filename:
        return ""

    contents = b""
    try:
        if hasattr(media_file, "file") and hasattr(media_file.file, "read"):
            if hasattr(media_file.file, "seek"):
                media_file.file.seek(0)
            contents = media_file.file.read()
        if not contents and hasattr(media_file, "read"):
            contents = await media_file.read()
    except Exception as e:
        print(f"[Upload Read Error] {e}")

    if not contents or len(contents) == 0:
        return ""

    ext = os.path.splitext(media_file.filename)[1].lower()
    is_video_ext = ext in [".mp4", ".mov", ".webm", ".m4v"]

    # 1. Traitement des images
    if not is_video_ext:
        try:
            img = Image.open(io.BytesIO(contents))
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((900, 900), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64}"
        except Exception as e:
            print(f"[Pillow Processing Error] {e}")

    # 2. Vidéo légère (< 3.5 Mo)
    if is_video_ext and len(contents) < 3.5 * 1024 * 1024:
        mime = "video/mp4" if ext in [".mp4", ".mov", ".m4v"] else "video/webm"
        b64 = base64.b64encode(contents).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    # 3. Fallback stockage fichier
    try:
        os.makedirs("app/static/uploads", exist_ok=True)
        unique_name = f"media_{uuid.uuid4().hex[:12]}{ext}"
        filepath = os.path.join("app/static/uploads", unique_name)
        with open(filepath, "wb") as f:
            f.write(contents)
        return f"/static/uploads/{unique_name}"
    except Exception as e:
        print(f"[Disk Fallback Error] {e}")
        return ""

def get_current_merchant(db: Session, request: Request = None):
    """
    Charge exclusivement le marchand connecté via cookie de session.
    Retourne None si l'utilisateur n'est pas authentifié.
    """
    if request:
        merchant_id = request.cookies.get("merchant_id")
        if merchant_id:
            try:
                m = db.query(Merchant).filter(Merchant.id == int(merchant_id)).first()
                if m:
                    return m
            except Exception:
                pass
    return None

@router.get("/merchant/dashboard", response_class=HTMLResponse)
async def merchant_dashboard(request: Request, db: Session = Depends(get_db)):
    """Tableau de bord marchand : Accessible UNIQUEMENT par le marchand connecté."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    orders = db.query(Order).filter(Order.merchant_id == merchant.id).order_by(Order.created_at.desc()).all()

    # Calcul des statistiques exclusives à ce marchand
    total_revenue = sum(o.total_amount for o in orders if o.payment_status in [PaymentStatusEnum.DEPOSIT_PAID.value, PaymentStatusEnum.FULLY_PAID.value])
    total_deposits = sum(o.deposit_paid for o in orders)
    lapins_evites = len([o for o in orders if o.deposit_paid > 0])
    economie_livraisons = sum(o.delivery_fee for o in orders if o.deposit_paid > 0)

    # Préparation des liens WhatsApp livreur pour chaque commande
    orders_with_links = []
    for o in orders:
        rider_link = generate_rider_dispatch_whatsapp(o, merchant)
        orders_with_links.append({"order": o, "rider_link": rider_link})

    return templates.TemplateResponse("merchant/dashboard.html", {
        "request": request,
        "merchant": merchant,
        "orders_with_links": orders_with_links,
        "total_revenue": total_revenue,
        "total_deposits": total_deposits,
        "lapins_evites": lapins_evites,
        "economie_livraisons": economie_livraisons
    })

@router.post("/merchant/orders/{order_number}/status")
async def update_order_status(
    request: Request,
    order_number: str,
    delivery_status: str = Form(...),
    delivery_rider_phone: str = Form(""),
    db: Session = Depends(get_db)
):
    """Mise à jour du statut d'expédition (uniquement pour les commandes du marchand connecté)."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    order = db.query(Order).filter(
        Order.order_number == order_number,
        Order.merchant_id == merchant.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable ou non autorisée")

    order.delivery_status = delivery_status
    if delivery_rider_phone:
        order.delivery_rider_phone = delivery_rider_phone
    db.commit()

    return RedirectResponse(url="/merchant/dashboard", status_code=303)

@router.get("/merchant/products", response_class=HTMLResponse)
async def merchant_products(request: Request, db: Session = Depends(get_db)):
    """Gestion du catalogue produits du marchand connecté."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    products = db.query(Product).filter(Product.merchant_id == merchant.id).all()

    return templates.TemplateResponse("merchant/products.html", {
        "request": request,
        "merchant": merchant,
        "products": products
    })

@router.post("/merchant/products/add")
async def add_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    price: int = Form(...),
    compare_at_price: int = Form(None),
    image_url: str = Form(""),
    media_file: UploadFile = File(None),
    stock: int = Form(10),
    db: Session = Depends(get_db)
):
    """Ajout d'un nouveau produit au catalogue avec photo directe smartphone ou vidéo."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    final_media_url = image_url.strip() if image_url else ""

    # Traitement du fichier uploadé (Appareil photo smartphone, galerie ou vidéo)
    # Convertit automatiquement les photos en Base64 JPEG optimisé (survit à TOUS les redémarrages de Render !)
    if media_file and hasattr(media_file, "filename") and media_file.filename:
        uploaded_media = await process_uploaded_media(media_file)
        if uploaded_media:
            final_media_url = uploaded_media

    if not final_media_url:
        final_media_url = "/static/images/product_placeholder.svg"

    product = Product(
        merchant_id=merchant.id,
        title=title,
        description=description,
        price=price,
        compare_at_price=compare_at_price if compare_at_price else None,
        image_url=final_media_url,
        stock=stock,
        is_active=True
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url="/merchant/products", status_code=303)

@router.post("/merchant/products/{product_id}/edit")
async def edit_product(
    request: Request,
    product_id: int,
    title: str = Form(...),
    description: str = Form(""),
    price: int = Form(...),
    compare_at_price: int = Form(None),
    stock: int = Form(10),
    is_active: bool = Form(True),
    media_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    Modification d'un produit : STRICTEMENT réservé au marchand propriétaire.
    Chaque marchand ne peut modifier QUE ses propres articles.
    """
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.merchant_id == merchant.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Article introuvable ou vous n'êtes pas autorisé à modifier ce produit")

    # Mise à jour des informations
    product.title = title.strip()
    product.description = description.strip()
    product.price = price
    product.compare_at_price = compare_at_price if compare_at_price else None
    product.stock = stock
    product.is_active = is_active

    # Nouveau fichier média si fourni (Pillow Base64 permanent)
    if media_file and hasattr(media_file, "filename") and media_file.filename:
        uploaded_media = await process_uploaded_media(media_file)
        if uploaded_media:
            product.image_url = uploaded_media

    db.commit()
    return RedirectResponse(url="/merchant/products?saved=1", status_code=303)

@router.post("/merchant/products/{product_id}/toggle")
async def toggle_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Active ou désactive la visibilité d'un produit (réservé au propriétaire)."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.merchant_id == merchant.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Article introuvable")

    product.is_active = not product.is_active
    db.commit()
    return RedirectResponse(url="/merchant/products", status_code=303)

@router.post("/merchant/products/{product_id}/delete")
async def delete_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Suppression d'un produit (sécurisé, réservé au propriétaire du produit)."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    product = db.query(Product).filter(Product.id == product_id, Product.merchant_id == merchant.id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/merchant/products", status_code=303)

@router.get("/merchant/settings", response_class=HTMLResponse)
async def merchant_settings(request: Request, db: Session = Depends(get_db)):
    """Paramètres boutique, Wave, Mobile Money et politique Anti-Lapin."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    zones = db.query(DeliveryZone).filter(DeliveryZone.merchant_id == merchant.id).all()
    clean_logo = merchant.logo_url if (merchant.logo_url and "unsplash" not in merchant.logo_url and "photo-" not in merchant.logo_url) else ""

    return templates.TemplateResponse("merchant/settings.html", {
        "request": request,
        "merchant": merchant,
        "clean_logo": clean_logo,
        "zones": zones
    })

@router.post("/merchant/settings/update")
async def update_settings(
    request: Request,
    store_name: str = Form(...),
    phone: str = Form(...),
    bio: str = Form(""),
    wave_number: str = Form(""),
    orange_money_number: str = Form(""),
    mtn_momo_number: str = Form(""),
    moov_money_number: str = Form(""),
    deposit_policy: str = Form(...),
    fixed_deposit_amount: int = Form(2000),
    logo_file: UploadFile = File(None),
    remove_logo: str = Form(""),
    db: Session = Depends(get_db)
):
    """Mise à jour des coordonnées, de la photo/logo et de la politique d'acompte du marchand."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    merchant.store_name = store_name.strip()
    merchant.phone = phone.strip()
    merchant.bio = bio.strip()
    merchant.wave_number = wave_number.strip()
    merchant.orange_money_number = orange_money_number.strip()
    merchant.mtn_momo_number = mtn_momo_number.strip()
    merchant.moov_money_number = moov_money_number.strip()
    merchant.deposit_policy = deposit_policy
    merchant.fixed_deposit_amount = fixed_deposit_amount

    # Traitement de la photo de profil / logo de la boutique
    if remove_logo == "1":
        merchant.logo_url = None
    elif logo_file and hasattr(logo_file, "filename") and logo_file.filename:
        uploaded_logo = await process_uploaded_media(logo_file)
        if uploaded_logo:
            merchant.logo_url = uploaded_logo

    db.commit()

    return RedirectResponse(url="/merchant/settings?saved=1", status_code=303)

@router.post("/merchant/zones/add")
async def add_delivery_zone(
    request: Request,
    name: str = Form(...),
    fee: int = Form(...),
    estimated_time: str = Form("1h - 3h"),
    db: Session = Depends(get_db)
):
    """Ajouter une nouvelle zone de livraison pour le marchand connecté."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    zone = DeliveryZone(
        merchant_id=merchant.id,
        name=name,
        fee=fee,
        estimated_time=estimated_time
    )
    db.add(zone)
    db.commit()
    return RedirectResponse(url="/merchant/settings", status_code=303)

@router.post("/merchant/zones/{zone_id}/delete")
async def delete_delivery_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Supprimer une zone de livraison."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    zone = db.query(DeliveryZone).filter(DeliveryZone.id == zone_id, DeliveryZone.merchant_id == merchant.id).first()
    if zone:
        db.delete(zone)
        db.commit()
    return RedirectResponse(url="/merchant/settings", status_code=303)

@router.post("/merchant/zones/{zone_id}/edit")
async def edit_delivery_zone(
    request: Request,
    zone_id: int,
    name: str = Form(...),
    fee: int = Form(...),
    estimated_time: str = Form("1h - 3h"),
    db: Session = Depends(get_db)
):
    """Modifier le nom ou le tarif d'une zone de livraison du vendeur."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    zone = db.query(DeliveryZone).filter(DeliveryZone.id == zone_id, DeliveryZone.merchant_id == merchant.id).first()
    if zone:
        zone.name = name.strip()
        zone.fee = fee
        zone.estimated_time = estimated_time.strip()
        db.commit()
    return RedirectResponse(url="/merchant/settings?saved=1", status_code=303)

@router.post("/merchant/zones/clear-all")
async def clear_all_delivery_zones(request: Request, db: Session = Depends(get_db)):
    """Supprimer toutes les zones de livraison en 1 clic pour repartir de zéro."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    db.query(DeliveryZone).filter(DeliveryZone.merchant_id == merchant.id).delete()
    db.commit()
    return RedirectResponse(url="/merchant/settings?saved=1", status_code=303)

@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, db: Session = Depends(get_db)):
    """Page des forfaits et tarifs d'abonnement SaaS."""
    merchant = get_current_merchant(db, request)
    return templates.TemplateResponse("merchant/pricing.html", {
        "request": request,
        "merchant": merchant
    })

@router.get("/merchant/subscription", response_class=HTMLResponse)
async def merchant_subscription(request: Request, db: Session = Depends(get_db)):
    """Gestion de l'abonnement du marchand (Passer au Plan Pro)."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    return templates.TemplateResponse("merchant/subscription.html", {
        "request": request,
        "merchant": merchant
    })

@router.post("/merchant/subscription/upgrade")
async def upgrade_subscription(
    request: Request,
    plan: str = Form("PRO"),
    payment_method: str = Form("WAVE"),
    db: Session = Depends(get_db)
):
    """Initialise le paiement d'un abonnement SaaS vers le compte du fondateur."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    amount = 9900 if plan == "PRO" else 19900
    
    # Intégration 100% Autonome : si la clé API Wave est présente, redirection Wave Checkout officielle !
    if payment_method == "WAVE" and settings.WAVE_API_KEY:
        wave_session = PaymentService.initiate_subscription_wave_payment(merchant, plan=plan, amount=amount)
        if wave_session.get("payment_url"):
            return RedirectResponse(url=wave_session["payment_url"], status_code=303)

    return templates.TemplateResponse("payments/subscription_pay.html", {
        "request": request,
        "merchant": merchant,
        "plan": plan,
        "amount": amount,
        "method": payment_method,
        "settings": settings
    })

@router.post("/merchant/subscription/confirm")
async def confirm_subscription(
    request: Request,
    plan: str = Form("PRO"),
    amount: int = Form(9900),
    transaction_ref: str = Form(""),
    db: Session = Depends(get_db)
):
    """
    Enregistre la demande d'activation d'abonnement.
    Le statut reste 'PENDING_VERIFICATION' jusqu'à validation par le Fondateur 
    après vérification effective des 9 900 FCFA sur son compte Wave Business !
    """
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    # Protection anti-fraude : ne PAS donner le mode PRO tant que le Fondateur n'a pas confirmé l'argent sur son Wave
    merchant.subscription_status = "PENDING_VERIFICATION"
    db.commit()

    return RedirectResponse(url="/merchant/subscription?pending=1", status_code=303)
