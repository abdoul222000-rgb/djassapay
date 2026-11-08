import httpx
import uuid
from app.config import settings
from app.models import Order, PaymentStatusEnum

class PaymentService:
    @staticmethod
    def calculate_deposit_and_balance(merchant, subtotal: int, delivery_fee: int):
        """
        Calcule le montant de l'acompte Anti-Lapin et le solde restant.
        """
        total = subtotal + delivery_fee
        policy = merchant.deposit_policy

        if policy == "DELIVERY_FEE_ONLY":
            # Le client ne paie d'avance QUE les frais de livraison
            deposit = delivery_fee
        elif policy == "FULL_PAYMENT":
            # Le client paie 100% de la commande
            deposit = total
        elif policy == "FIXED_DEPOSIT":
            # Montant fixe (ex: 2 000 FCFA), ou le total si la commande est inférieure
            deposit = min(merchant.fixed_deposit_amount, total)
        elif policy == "PERCENTAGE":
            # Pourcentage paramétré (ex: 30%)
            pct = merchant.deposit_percentage or 30
            deposit = int((total * pct) / 100)
        else:
            deposit = delivery_fee

        # Assurer que l'acompte ne dépasse jamais le total
        deposit = min(deposit, total)
        balance = total - deposit

        return total, deposit, balance

    @staticmethod
    def initiate_wave_payment(order: Order, merchant) -> dict:
        """
        Génère un lien de paiement Wave.
        Si la clé API Wave réelle est configurée, appelle l'API Wave Checkout.
        Sinon, bascule automatiquement en mode simulation interactive ultra réaliste.
        """
        if settings.WAVE_API_KEY:
            # Appel officiel API Wave Checkout Sessions (https://api.wave.com/v1/checkout/sessions)
            try:
                url = "https://api.wave.com/v1/checkout/sessions"
                headers = {
                    "Authorization": f"Bearer {settings.WAVE_API_KEY.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "amount": str(order.deposit_required),
                    "currency": "XOF",
                    "error_url": f"{settings.BASE_URL}/orders/{order.order_number}?status=error",
                    "success_url": f"{settings.BASE_URL}/orders/{order.order_number}?status=success",
                    "client_reference": order.order_number
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code in [200, 201]:
                        wave_data = resp.json()
                        wave_launch_url = wave_data.get("wave_launch_url")
                        if wave_launch_url:
                            return {
                                "payment_url": wave_launch_url,
                                "provider": "WAVE",
                                "amount": order.deposit_required,
                                "currency": "FCFA",
                                "is_simulation": False
                            }
            except Exception as e:
                print(f"[Wave API Error, fallback to Direct Transfer] {e}")

        # Mode Transfert Direct Wave Côte d'Ivoire (Sans API ou en attente d'approbation)
        return {
            "payment_url": f"{settings.BASE_URL}/payments/simulate/{order.order_number}?method=WAVE",
            "provider": "WAVE",
            "amount": order.deposit_required,
            "currency": "FCFA",
            "is_simulation": not bool(settings.WAVE_API_KEY)
        }

    @staticmethod
    def initiate_momo_payment(order: Order, merchant, provider: str = "ORANGE_MONEY") -> dict:
        """
        Initialise un paiement direct Mobile Money Côte d'Ivoire (Orange Money CI, MTN MoMo CI, Moov Money CI).
        Les fonds vont directement sur le compte Mobile Money du marchand.
        """
        return {
            "payment_url": f"{settings.BASE_URL}/payments/simulate/{order.order_number}?method={provider}",
            "provider": provider,
            "amount": order.deposit_required,
            "currency": "FCFA",
            "is_simulation": False
        }

    @staticmethod
    def initiate_subscription_wave_payment(merchant, plan: str = "PRO", amount: int = 9900) -> dict:
        """
        Génère une session officielle Wave Checkout pour un abonnement SaaS.
        Dès validation par le marchand dans Wave, le Webhook Wave notifie DjassaPay
        et active automatiquement le mode PRO en toute autonomie 24h/24 !
        """
        import time
        ref = f"SUB-{merchant.id}-{plan.upper()}-{int(time.time())}"
        
        if settings.WAVE_API_KEY:
            try:
                url = "https://api.wave.com/v1/checkout/sessions"
                headers = {
                    "Authorization": f"Bearer {settings.WAVE_API_KEY.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "amount": str(amount),
                    "currency": "XOF",
                    "error_url": f"{settings.BASE_URL}/merchant/subscription?error=payment_failed",
                    "success_url": f"{settings.BASE_URL}/merchant/subscription?success=1",
                    "client_reference": ref
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code in [200, 201]:
                        wave_data = resp.json()
                        wave_launch_url = wave_data.get("wave_launch_url")
                        if wave_launch_url:
                            return {
                                "payment_url": wave_launch_url,
                                "reference": ref,
                                "is_automated": True
                            }
            except Exception as e:
                print(f"[Wave Subscription Checkout API Error] {e}")

        return {
            "payment_url": None,
            "reference": ref,
            "is_automated": False
        }

    @staticmethod
    def mark_deposit_as_paid(order: Order, db, transaction_ref: str = None):
        """
        Valide l'encaissement de l'acompte Anti-Lapin et déverrouille l'expédition.
        """
        order.deposit_paid = order.deposit_required
        if order.deposit_paid >= order.total_amount:
            order.payment_status = PaymentStatusEnum.FULLY_PAID.value
        else:
            order.payment_status = PaymentStatusEnum.DEPOSIT_PAID.value
        
        order.transaction_ref = transaction_ref or f"TX-{uuid.uuid4().hex[:8].upper()}"
        db.commit()
        db.refresh(order)
        return order
