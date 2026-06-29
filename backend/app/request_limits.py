"""
Request body size limit middleware.

Rejects requests whose declared Content-Length exceeds the cap (first-line DoS
defense). The cap covers the 2 MB avatar upload plus headroom; JSON endpoints are
far smaller. Chunked requests without Content-Length still pass here, but the
avatar handler independently caps what it reads.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 3 * 1024 * 1024  # 3 MB


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "İstek gövdesi çok büyük."},
                    )
            except ValueError:
                pass
        return await call_next(request)
