import urllib.parse
import httpx
from app.config import settings

def clean_phone_number(phone: str, default_country_code: str = "225") -> str:
    """Clean and normalize phone number for WhatsApp wa.me links and Cloud API."""
    clean = "".join([c for c in phone if c.isdigit()])
    # If 10 digits starting with 0 (ex CI: 0708091011 or 0102030405)
    if clean.startswith("0") and len(clean) == 10:
        clean = default_country_code + clean[1:]
    elif len(clean) == 8: # Old 8-digit format
        clean = default_country_code + clean
    elif not clean.startswith(default_country_code) and len(clean) <= 10:
        clean = default_country_code + clean
    return clean

async def send_whatsapp_cloud_message(recipient_phone: str, message_text: str) -> dict:
    """
    Envoie un message WhatsApp automatique via l'API officielle WhatsApp Cloud de Meta.
    Si le token Meta n'est pas encore configuré, simule l'envoi et logue le contenu.
    """
    cleaned_to = clean_phone_number(recipient_phone)
    
    # Si les identifiants Meta Cloud API sont présents
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID:
        url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_to,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": message_text
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                data = response.json()
                print(f"[WhatsApp Cloud API] Envoyé à {cleaned_to} - Statut: {response.status_code}")
                return {"status": "success", "response": data}
        except Exception as e:
            print(f"[WhatsApp Cloud API Error] Échec d'envoi à {cleaned_to} : {e}")
            return {"status": "error", "message": str(e)}

    # Mode Simulation / Log local
    try:
        print(f"[WhatsApp Démo Simulation] Message automatique pour {cleaned_to} :")
        print("-" * 50)
        print(message_text)
        print("-" * 50)
    except UnicodeEncodeError:
        print(f"[WhatsApp Démo Simulation] Message automatique pour {cleaned_to} (texte encodé) :")
        print(message_text.encode("ascii", errors="replace").decode())
    return {"status": "simulated", "recipient": cleaned_to}

async def auto_notify_order_created(order, merchant):
    """Notification automatique envoyée au client dès la création de sa commande."""
    msg = (
        f"Bonjour {order.customer_name} ! 👋\n\n"
        f"Votre commande #{order.order_number} chez *{merchant.store_name}* est bien enregistrée !\n\n"
        f"🔒 *Acompte Anti-Lapin à régler :* {order.deposit_required:,} FCFA\n"
        f"💵 *Solde restant à payer au livreur :* {order.balance_due:,} FCFA\n\n"
        f"👉 Cliquez ici pour valider votre expédition par Wave ou Mobile Money :\n"
        f"{settings.BASE_URL}/orders/{order.order_number}\n\n"
        f"Le livreur se met en route dès confirmation de l'acompte. Merci !"
    )
    return await send_whatsapp_cloud_message(order.customer_phone, msg)

async def auto_notify_deposit_confirmed(order, merchant):
    """Notification automatique envoyée au client ET au vendeur dès que l'acompte est payé."""
    # 1. Message au client
    msg_client = (
        f"✅ *ACOMPTE CONFIRMÉ !* #{order.order_number}\n\n"
        f"Merci {order.customer_name}, votre acompte de {order.deposit_paid:,} FCFA a bien été reçu par *{merchant.store_name}*.\n\n"
        f"📦 Votre colis est en cours de préparation.\n"
        f"🏍️ Le livreur a été prévenu.\n"
        f"💵 Pensez à préparer les *{order.balance_due:,} FCFA* en espèces pour le coursier.\n\n"
        f"Suivez votre livraison en direct :\n"
        f"{settings.BASE_URL}/orders/{order.order_number}"
    )
    await send_whatsapp_cloud_message(order.customer_phone, msg_client)

    # 2. Alerte au vendeur (WhatsApp du marchand)
    msg_merchant = (
        f"🎉 *NOUVELLE COMMANDE SÉCURISÉE !* 🎉\n\n"
        f"La commande #{order.order_number} de {order.customer_name} est confirmée !\n"
        f"💰 Acompte reçu : {order.deposit_paid:,} FCFA ({order.payment_method})\n"
        f"📍 Destination : {order.delivery_zone_name} - {order.delivery_address}\n\n"
        f"👉 Transférez la course au livreur en 1 clic :\n"
        f"{settings.BASE_URL}/delivery/{order.order_number}"
    )
    return await send_whatsapp_cloud_message(merchant.phone, msg_merchant)

def generate_customer_order_whatsapp(order, merchant) -> str:
    """
    Génère le lien 1-clic wa.me permettant au client de causer directement avec le vendeur
    sur WhatsApp après ou pendant sa commande.
    Le message est adressé au vendeur et pré-rempli avec les détails de la commande.
    """
    # Numéro de destination : celui du MARCHAND (vendeur)
    seller_phone = merchant.phone or merchant.wave_number or "0595094159"
    phone = clean_phone_number(seller_phone)

    # Détails des articles
    items_desc = []
    if hasattr(order, "items") and order.items:
        for it in order.items:
            items_desc.append(f"• {it.quantity}x {it.product_title}")
    items_str = "\n".join(items_desc) if items_desc else "Articles commandés"

    deposit_paid = getattr(order, "deposit_paid", 0) or 0
    is_paid = (order.payment_status in ["DEPOSIT_PAID", "FULLY_PAID"]) or (deposit_paid > 0)

    if is_paid:
        msg = (
            f"Bonjour {merchant.store_name} ! 👋\n\n"
            f"Je viens de régler mon acompte Wave de *{deposit_paid:,} FCFA* pour ma commande *#{order.order_number}*.\n\n"
            f"📦 *Articles :*\n{items_str}\n\n"
            f"💰 *Montant Total :* {order.total_amount:,} FCFA\n"
            f"💵 *Solde restant à remettre au livreur :* {order.balance_due:,} FCFA\n\n"
            f"📍 *Mon adresse de livraison :*\n"
            f"{order.delivery_zone_name} - {order.delivery_address}\n"
            f"👤 *Client :* {order.customer_name} ({order.customer_phone})\n\n"
            f"Pouvez-vous me confirmer la bonne réception et l'expédition du colis avec le coursier moto ? Merci !"
        )
    else:
        msg = (
            f"Bonjour {merchant.store_name} ! 👋\n\n"
            f"Je souhaite échanger avec vous concernant ma commande *#{order.order_number}* chez *{merchant.store_name}*.\n\n"
            f"📦 *Articles :*\n{items_str}\n"
            f"💰 *Total :* {order.total_amount:,} FCFA\n"
            f"🔒 *Acompte prévu :* {order.deposit_required:,} FCFA\n"
            f"📍 *Destination :* {order.delivery_zone_name} - {order.delivery_address}\n"
            f"👤 *Client :* {order.customer_name} ({order.customer_phone})\n\n"
            f"Pouvez-vous me donner des précisions pour la livraison ? Merci !"
        )

    encoded = urllib.parse.quote(msg)
    return f"https://wa.me/{phone}?text={encoded}"

def generate_rider_dispatch_whatsapp(order, merchant, rider_phone: str = "") -> str:
    """Génère le lien de secours 1-clic wa.me avec la fiche de course pour le livreur."""
    phone = clean_phone_number(rider_phone) if rider_phone else ""
    slip_url = f"{settings.BASE_URL}/delivery/{order.order_number}"
    msg = (
        f"🚨 *NOUVELLE COURSE LIVRAISON - {merchant.store_name}* 🚨\n\n"
        f"📦 Commande : #{order.order_number}\n"
        f"👤 Destinataire : {order.customer_name}\n"
        f"📞 Tél client : {order.customer_phone}\n"
        f"📍 Commune : *{order.delivery_zone_name}*\n"
        f"🏠 Adresse/Repère : {order.delivery_address}\n"
        f"💵 *ESPÈCES À RÉCUPÉRER : {order.balance_due:,} FCFA*\n"
        f"(L'acompte de {order.deposit_paid:,} FCFA a déjà été payé par Wave/MoMo ✅)\n\n"
        f"📋 Ouvrir la feuille de route livreur :\n"
        f"{slip_url}"
    )
    encoded = urllib.parse.quote(msg)
    if phone:
        return f"https://wa.me/{phone}?text={encoded}"
    return f"https://wa.me/?text={encoded}"
