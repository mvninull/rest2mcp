# ─── Engine multi-servidor descontinuado ──────────────────────────────
# Cada servidor expõe o seu próprio par search/run. O engine central
# foi removido — as LLMs ligam-se diretamente ao per-server que precisam.
# Para referência, o código anterior está preservado em git history.

from fastapi import APIRouter

router = APIRouter(prefix="/v1/engine", tags=["engine"])
