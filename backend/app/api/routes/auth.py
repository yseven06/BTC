"""
Authentication API routes.

Handles user registration, login (email + Google), token refresh,
and profile retrieval.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.google_oauth import GoogleOAuthError, verify_google_token
from app.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from app.auth.password import hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models.user import AuthProvider, Language, User
from app.schemas.user import (
    GoogleLoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _create_token_response(user: User) -> TokenResponse:
    """Build a JWT token pair for the given user."""
    token_data = {"sub": str(user.id), "email": user.email}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Register a new user with email and password.

    Returns a JWT token pair on successful registration.
    """
    # Check if the email already exists
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create the user
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        provider=AuthProvider.EMAIL,
        language=Language(payload.language),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("New user registered: %s", user.email)
    return _create_token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate a user with email and password.

    Returns a JWT token pair on success.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    logger.info("User logged in: %s", user.email)
    return _create_token_response(user)


@router.post(
    "/google-login",
    response_model=TokenResponse,
    summary="Login or register with Google",
)
async def google_login(
    payload: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate or register a user via Google OAuth2.

    If the email is not yet registered, a new account is created automatically.
    If an email-registered account exists, it is linked to Google.
    """
    try:
        google_data = await verify_google_token(payload.token)
    except GoogleOAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
        )

    email = google_data["email"]
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Create a new user from Google data
        user = User(
            email=email,
            full_name=google_data.get("full_name"),
            avatar_url=google_data.get("avatar_url"),
            provider=AuthProvider.GOOGLE,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("New Google user registered: %s", email)
    else:
        # Update avatar if not set
        if not user.avatar_url and google_data.get("avatar_url"):
            user.avatar_url = google_data["avatar_url"]
        if user.provider == AuthProvider.EMAIL:
            user.provider = AuthProvider.GOOGLE
        await db.flush()
        logger.info("Google user logged in: %s", email)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return _create_token_response(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new token pair.
    """
    token_payload = verify_token(payload.refresh_token, expected_type="refresh")
    if token_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user_id_str = token_payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload.",
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    return _create_token_response(user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Return the profile of the currently authenticated user.
    """
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update the authenticated user's profile fields.

    Only provided (non-None) fields are updated.
    """
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "language" and value is not None:
            value = Language(value)
        setattr(current_user, field, value)

    await db.flush()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


from fastapi import File, UploadFile
import uuid
import os

@router.post(
    "/upload-avatar",
    summary="Upload profile avatar image",
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload user profile picture and return the public URL."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP."
        )

    upload_dir = os.path.join("static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save image: {str(e)}"
        )

    avatar_url = f"http://localhost:8000/static/uploads/{filename}"
    return {"avatar_url": avatar_url}


from pydantic import BaseModel, Field


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


@router.post(
    "/change-password",
    summary="Change the current user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify current password, then store the new one."""
    if current_user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu hesap şifre tabanlı değil (OAuth ile giriş yapılmış).",
        )
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mevcut şifre hatalı.",
        )
    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"status": "ok", "message": "Şifre güncellendi."}
