import stripe

try:
    from .config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
except ImportError:
    from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

stripe.api_key = STRIPE_SECRET_KEY


def create_checkout_session(
    price_id: str, user_id: str, success_url: str, cancel_url: str, customer_email: str | None = None
):
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "client_reference_id": user_id,
        "subscription_data": {
            "metadata": {"user_id": user_id},
        },
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if customer_email:
        params["customer_email"] = customer_email
    session = stripe.checkout.Session.create(**params)
    return session


def parse_webhook_event(payload: bytes, sig_header: str | None):
    if not sig_header or not STRIPE_WEBHOOK_SECRET:
        return None
    try:
        return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return None


def get_subscription(subscription_id: str):
    return stripe.Subscription.retrieve(subscription_id)


def retrieve_checkout_session(session_id: str):
    return stripe.checkout.Session.retrieve(session_id)


EVENT_MAP = {
    "checkout.session.completed": "session_completed",
    "invoice.payment_succeeded": "payment_succeeded",
    "invoice.payment_failed": "payment_failed",
    "customer.subscription.deleted": "subscription_deleted",
}


def parse_event_type(event_type: str) -> str | None:
    return EVENT_MAP.get(event_type)


def sget(obj, key, default=None):
    """
    Acesso seguro a uma chave, funciona tanto em dicts normais como em
    objetos stripe.StripeObject (que, nesta versão da lib, NÃO implementa
    .get() -- chamar obj.get(...) rebenta com AttributeError/KeyError('get')
    porque __getattr__ tenta tratar "get" como uma chave do próprio objeto).
    Usa sempre esta função em vez de obj.get(...) para qualquer objeto
    vindo de event.data.object ou de stripe.Subscription.retrieve(...).
    """
    if obj is None:
        return default
    try:
        value = obj[key]
        return default if value is None else value
    except (KeyError, TypeError, IndexError):
        return default