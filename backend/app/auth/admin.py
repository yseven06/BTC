"""
Admin authentication dependency.

Use as a FastAPI Depends() to restrict endpoints to admin users only.
"""

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Allow only admin users. Raises 403 for non-admins."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin yetkisi gereklidir.",
        )
    return current_user
