from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import uuid

from app.database import get_db
from app.models import Merchant, Product, DeliveryZone, Order, OrderItem, PaymentStatusEnum
from app.services.payment_service import PaymentService
from app.services.whatsapp_service import generate_customer_order_whatsapp, auto_notify_order_created

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request, db: Session = Depends(get_db)):
    """Page d'accueil de la plateforme DjassaPay avec vitrine Marketplace."""
    merchants = db.query(Merchant).all()
    marketplace_products = db.query(Product).join(Merchant).filter(
        Product.is_active != False,
        (Product.stock == None) | (Product.stock >= 0)
    ).order_by(Product.created_at.desc()).limit(8).all()
    total_products_count = db.query(Product).filter(
        Product.is_active != False,
        (Product.stock == None) | (Product.stock >= 0)
    ).count()

    return templates.TemplateResponse("landing.html", {
        "request": request,
        "merchants": merchants,
        "marketplace_products": marketplace_products,
        "total_products_count": total_products_count
    })

@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace_view(
    request: Request,
    q: str = "",
    city: str = "all",
    sort: str = "recent",
    db: Session = Depends(get_db)
):
    """
    Marketplace publique permettant à tout visiteur de découvrir et d'acheter 
    directement les articles ajoutés par les vendeurs vérifiés de Côte d'Ivoire.
    """
    query = db.query(Product).join(Merchant).filter(
        Product.is_active != False,
        (Product.stock == None) | (Product.stock >= 0)
    )

    clean_q = q.strip()
    if clean_q:
        search_pattern = f"%{clean_q}%"
        query = query.filter(
            (Product.title.ilike(search_pattern)) |
            (Product.description.ilike(search_pattern)) |
            (Merchant.store_name.ilike(search_pattern))
        )

    clean_city = city.strip()
    if clean_city and clean_city.lower() != "all":
        query = query.filter(Merchant.city.ilike(f"%{clean_city}%"))

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.all()

    # Liste des villes représentées
    active_cities_raw = db.query(Merchant.city).filter(Merchant.city != None).distinct().all()
    available_cities = sorted(list(set(c[0] for c in active_cities_raw if c[0])))

    return templates.TemplateResponse("store/marketplace.html", {
        "request": request,
        "products": products,
        "total_count": len(products),
        "q": clean_q,
        "selected_city": clean_city,
        "sort": sort,
        "available_cities": available_cities
    })

@router.get("/shop/{store_slug}", response_class=HTMLResponse)
async def view_store(request: Request, store_slug: str, db: Session = Depends(get_db)):
    """Vitrine mobile publique d'une boutique (ex: /shop/glam-abidjan)."""
    merchant = db.query(Merchant).filter(Merchant.store_slug == store_slug).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Boutique introuvable")
    
    products = db.query(Product).filter(
        Product.merchant_id == merchant.id,
        Product.is_active != False
    ).order_by(Product.created_at.desc()).all()
    
    delivery_zones = db.query(DeliveryZone).filter(
        DeliveryZone.merchant_id == merchant.id
    ).all()

    return templates.TemplateResponse("store/index.html", {
        "request": request,
        "merchant": merchant,
        "products": products,
        "delivery_zones": delivery_zones
    })

@router.get("/shop/{store_slug}/product/{product_id}", response_class=HTMLResponse)
async def view_product(request: Request, store_slug: str, product_id: int, db: Session = Depends(get_db)):
    """Fiche produit détaillée avec bouton Achat Rapide."""
    merchant = db.query(Merchant).filter(Merchant.store_slug == store_slug).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Boutique introuvable")
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.merchant_id == merchant.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    delivery_zones = db.query(DeliveryZone).filter(
        DeliveryZone.merchant_id == merchant.id
    ).all()

    return templates.TemplateResponse("store/product.html", {
        "request": request,
        "merchant": merchant,
        "product": product,
        "delivery_zones": delivery_zones
    })

@router.post("/shop/{store_slug}/checkout")
async def process_checkout(
    store_slug: str,
    product_id: int = Form(...),
    quantity: int = Form(1),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    delivery_zone_id: int = Form(0),
    delivery_address: str = Form(...),
    customer_notes: str = Form(""),
    payment_method: str = Form("WAVE"),
    db: Session = Depends(get_db)
):
    """Traitement de la commande client avec calcul immédiat de l'acompte Anti-Lapin."""
    merchant = db.query(Merchant).filter(Merchant.store_slug == store_slug).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Boutique introuvable")

    product = db.query(Product).filter(Product.id == product_id, Product.merchant_id == merchant.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit indisponible")

    zone = db.query(DeliveryZone).filter(DeliveryZone.id == delivery_zone_id, DeliveryZone.merchant_id == merchant.id).first()
    delivery_fee = zone.fee if zone else 1500
    zone_name = zone.name if zone else "Livraison standard"

    subtotal = product.price * quantity
    total, deposit_required, balance_due = PaymentService.calculate_deposit_and_balance(
        merchant=merchant,
        subtotal=subtotal,
        delivery_fee=delivery_fee
    )

    # Création du numéro de commande unique (ex: DJA-7382)
    order_number = f"DJA-{uuid.uuid4().hex[:5].upper()}"

    clean_notes = customer_notes if isinstance(customer_notes, str) else ""
    clean_method = payment_method if isinstance(payment_method, str) else "WAVE"

    order = Order(
        order_number=order_number,
        merchant_id=merchant.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_zone_name=zone_name,
        delivery_address=delivery_address,
        customer_notes=clean_notes,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total_amount=total,
        deposit_required=deposit_required,
        deposit_paid=0,
        balance_due=balance_due,
        payment_method=clean_method,
        payment_status=PaymentStatusEnum.PENDING_DEPOSIT.value
    )
    db.add(order)
    db.flush()

    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_title=product.title,
        quantity=quantity,
        unit_price=product.price,
        total_price=subtotal
    )
    db.add(item)
    db.commit()

    # Déclencher la notification WhatsApp automatique
    try:
        await auto_notify_order_created(order, merchant)
    except Exception as e:
        print(f"[WhatsApp Trigger Error] {e}")

    # Redirection vers la page de paiement de l'acompte
    return RedirectResponse(url=f"/orders/{order.order_number}", status_code=303)
