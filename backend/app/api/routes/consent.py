"""
Consent API.

Cookie-consent sync for LOGGED-IN users (anonymous cookie consent stays
client-side — compliant and avoids unauthenticated DB writes). Writes to the
single append-only ConsentLog and mirrors the current state on the user row.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.consent_log import ConsentLog
from app.models.user import User
from app.schemas.user import ConsentAcceptance
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


_RECONSENT_TYPES = ("tos", "privacy", "risk")


@router.get("/status", summary="Latest accepted version per consent type (logged-in)")
async def consent_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Most recent accepted document_version per consent type, so the client can
    decide via semver (MAJOR/MINOR/PATCH) whether a re-consent prompt is needed.
    Defensive: if the consent table isn't migrated yet, returns all-null.
    """
    result: dict = {t: None for t in _RECONSENT_TYPES}
    try:
        rows = (
            await db.execute(
                select(ConsentLog.consent_type, ConsentLog.document_version)
                .where(
                    ConsentLog.user_id == current_user.id,
                    ConsentLog.consent_type.in_(_RECONSENT_TYPES),
                    ConsentLog.action.in_(("accepted", "granted")),
                )
                .order_by(ConsentLog.created_at.desc())
            )
        ).all()
        for ct, ver in rows:
            if result.get(ct) is None:
                result[ct] = ver
    except Exception as exc:  # table missing pre-migration → treat as no consent
        logger.warning("consent_status sorgusu başarısız (0001 migration?): %s", exc)
    return result


class ReconsentIn(BaseModel):
    consents: List[ConsentAcceptance]


@router.post("/reconsent", summary="Re-accept updated legal documents (logged-in)")
async def reconsent(
    payload: ReconsentIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    for c in payload.consents:
        await record_consent(
            db,
            consent_type=c.consent_type,
            action="accepted",
            source="re_consent",
            user_id=current_user.id,
            document_slug=c.slug,
            document_version=c.version,
            document_hash=c.hash or None,
            locale="tr",
            request=request,
            checkbox_states={"checked": True},
        )
        if c.consent_type == "tos":
            current_user.terms_accepted_at = now
            current_user.legal_version = c.version
        elif c.consent_type == "privacy":
            current_user.privacy_acked_at = now
        elif c.consent_type == "risk":
            current_user.risk_acked_at = now
    db.add(current_user)
    return {"status": "recorded"}
