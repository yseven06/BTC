"""
NotificationSettings database model.

Stores Telegram delivery configuration. Single global row (singleton)
keyed by a fixed UUID so the app can fetch/update it without a user context.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

# Fixed singleton id so there is always at most one settings row.
SETTINGS_SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class NotificationSettings(Base):
    """
    Global notification/delivery settings.

    Attributes:
        telegram_enabled: Master switch for Telegram delivery.
        telegram_bot_token: The user's Telegram bot token (from @BotFather).
        telegram_chat_id: The destination chat/channel id.
        min_confidence: Only notify when signal confidence >= this.
        notify_hold: Whether to also send notifications for HOLD signals.
    """

    __tablename__ = "notification_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=SETTINGS_SINGLETON_ID)
    telegram_enabled = Column(Boolean, nullable=False, default=False)
    telegram_bot_token = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(64), nullable=True)
    min_confidence = Column(Integer, nullable=False, default=70)
    notify_hold = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<NotificationSettings(telegram_enabled={self.telegram_enabled})>"
