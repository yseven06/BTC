"""
Subscription database model.

Tracks user membership tier, billing cycle, and expiry. One row per user
(latest active subscription). Payments are recorded separately so a user's
billing history is preserved.
"""

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Numeric, String, func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SubscriptionTier(str, enum.Enum):
    """Membership tiers."""
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


class SubscriptionStatus(str, enum.Enum):
    """Active state of a subscription."""
    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"
    TRIAL = "trial"


class BillingCycle(str, enum.Enum):
    """Billing intervals."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"        # 3 months
    SEMI_ANNUAL = "semi_annual"    # 6 months
    YEARLY = "yearly"


class Subscription(Base):
    """A user's current/last subscription record."""

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    tier = Column(
        Enum(SubscriptionTier, name="subscription_tier", create_constraint=True),
        nullable=False, default=SubscriptionTier.FREE,
    )
    status = Column(
        Enum(SubscriptionStatus, name="subscription_status", create_constraint=True),
        nullable=False, default=SubscriptionStatus.ACTIVE,
    )
    billing_cycle = Column(
        Enum(BillingCycle, name="billing_cycle", create_constraint=True),
        nullable=True,
    )
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end   = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)

    # Stripe references (nullable for free / manual users)
    stripe_customer_id     = Column(String(128), nullable=True, index=True)
    stripe_subscription_id = Column(String(128), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    user = relationship("User", backref="subscription", uselist=False)


class Payment(Base):
    """A single payment transaction (record of a successful charge)."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    tier = Column(
        Enum(SubscriptionTier, name="subscription_tier", create_constraint=False),
        nullable=False,
    )
    billing_cycle = Column(
        Enum(BillingCycle, name="billing_cycle", create_constraint=False),
        nullable=False,
    )
    method = Column(String(32), nullable=False, default="stripe")
    stripe_session_id = Column(String(128), nullable=True, index=True)
    stripe_payment_intent_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
