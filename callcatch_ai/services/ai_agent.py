import logging
import httpx
from ..config import settings

logger = logging.getLogger("callcatch.ai")

SYSTEM_PROMPT = """
You are an expert AI receptionist for an American home service contractor (plumber, roofer, HVAC, or electrician).
Your goal is to save missed phone calls by chatting via SMS with the homeowner who just called.

Rules:
1. Be friendly, concise, and professional (it's SMS, keep it under 160 words).
2. Acknowledge what they need help with.
3. If they haven't provided their location/address, politely ask for their address or zip code.
4. If it's an emergency (active water flood, no heat in winter, sparks), flag urgency as HIGH and assure them we are alerting the technician.
5. Offer to schedule an inspection or dispatch a technician.
"""

async def process_inbound_sms_with_ai(
    incoming_text: str, 
    conversation_history: list,
    contractor_name: str,
    business_name: str,
    business_type: str
) -> dict:
    """
    Analyse le SMS du client américain et génère une réponse professionnelle ainsi qu'une qualification du lead.
    Retourne :
    {
        "reply_text": "...",
        "urgency": "HIGH" | "MEDIUM" | "LOW",
        "job_summary": "...",
        "address_detected": "..."
    }
    """
    # Si la clé OpenAI est fournie, utiliser GPT-4o-mini
    if settings.OPENAI_API_KEY:
        try:
            messages = [
                {
                    "role": "system", 
                    "content": f"{SYSTEM_PROMPT}\nBusiness: {business_name} ({business_type}). Owner: {contractor_name}."
                }
            ]
            for msg in conversation_history[-6:]: # 6 derniers messages
                role = "assistant" if msg["direction"] == "OUTBOUND" else "user"
                messages.append({"role": role, "content": msg["body"]})
            
            messages.append({"role": "user", "content": incoming_text})

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": settings.AI_MODEL,
                        "messages": messages,
                        "temperature": 0.5,
                        "max_tokens": 200
                    },
                    timeout=15.0
                )
                if res.status_code == 200:
                    ai_reply = res.json()["choices"][0]["message"]["content"].strip()
                    urgency = "HIGH" if any(k in incoming_text.lower() for k in ["leak", "burst", "urgent", "emergency", "flood", "now", "asap"]) else "MEDIUM"
                    return {
                        "reply_text": ai_reply,
                        "urgency": urgency,
                        "job_summary": incoming_text[:100],
                        "address_detected": None
                    }
        except Exception as e:
            logger.error(f"Erreur API OpenAI : {e}, utilisation du moteur intelligent local.")

    # Moteur intelligent local de secours (Zéro coût, 100% fonctionnel pour tester)
    text_lower = incoming_text.lower()
    
    # 1. Détection d'urgence
    if any(k in text_lower for k in ["leak", "burst", "flood", "emergency", "sparks", "smoke", "asap", "broken"]):
        urgency = "HIGH"
        reply = (
            f"Got it! That sounds urgent. I'm alerting {contractor_name} right away. "
            f"What's your full street address or zip code so we can check technician availability in your area?"
        )
    elif any(k in text_lower for k in ["quote", "price", "estimate", "cost", "how much"]):
        urgency = "MEDIUM"
        reply = (
            f"Thanks for reaching out to {business_name}! We'd be happy to give you a clear estimate. "
            f"Could you briefly describe the job and what city/area you're located in?"
        )
    elif any(k in text_lower for k in ["st", "street", "ave", "avenue", "rd", "road", "blvd", "austin", "dallas", "houston", "miami"]):
        urgency = "MEDIUM"
        reply = (
            f"Thank you! We have technicians covering your area. "
            f"Would today after 2:00 PM or tomorrow morning work best for a quick on-site inspection?"
        )
    else:
        urgency = "NORMAL"
        reply = (
            f"Thanks for getting back to us! {contractor_name} is reviewing your message. "
            f"What is the best time today for us to call you back or come take a look?"
        )

    return {
        "reply_text": reply,
        "urgency": urgency,
        "job_summary": incoming_text[:120],
        "address_detected": None
    }
