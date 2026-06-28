"""
TradeMinds AI Backend Application Entrypoint.

Sets up FastAPI instance, CORS headers, global exception handlers,
and wires in all REST api routes.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.database import init_db, close_db
from app.services.scheduler import start_scheduler, stop_scheduler

settings = get_settings()

# Configure the root logger from settings (LOG_LEVEL env; default INFO). Lets
# production lower verbosity (e.g. WARNING) without code changes.
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- Error monitoring (Sentry) — env-gated; a no-op when SENTRY_DSN is unset,
# so local/dev and the TM v2 data-collection process are unaffected. Only sends
# to Sentry once a DSN is provided via env (production). PII off by default. ---
if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    logger.info("Sentry monitoring enabled (environment=%s).", settings.ENVIRONMENT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    logger.info("Starting TradeMinds AI Backend...")
    if settings.DEBUG:
        try:
            await init_db()
            logger.info("Database tables initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")

    # Start background signal scheduler
    try:
        start_scheduler()
        logger.info("Background scheduler started.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {str(e)}")

    yield

    logger.info("Shutting down TradeMinds AI Backend...")
    stop_scheduler()
    await close_db()
    logger.info("Database connection closed.")


app = FastAPI(
    title="TradeMinds AI API",
    description="Advanced AI-Powered multi-engine trading intelligence and signal generation platform.",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Configure CORS using the origins list from settings.
# In development the default is ["http://localhost:3000", "http://localhost:5173"].
# Override via CORS_ORIGINS env var for production (comma-separated or JSON list).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router, prefix="/api/v1")

from fastapi.staticfiles import StaticFiles
import os

# Ensure static/uploads directory exists
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for container / server validation."""
    return {
        "status": "healthy",
        "service": "trademinds-backend",
        "debug_mode": settings.DEBUG,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catches all unhandled exceptions to return a clean JSON error response."""
    logger.error(f"Unhandled exception occurred on path {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred. Please try again later.",
            "error_type": type(exc).__name__,
        },
    )
