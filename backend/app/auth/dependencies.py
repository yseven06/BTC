"""
FastAPI authentication dependencies.

Provides injectable dependencies for route-level authentication:
- get_current_user: Requires a valid JWT access token.
- get_optional_user: Returns the user if authenticated, None otherwise.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import verify_token
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

# HTTPBearer extracts the token from the Authorization header.
# auto_error=True makes it raise 403 when the header is missing.
_security = HTTPBearer(auto_error=True)
_security_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that extracts and validates the JWT from the Authorization
    header, then loads the corresponding User from the database.

    Args:
        credentials: Bearer token from the request header.
        db: Database session (injected).

    Returns:
        The authenticated User ORM instance.

    Raises:
        HTTPException 401: If the token is invalid, expired, or the user
            does not exist or is deactivated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = verify_token(token, expected_type="access")
    if payload is None:
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = UUID(user_id_str)
    except (ValueError, AttributeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependency that optionally authenticates the user.

    If a valid Bearer token is present, returns the User. If no token
    is provided or the token is invalid, returns None without raising.

    Args:
        credentials: Optional bearer token from the request header.
        db: Database session (injected).

    Returns:
        The authenticated User, or None if not authenticated.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = verify_token(token, expected_type="access")
    if payload is None:
        return None

    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None

    try:
        user_id = UUID(user_id_str)
    except (ValueError, AttributeError):
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user
