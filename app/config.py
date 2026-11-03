import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "DjassaPay"
    APP_DESCRIPTION: str = "SaaS E-commerce & Acompte Anti-Lapin pour Vendeurs WhatsApp / Réseaux Sociaux"
    APP_ENV: str = "development"
    SECRET_KEY: str = "djassapay-super-secret-key-abidjan-2026"
    DATABASE_URL: str = "sqlite:///./djassapay.db"
    
    # Base URL for public links (storefront, delivery slip, webhooks)
    BASE_URL: str = "http://localhost:8000"
    
    # Coordonnées du Fondateur (Pour recevoir vos abonnements SaaS & commissions)
    FOUNDER_NAME: str = "Fondateur DjassaPay"
    FOUNDER_PHONE: str = ""
    FOUNDER_WAVE_NUMBER: str = ""
    FOUNDER_ORANGE_MONEY_NUMBER: str = ""
    FOUNDER_MTN_MOMO_NUMBER: str = ""
    COMMISSION_PERCENTAGE: float = 1.5 # 1.5% de commission plateforme
    
    # Payment Gateway Configuration (Production)
    # Wave Business API credentials
    WAVE_API_KEY: str = ""
    WAVE_WEBHOOK_SECRET: str = ""
    
    # CinetPay credentials (supports Orange Money, MTN MoMo, Moov, Wave)
    CINETPAY_API_KEY: str = ""
    CINETPAY_SITE_ID: str = ""
    
    # Paystack credentials
    PAYSTACK_SECRET_KEY: str = ""

    # WhatsApp Cloud API (Meta Official)
    WHATSAPP_TOKEN: str = "" # Bearer Token Meta
    WHATSAPP_PHONE_NUMBER_ID: str = "" # ID du numéro WhatsApp Cloud
    WHATSAPP_VERIFY_TOKEN: str = "djassapay_secret_token_2026" # Token pour valider le webhook Meta
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
