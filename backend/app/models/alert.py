"""
Alert database model.

Supports price alerts, signal-based alerts, and custom condition alerts
that notify users when specified conditions are met.
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class AlertType(str, enum.Enum):
    """Types of supported alerts."""
    PRICE = "price"
    SIGNAL = "signal"
    CUSTOM = "custom"


class Alert(Base):
    """
    User alert model.

    Defines conditions under which a user should be notified.
    The conditions JSON field stores alert-type-specific parameters:

    - price: {"direction": "above"|"below", "target_price": 50000}
    - signal: {"signal_types": ["strong_buy", "buy"], "min_confidence": 75}
    - custom: {"indicator": "RSI", "condition": "below", "value": 30}

    Attributes:
        id: Unique UUID primary key.
        user_id: Foreign key to the owning user.
        asset_id: Foreign key to the target asset.
        alert_type: The category of alert.
        conditions: JSON object with alert-specific parameters.
        is_active: Whether the alert is currently active.
        triggered_at: When the alert was last triggered (null if never).
        created_at: Creation timestamp.
    """

    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_type = Column(
        Enum(AlertType, name="alert_type", create_constraint=True),
        nullable=False,
    )
    conditions = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="alerts")
    asset = relationship("Asset", back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, user_id={self.user_id}, "
            f"asset_id={self.asset_id}, type={self.alert_type})>"
        )
