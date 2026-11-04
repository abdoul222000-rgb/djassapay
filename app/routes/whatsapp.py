from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from app.config import settings
from app.services.whatsapp_service import send_whatsapp_cloud_message

router = APIRouter()

@router.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """
    Validation du Webhook par Meta (Facebook Developers).
    Meta envoie une requête GET avec un challenge pour vérifier la propriété du serveur.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        print("[WhatsApp Webhook Verified] Poignée de main Meta réussie !")
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Vérification échouée : token invalide")

@router.post("/webhook/whatsapp")
async def receive_whatsapp_event(request: Request):
    """
    Réception des événements WhatsApp de Meta (statuts de message, accusés de réception).
    """
    try:
        body = await request.json()
        # Ici on peut traiter les réponses des clients ou les statuts (delivered, read)
        return JSONResponse({"status": "received"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.post("/api/whatsapp/test-send")
async def test_send_whatsapp(phone: str = Form(...), message: str = Form("Test DjassaPay WhatsApp Cloud API")):
    """Permet de tester l'envoi d'un message vers votre numéro."""
    res = await send_whatsapp_cloud_message(phone, message)
    return JSONResponse(res)
