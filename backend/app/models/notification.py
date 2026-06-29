"""
NotificationSettings database model.

**Per-user** Telegram delivery configuration — exactly one row per user. This
replaces the old global singleton: a user's settings (bot token, chat id,
thresholds) never affect any other user.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class NotificationSettings(Base):
    """Per-user notification/delivery settings (Telegram).

    Attributes:
        user_id: Owner — unique, so there is at most one settings row per user.
        telegram_enabled: Master switch for this user's Telegram delivery.
        telegram_bot_token: The user's own Telegram bot token (from @BotFather).
        telegram_chat_id: The user's destination chat/channel id.
        min_confidence: Only notify this user when signal confidence >= this.
        notify_hold: Whether this user also wants HOLD-signal notifications.
    """

    __tablename__ = "notification_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    telegram_enabled = Column(Boolean, nullable=False, default=False)
    telegram_bot_token = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(64), nullable=True)
    min_confidence = Column(Integer, nullable=False, default=70)
    notify_hold = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<NotificationSettings(user_id={self.user_id}, telegram_enabled={self.telegram_enabled})>"
