"""
Authentication package.

Provides JWT token handling, password hashing, FastAPI dependencies
for protecting routes, and Google OAuth2 integration.
"""

from app.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from app.auth.password import hash_password, verify_password
from app.auth.dependencies import get_current_user, get_optional_user

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "hash_password",
    "verify_password",
    "get_current_user",
    "get_optional_user",
]
