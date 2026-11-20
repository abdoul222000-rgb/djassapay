import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "CallCatch AI"
    CALLCATCH_SECRET_KEY: str = "super-secret-key-callcatch-2026-high-security"
    CALLCATCH_DATABASE_URL: str = os.getenv(
        "CALLCATCH_DATABASE_URL",
        "sqlite:////tmp/callcatch.db" if os.getenv("VERCEL") else "sqlite:///./callcatch.db"
    )
    
    # Intégration Whop (Merchant of Record & Abonnements Internationaux)
    WHOP_API_KEY: str = os.getenv("WHOP_API_KEY", "")
    WHOP_WEBHOOK_SECRET: str = os.getenv("WHOP_WEBHOOK_SECRET", "")
    WHOP_STARTER_CHECKOUT_URL: str = os.getenv("WHOP_STARTER_CHECKOUT_URL", "")
    WHOP_PRO_CHECKOUT_URL: str = os.getenv("WHOP_PRO_CHECKOUT_URL", "")
    WHOP_SCALE_CHECKOUT_URL: str = os.getenv("WHOP_SCALE_CHECKOUT_URL", "")
    
    # Identifiants Maître Fondateur / SuperAdmin (Accès VIP Privé CallCatch)
    CALLCATCH_FOUNDER_EMAIL: str = "abdoul222000@gmail.com"
    CALLCATCH_FOUNDER_PIN: str = "4568"
    CALLCATCH_FOUNDER_PASSWORD: str = "@Abdoul20017"
    
    # Twilio (pour les numéros US, détection des appels et envoi SMS)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "+1234567890")
    
    # Intelligence Artificielle (OpenAI / Claude pour les réponses SMS intelligentes)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    AI_MODEL: str = "gpt-4o-mini"
    
    # Valeur moyenne estimée d'un chantier US (pour afficher les $ économisés à l'artisan)
    DEFAULT_JOB_VALUE_USD: float = 450.0

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
