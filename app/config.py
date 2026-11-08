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
    
    # Coordonnées & Sécurité du Fondateur (Accès Exclusif & Réception des Gains)
    FOUNDER_NAME: str = "Diabagate Assouman (Djassapay)"
    FOUNDER_PIN: str = "7788" # Code PIN Secret Fondateur pour accéder à l'espace
    FOUNDER_PASSWORD: str = "DjassaFondateur2026@" # Mot de passe de secours
    FOUNDER_PHONE: str = "0595094159"
    FOUNDER_EMAIL: str = "djassapay9@gmail.com"
    FOUNDER_WAVE_NUMBER: str = "0595094159"
    FOUNDER_ORANGE_MONEY_NUMBER: str = "0595094159"
    FOUNDER_MTN_MOMO_NUMBER: str = "0595094159"
    FOUNDER_MOOV_MONEY_NUMBER: str = ""
    COMMISSION_PERCENTAGE: float = 1.5 # 1.5% de commission plateforme
    
    # Compte Officiel Wave Business CI
    FOUNDER_WAVE_ACCOUNT_NUMBER: str = "CI 94 95 29 42" # Numéro de Compte B2B Wave Business
    FOUNDER_WAVE_B2B_ID: str = "M_ci_OunaDzCXM0MS" # Identifiant Marchand Wave
    FOUNDER_WAVE_BUSINESS_NAME: str = "Djassapay"
    
    # Passerelle Wave Business (Optionnel)
    WAVE_API_KEY: str = ""
    WAVE_WEBHOOK_SECRET: str = ""

    # WhatsApp Cloud API (Meta Official)
    WHATSAPP_TOKEN: str = "" # Bearer Token Meta
    WHATSAPP_PHONE_NUMBER_ID: str = "" # ID du numéro WhatsApp Cloud
    WHATSAPP_VERIFY_TOKEN: str = "djassapay_secret_token_2026" # Token pour valider le webhook Meta
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
