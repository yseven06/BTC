"""
User database model.

Stores user accounts with support for email/password and Google OAuth
authentication providers, user preferences, and language settings.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class AuthProvider(str, enum.Enum):
    """Supported authentication providers."""
    EMAIL = "email"
    GOOGLE = "google"


class Language(str, enum.Enum):
    """Supported application languages."""
    TR = "tr"
    EN = "en"


class UserRole(str, enum.Enum):
    """
    Granular admin role, layered on top of the legacy `is_admin` flag.

    `is_admin` stays in sync (True for ADMIN and SUPER_ADMIN) so existing
    gating/dependency code that reads `is_admin` keeps working unchanged.
    `role` is what new admin-panel permission checks should use when an
    action needs to be restricted to the founder tier (e.g. granting admin
    rights, deleting users, role changes).
    """
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class User(Base):
    """
    User account model.

    Attributes:
        id: Unique UUID primary key.
        email: Unique email address used for login.
        password_hash: Bcrypt-hashed password (nullable for OAuth users).
        full_name: Display name.
        avatar_url: URL to the user's profile picture.
        provider: Authentication provider (email or google).
        preferences: JSON blob for user-specific settings.
        language: Preferred UI language.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=True)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    provider = Column(
        Enum(AuthProvider, name="auth_provider", create_constraint=True),
        nullable=False,
        default=AuthProvider.EMAIL,
    )
    preferences = Column(JSON, nullable=True, default=dict)
    language = Column(
        Enum(Language, name="language", create_constraint=True),
        nullable=False,
        default=Language.EN,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    role = Column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, provider={self.provider})>"
