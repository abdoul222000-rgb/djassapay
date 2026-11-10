import hmac
import hashlib
import time
from collections import defaultdict
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from .config import settings

# Clé secrète de signature cryptographique (empêche la falsification de session)
SIGNING_KEY = settings.CALLCATCH_SECRET_KEY.encode('utf-8')

# ==============================================================================
# 1. SIGNATURE CRYPTOGRAPHIQUE DES SESSIONS (ANTI-FALSIFICATION / ANTI-TAMPERING)
# ==============================================================================

def create_signed_session_cookie(user_id: int, role: str = "contractor") -> str:
    """
    Crée un cookie inviolable signé avec HMAC-SHA256.
    Même si un hacker modifie l'ID dans son navigateur, la signature sera invalide.
    Format : {user_id}:{role}:{timestamp}:{signature_hmac}
    """
    timestamp = int(time.time())
    payload = f"{user_id}:{role}:{timestamp}"
    signature = hmac.new(SIGNING_KEY, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_signed_session_cookie(cookie_value: str) -> dict:
    """
    Vérifie la validité mathématique et l'intégrité de la session.
    Rejette immédiatement toute tentative de falsification par un hacker.
    """
    if not cookie_value or ":" not in cookie_value:
        return None
    
    parts = cookie_value.split(":")
    if len(parts) != 4:
        return None
    
    user_id_str, role, timestamp_str, received_sig = parts
    payload = f"{user_id_str}:{role}:{timestamp_str}"
    expected_sig = hmac.new(SIGNING_KEY, payload.encode('utf-8'), hashlib.sha256).hexdigest()

    # Comparaison à temps constant contre les attaques de timing (Timing Attacks)
    if not hmac.compare_digest(expected_sig, received_sig):
        return None
    
    # Expiration de la session après 30 jours
    try:
        if time.time() - int(timestamp_str) > (86400 * 30):
            return None
        return {"user_id": int(user_id_str), "role": role}
    except ValueError:
        return None


# ==============================================================================
# 2. SYSTÈME ANTI-BRUTE FORCE / RATE LIMITER (ANTI-HACKERS)
# ==============================================================================

# Dictionnaire en mémoire des tentatives par IP : ip -> [timestamps]
FAILED_ATTEMPTS = defaultdict(list)
MAX_FAILED_ATTEMPTS = 5 # 5 erreurs max
BLOCK_DURATION_SECONDS = 900 # Blocage de 15 minutes

def check_rate_limit(request: Request):
    """Bloque les adresses IP suspectes qui essaient de forcer les mots de passe"""
    client_ip = request.client.host if request.client else "unknown"
    
    # Ne pas bloquer les tests locaux sur localhost
    if client_ip in ["127.0.0.1", "localhost", "testclient"]:
        return

    now = time.time()
    
    # Nettoyer les tentatives anciennes
    FAILED_ATTEMPTS[client_ip] = [t for t in FAILED_ATTEMPTS[client_ip] if now - t < BLOCK_DURATION_SECONDS]
    
    if len(FAILED_ATTEMPTS[client_ip]) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives suspectes. Votre adresse IP a été temporairement bloquée par notre pare-feu / Too many requests. IP blocked."
        )

def record_failed_attempt(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    FAILED_ATTEMPTS[client_ip].append(time.time())

def clear_failed_attempts(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if client_ip in FAILED_ATTEMPTS:
        del FAILED_ATTEMPTS[client_ip]


# ==============================================================================
# 3. MIDDLEWARE DE SÉCURITÉ DES EN-TÊTES HTTP (SHIELD PROTECTION)
# ==============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injecte des en-têtes de sécurité stricts conformes aux normes bancaires US"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Anti-Clickjacking (interdit d'afficher ton site dans une iframe pirate)
        response.headers["X-Frame-Options"] = "DENY"
        # Anti-MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Protection XSS navigateur
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Politique de référence stricte
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Protection contre l'accès direct aux API de permissions
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
