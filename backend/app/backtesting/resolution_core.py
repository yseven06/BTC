"""Single source of truth for trade-path resolution geometry.

ONE pure function — ``resolve_trade_path`` — walks the candles after entry and
applies the EXACT same SL / TP1-TP2-TP3 scale-out / break-even / inside-bar rules
that the live tracker and the backtest engine each used to implement inline. Both
now call this core so they resolve identical geometry identically (the BP2 gate
premise), and future work (Coin Memory v2, Similarity v2, Adaptive Learning, TP/SL
calibration) shares the same definition.

Design invariants:
  • PURE: no DB, no I/O, no fetches, no engine state, no clock. Deterministic in
    (direction, levels, bars, execution_model).
  • The geometry is a FAITHFUL extraction of the live tracker bar-walk — byte-for-
    byte behaviour, locked by golden characterization tests.
  • EXPIRY is NOT decided here. The core walks the bars it is given and reports
    whether SL/TP closed the position; the CALLER decides expiry semantics (the
    live tracker uses wall-clock ``expires_at``; the backtest a bar window) and
    books any ``remaining_share`` at the last bar's close. This keeps each caller's
    expiry behaviour intact.
  • ``realized_return_frac`` is SHARE-weighted (capital-agnostic): live uses it
    directly (×100 = pnl_pct); backtest multiplies by allocated_capital.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    applies its own expiry (book ``remaining_share`` at the last close)."""
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
    """Walk post-entry candles applying SL / TP scale-out (50% TP1 + move SL to
    break-even, 30% TP2, remainder TP3) / inside-bar ambiguity. Faithful extraction
    of the live tracker bar-walk; ``execution_model='conservative'`` == live."""
    is_bull = direction == "bullish"
    current_sl = sl
    remaining_share = 1.0
    realized = 0.0

    hit_tp1 = hit_tp2 = hit_tp3 = False
    tp1_bar_idx = tp2_bar_idx = tp3_bar_idx = None
    resolved = False
    resolved_by_sl = False
    closed_bar_idx: Optional[int] = None

    max_favorable = 0.0
    max_drawdown = 0.0
    mfe_bar_idx = 0
    mae_bar_idx = 0
    post_tp1_mfe = 0.0
    post_tp1_mae = 0.0
    intrabar_ambiguous = False
    bars_walked = 0

    for k, bar in enumerate(bars):
        o, h, l, c = bar
        bars_walked = k + 1

        # --- MFE / MAE (observation only; updated BEFORE hit checks, as live does) ---
        if is_bull:
            drawdown = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
            favorable = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
        else:
            drawdown = ((h - entry) / entry) * 100.0 if entry > 0 else 0.0
            favorable = ((entry - l) / entry) * 100.0 if entry > 0 else 0.0
        if favorable > max_favorable:
            max_favorable = favorable
            mfe_bar_idx = k
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            mae_bar_idx = k
        if hit_tp1:  # reflects PRIOR bars (post-TP1 excursion)
            post_tp1_mfe = max(post_tp1_mfe, favorable)
            post_tp1_mae = max(post_tp1_mae, drawdown)

        # --- hit detection ---
        sl_hit = l <= current_sl if is_bull else h >= current_sl
        if is_bull:
            tp1_t = h >= tp1 and not hit_tp1
            tp2_t = h >= tp2 and not hit_tp2
            tp3_t = h >= tp3 and not hit_tp3
        else:
            tp1_t = l <= tp1 and not hit_tp1
            tp2_t = l <= tp2 and not hit_tp2
            tp3_t = l <= tp3 and not hit_tp3
        tp_hit = tp1_t or tp2_t or tp3_t

        # --- inside-bar ambiguity (both touched same candle) ---
        if sl_hit and tp_hit:
            intrabar_ambiguous = True
            winner = resolve_inside_bar_ambiguity(direction, o, c, execution_model)
            if winner == "sl":
                tp_hit = False
                tp1_t = tp2_t = tp3_t = False
            else:
                sl_hit = False

        # --- process ---
        if sl_hit:
            ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
            realized += remaining_share * ret_sl
            remaining_share = 0.0
            resolved = True
            resolved_by_sl = True
            closed_bar_idx = k
            break
        elif tp_hit:
            if tp1_t:
                hit_tp1 = True
                tp1_bar_idx = k
                ret_tp1 = ((tp1 - entry) / entry) if is_bull else ((entry - tp1) / entry)
                realized += 0.50 * ret_tp1
                remaining_share -= 0.50
                current_sl = entry  # move stop to break-even
            if tp2_t and remaining_share > 0:
                hit_tp2 = True
                tp2_bar_idx = k
                portion = min(0.30, remaining_share)
                ret_tp2 = ((tp2 - entry) / entry) if is_bull else ((entry - tp2) / entry)
                realized += portion * ret_tp2
                remaining_share -= portion
            if tp3_t and remaining_share > 0:
                hit_tp3 = True
                tp3_bar_idx = k
                portion = remaining_share
                ret_tp3 = ((tp3 - entry) / entry) if is_bull else ((entry - tp3) / entry)
                realized += portion * ret_tp3
                remaining_share = 0.0
                resolved = True
                closed_bar_idx = k
                break
            # same candle may also hit the new break-even stop
            if remaining_share > 0:
                sl_after = l <= current_sl if is_bull else h >= current_sl
                if sl_after:
                    ret_sl = ((current_sl - entry) / entry) if is_bull else ((entry - current_sl) / entry)
                    realized += remaining_share * ret_sl
                    remaining_share = 0.0
                    resolved = True
                    resolved_by_sl = True
                    closed_bar_idx = k
                    break

    return TradeResolution(
        resolved=resolved,
        resolved_by_sl=resolved_by_sl,
        hit_tp1=hit_tp1,
        hit_tp2=hit_tp2,
        hit_tp3=hit_tp3,
        tp1_bar_idx=tp1_bar_idx,
        tp2_bar_idx=tp2_bar_idx,
        tp3_bar_idx=tp3_bar_idx,
        bars_walked=bars_walked,
        realized_return_frac=realized,
        remaining_share=remaining_share,
        mfe_pct=max_favorable,
        mae_pct=max_drawdown,
        mfe_bar_idx=mfe_bar_idx,
        mae_bar_idx=mae_bar_idx,
        post_tp1_mfe_pct=post_tp1_mfe,
        post_tp1_mae_pct=post_tp1_mae,
        intrabar_ambiguous=intrabar_ambiguous,
        closed_bar_idx=closed_bar_idx,
    )
