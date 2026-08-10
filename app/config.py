import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")
PAYPAL_PRO_PLAN_ID = os.getenv("PAYPAL_PRO_PLAN_ID", "")
PAYPAL_API_URL = os.getenv("PAYPAL_API_URL", "https://api-m.sandbox.paypal.com")
PAYPAL_SANDBOX = os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "price_1TbKy7QdlPUKQK2wQmXUzWOM")

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8080"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://rest2mcp.fly.dev").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///cloud.db").strip()

# NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "")

FREE_TIER_MAX_SERVERS = int(os.getenv("FREE_TIER_MAX_SERVERS", "2"))
FREE_TIER_RPM = int(os.getenv("FREE_TIER_RPM", "10"))
PRO_TIER_MAX_SERVERS = int(os.getenv("PRO_TIER_MAX_SERVERS", "10"))
PRO_TIER_RPM = int(os.getenv("PRO_TIER_RPM", "100"))

# Rate limiting de endpoints de autenticação (modelo Supabase: token bucket por IP).
# O bucket tem capacidade de AUTH_RATE_LIMIT_BURST (rajada) e é recarregado a uma
# taxa definida por endpoint (requests por hora). Excedido o limite -> HTTP 429.
AUTH_RATE_LIMIT_BURST = int(os.getenv("AUTH_RATE_LIMIT_BURST", "30"))
AUTH_LOGIN_RATE_PER_HOUR = int(os.getenv("AUTH_LOGIN_RATE_PER_HOUR", "360"))
AUTH_REGISTER_RATE_PER_HOUR = int(os.getenv("AUTH_REGISTER_RATE_PER_HOUR", "30"))
AUTH_CREDENTIALS_RATE_PER_HOUR = int(os.getenv("AUTH_CREDENTIALS_RATE_PER_HOUR", "120"))

# Se True, o gateway confia em Sb-Forwarded-For / X-Forwarded-For para obter o IP real
# do client quando está atrás de um proxy (mesmo conceito do Supabase). Default: off.
RATE_LIMIT_TRUST_FORWARDED_HEADERS = os.getenv("RATE_LIMIT_TRUST_FORWARDED_HEADERS", "false").lower() == "true"
