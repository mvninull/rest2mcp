import threading
import time
from typing import Callable

from fastapi import HTTPException, Request

try:
    from .config import RATE_LIMIT_TRUST_FORWARDED_HEADERS
except ImportError:
    from config import RATE_LIMIT_TRUST_FORWARDED_HEADERS


def get_client_ip(request: Request) -> str:
    if RATE_LIMIT_TRUST_FORWARDED_HEADERS:
        forwarded = request.headers.get("sb-forwarded-for") or request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class TokenBucketLimiter:
    """Token bucket por chave (ex.: IP + endpoint), no modelo do Supabase.

    Cada bucket tem capacidade máxima (rajada). Quando está cheio, tolera um pico de
    até `capacity` requests; depois os tokens são recarregados a `refill_per_sec`.
    Quando o bucket esvazia, as requests são rejeitadas até os tokens reencherem.
    """

    def __init__(
        self,
        name: str,
        capacity: int,
        refill_per_sec: float,
        max_keys: int = 100_000,
        stale_after: float = 3600.0,
    ):
        self.name = name
        self.capacity = float(capacity)
        self.refill_per_sec = refill_per_sec
        self.max_keys = max_keys
        self.stale_after = stale_after
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Consome um token para `key`. Retorna (permitido, retry_after_seg)."""
        with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_keys:
                    self._prune(now)
                bucket = [self.capacity, now]
                self._buckets[key] = bucket

            tokens, last_refill = bucket
            elapsed = now - last_refill
            tokens = min(self.capacity, tokens + elapsed * self.refill_per_sec)
            bucket[1] = now

            if tokens < 1:
                bucket[0] = tokens
                if self.refill_per_sec > 0:
                    retry_after = (1 - tokens) / self.refill_per_sec
                else:
                    retry_after = float("inf")
                return False, max(retry_after, 0.0)

            bucket[0] = tokens - 1
            return True, 0.0

    def _prune(self, now: float) -> None:
        cutoff = now - self.stale_after
        stale = [k for k, (_, last_refill) in self._buckets.items() if last_refill < cutoff]
        for k in stale:
            self._buckets.pop(k, None)


def rate_limit_dependency(limiter: TokenBucketLimiter) -> Callable:
    """Cria uma dependency FastAPI que limita por IP para um determinado limiter."""

    async def check(request: Request) -> None:
        key = f"{limiter.name}:{get_client_ip(request)}"
        allowed, retry_after = limiter.allow(key)
        if not allowed:
            headers = {}
            if retry_after != float("inf"):
                headers["Retry-After"] = str(int(retry_after) + 1)
            raise HTTPException(status_code=429, detail="Too many requests", headers=headers)

    return check
