"""
Consent recording service — the single way to write the append-only ConsentLog.

Every consent surface (register, checkout, cookie banner, re-consent, and future
high-risk features like Auto Trade / API key / Copy Trade) calls `record_consent`.
Rows are only ever inserted — never updated or deleted.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent_log import ConsentLog


def client_ip(request: Optional[Request]) -> Optional[str]:
    """Real client IP behind a proxy (left-most X-Forwarded-For, else peer)."""
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


async def record_consent(
    db: AsyncSession,
    *,
    consent_type: str,
    action: str,
    source: str,
    user_id: Optional[Any] = None,
    document_slug: Optional[str] = None,
    document_version: Optional[str] = None,
    document_hash: Optional[str] = None,
    locale: Optional[str] = None,
    request: Optional[Request] = None,
    checkbox_states: Optional[dict] = None,
    details: Optional[dict] = None,
) -> ConsentLog:
    """
    Append one consent event. IP/User-Agent are captured from `request` when
    provided. The caller's transaction (e.g. the get_db dependency) commits.
    """
    entry = ConsentLog(
        user_id=user_id,
        anonymous=user_id is None,
        consent_type=consent_type,
        action=action,
        source=source,
        document_slug=document_slug,
        document_version=document_version,
        document_hash=document_hash,
        locale=locale,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("User-Agent") if request else None),
        checkbox_states=checkbox_states,
        details=details,
    )
    db.add(entry)
    await db.flush()  # assign id; commit is handled by the request session
    return entry
