"""
Admin authentication dependencies.

`require_admin` gates anything an ADMIN or SUPER_ADMIN may do (the bulk of
the admin panel: user tier/active toggles, signal moderation, asset
management). `require_super_admin` gates founder-only actions — granting or
revoking admin rights, deleting users — so a regular admin can't escalate
themselves or remove the only super admin.
"""

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User, UserRole


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Allow ADMIN or SUPER_ADMIN. Raises 403 otherwise."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin yetkisi gereklidir.",
        )
    return current_user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Allow only SUPER_ADMIN. Raises 403 otherwise."""
    if getattr(current_user, "role", None) != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için kurucu (super admin) yetkisi gereklidir.",
        )
    return current_user
