from fastapi import APIRouter, Depends, HTTPException, Request, Form
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
    """Charge le marchand connecté via cookie de session ou le premier par défaut."""
    if request:
        merchant_id = request.cookies.get("merchant_id")
        if merchant_id:
            try:
                m = db.query(Merchant).filter(Merchant.id == int(merchant_id)).first()
                if m:
                    return m
            except Exception:
                pass

    merchant = db.query(Merchant).first()
    if not merchant:
        merchant = Merchant(
            name="Aïcha Traoré",
            phone="0708091011",
            email="aicha@glam-abidjan.ci",
            store_name="Glamour Abidjan",
            store_slug="glamour-abidjan",
            city="Abidjan",
            pin_code="1234",
            bio="Mode chic, robes tendances & accessoires haute qualité livrés partout à Abidjan & banlieues.",
            logo_url="https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=200&q=80",
            wave_number="0708091011",
            orange_money_number="0708091011",
            mtn_momo_number="0505060708",
            deposit_policy="DELIVERY_FEE_ONLY",
            fixed_deposit_amount=2000,
            subscription_plan="STARTER"
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

        # Ajouter quelques zones par défaut à Abidjan
        zones = [
            DeliveryZone(merchant_id=merchant.id, name="Cocody (Angré, Riviera, 2 Plateaux)", fee=1500, estimated_time="1h - 3h"),
            DeliveryZone(merchant_id=merchant.id, name="Yopougon (Maroc, Selmer, Bel Air)", fee=2000, estimated_time="2h - 4h"),
            DeliveryZone(merchant_id=merchant.id, name="Marcory & Zone 4 / Bietry", fee=1500, estimated_time="1h - 3h"),
            DeliveryZone(merchant_id=merchant.id, name="Koumassi & Treichville", fee=1500, estimated_time="2h - 3h"),
            DeliveryZone(merchant_id=merchant.id, name="Plateau & Adjamé", fee=1500, estimated_time="1h - 2h"),
            DeliveryZone(merchant_id=merchant.id, name="Bingerville & Bassam", fee=2500, estimated_time="3h - 5h"),
        ]
        db.add_all(zones)

        # Ajouter quelques produits d'exemple
        prods = [
            Product(
                merchant_id=merchant.id,
                title="Robe Soirée Satin Émeraude",
                description="Robe longue glamour en satin soyeux de qualité supérieure, idéale pour cérémonies et sorties chic.",
                price=18500,
                compare_at_price=25000,
                image_url="https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=600&q=80",
                stock=15
            ),
            Product(
                merchant_id=merchant.id,
                title="Sac à Main Cuir Luxia Gold",
                description="Sac cabas élégant avec finitions dorées dorées premium. Résistant et raffiné.",
                price=14000,
                compare_at_price=18000,
                image_url="https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&w=600&q=80",
                stock=8
            ),
            Product(
                merchant_id=merchant.id,
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
    return merchant

@router.get("/merchant/dashboard", response_class=HTMLResponse)
async def merchant_dashboard(request: Request, db: Session = Depends(get_db)):
    """Tableau de bord marchand : commandes, stats de cash & prévention des lapins."""
    merchant = get_current_merchant(db, request)

    orders = db.query(Order).filter(Order.merchant_id == merchant.id).order_by(Order.created_at.desc()).all()

    # Calcul des statistiques
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
    order_number: str,
    delivery_status: str = Form(...),
    delivery_rider_phone: str = Form(""),
    db: Session = Depends(get_db)
):
    """Mise à jour du statut d'expédition."""
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    order.delivery_status = delivery_status
    if delivery_rider_phone:
        order.delivery_rider_phone = delivery_rider_phone
    db.commit()

    return RedirectResponse(url="/merchant/dashboard", status_code=303)

@router.get("/merchant/products", response_class=HTMLResponse)
async def merchant_products(request: Request, db: Session = Depends(get_db)):
    """Gestion du catalogue produits."""
    merchant = get_current_merchant(db, request)
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
    stock: int = Form(10),
    db: Session = Depends(get_db)
):
    """Ajout d'un nouveau produit au catalogue."""
    merchant = get_current_merchant(db, request)
    product = Product(
        merchant_id=merchant.id,
        title=title,
        description=description,
        price=price,
        compare_at_price=compare_at_price if compare_at_price else None,
        image_url=image_url or "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80",
        stock=stock
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url="/merchant/products", status_code=303)

@router.post("/merchant/products/{product_id}/delete")
async def delete_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Suppression d'un produit."""
    merchant = get_current_merchant(db, request)
    product = db.query(Product).filter(Product.id == product_id, Product.merchant_id == merchant.id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/merchant/products", status_code=303)

@router.get("/merchant/settings", response_class=HTMLResponse)
async def merchant_settings(request: Request, db: Session = Depends(get_db)):
    """Paramètres boutique, Wave, Mobile Money et politique Anti-Lapin."""
    merchant = get_current_merchant(db, request)
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
    """Mise à jour des coordonnées et de la politique d'acompte."""
    merchant = get_current_merchant(db, request)
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
    name: str = Form(...),
    fee: int = Form(...),
    estimated_time: str = Form("1h - 3h"),
    db: Session = Depends(get_db)
):
    """Ajouter une nouvelle zone de livraison."""
    merchant = get_current_merchant(db)
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
async def delete_delivery_zone(zone_id: int, db: Session = Depends(get_db)):
    """Supprimer une zone de livraison."""
    merchant = get_current_merchant(db)
    zone = db.query(DeliveryZone).filter(DeliveryZone.id == zone_id, DeliveryZone.merchant_id == merchant.id).first()
    if zone:
        db.delete(zone)
        db.commit()
    return RedirectResponse(url="/merchant/settings", status_code=303)

@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, db: Session = Depends(get_db)):
    """Page publique des forfaits et tarifs d'abonnement SaaS."""
    merchant = get_current_merchant(db, request)
    return templates.TemplateResponse("merchant/pricing.html", {
        "request": request,
        "merchant": merchant
    })

@router.get("/merchant/subscription", response_class=HTMLResponse)
async def merchant_subscription(request: Request, db: Session = Depends(get_db)):
    """Gestion de l'abonnement du marchand (Passer au Plan Pro)."""
    merchant = get_current_merchant(db, request)
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
    amount = 9900 if plan == "PRO" else 19900
    
    # Redirection vers la page de paiement d'abonnement
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
    merchant.subscription_plan = plan.upper()
    merchant.subscription_status = "ACTIVE"
    merchant.subscription_paid_amount += amount
    db.commit()

    return RedirectResponse(url="/merchant/subscription?upgraded=1", status_code=303)
