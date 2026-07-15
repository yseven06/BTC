"""Generation-time ("birth") telemetry for a freshly generated signal.

PURE helper: takes values the signal generator already has at decision time and
returns a rich, versioned dict. ADDITIVE observability — the live decision path
NEVER reads it back; it exists for backward analysis, Coin Memory v2, Similarity v2,
Adaptive Learning and TP/SL floor calibration. Stored at SignalSnapshot.extra
["birth"] and copied onto SignalTradePath.extra["birth"] at resolution.

Extensible: unknown inputs become None; new keys append WITHOUT a schema change.
See docs/TELEMETRY-TRADE-PATH.md.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.trade_geometry import dist_pct, planned_rr

BIRTH_TELEMETRY_VERSION = 1


def _v(x: Any) -> Any:
    """Coerce enums (e.g. VolatilityClass) to their JSON-safe .value."""
    return x.value if hasattr(x, "value") else x


def build_birth_telemetry(
    *,
    direction: str,
    signal_type: str,
    current_price: float,
    atr_used: Optional[float],
    atr_raw: Optional[float],
    atr_fallback_used: bool,
    nearest_support: Optional[float],
    nearest_resistance: Optional[float],
    sr_override_tp1: bool,
    sr_override_tp2: bool,
    sr_override_sl: bool,
    entry_zone_low: Optional[float],
    entry_zone_high: Optional[float],
    stop_loss: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    tp3: Optional[float],
    risk_score: Optional[float],
    risk_level: Optional[str],
    confidence_score: Optional[float],
    probability_score: Optional[float],
    composite_score: Optional[float],
    risk_supporting: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the rich birth-telemetry dict from generation-time primitives."""
    rs = risk_supporting or {}

    atr_pct = round(atr_used / current_price * 100.0, 4) if (atr_used and current_price) else None

    entry_mid = None
    entry_zone_width_pct = None
    if entry_zone_low is not None and entry_zone_high is not None:
        entry_mid = (entry_zone_low + entry_zone_high) / 2.0
        if current_price:
            entry_zone_width_pct = round(abs(entry_zone_high - entry_zone_low) / current_price * 100.0, 4)

    return {
        "telemetry_version": BIRTH_TELEMETRY_VERSION,
        # --- ATR provenance ---
        "atr_used": round(atr_used, 8) if atr_used is not None else None,
        "atr_raw": round(atr_raw, 8) if atr_raw is not None else None,
        "atr_fallback_used": bool(atr_fallback_used),    # BUG-1 marker
        "atr_pct": atr_pct,
        # --- Support/Resistance + override provenance (WHY these levels) ---
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "sr_override_tp1": bool(sr_override_tp1),
        "sr_override_tp2": bool(sr_override_tp2),
        "sr_override_sl": bool(sr_override_sl),
        # --- Entry geometry (published levels at birth) ---
        "current_price": current_price,
        "entry_zone_low": entry_zone_low,
        "entry_zone_high": entry_zone_high,
        "entry_mid": entry_mid,                          # midpoint = live tracker fill ref (D2)
        "entry_zone_width_pct": entry_zone_width_pct,
        "stop_loss": stop_loss,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "sl_dist_pct": dist_pct(entry_mid, stop_loss),
        "tp1_dist_pct": dist_pct(entry_mid, tp1),
        "tp2_dist_pct": dist_pct(entry_mid, tp2),
        "tp3_dist_pct": dist_pct(entry_mid, tp3),
        "planned_rr_tp1": planned_rr(entry_mid, stop_loss, tp1),
        "planned_rr_tp2": planned_rr(entry_mid, stop_loss, tp2),
        "planned_rr_tp3": planned_rr(entry_mid, stop_loss, tp3),
        # --- Risk-model snapshot (inputs + outputs) ---
        "risk_score": risk_score,                        # 1-10 canonical
        "risk_level": _v(risk_level),
        "risk_volatility_class": _v(rs.get("volatility_class")),
        "risk_atr_pct": rs.get("atr_pct"),
        "risk_max_drawdown_pct": rs.get("max_drawdown_pct"),
        "risk_recommended_position_pct": rs.get("recommended_position_pct"),
        "risk_rr_ratio": rs.get("rr_ratio"),
        # --- Confidence / probability snapshot ---
        "confidence_score": confidence_score,
        "probability_score": probability_score,
        "composite_score": composite_score,
        "signal_type": signal_type,
        "direction": direction,
    }


# ── CP-OBS-1A · Aggregate directional exposure at birth ──────────────────────
# WHY: the CP-OBS-1B read-only report found the book's entire edge (+290) is
# handed back by correlated same-direction stop clusters (-278), and EVERY large
# cluster was preceded by 83-96% one-sided exposure (up to 44 LONG / 1 SHORT).
# The system never recorded that state, so it can neither be measured forward
# nor shadow-tested. This captures it. ADDITIVE — never read by any decision.
EXPOSURE_TELEMETRY_VERSION = 1


def exposure_unavailable(reason: str) -> Dict[str, Any]:
    """Safe placeholder when the exposure probe fails — the signal MUST still be
    born. Structured + short so a FAILED probe stays distinguishable from a
    genuine 'no exposure' (all-zero) reading in later analysis."""
    return {
        "version": EXPOSURE_TELEMETRY_VERSION,
        "unavailable": True,
        "reason": (str(reason) or "unknown")[:120],
    }


def build_exposure_telemetry(
    *,
    direction: Optional[str],
    active_long: int,
    active_short: int,
    same_timeframe_active: int,
    same_direction_same_timeframe_active: int,
    concurrent_coin_count: int,
    same_direction_stop_1h: int,
    same_direction_stop_3h: int,
    same_regime_active: Optional[int] = None,
    same_direction_same_regime_active: Optional[int] = None,
) -> Dict[str, Any]:
    """PURE: raw counts -> versioned exposure dict. No DB, no clock, no I/O.

    Counts EXCLUDE the signal being born (the probe runs before it is added), so
    the reading answers "what was the book already holding when this idea was
    minted?". same_direction/opposite are None for a NEUTRAL/HOLD direction (the
    question is undefined without a side)."""
    active_total = active_long + active_short
    side = (direction or "").upper()

    if side == "BULLISH":
        same_direction_active, opposite_direction_active = active_long, active_short
    elif side == "BEARISH":
        same_direction_active, opposite_direction_active = active_short, active_long
    else:
        same_direction_active = opposite_direction_active = None

    def _share(x: int) -> Optional[float]:
        return round(x / active_total, 4) if active_total else None

    return {
        "version": EXPOSURE_TELEMETRY_VERSION,
        "active_total": active_total,
        "active_long": active_long,
        "active_short": active_short,
        "long_share": _share(active_long),
        "short_share": _share(active_short),
        "same_direction_active": same_direction_active,
        "opposite_direction_active": opposite_direction_active,
        "same_timeframe_active": same_timeframe_active,
        "same_direction_same_timeframe_active": same_direction_same_timeframe_active,
        "concurrent_coin_count": concurrent_coin_count,
        "same_direction_stop_1h": same_direction_stop_1h,
        "same_direction_stop_3h": same_direction_stop_3h,
        "same_regime_active": same_regime_active,
        "same_direction_same_regime_active": same_direction_same_regime_active,
    }
