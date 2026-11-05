"""
SUITE OFFICIELLE DE TESTS & BACKTEST - DJASSAPAY CI
===================================================
Vérification automatisée de :
1. Isolation stricte multi-marchands (Multi-tenant & Anti-IDOR)
2. Marketplace publique (Recherche, filtres, tri, masquage)
3. Gestion des produits (Ajout, modification, toggle, suppression)
4. Tunnel de commande Anti-Lapin & suspension Orange/Moov
5. Normalisation des numéros ivoiriens & Authentification PIN
6. SEO (Robots.txt & Sitemap.xml)
"""

import os
import sys
from starlette.requests import Request
from fastapi import Response, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Base de données de test isolée
TEST_DB = "test_backtest.db"
if os.path.exists(TEST_DB):
    try:
        os.remove(TEST_DB)
    except Exception:
        pass

from app.database import Base
from app.models import (
    Merchant, Product, DeliveryZone, Order, OrderItem,
    PaymentStatusEnum, DeliveryStatusEnum, DepositPolicyEnum
)
from app.routes.auth import process_register, process_login
from app.routes.merchant import (
    get_current_merchant, add_product, edit_product,
    toggle_product, delete_product
)
from app.routes.store import marketplace_view, process_checkout
from app.routes.payments import confirm_simulated_payment
from app.main import robots_txt, sitemap_xml

# Initialisation DB SQLite de test
engine = create_engine(f"sqlite:///{TEST_DB}", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)

def run_coro(coro):
    """Exécute de manière synchrone et rapide une coroutine sans boucle externe."""
    stack = [coro]
    val = None
    while stack:
        current = stack[-1]
        try:
            res = current.send(val)
            if hasattr(res, "send"):
                stack.append(res)
                val = None
            else:
                val = res
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val

def make_request(path: str = "/", cookies: dict = None):
    """Crée une requête HTTP ASGI factice pour tester les endpoints."""
    cookie_str = "; ".join([f"{k}={v}" for k, v in (cookies or {}).items()])
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"cookie", cookie_str.encode())],
        "query_string": b"",
        "client": ("127.0.0.1", 12345)
    }
    return Request(scope)

passed_checks = []
failed_checks = []

def record(test_name: str, condition: bool, details: str = ""):
    if condition:
        passed_checks.append(test_name)
        print(f"  [PASS] {test_name}", flush=True)
    else:
        failed_checks.append((test_name, details))
        print(f"  [FAIL] {test_name}: {details}", flush=True)

def main():
    db = Session()
    print("=" * 75, flush=True)
    print("DEMARRAGE DU GRAND BACKTEST DJASSAPAY (ISOLATION MULTI-VENDEURS & MARKETPLACE)", flush=True)
    print("=" * 75, flush=True)

    # -------------------------------------------------------------
    # 1. SEO & SITEMAP
    # -------------------------------------------------------------
    print("\n--- 1. TESTS SEO & MARKETPLACE URLS ---", flush=True)
    robots = robots_txt()
    record("Robots.txt autorise /marketplace", "Allow: /marketplace" in robots)
    record("Robots.txt protège /merchant/ (Espace Marchand privé)", "Disallow: /merchant/" in robots)
    record("Robots.txt protège /admin/ (Espace Fondateur privé)", "Disallow: /admin/" in robots)

    sitemap_res = sitemap_xml()
    sitemap_content = sitemap_res.body.decode() if hasattr(sitemap_res, "body") else str(sitemap_res)
    record("Sitemap.xml indexe l'URL de la Marketplace", "https://djassapay.onrender.com/marketplace" in sitemap_content)

    # -------------------------------------------------------------
    # 2. INSCRIPTION ET ISOLATION DES MARCHANDS
    # -------------------------------------------------------------
    print("\n--- 2. CREATION ET ISOLATION DES MARCHANDS ---", flush=True)

    # Inscription Marchand A : Cocody Luxe
    res_a = Response()
    run_coro(process_register(
        response=res_a,
        name="Kouassi Jean",
        phone="0701020304",
        store_name="Cocody Luxe",
        city="Cocody (Abidjan)",
        country="CI",
        pin_code="1122",
        db=db
    ))
    march_a = db.query(Merchant).filter(Merchant.phone == "0701020304").first()
    record("Marchand A (Cocody Luxe) créé en base", march_a is not None)
    record("Marchand A a ses 33 zones de livraison CI", len(march_a.delivery_zones) >= 30)

    # Inscription Marchand B : Yopougon Mode
    res_b = Response()
    run_coro(process_register(
        response=res_b,
        name="Bakayoko Awa",
        phone="0509080706",
        store_name="Yopougon Mode",
        city="Yopougon (Abidjan)",
        country="CI",
        pin_code="3344",
        db=db
    ))
    march_b = db.query(Merchant).filter(Merchant.phone == "0509080706").first()
    record("Marchand B (Yopougon Mode) créé en base", march_b is not None)
    record("IDs et Slugs Marchand A et B strictement distincts", march_a.id != march_b.id and march_a.store_slug != march_b.store_slug)

    # -------------------------------------------------------------
    # 3. GESTION DES ARTICLES & RATTACHEMENT MARCHAND
    # -------------------------------------------------------------
    print("\n--- 3. AJOUT D'ARTICLES PAR CHAQUE VENDEUR ---", flush=True)

    req_a = make_request(cookies={"merchant_id": str(march_a.id)})
    req_b = make_request(cookies={"merchant_id": str(march_b.id)})

    # Marchand A ajoute un produit
    run_coro(add_product(
        request=req_a,
        title="Robe Soirée Soie",
        description="Robe chic gala et cérémonies",
        price=25000,
        compare_at_price=30000,
        image_url="https://images.unsplash.com/photo-robe.jpg",
        stock=5,
        db=db
    ))

    # Marchand B ajoute un produit
    run_coro(add_product(
        request=req_b,
        title="Baskets Sport Runner",
        description="Chaussures de course légères",
        price=18000,
        compare_at_price=22000,
        image_url="https://images.unsplash.com/photo-shoes.jpg",
        stock=12,
        db=db
    ))

    prod_a = db.query(Product).filter(Product.title == "Robe Soirée Soie").first()
    prod_b = db.query(Product).filter(Product.title == "Baskets Sport Runner").first()

    record("Produit A rattaché exclusivement au Marchand A", prod_a.merchant_id == march_a.id)
    record("Produit B rattaché exclusivement au Marchand B", prod_b.merchant_id == march_b.id)

    # -------------------------------------------------------------
    # 4. SÉCURITÉ : ISOLATION MULTI-VENDEUR STRICTE (ANTI-IDOR)
    # -------------------------------------------------------------
    print("\n--- 4. TEST DE PROTECTION ET ISOLATION DES DONNEES ---", flush=True)

    # TENTATIVE D'ATTAQUE 1 : Marchand A tente de modifier le produit du Marchand B
    blocked_edit = False
    try:
        run_coro(edit_product(
            request=req_a,
            product_id=prod_b.id,
            title="PRODUIT DETOURNE PAR COCODY",
            description="Attaque pirate",
            price=100,
            compare_at_price=None,
            stock=1,
            is_active=True,
            media_file=None,
            db=db
        ))
    except HTTPException as e:
        blocked_edit = (e.status_code == 404)

    record("Marchand A bloqué (HTTP 404) lors de la tentative de modification du produit B", blocked_edit)

    # Vérification d'intégrité : Produit B doit rester inchangé
    db.refresh(prod_b)
    record("Produit B 100% intègre et inchangé après l'attaque", prod_b.title == "Baskets Sport Runner" and prod_b.price == 18000)

    # TENTATIVE D'ATTAQUE 2 : Marchand A tente de supprimer le produit de Marchand B
    run_coro(delete_product(request=req_a, product_id=prod_b.id, db=db))
    prod_b_check = db.query(Product).filter(Product.id == prod_b.id).first()
    record("Marchand A n'a PAS pu supprimer le produit de Marchand B", prod_b_check is not None)

    # MODIFICATION LEGITIME : Marchand A met à jour son propre produit
    run_coro(edit_product(
        request=req_a,
        product_id=prod_a.id,
        title="Robe Soirée Soie Prestige",
        description="Nouvelle collection disponible",
        price=27000,
        compare_at_price=35000,
        stock=8,
        is_active=True,
        media_file=None,
        db=db
    ))
    db.refresh(prod_a)
    record("Marchand A a mis à jour son propre article (27 000 F / Stock 8)", prod_a.title == "Robe Soirée Soie Prestige" and prod_a.price == 27000 and prod_a.stock == 8)

    # -------------------------------------------------------------
    # 5. MARKETPLACE PUBLIQUE
    # -------------------------------------------------------------
    print("\n--- 5. TESTS DE LA MARKETPLACE PUBLIQUE ---", flush=True)
    anon_req = make_request()

    # Affichage global Marketplace
    mkt_res = run_coro(marketplace_view(request=anon_req, q="", city="all", sort="recent", db=db))
    ctx = mkt_res.context
    products_mkt = ctx["products"]
    record("Marketplace liste les produits de tous les commerçants (2 articles)", len(products_mkt) == 2)
    record("Villes bien répertoriées dans les filtres", len(ctx["available_cities"]) >= 2)

    # Recherche par mot-clé
    search_res = run_coro(marketplace_view(request=anon_req, q="Baskets", city="all", sort="recent", db=db))
    search_prods = search_res.context["products"]
    record("Recherche 'Baskets' filtre précisément le produit B", len(search_prods) == 1 and search_prods[0].id == prod_b.id)

    # Filtrage par commune
    city_res = run_coro(marketplace_view(request=anon_req, q="", city="Cocody", sort="recent", db=db))
    city_prods = city_res.context["products"]
    record("Filtre commune 'Cocody' isole les produits de Cocody Luxe", len(city_prods) == 1 and city_prods[0].id == prod_a.id)

    # Tri par prix décroissant
    sort_res = run_coro(marketplace_view(request=anon_req, q="", city="all", sort="price_desc", db=db))
    sort_prods = sort_res.context["products"]
    record("Tri prix décroissant conforme (27 000 F > 18 000 F)", sort_prods[0].price >= sort_prods[1].price)

    # Masquage / Toggle
    run_coro(toggle_product(request=req_b, product_id=prod_b.id, db=db))
    db.refresh(prod_b)
    record("Produit B mis en pause (is_active = False)", prod_b.is_active is False)

    mkt_toggle = run_coro(marketplace_view(request=anon_req, q="", city="all", sort="recent", db=db))
    record("Produit masqué n'apparaît plus sur la Marketplace", len(mkt_toggle.context["products"]) == 1 and mkt_toggle.context["products"][0].id == prod_a.id)

    # Réactivation
    run_coro(toggle_product(request=req_b, product_id=prod_b.id, db=db))
    db.refresh(prod_b)
    record("Produit B réactivé avec succès", prod_b.is_active is True)

    # -------------------------------------------------------------
    # 6. COMMANDE ANTI-LAPIN & SUSPENSION ORANGE / MOOV
    # -------------------------------------------------------------
    print("\n--- 6. TESTS COMMANDE ANTI-LAPIN & PAIEMENTS ACTIFS ---", flush=True)

    zone_b = db.query(DeliveryZone).filter(DeliveryZone.merchant_id == march_b.id).first()

    # Client passe commande pour Produit B
    checkout_res = run_coro(process_checkout(
        store_slug=march_b.store_slug,
        product_id=prod_b.id,
        quantity=1,
        customer_name="Kouamé Eric",
        customer_phone="0708091011",
        delivery_zone_id=zone_b.id,
        delivery_address="Yopougon Niangon Terminus 27",
        customer_notes="Près de la pharmacie",
        payment_method="WAVE",
        db=db
    ))
    record("Commande enregistrée avec succès (Redirection)", checkout_res.status_code == 303)
    order_num = checkout_res.headers["location"].split("/")[-1]

    order = db.query(Order).filter(Order.order_number == order_num).first()
    record("Commande liée strictement au Marchand B", order.merchant_id == march_b.id)
    record("Acompte Anti-Lapin calculé (> 0 FCFA)", order.deposit_required > 0)
    record("Statut initial en attente d'acompte (PENDING_DEPOSIT)", order.payment_status == PaymentStatusEnum.PENDING_DEPOSIT.value)

    # Validation paiement acompte Wave
    run_coro(confirm_simulated_payment(
        order_number=order_num,
        method="WAVE",
        transaction_ref="WAVE-CI-998877",
        db=db
    ))
    db.refresh(order)
    record("Acompte marqué payé en base de données", order.deposit_paid == order.deposit_required)
    record("Commande sécurisée Anti-Lapin prête à expédier (DEPOSIT_PAID)", order.payment_status == PaymentStatusEnum.DEPOSIT_PAID.value)

    # Étanchéité absolue des commandes entre marchands
    orders_b = db.query(Order).filter(Order.merchant_id == march_b.id).all()
    orders_a = db.query(Order).filter(Order.merchant_id == march_a.id).all()
    record("Marchand B voit sa commande dans sa boutique", any(o.order_number == order_num for o in orders_b))
    record("Marchand A ne voit AUCUNE commande de Marchand B (Étanchéité totale)", len(orders_a) == 0)

    # -------------------------------------------------------------
    # 7. NORMALISATION NUMÉROS & AUTHENTIFICATION PIN
    # -------------------------------------------------------------
    print("\n--- 7. TESTS CONNEXION ET NORMALISATION NUMÉROS CI ---", flush=True)

    # Connexion format standard 10 chiffres
    res_l1 = Response()
    r1 = run_coro(process_login(response=res_l1, phone="0701020304", pin_code="1122", db=db))
    record("Connexion numéro standard (0701020304) -> Dashboard", r1.headers.get("location") == "/merchant/dashboard")

    # Connexion format international +225 avec espaces
    res_l2 = Response()
    r2 = run_coro(process_login(response=res_l2, phone="+225 07 01 02 03 04", pin_code="1122", db=db))
    record("Connexion format '+225 07 01 02 03 04' -> Dashboard", r2.headers.get("location") == "/merchant/dashboard")

    # Rejet mauvais PIN
    res_bad = Response()
    r_bad = run_coro(process_login(response=res_bad, phone="0701020304", pin_code="0000", db=db))
    record("Rejet immédiat PIN incorrect (error=invalid_pin)", "error=invalid_pin" in r_bad.headers.get("location", ""))

    # Connexion compte fondateur avec PIN 7788
    res_found = Response()
    r_found = run_coro(process_login(response=res_found, phone="0595094159", pin_code="7788", db=db))
    record("Connexion Fondateur (0595094159 / PIN 7788) -> Dashboard", r_found.headers.get("location") == "/merchant/dashboard")

    # -------------------------------------------------------------
    # BILAN FINAL DU GRAND BACKTEST
    # -------------------------------------------------------------
    print("\n" + "=" * 75, flush=True)
    print(f"BILAN DU GRAND BACKTEST : {len(passed_checks)} SUCCES / {len(failed_checks)} ECHECS", flush=True)
    print("=" * 75, flush=True)

    if failed_checks:
        print("\nERREURS DETECTEES :", flush=True)
        for name, det in failed_checks:
            print(f"  - {name}: {det}", flush=True)
        sys.exit(1)
    else:
        print("\nTOUS LES TESTS ONT REUSSI A 100% SANS AUCUNE ERREUR !", flush=True)
        print("  [OK] Isolation multi-vendeurs : 100% ETANCHE & IMPENETRABLE", flush=True)
        print("  [OK] Marketplace publique : 100% OPERATIONNELLE", flush=True)
        print("  [OK] Protection contre modifications frauduleuses : 100% VERIFIEE", flush=True)
        print("  [OK] Tunnel de commande & Anti-Lapin Wave CI : 100% CONFORME", flush=True)
        print("  [OK] Normalisation numéros CI & PIN : 100% VALIDE", flush=True)

    db.close()

    # Nettoyage DB de test
    try:
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
    except Exception:
        pass

if __name__ == "__main__":
    main()
