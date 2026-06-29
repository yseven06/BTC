"""
Application configuration module.

Reads all settings from environment variables using pydantic-settings.
Provides a singleton settings instance used across the application.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All configuration for database connections, API keys, JWT tokens,
    and external services is centralized here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "TradeMinds AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1"

    # --- Supabase PostgreSQL ---
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trademinds"

    # --- Upstash Redis ---
    UPSTASH_REDIS_URL: str = "redis://localhost:6379"

    # --- JWT Authentication ---
    JWT_SECRET: str = "change-me-in-production-super-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Google OAuth2 ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # --- Binance API ---
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_BASE_URL: str = "https://api.binance.com"

    # --- CoinGecko API ---
    COINGECKO_API_KEY: str = ""
    COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"

    # --- Frontend base URL (for Stripe redirects) ---
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # --- Stripe (optional — leave blank to use mock mode) ---
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # --- FRED (optional — required for US macro indicators) ---
    FRED_API_KEY: str = ""

    # --- Finnhub (optional — company news + earnings calendar for stocks).
    # Free tier: 60 calls/min, get a key at finnhub.io/register. Leave blank
    # to fall back to baseline/synthetic fundamentals. ---
    FINNHUB_API_KEY: str = ""

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Monitoring (Sentry) — error/perf tracking; empty DSN = disabled ---
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # --- Rate limiting (slowapi) — applied ONLY to selected public endpoints
    # (auth + checkout). Format "<count>/<period>" (e.g. "5/minute"). Defaults
    # are lenient (dev); set stricter values per-env in production. Toggle the
    # whole feature with RATE_LIMIT_ENABLED. ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_REGISTER: str = "5/minute"
    RATE_LIMIT_REFRESH: str = "30/minute"
    RATE_LIMIT_CHECKOUT: str = "10/minute"

    # --- Adaptive bot challenge (Cloudflare Turnstile) — env-gated / no-op.
    # With TURNSTILE_SECRET_KEY empty (or CHALLENGE_ENABLED=false) the whole
    # challenge layer is a pass-through (dev/CI = zero friction). Independent of
    # rate limiting + the auth-failure lockout (defense in depth).
    # See docs/CAPTCHA-STRATEGY.md. ---
    CHALLENGE_ENABLED: bool = True
    TURNSTILE_SECRET_KEY: str = ""              # empty = verification skipped (no-op)
    TURNSTILE_SITE_KEY: str = ""                # public site key (sent in 428; also used by frontend)
    CHALLENGE_LOGIN_SOFT: str = "6/minute"      # soft band threshold (< hard RATE_LIMIT_*)
    CHALLENGE_AUTH_FAIL_THRESHOLD: int = 3      # A3: repeated auth failures → challenge
    CHALLENGE_CLEARANCE_TTL: int = 600          # chal_ok clearance cookie lifetime (sec)
    CHALLENGE_BYPASS_SECRET: str = ""           # empty = internal bypass disabled (§8B)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        """Parse CORS origins from comma-separated string or JSON list."""
        if isinstance(v, str):
            if v.startswith("["):
                import json
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        """Fail-fast in production on unsafe defaults — refuse to start rather than
        boot with a guessable JWT secret, DEBUG on, or a localhost DB/CORS."""
        if self.ENVIRONMENT == "production":
            problems = []
            if self.DEBUG:
                problems.append("DEBUG must be false in production")
            if "change-me" in self.JWT_SECRET or len(self.JWT_SECRET) < 32:
                problems.append("JWT_SECRET must be a strong (>=32 char) non-default value")
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                problems.append("DATABASE_URL must point to the production database (not localhost)")
            if any(("localhost" in o or "127.0.0.1" in o) for o in self.CORS_ORIGINS):
                problems.append("CORS_ORIGINS must be the production frontend domain (no localhost)")
            if problems:
                raise RuntimeError(
                    "Unsafe production configuration — refusing to start:\n  - "
                    + "\n  - ".join(problems)
                )
        return self

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if the application is running in development mode."""
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    """
    Get the cached application settings instance.

    Returns a singleton Settings object to avoid re-reading
    environment variables on every access.
    """
    return Settings()
