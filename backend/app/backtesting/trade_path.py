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
from app.services.trade_geometry import (
    safe_div as _safe_div,
    planned_rr as _planned_rr,
    dist_pct as _geo_dist_pct,
)


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


# Telemetry contract version for the SignalTradePath.extra payload. Bump ONLY when
# the MEANING of an existing key changes (new keys can be added without a bump —
# consumers must treat missing keys as None). See docs/TELEMETRY-TRADE-PATH.md.
TRADE_PATH_EXTRA_VERSION = 1


def build_trade_path_extra(
    *,
    entry: Optional[float],
    sl: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    tp3: Optional[float],
    direction: Optional[str] = None,
    mfe_pct: Optional[float] = None,
    mae_pct: Optional[float] = None,
    atr_pct: Optional[float] = None,
    sl_dist_pct: Optional[float] = None,
    mfe_bar_idx: Optional[int] = None,
    mae_bar_idx: Optional[int] = None,
    bars_to_tp1: Optional[int] = None,
    realized_return: Optional[float] = None,
    gave_back_after_tp1: Optional[bool] = None,
    resolution_source: Optional[str] = None,
    tp_touched_but_sl_won: Optional[bool] = None,
    sl_before_tp: Optional[bool] = None,
    entry_zone_low: Optional[float] = None,
    entry_zone_high: Optional[float] = None,
    birth: Optional[dict] = None,
) -> dict:
    """Rich, versioned ``extra`` telemetry for a resolved SignalTradePath.

    Every value is a DERIVED or PROVENANCE fact about an ALREADY-resolved trade —
    it never alters outcome/levels (pure observability). Designed for backward
    analysis, Coin Memory, Similarity and Adaptive Learning. Extensible by design:
    unknown values are ``None`` and new keys append WITHOUT a schema change (the
    row's JSON ``extra`` column is the escape hatch; reserved ``birth``/``shadow``
    slots pre-allocate the next two telemetry waves). Field-by-field purpose:
    docs/TELEMETRY-TRADE-PATH.md.
    """
    tp1_dist_pct = _geo_dist_pct(entry, tp1)
    tp2_dist_pct = _geo_dist_pct(entry, tp2)
    tp3_dist_pct = _geo_dist_pct(entry, tp3)

    gave_back_pct = None
    if mfe_pct is not None and realized_return is not None:
        gave_back_pct = round(max(0.0, mfe_pct - realized_return), 4)

    entry_zone_width_pct = None
    if entry_zone_low is not None and entry_zone_high is not None and entry:
        entry_zone_width_pct = round(abs(entry_zone_high - entry_zone_low) / entry * 100.0, 4)

    captured_tp1 = None
    if mfe_pct is not None and tp1_dist_pct is not None:
        captured_tp1 = bool(mfe_pct + 1e-9 >= tp1_dist_pct)

    return {
        "telemetry_version": TRADE_PATH_EXTRA_VERSION,
        # --- geometry quality (planned R:R + distances from self-contained prices) ---
        "planned_rr_tp1": _planned_rr(entry, sl, tp1),
        "planned_rr_tp2": _planned_rr(entry, sl, tp2),
        "planned_rr_tp3": _planned_rr(entry, sl, tp3),
        "tp1_dist_pct": tp1_dist_pct,
        "tp2_dist_pct": tp2_dist_pct,
        "tp3_dist_pct": tp3_dist_pct,
        "tp1_dist_atr": _safe_div(tp1_dist_pct, atr_pct),
        "tp2_dist_atr": _safe_div(tp2_dist_pct, atr_pct),
        "tp3_dist_atr": _safe_div(tp3_dist_pct, atr_pct),
        "sl_dist_atr": _safe_div(sl_dist_pct, atr_pct),
        "entry_zone_width_pct": entry_zone_width_pct,
        # --- excursion quality (realized vs planned) ---
        "mfe_to_tp1": _safe_div(mfe_pct, tp1_dist_pct),   # >=1 => price reached TP1 distance
        "mae_to_sl": _safe_div(mae_pct, sl_dist_pct),     # >=1 => price reached SL distance
        "captured_tp1_potential": captured_tp1,
        "final_return_pct": realized_return,
        "gave_back_pct": gave_back_pct,
        # --- timing ---
        "time_to_mfe_bars": mfe_bar_idx,
        "time_to_mae_bars": mae_bar_idx,
        "bars_to_tp1": bars_to_tp1,
        # --- resolution provenance (how the outcome was determined) ---
        "resolution_source": resolution_source,            # bar_walk | live_sl | expiry
        "sl_before_tp": sl_before_tp,                       # JSON mirror of the column
        "tp_touched_but_sl_won": tp_touched_but_sl_won,     # conservative inside-bar rule fired
        "gave_back_after_tp1": gave_back_after_tp1,
        # --- reserved future slots (extensible — fill WITHOUT a schema change) ---
        "birth": birth,   # birth-time geometry provenance (from SignalSnapshot.extra["birth"])
        "shadow": None,   # reserved: alternative-geometry shadow-policy outcomes (Adaptive Learning v2)
    }


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
    # resolution provenance + birth context (all optional → existing callers unchanged)
    resolution_source: Optional[str] = None,
    tp_touched_but_sl_won: Optional[bool] = None,
    entry_zone_low: Optional[float] = None,
    entry_zone_high: Optional[float] = None,
    birth: Optional[dict] = None,
    source: str = "live",
) -> SignalTradePath:
    """Build (don't persist) a SignalTradePath from resolution-time primitives."""
    sl_dist_pct = None
    if entry is not None and sl is not None and entry != 0:
        sl_dist_pct = round(abs(entry - sl) / entry * 100.0, 4)

    gen_hour = generated_at.hour if generated_at is not None else None
    weekday = generated_at.weekday() if generated_at is not None else None

    extra = build_trade_path_extra(
        entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3, direction=direction,
        mfe_pct=mfe_pct, mae_pct=mae_pct, atr_pct=atr_pct, sl_dist_pct=sl_dist_pct,
        mfe_bar_idx=mfe_bar_idx, mae_bar_idx=mae_bar_idx, bars_to_tp1=bars_to_tp1,
        realized_return=realized_return, gave_back_after_tp1=gave_back_after_tp1,
        resolution_source=resolution_source, tp_touched_but_sl_won=tp_touched_but_sl_won,
        sl_before_tp=sl_before_tp, entry_zone_low=entry_zone_low, entry_zone_high=entry_zone_high,
        birth=birth,
    )

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
        extra=extra,
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
