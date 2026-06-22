"""
Adaptive Signal Intelligence models.

These tables turn TradeMinds from a stateless signal generator into a system
that *remembers*:

  • SignalSnapshot — an immutable photograph of every condition that existed
    the moment a signal was born (engine scores, market regime, volatility,
    sentiment). Without this, once a signal resolves we can never ask "what did
    the market look like when we got this right / wrong?" — which is the raw
    material every learning step downstream depends on.

  • CoinMemory — the accumulated, per-(symbol, timeframe) track record distilled
    from those snapshots and their outcomes: which engines actually predict well
    for THIS asset, in which regime it performs, and the adaptive engine weights
    learned from that history.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SignalSnapshot(Base):
    """Immutable record of the full context at signal-generation time.

    One-to-one with a Signal. Captured the instant a signal is persisted and
    never updated afterwards — it is history, not live state (live state lives
    on the signal/performance rows and is tracked separately).

    Attributes:
        engine_scores: {engine_name: {"score", "bias", "confidence"}} for all
            nine engines at generation time. Lets us later attribute outcome to
            individual engines per asset.
        regime: Coarse market-regime label (see MarketRegime).
        regime_data: Raw metrics behind the regime call (ADX, ATR%, etc.).
        atr_pct / volatility_ratio: Volatility at signal time, absolute and
            relative to the asset's own recent baseline.
        volume_ratio: Current volume vs 20-bar average.
        trend_direction: EMA20-vs-EMA50 direction at signal time.
        fear_greed / ath_distance_pct: Sentiment / positioning context (crypto).
        composite_confidence / composite_probability: The headline scores as
            they were when the signal fired (the live signal row can change;
            this preserves the original).
        mtf_trends: Multi-timeframe trend alignment snapshot.
    """

    __tablename__ = "signal_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    engine_scores = Column(JSON, nullable=True, default=dict)

    regime = Column(String(32), nullable=True, index=True)
    regime_data = Column(JSON, nullable=True, default=dict)

    atr_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    volatility_ratio = Column(Numeric(precision=10, scale=4), nullable=True)
    volume_ratio = Column(Numeric(precision=10, scale=4), nullable=True)
    trend_direction = Column(String(16), nullable=True)

    fear_greed = Column(Integer, nullable=True)
    ath_distance_pct = Column(Numeric(precision=10, scale=2), nullable=True)

    composite_confidence = Column(Numeric(precision=5, scale=2), nullable=True)
    composite_probability = Column(Numeric(precision=5, scale=2), nullable=True)

    mtf_trends = Column(JSON, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    signal = relationship("Signal", backref="snapshot", uselist=False)

    def __repr__(self) -> str:
        return f"<SignalSnapshot(signal_id={self.signal_id}, regime={self.regime})>"


class CoinMemory(Base):
    """Per-(symbol, timeframe) learned track record.

    Updated incrementally each time a signal for this symbol/timeframe resolves.
    Holds aggregate statistics and the adaptive engine weights derived from
    them. Kept deliberately coarse and slow-moving (small update steps, minimum
    sample sizes) to avoid overfitting to a recent lucky/unlucky streak.

    Attributes:
        symbol / timeframe: Identity of the memory cell.
        total_signals / wins / losses: Resolved-signal counters.
        engine_stats: {engine_name: {"correct", "total", "win_rate"}} — how
            often each engine's bias matched the eventual outcome for THIS asset.
        regime_stats: {regime: {"wins", "total", "win_rate"}} — performance
            broken down by the regime the signal was born in.
        outcome_label_stats: {detail_label: count} — distribution of detailed
            outcome reasons (tight SL, late entry, whipsaw, ...).
        adaptive_weights: {engine_name: weight} learned weights (None until
            enough samples accumulate; falls back to base weights meanwhile).
        avg_bars_to_outcome: Mean candles from signal to resolution.
        last_updated_at: When this cell was last touched.
    """

    __tablename__ = "coin_memory"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", name="uq_coin_memory_symbol_tf"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    symbol = Column(String(32), nullable=False, index=True)
    timeframe = Column(String(8), nullable=False, index=True)

    total_signals = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)

    engine_stats = Column(JSON, nullable=True, default=dict)
    regime_stats = Column(JSON, nullable=True, default=dict)
    outcome_label_stats = Column(JSON, nullable=True, default=dict)
    adaptive_weights = Column(JSON, nullable=True, default=None)

    avg_bars_to_outcome = Column(Numeric(precision=10, scale=2), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<CoinMemory(symbol={self.symbol}, tf={self.timeframe}, "
            f"signals={self.total_signals}, wins={self.wins})>"
        )
