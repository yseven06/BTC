"""
TradeMinds AI – Notification orchestration.

Fetches the singleton NotificationSettings and dispatches signal
notifications via the configured channels (currently Telegram).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.database import async_session_factory
from app.models.notification import NotificationSettings, SETTINGS_SINGLETON_ID
from app.notifications.telegram import send_telegram_message, format_signal_message

logger = logging.getLogger(__name__)


async def get_or_create_settings(db) -> NotificationSettings:
    """Fetch the singleton settings row, creating it if missing."""
    res = await db.execute(
        select(NotificationSettings).where(NotificationSettings.id == SETTINGS_SINGLETON_ID)
    )
    settings = res.scalar_one_or_none()
    if settings is None:
        settings = NotificationSettings(id=SETTINGS_SINGLETON_ID)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def notify_signal(decision: Dict[str, Any], symbol: str, timeframe: str) -> None:
    """
    Send a Telegram notification for a freshly generated signal,
    respecting the configured filters (enabled, min confidence, HOLD).
    Safe to call fire-and-forget; never raises.
    """
    try:
        async with async_session_factory() as db:
            settings = await get_or_create_settings(db)

            if not settings.telegram_enabled:
                return
            if not settings.telegram_bot_token or not settings.telegram_chat_id:
                return

            signal_type = decision.get("signal_type", "HOLD")
            confidence = float(decision.get("confidence_score", 0.0))

            if signal_type == "HOLD" and not settings.notify_hold:
                return
            if confidence < settings.min_confidence:
                return

            text = format_signal_message(
                symbol=symbol,
                signal_type=signal_type,
                confidence=confidence,
                direction=decision.get("direction", "neutral"),
                entry_low=decision.get("entry_zone_low"),
                entry_high=decision.get("entry_zone_high"),
                stop_loss=decision.get("stop_loss"),
                tp1=decision.get("tp1"),
                tp2=decision.get("tp2"),
                timeframe=timeframe,
                risk_level=decision.get("risk_level", "medium"),
            )
            result = await send_telegram_message(
                settings.telegram_bot_token, settings.telegram_chat_id, text
            )
            if result["ok"]:
                logger.info("[Notify] Telegram sent for %s (%s)", symbol, signal_type)
            else:
                logger.warning("[Notify] Telegram failed for %s: %s", symbol, result["error"])
    except Exception as exc:
        logger.error("[Notify] notify_signal error: %s", exc)
