# Security Best Practices Report (rest2mcp)

Date: 2026-05-25

## Executive Summary

The codebase contains multiple issues that materially weaken authentication, enable destructive actions without authorization, and expose secrets. The most urgent items are: (1) real secrets committed in `.env`, (2) JWT validation that does not verify signatures, (3) an unauthenticated `/v1/reset` endpoint that wipes the database, (4) accepting PayPal webhooks without verification when a config value is missing, and (5) credential leakage via API keys in URLs + full request/response body logging.

## Critical Findings

### CRIT-01 — Secrets committed to repository (.env)

**Impact:** Anyone with repository access can use the leaked credentials to access Supabase (service role) and PayPal APIs, potentially leading to data exfiltration, unauthorized writes, and billing abuse.

**Evidence**
- [.env](file:///c:/Users/matias.fernando/Documents/case/.env#L1-L19) contains Supabase and PayPal credentials.
- [.gitignore](file:///c:/Users/matias.fernando/Documents/case/.gitignore#L1-L1) does not ignore `.env`.

**Recommendations**
- Immediately rotate all leaked credentials (Supabase service role key, PayPal client secret, and any related tokens).
- Remove `.env` from version control history and keep only a redacted template such as `.env.example`.
- Update `.gitignore` to ignore `.env`, local databases (`*.db`), and other sensitive runtime artifacts.

---

### CRIT-02 — JWT validation does not verify signature (auth bypass)

**Impact:** Attackers can forge tokens and access any authenticated endpoint, impersonate users, and overwrite profile data.

**Evidence**
- [validate_jwt](file:///c:/Users/matias.fernando/Documents/case/app/supabase_auth.py#L72-L84) only parses the JWT payload and checks `exp`, without signature verification.
- [require_auth](file:///c:/Users/matias.fernando/Documents/case/app/supabase_auth.py#L146-L153) trusts `sub` from the unverified payload and uses it as `user_id`.
- [auth_register](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L1160-L1179) uses the unverified JWT payload to upsert profile fields.

**Recommendations**
- Validate the token using a trusted mechanism:
  - Prefer calling Supabase Auth (`/auth/v1/user`) with the bearer token + `apikey` and caching results briefly (fast, correct, supports revocation), or
  - Verify JWT signature locally using the correct algorithm and key material for your Supabase project (only if you have stable signing keys and can safely manage them).
- Enforce issuer/audience checks and require `sub` to be present and well-formed.

---

### CRIT-03 — Unauthenticated database reset endpoint

**Impact:** Anyone can wipe all server and log data, causing total service outage and data loss.

**Evidence**
- [/v1/reset](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L1033-L1042) drops and recreates the DB without any authentication/authorization.

**Recommendations**
- Remove this endpoint from production builds, or protect it with strong authentication + authorization (admin-only) and an additional guard (e.g., environment flag + secret header).

---

### CRIT-04 — PayPal webhooks accepted without signature verification by default

**Impact:** If `PAYPAL_WEBHOOK_ID` is missing, any party can POST fake webhook events and escalate/alter user plan state.

**Evidence**
- [verify_webhook_signature](file:///c:/Users/matias.fernando/Documents/case/app/paypal.py#L36-L39) returns `True` when `PAYPAL_WEBHOOK_ID` is not set.
- [/v1/webhooks/paypal](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L1047-L1097) trusts the result to update subscription state.

**Recommendations**
- Fail closed: reject webhook requests when verification cannot be performed, except in an explicit development mode.
- Log verification failures with minimal details (avoid dumping payloads).

## High Findings

### HIGH-01 — API keys embedded in URLs (leak via logs/proxies/history)

**Impact:** API keys in paths are likely to leak via browser history, reverse proxy logs, analytics, referrers, and copy/paste. They are also exposed to the frontend UI (and user clipboard).

**Evidence**
- Gateway routes include `apikey` in the path:
  - [/v1/{server_id}/{apikey}/sse](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L823-L897)
  - [/v1/{server_id}/{apikey}/messages](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L899-L944)
  - [/v1/{server_id}/{apikey}/mcp](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L965-L1023)
- URLs returned by the API include the key:
  - [create_server response URL](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L403-L416)
  - [list_servers response URL](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L419-L451)

**Recommendations**
- Move the API key to an `Authorization: Bearer …` header (or `X-API-Key`) and remove it from URLs.
- If backward compatibility is needed, support both styles temporarily and mark URL keys as deprecated.

---

### HIGH-02 — Request/response bodies logged and stored without redaction

**Impact:** Sensitive data (tokens, credentials, PII, API responses) can be persisted in SQLite logs and displayed in the UI.

**Evidence**
- `LoggedTransport` captures and forwards full request/response bodies to a logger callback: [openapi.py](file:///c:/Users/matias.fernando/Documents/case/app/openapi.py#L17-L63)
- Logs are stored in DB including `request_body` and `response_body`: [_make_log_func](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L61-L79) and [LogDB](file:///c:/Users/matias.fernando/Documents/case/app/cloud_models.py#L36-L48)
- Frontend exposes “Requisição e resposta completas”: [Dashboard.svelte](file:///c:/Users/matias.fernando/Documents/case/rest2mcp/src/Dashboard.svelte#L809-L846)

**Recommendations**
- Implement structured redaction (Authorization headers, cookies, `password`, `token`, `secret`, `apikey`, etc.).
- Make body logging opt-in and default to metadata-only (status, latency, endpoint/tool name).
- Add retention controls and consider encryption-at-rest if logs must include sensitive content.

---

### HIGH-03 — CORS allows any origin + credentials

**Impact:** Enables cross-origin authenticated requests in some deployments and violates browser expectations; it increases the blast radius of any XSS or origin confusion.

**Evidence**
- CORS is configured with wildcard origins and `allow_credentials=True`: [cloud.py](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L264-L270)

**Recommendations**
- Restrict `allow_origins` to known frontend domains.
- If you truly need wildcard origins, set `allow_credentials=False` and redesign auth accordingly.

---

### HIGH-04 — SSRF risk by fetching user-supplied OpenAPI spec URLs

**Impact:** An attacker can coerce the server to make HTTP requests to internal services (metadata endpoints, private networks), potentially leaking data or pivoting.

**Evidence**
- The API fetches a user-supplied `spec_url`: [create_server](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L341-L356)

**Recommendations**
- Restrict allowed URL schemes to `https` (and `http` only for explicit dev mode).
- Block private IP ranges, localhost, and link-local addresses; resolve DNS and re-check the resolved IP.
- Consider maintaining an allowlist of domains or require proof-of-ownership for private specs.

## Medium Findings

### MED-01 — API keys stored in plaintext in database

**Impact:** If the DB is leaked, all gateways can be accessed until keys are rotated.

**Evidence**
- API key stored as plaintext: [ServerDB.apikey](file:///c:/Users/matias.fernando/Documents/case/app/cloud_models.py#L15-L33)
- Validation compares plaintext key: [_validate_server](file:///c:/Users/matias.fernando/Documents/case/app/cloud.py#L99-L110)

**Recommendations**
- Store a salted hash of API keys and compare using constant-time comparison.
- Provide a one-time display of the raw key at creation time and require rotation if lost.

---

### MED-02 — Frontend stores access tokens in localStorage

**Impact:** Any XSS yields immediate account takeover because bearer tokens are readable by JavaScript.

**Evidence**
- Token stored in localStorage: [Landing.svelte](file:///c:/Users/matias.fernando/Documents/case/rest2mcp/src/Landing.svelte#L136-L153) and [Dashboard.svelte](file:///c:/Users/matias.fernando/Documents/case/rest2mcp/src/Dashboard.svelte#L25-L28)

**Recommendations**
- Prefer HttpOnly, Secure cookies for session tokens (requires server-side session exchange), or at minimum use in-memory/sessionStorage and short-lived tokens.
- Deploy a strong Content Security Policy and avoid inline scripts/handlers to reduce XSS risk.

## Low Findings

### LOW-01 — Demo APIs include hardcoded “super-secret-key”

**Impact:** Low in production if these examples are not deployed, but they are easy to copy/paste into real deployments.

**Evidence**
- [examples/loja_api.py](file:///c:/Users/matias.fernando/Documents/case/examples/loja_api.py#L113-L115)
- [examples/tarefas_api.py](file:///c:/Users/matias.fernando/Documents/case/examples/tarefas_api.py#L51-L53)

**Recommendations**
- Replace with environment-based config and clearly mark as example-only.

## Suggested Fix Order

1. Rotate and remove committed secrets (.env) and update ignore rules.
2. Fix JWT validation (Supabase token verification) and audit all auth-protected endpoints.
3. Remove/protect `/v1/reset` and ensure webhook verification fails closed.
4. Move API keys out of URLs and implement redacted logging + retention controls.
5. Lock down CORS and add rate limiting for gateway endpoints.

