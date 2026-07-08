import json

import httpx

try:
    from .config import PAYPAL_API_URL, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_PRO_PLAN_ID, PAYPAL_SANDBOX, PAYPAL_WEBHOOK_ID
    from .utils import logger
except ImportError:
    from config import PAYPAL_API_URL, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_PRO_PLAN_ID, PAYPAL_SANDBOX, PAYPAL_WEBHOOK_ID
    from utils import logger


_paypal_token: str | None = None
_paypal_token_expiry: float = 0


async def _get_paypal_token() -> str:
    global _paypal_token, _paypal_token_expiry
    import time

    now = time.time()
    if _paypal_token and now < _paypal_token_expiry:
        return _paypal_token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/oauth2/token",
            headers={"Accept": "application/json"},
            data={"grant_type": "client_credentials"},
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        )
        resp.raise_for_status()
        data = resp.json()
        _paypal_token = data["access_token"]
        _paypal_token_expiry = now + data.get("expires_in", 30000) - 60
    return _paypal_token


async def verify_webhook_signature(headers: dict, body: bytes) -> bool:
    if not PAYPAL_WEBHOOK_ID:
        logger.error("PAYPAL_WEBHOOK_ID não configurado — rejeitando webhook")
        return False
    token = await _get_paypal_token()
    verification_data = {
        "auth_algo": headers.get("paypal-auth-algo", ""),
        "cert_url": headers.get("paypal-cert-url", ""),
        "transmission_id": headers.get("paypal-transmission-id", ""),
        "transmission_sig": headers.get("paypal-transmission-sig", ""),
        "transmission_time": headers.get("paypal-transmission-time", ""),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": json.loads(body.decode()),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/notifications/verify-webhook-signature",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=verification_data,
        )
        if resp.status_code != 200:
            return False
        result = resp.json()
        return result.get("verification_status") == "SUCCESS"


async def get_paypal_config() -> dict:
    return {
        "client_id": PAYPAL_CLIENT_ID,
        "plan_id": PAYPAL_PRO_PLAN_ID,
        "sandbox": PAYPAL_SANDBOX,
    }


async def create_paypal_product(name: str, description: str) -> str:
    token = await _get_paypal_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/catalogs/products",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "name": name,
                "description": description,
                "type": "SERVICE",
                "category": "SOFTWARE",
            },
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Falha ao criar produto PayPal: {data}")
        return data["id"]


async def create_paypal_billing_plan(
    product_id: str,
    name: str,
    description: str,
    price: float,
    currency: str = "USD",
) -> str:
    token = await _get_paypal_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/billing/plans",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "product_id": product_id,
                "name": name,
                "description": description,
                "status": "ACTIVE",
                "billing_cycles": [
                    {
                        "frequency": {
                            "interval_unit": "MONTH",
                            "interval_count": 1,
                        },
                        "tenure_type": "REGULAR",
                        "sequence": 1,
                        "total_cycles": 0,
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": f"{price:.2f}",
                                "currency_code": currency,
                            }
                        },
                    }
                ],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "setup_fee": {"value": "0", "currency_code": currency},
                    "setup_fee_failure_action": "CONTINUE",
                    "payment_failure_threshold": 3,
                },
            },
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Falha ao criar plano PayPal: {data}")
        return data["id"]


async def create_paypal_subscription(plan_id: str, user_id: str) -> dict:
    token = await _get_paypal_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/billing/subscriptions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "plan_id": plan_id,
                "custom_id": user_id,
                "application_context": {
                    "user_action": "SUBSCRIBE_NOW",
                    "return_url": "https://rest2mcp.app/?page=dashboard",
                    "cancel_url": "https://rest2mcp.app/",
                },
            },
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Falha ao criar subscrição PayPal: {data}")
        return data


EVENT_MAP = {
    "BILLING.SUBSCRIPTION.ACTIVATED": "activated",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED": "payment_failed",
    "BILLING.SUBSCRIPTION.CANCELLED": "cancelled",
    "BILLING.SUBSCRIPTION.RE-ACTIVATED": "reactivated",
}


def parse_webhook_event(body: bytes) -> dict | None:
    try:
        event = json.loads(body.decode())
        event_type = event.get("event_type", "")
        action = EVENT_MAP.get(event_type)
        if not action:
            return None
        resource = event.get("resource", {})
        custom_id = resource.get("custom_id", "")
        subscription_id = resource.get("id", "")
        return {
            "action": action,
            "event_type": event_type,
            "custom_id": custom_id,
            "subscription_id": subscription_id,
            "raw": event,
        }
    except (json.JSONDecodeError, KeyError):
        return None
