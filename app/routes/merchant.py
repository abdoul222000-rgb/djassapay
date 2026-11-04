import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid

from app.database import get_db
from app.config import settings
from app.models import Merchant, Product, DeliveryZone, Order, PaymentStatusEnum, DeliveryStatusEnum
from app.services.whatsapp_service import generate_rider_dispatch_whatsapp

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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
    if media_file and media_file.filename:
        try:
            os.makedirs("app/static/uploads", exist_ok=True)
            ext = os.path.splitext(media_file.filename)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm", ".m4v"]:
                ext = ".jpg"
            unique_name = f"media_{uuid.uuid4().hex[:12]}{ext}"
            filepath = os.path.join("app/static/uploads", unique_name)

            contents = await media_file.read()
            if len(contents) > 0:
                with open(filepath, "wb") as f:
                    f.write(contents)
                final_media_url = f"/static/uploads/{unique_name}"
        except Exception as e:
            print(f"[Upload Error] Échec de sauvegarde du média : {e}")

    if not final_media_url:
        final_media_url = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80"

    product = Product(
        merchant_id=merchant.id,
        title=title,
        description=description,
        price=price,
        compare_at_price=compare_at_price if compare_at_price else None,
        image_url=final_media_url,
        stock=stock
    )
    db.add(product)
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

    return templates.TemplateResponse("merchant/settings.html", {
        "request": request,
        "merchant": merchant,
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
    deposit_policy: str = Form(...),
    fixed_deposit_amount: int = Form(2000),
    db: Session = Depends(get_db)
):
    """Mise à jour des coordonnées et de la politique d'acompte du marchand."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    merchant.store_name = store_name
    merchant.phone = phone
    merchant.bio = bio
    merchant.wave_number = wave_number
    merchant.orange_money_number = orange_money_number
    merchant.mtn_momo_number = mtn_momo_number
    merchant.deposit_policy = deposit_policy
    merchant.fixed_deposit_amount = fixed_deposit_amount
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
    db: Session = Depends(get_db)
):
    """Valide l'activation du forfait Pro / Business pour le marchand."""
    merchant = get_current_merchant(db, request)
    if not merchant:
        return RedirectResponse(url="/login?unauthorized=1", status_code=303)

    merchant.subscription_plan = plan.upper()
    merchant.subscription_status = "ACTIVE"
    merchant.subscription_paid_amount += amount
    db.commit()

    return RedirectResponse(url="/merchant/subscription?upgraded=1", status_code=303)
