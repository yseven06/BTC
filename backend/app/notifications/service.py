"""
TradeMinds AI – Notification orchestration.

Per-user notification dispatch: each user has their own NotificationSettings and
their own Telegram destination. A new-signal notification fans out to every user
who has Telegram enabled, applying that user's own filters and tier gate, so one
user's configuration never affects another.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy import select

from app.backtesting.lifecycle import status_tr
from app.database import async_session_factory
from app.models.notification import NotificationSettings
from app.models.user import User
from app.notifications.telegram import (
    send_telegram_message, format_signal_message, format_lifecycle_message,
)
from app.subscriptions.gating import TIER_LIMITS, _effective_tier, _fetch_subscription

logger = logging.getLogger(__name__)

# P1.2: only transitions INTO these states warrant a proactive push (conservative
# set; WEAKENING is excluded — noisiest — pending real-usage feedback).
LIFECYCLE_ALERT_STATES = ("approaching_tp", "invalidating")


async def get_or_create_settings(db, user_id) -> NotificationSettings:
    """Fetch the given user's settings row, creating an empty one if missing."""
    res = await db.execute(
        select(NotificationSettings).where(NotificationSettings.user_id == user_id)
    )
    settings = res.scalar_one_or_none()
    if settings is None:
        settings = NotificationSettings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def _user_can_use_telegram(db, user: User) -> bool:
    """Tier gate: only Pro+ (or admin) may receive Telegram. Re-checked here so a
    downgraded user stops receiving even if telegram_enabled is still set."""
    if getattr(user, "is_admin", False):
        return True
    sub = await _fetch_subscription(db, user.id)
    return TIER_LIMITS[_effective_tier(sub)].can_use_telegram


async def notify_signal(decision: Dict[str, Any], symbol: str, timeframe: str) -> None:
    """
    Fan out a freshly generated signal to every user who has Telegram enabled,
    respecting each user's own min-confidence, HOLD preference and tier gate.
    One user's settings never affect another. Fire-and-forget; never raises.
    """
    try:
        signal_type = decision.get("signal_type", "HOLD")
        confidence = float(decision.get("confidence_score", 0.0))
        text = None  # built once, only when a recipient actually qualifies

        async with async_session_factory() as db:
            res = await db.execute(
                select(NotificationSettings, User)
                .join(User, NotificationSettings.user_id == User.id)
                .where(
                    NotificationSettings.telegram_enabled.is_(True),
                    NotificationSettings.telegram_bot_token.isnot(None),
                    NotificationSettings.telegram_chat_id.isnot(None),
                )
            )
            rows = res.all()
            if not rows:
                return

            for settings, user in rows:
                # Per-user filters.
                if signal_type == "HOLD" and not settings.notify_hold:
                    continue
                if confidence < settings.min_confidence:
                    continue
                if not await _user_can_use_telegram(db, user):
                    continue

                if text is None:
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
                    logger.info("[Notify] Telegram sent to user %s for %s (%s)",
                                settings.user_id, symbol, signal_type)
                else:
                    logger.warning("[Notify] Telegram failed for user %s on %s: %s",
                                   settings.user_id, symbol, result["error"])
    except Exception as exc:
        logger.error("[Notify] notify_signal error: %s", exc)


async def notify_lifecycle(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    old_status: str,
    new_status: str,
    reason: str,
    price: float,
) -> None:
    """Fan out a PROACTIVE lifecycle-transition alert to every user who OPTED IN
    (notify_lifecycle) and has Telegram enabled + Pro+ tier. Mirrors notify_signal's
    per-user isolation. Fire-and-forget; never raises.

    Detection is NOT changed here — this only DELIVERS an alert for an
    already-detected transition (the tracker calls it once per real transition into
    one of LIFECYCLE_ALERT_STATES). The new_status guard is a second safety net so a
    non-alert state can never produce a push even if called more broadly.
    """
    try:
        if new_status not in LIFECYCLE_ALERT_STATES:
            return
        text = None  # built once, only when a recipient actually qualifies

        async with async_session_factory() as db:
            res = await db.execute(
                select(NotificationSettings, User)
                .join(User, NotificationSettings.user_id == User.id)
                .where(
                    NotificationSettings.telegram_enabled.is_(True),
                    NotificationSettings.notify_lifecycle.is_(True),   # opt-in (default OFF)
                    NotificationSettings.telegram_bot_token.isnot(None),
                    NotificationSettings.telegram_chat_id.isnot(None),
                )
            )
            rows = res.all()
            if not rows:
                return

            for settings, user in rows:
                if not await _user_can_use_telegram(db, user):   # same Pro+ tier gate
                    continue

                if text is None:
                    text = format_lifecycle_message(
                        symbol=symbol, timeframe=timeframe, direction=direction,
                        new_status=new_status, new_status_tr=status_tr(new_status),
                        old_status_tr=status_tr(old_status), reason=reason, price=price,
                    )

                result = await send_telegram_message(
                    settings.telegram_bot_token, settings.telegram_chat_id, text
                )
                if result["ok"]:
                    logger.info("[Notify] Lifecycle alert sent to user %s for %s (%s->%s)",
                                settings.user_id, symbol, old_status, new_status)
                else:
                    logger.warning("[Notify] Lifecycle alert failed for user %s on %s: %s",
                                   settings.user_id, symbol, result["error"])
    except Exception as exc:
        logger.error("[Notify] notify_lifecycle error: %s", exc)
