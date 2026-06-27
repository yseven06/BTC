"""
Trade-path metric computation (Trade Management Faz 1 — observability).

PURE helper: no DB, no I/O, no resolution logic. Takes primitives the tracker
already has at resolution time and returns a SignalTradePath row ready to add.

Design invariants:
  • Computes only OBSERVED facts about the price path — never alters a trade's
    outcome, levels, or resolution.
  • Policy-independent primitives (MFE/MAE in %/R/ATR) are the durable core;
    cur_* fields are conditional on the current TP/SL/scale-out policy.
  • Context (session/weekday/volatility) is stored raw (hour 0-23, weekday 0-6,
    volatility ratio) plus convenience bucket labels (re-bucketable later).
The tracker wraps the call in try/except so any failure here is fail-open:
instrumentation never blocks trade resolution.
"""

from __future__ import annotations

from typing import Optional

from app.models.intelligence import SignalTradePath, TRADE_PATH_SCHEMA_VERSION


def session_for_hour(h: Optional[int]) -> Optional[str]:
    """UTC-hour → trading-session label (convenience; raw hour also stored)."""
    if h is None:
        return None
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 13:
        return "london"
    if 13 <= h < 16:
        return "overlap"   # London/NY overlap — highest liquidity
    if 16 <= h < 21:
        return "ny"
    return "late"


def volatility_bucket(ratio: Optional[float]) -> Optional[str]:
    """volatility_ratio (ATR% vs its own baseline) → coarse bucket label."""
    if ratio is None:
        return None
    if ratio < 0.8:
        return "low"
    if ratio < 1.3:
        return "normal"
    if ratio < 2.0:
        return "high"
    return "extreme"


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 4)


def compute_trade_path(
    *,
    signal_id,
    asset_id=None,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    direction: Optional[str] = None,
    regime: Optional[str] = None,
    resolved_at=None,
    outcome: Optional[str] = None,
    detail_label: Optional[str] = None,
    # prices (self-contained reference points)
    entry: Optional[float] = None,
    sl: Optional[float] = None,
    tp1: Optional[float] = None,
    tp2: Optional[float] = None,
    tp3: Optional[float] = None,
    # policy-independent path facts (from tracker bar-walk)
    mfe_pct: Optional[float] = None,
    mae_pct: Optional[float] = None,
    bars_total: Optional[int] = None,
    mfe_bar_idx: Optional[int] = None,
    mae_bar_idx: Optional[int] = None,
    # context (from snapshot + generated_at)
    atr_pct: Optional[float] = None,
    volatility_ratio: Optional[float] = None,
    generated_at=None,
    # policy-dependent (current geometry)
    reached_tp1: Optional[bool] = None,
    reached_tp2: Optional[bool] = None,
    reached_tp3: Optional[bool] = None,
    bars_to_tp1: Optional[int] = None,
    post_tp1_mae_pct: Optional[float] = None,
    post_tp1_mfe_pct: Optional[float] = None,
    gave_back_after_tp1: Optional[bool] = None,
    realized_return: Optional[float] = None,
    # ambiguity / confidence
    intrabar_ambiguous: bool = False,
    sl_before_tp: Optional[bool] = None,
    still_forming_resolution: bool = False,
    source: str = "live",
) -> SignalTradePath:
    """Build (don't persist) a SignalTradePath from resolution-time primitives."""
    sl_dist_pct = None
    if entry and sl and entry != 0:
        sl_dist_pct = round(abs(entry - sl) / entry * 100.0, 4)

    gen_hour = generated_at.hour if generated_at is not None else None
    weekday = generated_at.weekday() if generated_at is not None else None

    return SignalTradePath(
        signal_id=signal_id,
        asset_id=asset_id,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        regime=regime,
        resolved_at=resolved_at,
        outcome=outcome,
        detail_label=detail_label,
        schema_version=TRADE_PATH_SCHEMA_VERSION,
        source=source,
        # policy-independent
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        mfe_r=_safe_div(mfe_pct, sl_dist_pct),
        mae_r=_safe_div(mae_pct, sl_dist_pct),
        mfe_atr=_safe_div(mfe_pct, atr_pct),
        mae_atr=_safe_div(mae_pct, atr_pct),
        bars_total=bars_total,
        mfe_bar_idx=mfe_bar_idx,
        mae_bar_idx=mae_bar_idx,
        sl_dist_pct=sl_dist_pct,
        atr_pct_at_signal=atr_pct,
        # context
        gen_utc_hour=gen_hour,
        weekday=weekday,
        volatility_ratio=volatility_ratio,
        session=session_for_hour(gen_hour),
        volatility_bucket=volatility_bucket(volatility_ratio),
        # self-contained prices
        entry_price=entry,
        sl_price=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        tp3_price=tp3,
        # policy-dependent
        cur_reached_tp1=reached_tp1,
        cur_reached_tp2=reached_tp2,
        cur_reached_tp3=reached_tp3,
        cur_bars_to_tp1=bars_to_tp1,
        cur_post_tp1_mae_r=_safe_div(post_tp1_mae_pct, sl_dist_pct),
        cur_post_tp1_mfe_r=_safe_div(post_tp1_mfe_pct, sl_dist_pct),
        cur_gave_back_after_tp1=gave_back_after_tp1,
        cur_realized_return=realized_return,
        # ambiguity
        intrabar_ambiguous=intrabar_ambiguous,
        sl_before_tp=sl_before_tp,
        still_forming_resolution=still_forming_resolution,
    )
