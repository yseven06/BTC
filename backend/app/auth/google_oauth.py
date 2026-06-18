"""
Google OAuth2 authentication flow.

Verifies Google ID tokens and extracts user information for
social login registration and authentication.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Google's token info endpoint for ID token verification
GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthError(Exception):
    """Raised when Google OAuth verification fails."""

    def __init__(self, message: str = "Google authentication failed."):
        self.message = message
        super().__init__(self.message)


async def verify_google_token(id_token: str) -> Dict[str, Any]:
    """
    Verify a Google ID token and extract user information.

    Calls Google's tokeninfo endpoint to validate the token's signature,
    expiration, and audience claim.

    Args:
        id_token: The Google-issued ID token from the client.

    Returns:
        Dictionary containing user info:
        {
            "email": "user@gmail.com",
            "full_name": "John Doe",
            "avatar_url": "https://...",
            "google_id": "1234567890",
            "email_verified": True,
        }

    Raises:
        GoogleOAuthError: If the token is invalid or verification fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Verify the token with Google
            response = await client.get(
                GOOGLE_TOKEN_INFO_URL,
                params={"id_token": id_token},
            )

            if response.status_code != 200:
                logger.warning(
                    "Google token verification failed with status %d: %s",
                    response.status_code,
                    response.text,
                )
                raise GoogleOAuthError("Invalid Google token.")

            token_data = response.json()

            # Verify the audience matches our client ID
            aud = token_data.get("aud")
            if aud != settings.GOOGLE_CLIENT_ID:
                logger.warning(
                    "Google token audience mismatch: expected %s, got %s",
                    settings.GOOGLE_CLIENT_ID,
                    aud,
                )
                raise GoogleOAuthError("Token audience mismatch.")

            # Verify the email is present and verified
            email = token_data.get("email")
            email_verified = token_data.get("email_verified", "false")
            if not email:
                raise GoogleOAuthError("No email found in Google token.")

            if str(email_verified).lower() != "true":
                raise GoogleOAuthError("Google email is not verified.")

            return {
                "email": email,
                "full_name": token_data.get("name", ""),
                "avatar_url": token_data.get("picture", ""),
                "google_id": token_data.get("sub", ""),
                "email_verified": True,
            }

        except httpx.HTTPError as e:
            logger.error("HTTP error during Google token verification: %s", str(e))
            raise GoogleOAuthError(
                "Failed to communicate with Google authentication servers."
            ) from e


async def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Fetch user profile information using a Google access token.

    This is an alternative flow when working with authorization code
    grants rather than ID tokens.

    Args:
        access_token: Google OAuth2 access token.

    Returns:
        Dictionary with user profile fields.

    Raises:
        GoogleOAuthError: If the request fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.warning(
                    "Google userinfo request failed with status %d",
                    response.status_code,
                )
                raise GoogleOAuthError("Failed to fetch Google user info.")

            data = response.json()
            return {
                "email": data.get("email", ""),
                "full_name": data.get("name", ""),
                "avatar_url": data.get("picture", ""),
                "google_id": data.get("sub", ""),
                "email_verified": data.get("email_verified", False),
            }

        except httpx.HTTPError as e:
            logger.error("HTTP error fetching Google user info: %s", str(e))
            raise GoogleOAuthError(
                "Failed to communicate with Google servers."
            ) from e
