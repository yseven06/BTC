"""
Signal-related Pydantic schemas.

Covers signal listing, detail views, and performance tracking responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class _EmbeddedAsset(BaseModel):
    """Minimal asset info embedded in signal list items."""
    id: UUID
    symbol: str
    name: str
    asset_type: str
    market: Optional[str] = None

    model_config = {"from_attributes": True}


class SignalResponse(BaseModel):
    """Full signal for list views — includes all fields needed by the dashboard."""

    id: UUID
    asset_id: UUID
    asset: Optional[_EmbeddedAsset] = None
    signal_type: str
    confidence_score: float
    probability_score: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: str
    direction: str
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    invalidation_conditions: Optional[str] = None
    explanation_tr: Optional[str] = None
    explanation_en: Optional[str] = None
    # engines_data may be a dict {engine_name: result} or a list [result, ...]
    # depending on how the AI orchestrator serialized it.
    engines_data: Optional[Any] = None
    timeframe: str
    is_active: bool
    generated_at: datetime
    expires_at: Optional[datetime] = None
    # Live lifecycle state (Adaptive Signal Intelligence) — see Signal model.
    live_status: Optional[str] = None
    live_status_since: Optional[datetime] = None
    status_reason: Optional[str] = None
    status_updated_at: Optional[datetime] = None
    outcome: Optional[str] = None  # active / win / loss / breakeven / expired
    detail_label: Optional[str] = None  # detailed outcome reason (tp1_hit, correct_dir_tight_sl, ...)
    actual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    mfe_pct: Optional[float] = None
    bars_to_outcome: Optional[int] = None
    hit_tp1: bool = False
    hit_tp2: bool = False
    hit_tp3: bool = False
    tp1_hit_at: Optional[datetime] = None
    tp2_hit_at: Optional[datetime] = None
    tp3_hit_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SignalDetailResponse(BaseModel):
    """Full signal detail response with all fields."""

    id: UUID
    asset_id: UUID
    signal_type: str
    confidence_score: float
    probability_score: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: str
    direction: str
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    invalidation_conditions: Optional[str] = None
    engines_data: Optional[Any] = None
    explanation_tr: Optional[str] = None
    explanation_en: Optional[str] = None
    is_active: bool
    timeframe: str
    generated_at: datetime
    expires_at: Optional[datetime] = None
    live_status: Optional[str] = None
    status_reason: Optional[str] = None
    status_updated_at: Optional[datetime] = None
    performance: Optional["SignalPerformanceResponse"] = None

    model_config = {"from_attributes": True}


class SignalTransitionItem(BaseModel):
    """One lifecycle phase-transition row from signal_status_history.

    Serves the per-signal timeline (SL-b). Raw and un-collapsed by design —
    the client suppresses oscillation noise and extracts milestones for display.
    """

    from_status: Optional[str] = None
    to_status: str
    kind: str  # birth | transition | resolution
    reason: Optional[str] = None
    regime: Optional[str] = None
    price: Optional[float] = None
    retrace_to_sl: Optional[float] = None
    progress_to_tp: Optional[float] = None
    structure_event: Optional[str] = None
    momentum_dir: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalPerformanceResponse(BaseModel):
    """Signal performance tracking response."""

    id: UUID
    signal_id: UUID
    outcome: str
    actual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    hit_tp1: bool = False
    hit_tp2: bool = False
    hit_tp3: bool = False
    tp1_hit_at: Optional[datetime] = None
    tp2_hit_at: Optional[datetime] = None
    tp3_hit_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    is_expired: bool = False

    model_config = {"from_attributes": True}


class SignalListResponse(BaseModel):
    """Paginated list of signals."""

    items: List[SignalResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False


class SignalPerformanceSummary(BaseModel):
    """Aggregate performance statistics across signals."""

    total_signals: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    active_count: int = 0
    expired_count: int = 0
    win_rate: float = 0.0
    average_return: Optional[float] = None
    average_drawdown: Optional[float] = None
    tp1_hit_rate: float = 0.0
    tp2_hit_rate: float = 0.0
    tp3_hit_rate: float = 0.0
    
    # Enhanced metrics for dashboard additions
    win_rate_by_direction: Dict[str, float] = Field(default_factory=dict)
    win_rate_by_asset: Dict[str, float] = Field(default_factory=dict)
    performance_by_signal_type: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    historical_equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    drawdown_analysis: Dict[str, Any] = Field(default_factory=dict)


class SignalHistoryStats(BaseModel):
    """Summary statistics for the Signal History panel (closed signals only)."""

    total_signals: int = 0  # all signals matching filters, including still-active ones
    closed_count: int = 0   # total_signals - active_count — matches the table below, which only ever lists closed signals
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    expired_count: int = 0
    invalidated_count: int = 0
    active_count: int = 0
    win_rate: float = 0.0
    tp_hit_rate: float = 0.0       # any of TP1/TP2/TP3 hit
    sl_rate: float = 0.0           # loss rate
    average_return: Optional[float] = None
    profit_factor: Optional[float] = None  # gross profit / abs(gross loss)
    best_signal: Optional[Dict[str, Any]] = None
    worst_signal: Optional[Dict[str, Any]] = None


class BacktestRequest(BaseModel):
    """Configuration options for triggering a walk-forward backtest."""
    symbol: str
    # The seven timeframes the repository actually supports, as defined by the
    # Timeframe enum (models/price_data.py) and matched exactly by the Binance
    # collector's interval map. Validated rather than left an open string: an
    # unsupported value used to be swallowed twice over — the collector silently
    # substituted 1h data, and after F1 the closed-candle helper raised inside the
    # backtest's broad except and the run returned zero trades with HTTP 200.
    # Both failure modes look like "the strategy found nothing".
    # 30m/2h appear in some lookup tables but are NOT supported: no collector can
    # fetch them and the DB enum cannot store them.
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d", "1w"] = "1h"
    initial_capital: float = 10000.0
    risk_pct: float = 2.0
    max_age: int = 48
    # Inside-bar ambiguity model. 'conservative' (SL wins) is canonical — it matches
    # the LIVE tracker + resolution_core default and is the model any BP2 gate run must
    # use; 'optimistic'/'neutral' are sensitivity-analysis only. Validated (invalid
    # values now 422 instead of silently falling through to neutral).
    execution_model: Literal["conservative", "optimistic", "neutral"] = "conservative"


class BacktestResponse(BaseModel):
    """Report generated by a historical backtest run."""
    total_trades: int
    wins: int
    losses: int
    breakevens: int
    expired: int
    win_rate: float
    loss_rate: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: Optional[float] = None  # None when undefined (no/low downside variance)
    max_drawdown_pct: float
    average_return_pct: float
    average_rr: float
    expectancy_pct: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    # F1-B' provenance — what this run's numbers mean. Defaulted so an older
    # caller or a stored report without them still validates.
    backtest_input_version: Optional[str] = None
    feature_cutoff_policy: Optional[str] = None
    execution_start_policy: Optional[str] = None
    decision_price_policy: Optional[str] = None
    production_intrabar_parity: Optional[str] = None
    mtf_parity: Optional[str] = None
    dropped_forming_bars: Optional[int] = None
    # F1-C parity provenance. All optional so an older caller or a stored report
    # without them still validates.
    mtf_alignment_policy: Optional[str] = None
    mtf_data_source: Optional[str] = None
    adaptive_weights_parity: Optional[str] = None
    adaptive_weights_policy: Optional[str] = None
    confidence_score_parity: Optional[str] = None
    confidence_gate_policy: Optional[str] = None
    confidence_threshold: Optional[float] = None
    reversal_gate_policy: Optional[str] = None
    overall_decision_parity: Optional[str] = None
    parity_limitations: Optional[List[str]] = None
    mtf_frames_available: Optional[int] = None
    candidates_rejected_by_confidence: Optional[int] = None
    candidates_holded_by_mtf: Optional[int] = None
    confidence_distribution: Optional[Dict[str, float]] = None
    equity_curve: List[Dict[str, Any]]
    trades_log: List[Dict[str, Any]]

    @classmethod
    def from_report(cls, report: Any) -> "BacktestResponse":
        """Build the response from a BacktestReport, field by declared field.

        Driven by the SCHEMA, not by the report, and that direction is the whole
        point. The hand-written constructor this replaces named 18 of the 39
        declared fields, so every parity and provenance field the engine
        computes arrived at the client as null — present in the JSON, because
        the route does not exclude none, but empty. Iterating the schema means a
        field cannot be left out. Iterating the schema RATHER THAN the report
        means the eight report-only metrics (planned/realized R, TP reach rates)
        cannot leak into the API contract either; they are the engine's own
        bookkeeping and were never part of it.

        Values cross untouched: no defaulting, no coercion, no tidying. None
        stays None, 0 stays 0, [] stays [], and a float stays a float — a
        caller reading `dropped_forming_bars == 0` must not receive null.

        Missing attributes raise rather than quietly defaulting, because a quiet
        default is exactly the failure being fixed. A test asserts the report
        carries every declared field, so drift is caught in CI, not in prod.
        """
        return cls(**cls.report_values(report))

    @classmethod
    def report_values(cls, report: Any) -> Dict[str, Any]:
        """The declared fields pulled off `report`, before the model touches them.

        Split out from `from_report` so the pass-through can be asserted on the
        raw values. Once Pydantic has validated them a transformation becomes
        invisible — it coerces the string "65.0" straight back to 65.0, so a
        mapper that stringified everything would still produce a correct-looking
        response and only break the day a value stops round-tripping. Tests
        assert identity against the report here, where that is still visible.
        """
        missing = [name for name in cls.model_fields if not hasattr(report, name)]
        if missing:
            raise ValueError(
                f"BacktestReport is missing response fields: {sorted(missing)}"
            )
        return {name: getattr(report, name) for name in cls.model_fields}


# Resolve forward reference
SignalDetailResponse.model_rebuild()
