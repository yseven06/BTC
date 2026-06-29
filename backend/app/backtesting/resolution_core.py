"""Single source of truth for trade-path resolution geometry.

The per-bar geometry lives in ONE place — ``step_bar`` — which advances a single
candle of the SL / TP1-TP2-TP3 scale-out / break-even / inside-bar rules over a
mutable ``WalkState``. Two callers share it:

  • ``resolve_trade_path`` (whole-path) — a thin loop over ``step_bar``; used by the
    LIVE tracker, which resolves one signal at a time.
  • the BACKTEST walk-forward portfolio loop — calls ``step_bar`` once per active
    trade per bar, keeping its own equity-curve / capital accounting.

Both therefore resolve identical geometry identically (the BP2 gate premise), and
future work (Coin Memory v2, Similarity v2, Adaptive Learning, TP/SL calibration)
shares the same definition.

Design invariants:
  • PURE: no DB, no I/O, no fetches, no clock. Deterministic in
    (direction, levels, bars, execution_model).
  • Faithful extraction of the live tracker bar-walk — byte-for-byte behaviour,
    locked by golden + differential + mapping tests.
  • EXPIRY is NOT decided here. Each caller decides expiry (the live tracker uses
    wall-clock ``expires_at``; the backtest a bar window) and books any
    ``remaining_share`` at the relevant close.
  • ``realized_return_frac`` is SHARE-weighted (capital-agnostic): live uses it
    directly (×100 = pnl_pct); backtest multiplies by allocated_capital.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


def resolve_inside_bar_ambiguity(direction: str, open_price: float, close_price: float,
                                 execution_model: str) -> str:
    """Resolve a bar that touches BOTH stop-loss and a take-profit. Returns 'sl' or
    'tp'. 'conservative' (the live default) always lets SL win; 'optimistic' lets TP
    win; 'neutral' infers from the candle body direction."""
    if execution_model == "conservative":
        return "sl"
    if execution_model == "optimistic":
        return "tp"
    # neutral — infer from candle direction
    if direction == "bullish":
        return "tp" if close_price >= open_price else "sl"
    return "tp" if close_price <= open_price else "sl"


@dataclass
class TradeResolution:
    """Result of walking the post-entry candles. ``resolved`` is True only when SL
    or TP3 closed the whole position WITHIN the given bars; otherwise the caller
    applies its own expiry (book ``remaining_share`` at the relevant close)."""
    resolved: bool
    resolved_by_sl: bool
    hit_tp1: bool
    hit_tp2: bool
    hit_tp3: bool
    tp1_bar_idx: Optional[int]
    tp2_bar_idx: Optional[int]
    tp3_bar_idx: Optional[int]
    bars_walked: int
    realized_return_frac: float   # share-weighted fraction booked so far (e.g. 0.015 = +1.5%)
    remaining_share: float        # > 0 → not fully closed within these bars
    mfe_pct: float
    mae_pct: float
    mfe_bar_idx: Optional[int]
    mae_bar_idx: Optional[int]
    post_tp1_mfe_pct: float
    post_tp1_mae_pct: float
    intrabar_ambiguous: bool
    closed_bar_idx: Optional[int]


# A bar is (open, high, low, close).
Bar = Tuple[float, float, float, float]


@dataclass
class WalkState:
    """Mutable per-trade state advanced one candle at a time by ``step_bar``."""
    direction: str
    entry: float
    tp1: float
    tp2: float
    tp3: float
    current_sl: float
    execution_model: str = "conservative"
    remaining_share: float = 1.0
    realized: float = 0.0
    hit_tp1: bool = False
    hit_tp2: bool = False
    hit_tp3: bool = False
    tp1_bar_idx: Optional[int] = None
    tp2_bar_idx: Optional[int] = None
    tp3_bar_idx: Optional[int] = None
    resolved: bool = False
    resolved_by_sl: bool = False
    closed_bar_idx: Optional[int] = None
    max_favorable: float = 0.0
    max_drawdown: float = 0.0
    mfe_bar_idx: int = 0
    mae_bar_idx: int = 0
    post_tp1_mfe: float = 0.0
    post_tp1_mae: float = 0.0
    intrabar_ambiguous: bool = False
    bars_walked: int = 0
    # Per-fill log [(portion, ret_fraction), ...] in execution order. Lets a
    # capital-weighted caller (the backtest) reproduce its EXACT accounting in the
    # same float order; the whole-path resolver ignores it (uses `realized`).
    fills: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def is_bull(self) -> bool:
        return self.direction == "bullish"


def new_walk_state(*, direction: str, entry: float, sl: float, tp1: float, tp2: float,
                   tp3: float, execution_model: str = "conservative") -> WalkState:
    """Fresh state for a trade opening at ``entry`` with the given levels."""
    return WalkState(direction=direction, entry=entry, tp1=tp1, tp2=tp2, tp3=tp3,
                     current_sl=sl, execution_model=execution_model)


def step_bar(st: WalkState, k: int, bar: Bar) -> bool:
    """Advance the walk by ONE candle (index ``k``). Mutates ``st`` and returns True
    once the position is fully resolved (SL or TP3) — the caller should stop walking.
    This is the SINGLE SOURCE of the per-bar resolution geometry."""
    o, h, l, c = bar
    st.bars_walked = k + 1
    entry = st.entry
    is_bull = st.is_bull

    # --- MFE / MAE (observation only; updated BEFORE hit checks, as live does) ---
    if is_bull:
        drawdown = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
        favorable = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
    else:
        drawdown = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
        favorable = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
    if favorable > st.max_favorable:
        st.max_favorable = favorable
        st.mfe_bar_idx = k
    if drawdown > st.max_drawdown:
        st.max_drawdown = drawdown
        st.mae_bar_idx = k
    if st.hit_tp1:  # reflects PRIOR bars (post-TP1 excursion)
        st.post_tp1_mfe = max(st.post_tp1_mfe, favorable)
        st.post_tp1_mae = max(st.post_tp1_mae, drawdown)

    # --- hit detection ---
    sl_hit = l <= st.current_sl if is_bull else h >= st.current_sl
    if is_bull:
        tp1_t = h >= st.tp1 and not st.hit_tp1
        tp2_t = h >= st.tp2 and not st.hit_tp2
        tp3_t = h >= st.tp3 and not st.hit_tp3
    else:
        tp1_t = l <= st.tp1 and not st.hit_tp1
        tp2_t = l <= st.tp2 and not st.hit_tp2
        tp3_t = l <= st.tp3 and not st.hit_tp3
    tp_hit = tp1_t or tp2_t or tp3_t

    # --- inside-bar ambiguity (both touched same candle) ---
    if sl_hit and tp_hit:
        st.intrabar_ambiguous = True
        winner = resolve_inside_bar_ambiguity(st.direction, o, c, st.execution_model)
        if winner == "sl":
            tp_hit = False
            tp1_t = tp2_t = tp3_t = False
        else:
            sl_hit = False

    # --- process ---
    if sl_hit:
        ret_sl = ((st.current_sl - entry) / entry) if is_bull else ((entry - st.current_sl) / entry)
        st.fills.append((st.remaining_share, ret_sl))
        st.realized += st.remaining_share * ret_sl
        st.remaining_share = 0.0
        st.resolved = True
        st.resolved_by_sl = True
        st.closed_bar_idx = k
        return True
    elif tp_hit:
        if tp1_t:
            st.hit_tp1 = True
            st.tp1_bar_idx = k
            ret_tp1 = ((st.tp1 - entry) / entry) if is_bull else ((entry - st.tp1) / entry)
            st.fills.append((0.50, ret_tp1))
            st.realized += 0.50 * ret_tp1
            st.remaining_share -= 0.50
            st.current_sl = entry  # move stop to break-even
        if tp2_t and st.remaining_share > 0:
            st.hit_tp2 = True
            st.tp2_bar_idx = k
            portion = min(0.30, st.remaining_share)
            ret_tp2 = ((st.tp2 - entry) / entry) if is_bull else ((entry - st.tp2) / entry)
            st.fills.append((portion, ret_tp2))
            st.realized += portion * ret_tp2
            st.remaining_share -= portion
        if tp3_t and st.remaining_share > 0:
            st.hit_tp3 = True
            st.tp3_bar_idx = k
            portion = st.remaining_share
            ret_tp3 = ((st.tp3 - entry) / entry) if is_bull else ((entry - st.tp3) / entry)
            st.fills.append((portion, ret_tp3))
            st.realized += portion * ret_tp3
            st.remaining_share = 0.0
            st.resolved = True
            st.closed_bar_idx = k
            return True
        # same candle may also hit the new break-even stop
        if st.remaining_share > 0:
            sl_after = l <= st.current_sl if is_bull else h >= st.current_sl
            if sl_after:
                ret_sl = ((st.current_sl - entry) / entry) if is_bull else ((entry - st.current_sl) / entry)
                st.fills.append((st.remaining_share, ret_sl))
                st.realized += st.remaining_share * ret_sl
                st.remaining_share = 0.0
                st.resolved = True
                st.resolved_by_sl = True
                st.closed_bar_idx = k
                return True
    return False


def resolve_trade_path(
    *,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    bars: Sequence[Bar],
    execution_model: str = "conservative",
) -> TradeResolution:
    """Whole-path resolution — a thin loop over ``step_bar``. Faithful extraction of
    the live tracker bar-walk; ``execution_model='conservative'`` == live."""
    st = new_walk_state(direction=direction, entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                        tp3=tp3, execution_model=execution_model)
    for k, bar in enumerate(bars):
        if step_bar(st, k, bar):
            break

    return TradeResolution(
        resolved=st.resolved,
        resolved_by_sl=st.resolved_by_sl,
        hit_tp1=st.hit_tp1,
        hit_tp2=st.hit_tp2,
        hit_tp3=st.hit_tp3,
        tp1_bar_idx=st.tp1_bar_idx,
        tp2_bar_idx=st.tp2_bar_idx,
        tp3_bar_idx=st.tp3_bar_idx,
        bars_walked=st.bars_walked,
        realized_return_frac=st.realized,
        remaining_share=st.remaining_share,
        mfe_pct=st.max_favorable,
        mae_pct=st.max_drawdown,
        mfe_bar_idx=st.mfe_bar_idx,
        mae_bar_idx=st.mae_bar_idx,
        post_tp1_mfe_pct=st.post_tp1_mfe,
        post_tp1_mae_pct=st.post_tp1_mae,
        intrabar_ambiguous=st.intrabar_ambiguous,
        closed_bar_idx=st.closed_bar_idx,
    )
