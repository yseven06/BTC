"""
Rate limiting (slowapi).

Applied ONLY to selected PUBLIC endpoints (auth + checkout) via per-route
decorators. Admin / internal endpoints, the signal/price APIs, and the TM v2
data-collection / scheduler path are deliberately NOT rate limited. The
/health endpoint and the signature-verified Stripe webhook are also left out.

Design:
- Key = the real client IP. Behind a reverse proxy (Railway) `request.client.host`
  is the proxy IP, so we read the left-most `X-Forwarded-For` entry (the original
  client) and fall back to the peer address when the header is absent. This works
  regardless of uvicorn's `--proxy-headers` configuration.
- Limits are env-driven (`config.RATE_LIMIT_*`), so production and development can
  be tuned independently without code changes.
- Storage is in-memory, which is consistent because the backend runs single-replica
  with `--workers 1` (same constraint as the in-process scheduler). If ever scaled
  horizontally, point slowapi at Redis (UPSTASH_REDIS_URL is available).
- A no-op when `RATE_LIMIT_ENABLED` is false (`limiter.enabled=False`), so dev and
  tests can disable it entirely.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded  # re-exported for app wiring
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

__all__ = [
    "limiter",
    "rate_limit_exceeded_handler",
    "RateLimitExceeded",
    "LOGIN_LIMIT",
    "REGISTER_LIMIT",
    "REFRESH_LIMIT",
    "CHECKOUT_LIMIT",
]


def client_ip_key(request: Request) -> str:
    """Rate-limit / challenge key = the real client IP.

    We deliberately do NOT trust the raw left-most ``X-Forwarded-For`` value — it
    is fully client-controlled, so an attacker could forge it to dodge per-IP
    limits (and the adaptive challenge). Instead we read the proxy-validated peer
    via ``get_remote_address``. In production uvicorn runs with
    ``--proxy-headers --forwarded-allow-ips`` so ``request.client.host`` is the
    real client behind Railway/Cloudflare; in dev it is the direct peer.
    """
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_ip_key,
    enabled=settings.RATE_LIMIT_ENABLED,
    default_limits=[],       # no global limit — only decorated routes are limited
    # NOTE: headers_enabled is left OFF. With it on, slowapi injects rate-limit
    # headers into the endpoint's return value and REQUIRES that value to be a
    # starlette Response — but our routes return pydantic models (TokenResponse,
    # CheckoutResponse), which would crash. We add Retry-After in the 429 handler.
)

# Env-driven limit strings (read once at import; @lru_cache settings → a restart
# is needed to change them, consistent with the rest of the config).
LOGIN_LIMIT = settings.RATE_LIMIT_LOGIN
REGISTER_LIMIT = settings.RATE_LIMIT_REGISTER
REFRESH_LIMIT = settings.RATE_LIMIT_REFRESH
CHECKOUT_LIMIT = settings.RATE_LIMIT_CHECKOUT


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a clean HTTP 429 JSON body (+ best-effort Retry-After header)."""
    # Best-effort window (seconds) for the standard Retry-After header.
    retry_after = None
    try:
        retry_after = exc.limit.limit.get_expiry()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - header is a nicety, never fatal
        retry_after = None

    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return JSONResponse(
        status_code=429,
        headers=headers,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Çok fazla istek gönderildi. Lütfen biraz bekleyip tekrar deneyin.",
            "limit": getattr(exc, "detail", None),
            "retry_after_seconds": retry_after,
        },
    )
