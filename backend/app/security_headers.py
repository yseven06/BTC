"""
Security headers middleware for the API.

Adds defensive response headers to every backend response. CSP is intentionally
NOT set here — the backend serves JSON (+ static avatar images), so a page-level
Content-Security-Policy belongs on the frontend (Next.js). HSTS is harmless over
plain HTTP (browsers ignore it) and takes effect once served over HTTPS (Railway).
"""

from starlette.middleware.base import BaseHTTPMiddleware

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response
