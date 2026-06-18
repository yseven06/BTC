"""
Application configuration module.

Reads all settings from environment variables using pydantic-settings.
Provides a singleton settings instance used across the application.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
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

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

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
