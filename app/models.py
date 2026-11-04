from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class DepositPolicyEnum(str, enum.Enum):
    DELIVERY_FEE_ONLY = "DELIVERY_FEE_ONLY" # Le client paie seulement les frais de livraison en avance
    FULL_PAYMENT = "FULL_PAYMENT"           # 100% à la commande
    FIXED_DEPOSIT = "FIXED_DEPOSIT"         # Montant fixe (ex: 2 000 FCFA)
    PERCENTAGE = "PERCENTAGE"               # Pourcentage du panier (ex: 30%)

class PaymentStatusEnum(str, enum.Enum):
    PENDING_DEPOSIT = "PENDING_DEPOSIT" # En attente de l'acompte Wave/MoMo
    DEPOSIT_PAID = "DEPOSIT_PAID"       # Acompte validé -> Prêt à être expédié sans risque de lapin !
    FULLY_PAID = "FULLY_PAID"           # Payé à 100%
    CANCELLED = "CANCELLED"             # Annulée

class DeliveryStatusEnum(str, enum.Enum):
    WAITING_DISPATCH = "WAITING_DISPATCH" # En préparation
    DISPATCHED = "DISPATCHED"             # Remis au coursier / En route
    DELIVERED = "DELIVERED"               # Livré avec succès
    RETURNED = "RETURNED"                 # Échec / Retour

class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), unique=True, index=True, nullable=False) # WhatsApp number
    email = Column(String(100), unique=True, index=True, nullable=True)
    store_name = Column(String(100), nullable=False)
    store_slug = Column(String(100), unique=True, index=True, nullable=False)
    bio = Column(Text, nullable=True)
    logo_url = Column(String(255), nullable=True)
    currency = Column(String(10), default="FCFA")
    country = Column(String(10), default="CI") # CI, SN, CM, BF, ML, etc.
    city = Column(String(100), default="Abidjan")
    pin_code = Column(String(10), default="1234") # Code PIN 4 chiffres pour connexion mobile rapide
    
    # Abonnement SaaS (Monétisation de la plateforme)
    subscription_plan = Column(String(50), default="STARTER") # STARTER (Gratuit), PRO (9 900 F), BUSINESS (19 900 F)
    subscription_status = Column(String(50), default="ACTIVE")
    subscription_paid_amount = Column(Integer, default=0)
    
    # Numéros de réception directe (Côte d'Ivoire)
    wave_number = Column(String(30), nullable=True)
    orange_money_number = Column(String(30), nullable=True)
    mtn_momo_number = Column(String(30), nullable=True)
    moov_money_number = Column(String(30), nullable=True)
    
    # Politique d'acompte Anti-Lapin
    deposit_policy = Column(String(50), default=DepositPolicyEnum.DELIVERY_FEE_ONLY.value)
    fixed_deposit_amount = Column(Integer, default=2000)
    deposit_percentage = Column(Integer, default=30)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="merchant", cascade="all, delete-orphan")
    delivery_zones = relationship("DeliveryZone", back_populates="merchant", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="merchant")

class DeliveryZone(Base):
    __tablename__ = "delivery_zones"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    name = Column(String(100), nullable=False) # ex: "Cocody / Riviera", "Yopougon", "Marcory"
    fee = Column(Integer, nullable=False, default=1500) # Prix en FCFA
    estimated_time = Column(String(50), default="2h - 4h")

    merchant = relationship("Merchant", back_populates="delivery_zones")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False) # Prix en FCFA
    compare_at_price = Column(Integer, nullable=True) # Prix barré promo
    image_url = Column(String(255), nullable=True)
    stock = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("Merchant", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")

    @property
    def is_video(self) -> bool:
        if not self.image_url:
            return False
        lower = self.image_url.lower()
        return any(lower.endswith(ext) for ext in [".mp4", ".mov", ".webm", ".m4v"])

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(30), unique=True, index=True, nullable=False)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    
    # Coordonnées Client
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(30), nullable=False) # WhatsApp
    delivery_zone_name = Column(String(100), nullable=False)
    delivery_address = Column(Text, nullable=False) # Quartier, Rue, Repères
    customer_notes = Column(Text, nullable=True)
    
    # Montants financiers
    subtotal = Column(Integer, nullable=False) # Somme articles
    delivery_fee = Column(Integer, nullable=False) # Frais de livraison
    total_amount = Column(Integer, nullable=False) # Total commande
    
    # Mécanisme Anti-Lapin
    deposit_required = Column(Integer, nullable=False) # L'acompte à payer obligatoirement
    deposit_paid = Column(Integer, default=0) # Acompte effectivement reçu
    balance_due = Column(Integer, nullable=False) # Solde restant à encaisser en cash par le livreur
    
    payment_method = Column(String(50), default="WAVE") # WAVE, ORANGE_MONEY, MTN_MOMO, MOOV
    payment_status = Column(String(50), default=PaymentStatusEnum.PENDING_DEPOSIT.value)
    delivery_status = Column(String(50), default=DeliveryStatusEnum.WAITING_DISPATCH.value)
    transaction_ref = Column(String(100), nullable=True)
    
    # Suivi Coursier / Livreur
    delivery_rider_name = Column(String(100), nullable=True)
    delivery_rider_phone = Column(String(30), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_title = Column(String(150), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer, nullable=False)
    total_price = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
