"""
JWT token creation and verification.

Handles access token and refresh token lifecycle using python-jose
with HMAC-SHA256 signing.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Payload claims (must include 'sub' with user ID).
        expires_delta: Custom expiration duration. Defaults to
            ACCESS_TOKEN_EXPIRE_MINUTES from settings.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    })
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token.

    Refresh tokens have a longer lifetime and are used to obtain
    new access tokens without re-authenticating.

    Args:
        data: Payload claims (must include 'sub' with user ID).
        expires_delta: Custom expiration duration. Defaults to
            REFRESH_TOKEN_EXPIRE_DAYS from settings.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    })
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_token(
    token: str,
    expected_type: str = "access",
) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT string to verify.
        expected_type: Expected token type ('access' or 'refresh').

    Returns:
        Decoded payload dict if valid and type matches, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_type = payload.get("type")
        if token_type != expected_type:
            return None
        sub = payload.get("sub")
        if sub is None:
            return None
        return payload
    except JWTError:
        return None
