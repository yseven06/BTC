"""
TM v2 Phase 1 — core data types.

PURE: no I/O, no DB, no app imports. Just frozen dataclasses. Kept import-light
so the harness stays trivially unit-testable and isolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class PathRecord:
    """One `signal_trade_path` row, typed + with derived policy-independent
    quantities. The immutable unit the replay harness consumes.

    Derived fields (computed by PathReader, never stored in the DB):
      tp1_r          — TP1 reward / SL risk = |tp1-entry| / |entry-sl|
      tp1_atr        — TP1 distance in ATR units
      sl_before_tp   — ordering of SL vs first TP (True/False/None=unknown),
                       derived per the locked decision (NOT a stored column)
      confidence_flags — caveats that lower replay confidence for this row
    """

    # identity / context
    signal_id: str
    asset_id: Optional[str]
    symbol: Optional[str]
    timeframe: Optional[str]
    direction: Optional[str]
    regime: Optional[str]
    outcome: Optional[str]
    detail_label: Optional[str]
    resolved_at: Optional[datetime]
    schema_version: Optional[int]
    source: Optional[str]

    # self-contained prices (the metrics' reference points)
    entry: Optional[float]
    sl: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]

    # policy-independent path primitives
    mfe_r: Optional[float]
    mae_r: Optional[float]
    mfe_atr: Optional[float]
    mae_atr: Optional[float]
    mfe_pct: Optional[float]
    mae_pct: Optional[float]
    bars_total: Optional[int]
    mfe_bar_idx: Optional[int]
    mae_bar_idx: Optional[int]
    sl_dist_pct: Optional[float]
    atr_pct_at_signal: Optional[float]

    # policy-dependent (conditional on current TP/SL geometry)
    cur_reached_tp1: Optional[bool]
    cur_reached_tp2: Optional[bool]
    cur_reached_tp3: Optional[bool]
    cur_bars_to_tp1: Optional[int]
    cur_post_tp1_mfe_r: Optional[float]
    cur_post_tp1_mae_r: Optional[float]
    cur_gave_back_after_tp1: Optional[bool]
    cur_realized_return: Optional[float]

    # ambiguity / confidence caveats
    intrabar_ambiguous: bool
    still_forming_resolution: bool

    # --- derived (PathReader) ---
    tp1_r: Optional[float]
    tp1_atr: Optional[float]
    sl_before_tp: Optional[bool]
    confidence_flags: Tuple[str, ...]


@dataclass(frozen=True)
class Tp1Context:
    """Pre-decision view handed to a Policy at the TP1 juncture.

    Deliberately contains ONLY information available *at* the TP1 decision —
    no realized/future outcome (no look-ahead bias). The replay engine builds
    this; policies never see PathRecord's observed `cur_*` results.
    Optional priors are values known *before* the trade (e.g. a segment's
    historical give-back rate), so passing them in does not leak the future.
    """

    direction: Optional[str]
    entry: Optional[float]
    sl: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]
    tp1_r: Optional[float]
    tp2_r: Optional[float]
    tp3_r: Optional[float]
    tp1_atr: Optional[float]
    atr_pct: Optional[float]
    regime: Optional[str]
    timeframe: Optional[str]
    symbol: Optional[str]
    prior_giveback_rate: Optional[float] = None
    prior_tp1_to_tp2: Optional[float] = None


@dataclass(frozen=True)
class ManagementDecision:
    """A Policy's output at TP1: the scale-out schedule + remainder handling.
    The replay engine applies this mechanically (policy-independent)."""

    tp1_scale_frac: float                 # fraction of original position exited at TP1
    tp2_scale_frac: float = 0.0           # fraction (of original) exited at TP2
    tp3_scale_frac: float = 0.0           # fraction (of original) exited at TP3
    remainder_mode: str = "BREAKEVEN"     # "BREAKEVEN" | "TRAIL"
    trail_rule: Optional[str] = None      # "R_K" | "ATR_K" | "STRUCTURE" (when TRAIL)
    trail_k: Optional[float] = None
    reason: str = ""


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of replaying one PathRecord under one Policy. Realized return in
    R-multiples (policy-independent unit = entry↔SL distance)."""

    realized_r: float
    exit_reason: str
    scale_events: Tuple[Tuple[float, float, str], ...]  # (frac, r_at_exit, why)
    gave_back: bool
    bars_held: Optional[int]
    flags: Tuple[str, ...]
    confidence: float                      # 1.0 exact · <1 approximate (trail/fallback/forming)
