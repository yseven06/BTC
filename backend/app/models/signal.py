"""
Signal and SignalPerformance database models.

Represents AI-generated trading signals with entry/exit zones,
risk metrics, and their tracked performance outcomes.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.price_data import Timeframe


class SignalType(str, enum.Enum):
    """Signal strength classification."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class RiskLevel(str, enum.Enum):
    """Risk assessment level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class Direction(str, enum.Enum):
    """Market direction bias."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalOutcome(str, enum.Enum):
    """Signal performance outcome."""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"  # superseded by a genuine reversal signal before TP/SL/expiry


class Signal(Base):
    """
    AI-generated trading signal model.

    Contains the composite analysis result from all engines,
    complete with entry/exit zones, risk parameters, and
    bilingual explanations.

    Attributes:
        id: Unique UUID primary key.
        asset_id: Foreign key to the analysed asset.
        signal_type: Composite signal classification.
        confidence_score: Overall confidence (0-100).
        probability_score: Statistical win probability (0-100).
        risk_score: Composite risk score on a 1-10 scale (1=lowest risk,
            10=highest). Canonical single-source scale — every surface (PDF,
            explanations, UI) renders it as "X/10". NOT a 0-100 value.
        risk_level: Categorical risk level.
        direction: Predicted market direction.
        entry_zone_low: Lower bound of recommended entry.
        entry_zone_high: Upper bound of recommended entry.
        stop_loss: Recommended stop-loss price.
        tp1 / tp2 / tp3: Take-profit targets.
        invalidation_conditions: When the signal should be ignored.
        engines_data: Raw JSON output from each analysis engine.
        explanation_tr: Turkish explanation text.
        explanation_en: English explanation text.
        is_active: Whether the signal is still valid.
        timeframe: The analysis timeframe.
        generated_at: When the signal was created.
        expires_at: When the signal expires.
    """

    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_type = Column(
        Enum(SignalType, name="signal_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    confidence_score = Column(Numeric(precision=5, scale=2), nullable=False)
    probability_score = Column(Numeric(precision=5, scale=2), nullable=True)
    risk_score = Column(Numeric(precision=5, scale=2), nullable=True)  # 1-10 scale (canonical; see docstring)
    risk_level = Column(
        Enum(RiskLevel, name="risk_level", create_constraint=True),
        nullable=False,
        default=RiskLevel.MEDIUM,
    )
    direction = Column(
        Enum(Direction, name="direction", create_constraint=True),
        nullable=False,
    )
    entry_zone_low = Column(Numeric(precision=20, scale=8), nullable=True)
    entry_zone_high = Column(Numeric(precision=20, scale=8), nullable=True)
    stop_loss = Column(Numeric(precision=20, scale=8), nullable=True)
    tp1 = Column(Numeric(precision=20, scale=8), nullable=True)
    tp2 = Column(Numeric(precision=20, scale=8), nullable=True)
    tp3 = Column(Numeric(precision=20, scale=8), nullable=True)
    invalidation_conditions = Column(Text, nullable=True)
    engines_data = Column(JSON, nullable=True, default=dict)
    explanation_tr = Column(Text, nullable=True)
    explanation_en = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    admin_invalidated = Column(Boolean, nullable=False, default=False, server_default="false")
    # Live lifecycle state for an active signal — the answer to "is this signal
    # still valid RIGHT NOW?". Distinct from is_active (binary open/closed) and
    # from the resolved outcome: a signal can be active-but-weakening. Updated
    # each tracking pass from cheap price/regime cues (not a full engine re-run).
    # Values: active | approaching_tp | weakening | invalidating (terminal
    # states reversed/stopped are represented by resolution, not here).
    live_status = Column(Text, nullable=True)
    status_reason = Column(Text, nullable=True)
    # Last time the lifecycle was *evaluated* (every tracking pass).
    status_updated_at = Column(DateTime(timezone=True), nullable=True)
    # When the CURRENT live_status was first entered — distinct from
    # status_updated_at. Drives min-state-duration (don't undo a state too
    # soon) and "X süredir zayıflıyor" displays. Only advances when the
    # status actually changes, not on every re-evaluation.
    live_status_since = Column(DateTime(timezone=True), nullable=True)
    # Observability: how many times hysteresis / min-state-duration BLOCKED a
    # raw candidate change (a prevented flip-flop). Incremented in place each
    # such pass — cheaper than logging a row per suppression.
    flipflop_prevented_count = Column(Integer, nullable=False, default=0, server_default="0")
    timeframe = Column(
        Enum(Timeframe, name="timeframe", create_constraint=True, create_type=False),
        nullable=False,
        default=Timeframe.H4,
    )
    generated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    asset = relationship("Asset", back_populates="signals")
    performance = relationship(
        "SignalPerformance",
        back_populates="signal",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Signal(id={self.id}, asset_id={self.asset_id}, "
            f"type={self.signal_type}, confidence={self.confidence_score})>"
        )


class SignalPerformance(Base):
    """
    Tracks the real-world outcome of a generated signal.

    Attributes:
        id: Unique UUID primary key.
        signal_id: Foreign key to the parent signal.
        outcome: The resolved outcome of the signal.
        actual_return: Realised percentage return.
        max_drawdown: Maximum drawdown during the trade.
        hit_tp1 / hit_tp2 / hit_tp3: Whether each target was reached.
        closed_at: When the signal was resolved.
        is_expired: Whether the signal reached its expiration time before hit.
    """

    __tablename__ = "signal_performances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    outcome = Column(
        Enum(SignalOutcome, name="signal_outcome", create_constraint=True),
        nullable=False,
        default=SignalOutcome.ACTIVE,
    )
    actual_return = Column(Numeric(precision=10, scale=4), nullable=True)
    max_drawdown = Column(Numeric(precision=10, scale=4), nullable=True)
    hit_tp1 = Column(Boolean, nullable=False, default=False)
    hit_tp2 = Column(Boolean, nullable=False, default=False)
    hit_tp3 = Column(Boolean, nullable=False, default=False)
    # Detailed outcome reason beyond the coarse WIN/LOSS/BREAKEVEN above.
    # "win" vs "loss" doesn't tell you *why* — a loss because the direction was
    # wrong and a loss because the stop was a hair too tight are completely
    # different lessons. These power the per-coin learning in CoinMemory.
    # Free-form string (not a DB enum) so the scheduler's reversal path and
    # future regime/macro labels can write here without a schema migration.
    detail_label = Column(Text, nullable=True)
    # Candles elapsed from signal generation to resolution.
    bars_to_outcome = Column(Integer, nullable=True)
    # Maximum Favorable Excursion: how far price moved *in our favour* (% of
    # entry) before the trade resolved. Paired with max_drawdown (the adverse
    # excursion), this distinguishes "never worked" from "worked then reversed".
    mfe_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    # Exact moment each target was crossed — distinct from closed_at, which
    # marks full resolution (e.g. TP1 hits but the position stays open at
    # breakeven until TP2/TP3 or a later stop-out closes it; closed_at would
    # then be much later than the actual TP1 hit).
    tp1_hit_at = Column(DateTime(timezone=True), nullable=True)
    tp2_hit_at = Column(DateTime(timezone=True), nullable=True)
    tp3_hit_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    is_expired = Column(Boolean, nullable=False, default=False)

    # Relationships
    signal = relationship("Signal", back_populates="performance")

    def __repr__(self) -> str:
        return (
            f"<SignalPerformance(signal_id={self.signal_id}, "
            f"outcome={self.outcome}, return={self.actual_return}, expired={self.is_expired})>"
        )
