"""
TradeMinds AI – Notification Settings Routes

Manage Telegram delivery configuration and send a test message.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.notifications.service import get_or_create_settings
from app.notifications.telegram import send_telegram_message
from app.subscriptions.gating import require_feature

logger = logging.getLogger(__name__)
router = APIRouter()


class NotificationSettingsResponse(BaseModel):
    telegram_enabled: bool
    telegram_chat_id: Optional[str] = None
    has_bot_token: bool          # never expose the token itself
    min_confidence: int
    notify_hold: bool


class NotificationSettingsUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    min_confidence: Optional[int] = None
    notify_hold: Optional[bool] = None


def _to_response(s) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        telegram_enabled=s.telegram_enabled,
        telegram_chat_id=s.telegram_chat_id,
        has_bot_token=bool(s.telegram_bot_token),
        min_confidence=s.min_confidence,
        notify_hold=s.notify_hold,
    )


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)) -> NotificationSettingsResponse:
    """Return current notification settings (bot token is masked)."""
    s = await get_or_create_settings(db)
    return _to_response(s)


@router.put("/settings", response_model=NotificationSettingsResponse)
async def update_settings(
    payload: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _gate = Depends(require_feature("can_use_telegram")),
) -> NotificationSettingsResponse:
    """Update notification settings. Only provided fields are changed."""
    s = await get_or_create_settings(db)

    if payload.telegram_enabled is not None:
        s.telegram_enabled = payload.telegram_enabled
    if payload.telegram_bot_token is not None:
        # Empty string clears the token
        s.telegram_bot_token = payload.telegram_bot_token.strip() or None
    if payload.telegram_chat_id is not None:
        s.telegram_chat_id = payload.telegram_chat_id.strip() or None
    if payload.min_confidence is not None:
        s.min_confidence = max(0, min(100, payload.min_confidence))
    if payload.notify_hold is not None:
        s.notify_hold = payload.notify_hold

    await db.commit()
    await db.refresh(s)
    return _to_response(s)


@router.post("/test")
async def send_test(db: AsyncSession = Depends(get_db)) -> dict:
    """Send a test Telegram message using the stored settings."""
    s = await get_or_create_settings(db)
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return {"ok": False, "error": "Bot token ve chat id gerekli."}

    result = await send_telegram_message(
        s.telegram_bot_token,
        s.telegram_chat_id,
        "✅ <b>TradeMinds AI</b>\nTelegram bildirimleri başarıyla bağlandı!",
    )
    return result
