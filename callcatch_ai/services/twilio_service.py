import logging
import httpx
from ..config import settings

logger = logging.getLogger("callcatch.twilio")

async def send_sms_via_twilio(to_number: str, message_body: str, from_number: str = None) -> bool:
    """
    Envoie un SMS à un client américain via l'API Twilio.
    Si les clés Twilio ne sont pas configurées, fonctionne en mode simulation (idéal pour tester).
    """
    from_phone = from_number or settings.TWILIO_PHONE_NUMBER

    # Mode simulation si les clés Twilio ne sont pas renseignées
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info(f"[SIMULATION TWILIO] SMS envoyé à {to_number} depuis {from_phone} : '{message_body}'")
        print(f"\n=======================================================")
        print(f"📱 [SMS SIMULATION] TO: {to_number} | FROM: {from_phone}")
        print(f"💬 MESSAGE: {message_body}")
        print(f"=======================================================\n")
        return True

    # Mode réel Twilio API (Appel REST direct, pas besoin du SDK lourd)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    data = {
        "To": to_number,
        "From": from_phone,
        "Body": message_body
    }
    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data, auth=auth, timeout=10.0)
            if response.status_code in [200, 201]:
                logger.info(f"SMS envoyé avec succès à {to_number}")
                return True
            else:
                logger.error(f"Erreur Twilio ({response.status_code}) : {response.text}")
                return False
    except Exception as e:
        logger.error(f"Exception lors de l'envoi SMS : {e}")
        return False
