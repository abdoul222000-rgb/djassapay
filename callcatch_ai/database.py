from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import hashlib
import secrets
from .config import settings

engine = create_engine(
    settings.CALLCATCH_DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in settings.CALLCATCH_DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Utilitaires de sécurité pour les mots de passe (sans dépendance externe lourde)
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or "$" not in hashed_password:
        return False
    try:
        salt, key_hex = hashed_password.split("$", 1)
        computed = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return secrets.compare_digest(computed, key_hex)
    except Exception:
        return False


class Contractor(Base):
    """L'artisan américain abonné à CallCatch AI"""
    __tablename__ = "contractors"

    id = Column(Integer, primary_key=True, index=True)
    
    # Identifiants de connexion
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # Informations sur l'entreprise
    business_name = Column(String(150), nullable=False) # Ex: "Austin Rapid Plumbing"
    owner_name = Column(String(100), nullable=False)    # Ex: "Mike Anderson"
    owner_phone = Column(String(30), nullable=False)   # Le vrai numéro portable de l'artisan
    business_type = Column(String(50), default="Plumbing") # Plumbing, Roofing, HVAC, Electrician
    
    # Numéro virtuel Twilio US attribué à l'artisan
    twilio_phone_number = Column(String(30), unique=True, index=True)
    
    # Message automatique instantané
    custom_missed_text = Column(
        Text, 
        default="Hey! This is {owner_name} with {business_name}. Sorry I missed your call, I'm currently on a job. How can we help you right now?"
    )
    
    # Paramètres économiques
    avg_ticket_usd = Column(Float, default=450.0) # Gain moyen par intervention
    subscription_active = Column(Boolean, default=True)
    monthly_plan_price = Column(Float, default=99.0) # 99$/mois
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    calls = relationship("MissedCall", back_populates="contractor", cascade="all, delete-orphan")


class MissedCall(Base):
    """Un appel américain manqué qui a été capté et sauvé par CallCatch AI"""
    __tablename__ = "missed_calls"

    id = Column(Integer, primary_key=True, index=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id"), nullable=False)
    
    caller_phone = Column(String(30), nullable=False, index=True) # Numéro du client US qui a appelé
    caller_name = Column(String(100), nullable=True) # Ex: "Sarah Jenkins"
    
    call_sid = Column(String(100), unique=True, nullable=True) # Identifiant d'appel Twilio
    call_time = Column(DateTime, default=datetime.utcnow)
    
    # Statut du lead :
    # MISSED -> TEXT_SENT -> CONVERSATION_ONGOING -> APPOINTMENT_BOOKED -> COMPLETED
    status = Column(String(40), default="MISSED")
    
    urgency_level = Column(String(20), default="NORMAL") # HIGH, MEDIUM, LOW
    job_summary = Column(Text, nullable=True) # Résumé IA : "Fuite d'eau sous évier de cuisine"
    address = Column(String(255), nullable=True) # Adresse du client
    
    estimated_revenue_saved = Column(Float, default=0.0) # Montant $ sauvé pour le dashboard
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    contractor = relationship("Contractor", back_populates="calls")
    messages = relationship("SMSMessage", back_populates="call", cascade="all, delete-orphan")


class SMSMessage(Base):
    """Historique des échanges par SMS entre le client US et l'IA"""
    __tablename__ = "sms_messages"

    id = Column(Integer, primary_key=True, index=True)
    missed_call_id = Column(Integer, ForeignKey("missed_calls.id"), nullable=False)
    
    direction = Column(String(20)) # "INBOUND" (client) ou "OUTBOUND" (CallCatch IA)
    sender = Column(String(30))
    receiver = Column(String(30))
    body = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    call = relationship("MissedCall", back_populates="messages")


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Créer le compte artisan de démonstration (Mike le plombier) s'il n'existe pas
        contractor = db.query(Contractor).filter(Contractor.email == "mike@lonestarplumbing.com").first()
        if not contractor:
            demo_contractor = Contractor(
                email="mike@lonestarplumbing.com",
                hashed_password=hash_password("password123"), # Mot de passe de démo
                business_name="Lone Star Rapid Plumbing & HVAC",
                owner_name="Mike Anderson",
                owner_phone="+15125550198",
                business_type="Plumbing & HVAC",
                twilio_phone_number="+15128889479",
                avg_ticket_usd=550.0,
                monthly_plan_price=99.0,
                custom_missed_text="Hey! This is Mike with Lone Star Plumbing. Sorry I missed your call, I'm currently on a job. How can we help you right now?"
            )
            db.add(demo_contractor)
            db.commit()
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
