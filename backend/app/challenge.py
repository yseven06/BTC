"""
Adaptive bot-challenge layer (Cloudflare Turnstile) — SINGLE source of truth.

Any endpoint opts in with one line: ``Depends(require_challenge("action"))``.
The adaptive band, bypass rules, Turnstile verification and clearance cookie ALL
live here, so future surfaces (API Key, Auto Trade, Copy Trade, Exchange) reuse
the exact same logic — no copy-paste.

Design (see docs/CAPTCHA-STRATEGY.md):
- **Env-gated / no-op:** with ``TURNSTILE_SECRET_KEY`` empty (or ``CHALLENGE_ENABLED``
  false) the dependency is a pass-through — dev/CI has zero friction.
- **Adaptive, one counter, three bands:** ``< SOFT`` allow · ``SOFT..HARD`` challenge ·
  ``>= HARD`` is the *existing slowapi 429* (untouched here). Normal users never see it.
- **Bypass (does NOT skip the hard rate limit):** (A) admin JWT on authenticated
  endpoints; (B) constant-time internal secret header for automation/CI.
- **Clearance:** a one-shot Turnstile token is verified once via siteverify, then a
  short-lived, IP-bound, HMAC-signed ``chal_ok`` cookie prevents re-challenging.
- **Independent** of rate limiting and the auth-failure lockout (defense in depth).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, Response

from app.auth.dependencies import get_optional_user
from app.config import get_settings
from app.models.user import User
from app.rate_limit import client_ip_key

settings = get_settings()
logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_WINDOW = 60.0  # seconds; matches the "/minute" thresholds
_CLEARANCE_COOKIE = "chal_ok"


def _enabled() -> bool:
    """Challenge active only when explicitly enabled AND a secret is configured."""
    return bool(settings.CHALLENGE_ENABLED) and bool(settings.TURNSTILE_SECRET_KEY)


# ─── in-memory windowed counters (single-replica; ADR §14 → Redis when scaling) ──

class _WindowCounter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def _prune(self, key: str, now: float) -> list[float]:
        arr = [t for t in self._hits.get(key, []) if now - t < _WINDOW]
        self._hits[key] = arr
        return arr

    def incr(self, key: str) -> int:
        now = time.time()
        arr = self._prune(key, now)
        arr.append(now)
        return len(arr)

    def count(self, key: str) -> int:
        return len(self._prune(key, time.time()))

    def clear(self, key: str) -> None:
        self._hits.pop(key, None)


_attempts = _WindowCounter()   # soft band (per client IP)
_auth_fail = _WindowCounter()  # A3 repeated auth failures (per client IP)


def _soft_threshold() -> int:
    try:
        return int(str(settings.CHALLENGE_LOGIN_SOFT).split("/")[0])
    except Exception:
        return 6


# ─── auth-failure signal (A3) — called by the login routes ───────────────────

def record_auth_failure(request: Request) -> None:
    """Login/google-login call this on a failed attempt (bad creds)."""
    _auth_fail.incr(client_ip_key(request))


def clear_auth_failures(request: Request) -> None:
    """Login/google-login call this on success to reset the counter."""
    _auth_fail.clear(client_ip_key(request))


# ─── clearance cookie (HMAC, IP-bound, TTL; stateless) ───────────────────────

def _sign_clearance(ip: str, exp: int) -> str:
    sig = hmac.new(settings.JWT_SECRET.encode(), f"{ip}:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _valid_clearance(cookie: str, ip: str) -> bool:
    try:
        exp_s, sig = cookie.split(".", 1)
        exp = int(exp_s)
        if exp < int(time.time()):
            return False
        expected = hmac.new(settings.JWT_SECRET.encode(), f"{ip}:{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _set_clearance(response: Response, ip: str) -> None:
    ttl = int(settings.CHALLENGE_CLEARANCE_TTL)
    exp = int(time.time()) + ttl
    response.set_cookie(
        _CLEARANCE_COOKIE, _sign_clearance(ip, exp),
        max_age=ttl, httponly=True, samesite="lax", secure=not settings.DEBUG,
    )


# ─── Turnstile siteverify (one-shot token) ───────────────────────────────────

async def _siteverify(token: str, ip: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(_SITEVERIFY_URL, data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": ip,
            })
            return bool(r.json().get("success"))
    except Exception as exc:
        logger.warning("[challenge] siteverify error: %s", exc)
        return False


# ─── bypass (§8) — never skips the hard rate limit ───────────────────────────

def _internal_bypass(request: Request) -> bool:
    """(B) Constant-time internal secret header. Env-gated: empty secret = off."""
    secret = settings.CHALLENGE_BYPASS_SECRET
    if not secret:
        return False
    provided = request.headers.get("x-internal-challenge-bypass", "")
    ok = bool(provided) and hmac.compare_digest(provided, secret)
    if ok:
        logger.warning("[challenge] internal-secret bypass on %s from %s",
                       request.url.path, client_ip_key(request))
    return ok


# ─── the reusable dependency ─────────────────────────────────────────────────

def require_challenge(action: str, *, allow_role_bypass: bool = False):
    """Dependency factory. Attach to any endpoint to gate it behind the adaptive
    challenge. `allow_role_bypass` enables admin-JWT bypass (authenticated flows
    like checkout; NOT login/register which are pre-auth)."""

    async def _dependency(
        request: Request,
        response: Response,
        user: Optional[User] = Depends(get_optional_user),
    ) -> None:
        if not _enabled():
            return  # no-op (dev/CI)

        ip = client_ip_key(request)

        # Bypass (B): trusted internal automation (all endpoints).
        if _internal_bypass(request):
            return
        # Bypass (A): admin role on authenticated endpoints only.
        if allow_role_bypass and user is not None and getattr(user, "is_admin", False):
            logger.info("[challenge] admin role bypass on %s", request.url.path)
            return

        # Adaptive band: this attempt + recent auth failures.
        attempts = _attempts.incr(ip)
        auth_fails = _auth_fail.count(ip)
        in_band = attempts > _soft_threshold() or auth_fails >= int(settings.CHALLENGE_AUTH_FAIL_THRESHOLD)
        if not in_band:
            return  # happy path — no token required

        # In challenge band: accept a valid clearance cookie first.
        if _valid_clearance(request.cookies.get(_CLEARANCE_COOKIE, ""), ip):
            return

        # Otherwise verify a fresh Turnstile token from the header (one round-trip).
        token = request.headers.get("cf-turnstile-response", "")
        if token and await _siteverify(token, ip):
            _set_clearance(response, ip)
            return

        # No clearance, no valid token → ask the client to solve the widget.
        raise HTTPException(
            status_code=428,
            detail={
                "error": "challenge_required",
                "challenge": "turnstile",
                "sitekey": settings.TURNSTILE_SITE_KEY or "",
                "action": action,
            },
        )

    return _dependency
