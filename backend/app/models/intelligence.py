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
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

# Instrumentation contract version. A SINGLE monotonic integer stamped on every
# signal_trade_path row. Bump it whenever ANY of these change: table layout,
# metric computation definitions (MFE/MAE/ATR/R), regime algorithm, TP/SL/
# scale-out policy/geometry, or the session/volatility bucket schemes. Lets
# future analysis segment rows by the era/definitions that produced them, so a
# later policy change never silently mixes incomparable numbers.
TRADE_PATH_SCHEMA_VERSION = 2  # v2 (KEY1-d): live-SL resolution honors TP1/TP2 scale-out.
# v1 live-SL rows (still_forming_resolution + cur_reached_tp1 + cur_gave_back_after_tp1 IS NULL)
# may be contradictory (TP1 banked but recorded as a full original-stop loss) — learning layers
# should filter/down-weight them; see is_legacy_contradictory_live_sl().

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
        extra: Additive JSON escape hatch — extra["birth"] holds generation-time
            provenance (atr_fallback, sr_override, nearest S/R, entry geometry,
            risk inputs, volatility/confidence snapshot). Pure telemetry; the live
            decision path never reads it. See docs/TELEMETRY-TRADE-PATH.md.
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

    # Additive escape hatch for rich birth-time telemetry (extra["birth"]). Avoids
    # future ALTERs; pure observability — never read by the live decision path.
    extra = Column(JSON, nullable=True, default=None)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    signal = relationship("Signal", backref="snapshot", uselist=False)

    def __repr__(self) -> str:
        return f"<SignalSnapshot(signal_id={self.signal_id}, regime={self.regime})>"


class SignalStatusHistory(Base):
    """Append-only log of lifecycle state transitions for a signal.

    The observability layer behind "how good is the lifecycle itself?". One row
    per ACTUAL transition (from != to), plus a birth row and a resolution row —
    never one row per tracking pass. Suppressed (hysteresis-blocked) candidate
    changes are NOT rows here; they only bump signals.flipflop_prevented_count,
    so this table stays small and every row is a real state change.

    Attributes:
        from_status / to_status: The transition. from_status is NULL on birth;
            to_status is "closed" on resolution.
        kind: birth | transition | resolution.
        reason: The status_reason at the moment of transition.
        regime / price / retrace_to_sl / progress_to_tp / structure_event /
            momentum_dir: Context captured at transition, so accuracy/threshold
            analysis can be done later without re-deriving market state.
        outcome: Only on kind=resolution — the resolved SignalOutcome value,
            tying the lifecycle timeline to the eventual result.
    """

    __tablename__ = "signal_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="transition")
    reason = Column(Text, nullable=True)
    regime = Column(String(32), nullable=True)
    price = Column(Numeric(precision=20, scale=8), nullable=True)
    retrace_to_sl = Column(Numeric(precision=10, scale=4), nullable=True)
    progress_to_tp = Column(Numeric(precision=10, scale=4), nullable=True)
    structure_event = Column(String(24), nullable=True)
    momentum_dir = Column(String(16), nullable=True)
    outcome = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return (
            f"<SignalStatusHistory(signal_id={self.signal_id}, "
            f"{self.from_status}->{self.to_status}, kind={self.kind})>"
        )


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

    # Coin Memory v2 — trade-management learned stats (regime-keyed histograms of
    # policy-independent path metrics: MFE/MAE in R & ATR, plus diagnostics).
    # This is a DERIVABLE CACHE/rollup over signal_trade_path (the immutable
    # source of truth); never the sole record. Shape:
    #   {"<regime>": {"hist_mfe_r": {...}, "hist_mae_r": {...}, "n": int, ...}, "_all": {...}}
    tm_stats = Column(JSON, nullable=True, default=None)
    tm_sample_count = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<CoinMemory(symbol={self.symbol}, tf={self.timeframe}, "
            f"signals={self.total_signals}, wins={self.wins})>"
        )


class SignalTradePath(Base):
    """Immutable per-trade path record — the permanent SOURCE OF TRUTH for the
    adaptive trade-management learning layer (CoinMemory.tm_stats is a derivable
    cache over these; these rows are never pruned).

    Written once at resolution from the tracker's existing bar-walk — no new
    fetches, no behaviour change. Self-contained: stores the actual prices the
    metrics were computed against, so a row stays re-interpretable even if the
    parent signal later changes. Every row carries schema_version (the
    instrumentation contract era) so future policy/definition changes never
    silently mix incomparable numbers.

    Field classes:
      🟢 policy-independent  — pure price-path facts (survive geometry changes)
      🟢 context             — birth context for conditional-edge analysis
      🟡 cur_*               — CONDITIONAL on the current TP/SL/scale-out policy
      🔶 ambiguity           — confidence caveats for the estimate
    """

    __tablename__ = "signal_trade_path"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"),
                       nullable=False, unique=True, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"),
                      nullable=True, index=True)  # canonical key (survives ticker renames)
    symbol = Column(String(32), nullable=True, index=True)  # denormalized for display only
    timeframe = Column(String(8), nullable=True, index=True)
    direction = Column(String(16), nullable=True)
    regime = Column(String(32), nullable=True, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True, index=True)
    outcome = Column(String(16), nullable=True)
    detail_label = Column(Text, nullable=True)

    # Meta / future-proofing
    schema_version = Column(Integer, nullable=False, default=TRADE_PATH_SCHEMA_VERSION,
                            server_default=str(TRADE_PATH_SCHEMA_VERSION))
    source = Column(String(12), nullable=False, default="live", server_default="live")  # live|backtest|shadow
    extra = Column(JSON, nullable=True, default=None)  # additive escape hatch (avoid future ALTERs)

    # 🟢 policy-independent path primitives
    mfe_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    mae_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    mfe_r = Column(Numeric(precision=10, scale=4), nullable=True)
    mae_r = Column(Numeric(precision=10, scale=4), nullable=True)
    mfe_atr = Column(Numeric(precision=10, scale=4), nullable=True)
    mae_atr = Column(Numeric(precision=10, scale=4), nullable=True)
    bars_total = Column(Integer, nullable=True)
    mfe_bar_idx = Column(Integer, nullable=True)
    mae_bar_idx = Column(Integer, nullable=True)
    sl_dist_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    atr_pct_at_signal = Column(Numeric(precision=10, scale=4), nullable=True)

    # 🟢 context (for conditional-edge / Strategy-Lab analysis)
    gen_utc_hour = Column(Integer, nullable=True)        # raw 0-23 (re-bucketable)
    weekday = Column(Integer, nullable=True)             # raw 0-6 Mon..Sun
    volatility_ratio = Column(Numeric(precision=10, scale=4), nullable=True)  # raw
    session = Column(String(16), nullable=True)          # convenience label
    volatility_bucket = Column(String(12), nullable=True)  # convenience label

    # Self-contained prices (the metrics' reference points)
    entry_price = Column(Numeric(precision=20, scale=8), nullable=True)
    sl_price = Column(Numeric(precision=20, scale=8), nullable=True)
    tp1_price = Column(Numeric(precision=20, scale=8), nullable=True)
    tp2_price = Column(Numeric(precision=20, scale=8), nullable=True)
    tp3_price = Column(Numeric(precision=20, scale=8), nullable=True)

    # 🟡 policy-dependent (conditional on current geometry — re-derive on change)
    cur_reached_tp1 = Column(Boolean, nullable=True)
    cur_reached_tp2 = Column(Boolean, nullable=True)
    cur_reached_tp3 = Column(Boolean, nullable=True)
    cur_bars_to_tp1 = Column(Integer, nullable=True)
    cur_post_tp1_mae_r = Column(Numeric(precision=10, scale=4), nullable=True)
    cur_post_tp1_mfe_r = Column(Numeric(precision=10, scale=4), nullable=True)
    cur_gave_back_after_tp1 = Column(Boolean, nullable=True)
    cur_realized_return = Column(Numeric(precision=10, scale=4), nullable=True)

    # 🔶 ambiguity / confidence caveats
    intrabar_ambiguous = Column(Boolean, nullable=False, default=False, server_default="false")
    sl_before_tp = Column(Boolean, nullable=True)  # null = unknown/ambiguous
    still_forming_resolution = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<SignalTradePath(signal_id={self.signal_id}, mfe_r={self.mfe_r}, mae_r={self.mae_r})>"
