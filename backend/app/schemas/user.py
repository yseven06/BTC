"""
User-related Pydantic schemas.

Covers registration, login, profile responses, updates, and JWT tokens.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class ConsentAcceptance(BaseModel):
    """A single accepted legal document, recorded for the consent audit trail."""

    consent_type: str = Field(..., pattern="^(tos|privacy|risk|etk_marketing)$")
    slug: str = Field(..., max_length=100)
    version: str = Field(..., max_length=20)
    hash: str = Field("", max_length=64)


class UserCreate(BaseModel):
    """Schema for user registration via email/password."""

    email: EmailStr = Field(..., description="User's email address.")
    password: str = Field(..., min_length=8, max_length=128, description="User password (min 8 chars).")
    full_name: Optional[str] = Field(None, max_length=255, description="Display name.")
    language: str = Field("en", pattern="^(en|tr)$", description="Preferred language (en or tr).")
    consents: Optional[list[ConsentAcceptance]] = Field(
        None, description="Kayıt sırasında kabul edilen yasal belgeler (audit için)."
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Ensure password has at least one digit and one letter."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter.")
        return v


class UserLogin(BaseModel):
    """Schema for email/password login."""

    email: EmailStr = Field(..., description="User's email address.")
    password: str = Field(..., description="User password.")


class GoogleLoginRequest(BaseModel):
    """Schema for Google OAuth login with an ID token."""

    token: str = Field(..., description="Google OAuth2 ID token.")


class UserResponse(BaseModel):
    """Public user profile response."""

    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str
    language: str
    preferences: Optional[Dict[str, Any]] = None
    is_active: bool
    is_admin: bool = False
    role: str = "user"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user profile fields."""

    full_name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = None
    language: Optional[str] = Field(None, pattern="^(en|tr)$")
    preferences: Optional[Dict[str, Any]] = None


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str = Field(..., description="Short-lived JWT access token.")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token.")
    token_type: str = Field("bearer", description="Token type (always bearer).")
    expires_in: int = Field(..., description="Access token lifetime in seconds.")


class RefreshTokenRequest(BaseModel):
    """Schema for refreshing an access token."""

    refresh_token: str = Field(..., description="The refresh token to exchange.")
