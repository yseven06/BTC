"""
Consent API.

Cookie-consent sync for LOGGED-IN users (anonymous cookie consent stays
client-side — compliant and avoids unauthenticated DB writes). Writes to the
single append-only ConsentLog and mirrors the current state on the user row.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.consent import record_consent

logger = logging.getLogger(__name__)
router = APIRouter()


class CookieConsentIn(BaseModel):
    analytics: bool
    version: int
    locale: Optional[str] = None


@router.post("/cookie", summary="Record cookie consent (logged-in users)")
async def record_cookie_consent(
    payload: CookieConsentIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await record_consent(
        db,
        consent_type="cookie_analytics",
        action="granted" if payload.analytics else "declined",
        source="cookie_banner",
        user_id=current_user.id,
        document_slug="cerez-politikasi",
        document_version=str(payload.version),
        locale=payload.locale,
        request=request,
        checkbox_states={"necessary": True, "analytics": payload.analytics},
    )
    # Mirror current state on the user row (history stays in consent_logs).
    current_user.analytics_consent = payload.analytics
    db.add(current_user)
    return {"status": "recorded"}
