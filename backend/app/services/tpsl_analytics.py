"""TP/SL geometry & risk-scale quality analytics — PURE aggregation.

Read-only observability over EXISTING telemetry (SignalTradePath columns + Signal
risk fields). Never writes, never re-runs an engine, never changes a decision.
Single source for the /analytics/tpsl-quality and /analytics/risk-scale-audit
endpoints and any future admin / CLI / Strategy-Lab consumer.

Design notes:
  • Metrics are recomputed from first-class COLUMNS (entry/sl/tp prices, mfe_r,
    cur_reached_*, sl_dist_pct, atr_pct_at_signal …) so they work for EVERY row,
    including historical ones written before the `extra` JSON existed.
  • Every block carries its own denominator (n) plus the sub-checkpoint caveat so a
    small sample (n < CHECKPOINT_N) is never over-trusted.
  • High-confidence rows (complete bar-walk: MFE measured, not still-forming, not
    intrabar-ambiguous) are reported SEPARATELY from low-confidence rows — never
    blended into a headline number.
This report INFORMS prioritization; it does not by itself justify any engine change
(those stay gated on data + backtest — see docs/p06 plan).
"""

from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.backtesting.trade_path import is_legacy_contradictory_live_sl

# Below this many resolved trade-paths the sample is too small to draw policy
# conclusions (matches the tm-v2 data checkpoint).
CHECKPOINT_N = 250


def _f(x) -> Optional[float]:
    """Numeric/Decimal DB value → float (FastAPI serializes Decimal as a string)."""
    return float(x) if x is not None else None


def _rate(num: int, den: int) -> float:
    return round(num / den * 100.0, 1) if den else 0.0


def _avg(xs: Sequence[Optional[float]]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _median(xs: Sequence[Optional[float]]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    return round(median(vals), 4) if vals else None


def _planned_rr(entry: Optional[float], sl: Optional[float], tp: Optional[float]) -> Optional[float]:
    """Planned reward:risk = |tp-entry| / |entry-sl| (recomputed from stored prices)."""
    if entry is None or sl is None or tp is None:
        return None
    risk = abs(entry - sl)
    if risk == 0:
        return None
    return round(abs(tp - entry) / risk, 4)


def _is_high_confidence(r) -> bool:
    """Complete bar-walk row: MFE measured, not still-forming, not intrabar-ambiguous."""
    return (
        r.mfe_pct is not None
        and not bool(r.still_forming_resolution)
        and not bool(r.intrabar_ambiguous)
    )


def compute_tpsl_quality(rows: List[Any]) -> Dict[str, Any]:
    """Aggregate TP/SL geometry & resolution quality over SignalTradePath rows."""
    n = len(rows)
    hi = [r for r in rows if _is_high_confidence(r)]

    # TP reachability (current geometry)
    tp1 = sum(1 for r in rows if r.cur_reached_tp1)
    tp2 = sum(1 for r in rows if r.cur_reached_tp2)
    tp3 = sum(1 for r in rows if r.cur_reached_tp3)

    # Planned R:R recomputed from stored prices → covers ALL rows (incl. legacy)
    rr1 = [
        _planned_rr(_f(r.entry_price), _f(r.sl_price), _f(r.tp1_price)) for r in rows
    ]
    rr1 = [x for x in rr1 if x is not None]
    sub1 = sum(1 for x in rr1 if x < 1.0)

    # Degenerate-collapse signatures (BUG-1 / BUG-3 population)
    null_r_with_bars = sum(
        1 for r in rows if r.bars_total and r.bars_total > 0 and (r.mfe_r is None or r.mae_r is None)
    )
    sl_dist_zero = sum(1 for r in rows if r.sl_dist_pct is not None and _f(r.sl_dist_pct) == 0.0)
    atr_zero = sum(1 for r in rows if r.atr_pct_at_signal is not None and _f(r.atr_pct_at_signal) == 0.0)

    # Excursion (high-confidence rows only)
    avg_mfe_r = _avg([_f(r.mfe_r) for r in hi])
    avg_mae_r = _avg([_f(r.mae_r) for r in hi])

    # Give-back after TP1
    tp1_hit_rows = [r for r in rows if r.cur_reached_tp1]
    gave_back = sum(1 for r in tp1_hit_rows if r.cur_gave_back_after_tp1)
    avg_bars_tp1 = _avg([float(r.cur_bars_to_tp1) for r in tp1_hit_rows if r.cur_bars_to_tp1 is not None])

    # Confidence caveats (the low-confidence population)
    intrabar = sum(1 for r in rows if r.intrabar_ambiguous)
    still_forming = sum(1 for r in rows if r.still_forming_resolution)
    # v1-handling (KEY1-d): legacy live-SL rows that recorded a TP1-banked trade as a
    # full original-stop loss. Surfaced so the sample is read with this caveat; the
    # single-source predicate is what learning layers filter on going forward.
    legacy_contra_live_sl = sum(1 for r in rows if is_legacy_contradictory_live_sl(r))

    # Resolution-source mix (from extra on rows written after Commit 4)
    src = {"bar_walk": 0, "live_sl": 0, "expiry": 0, "unknown": 0}
    for r in rows:
        extra = r.extra if isinstance(r.extra, dict) else {}
        s = extra.get("resolution_source")
        src[s if s in src else "unknown"] += 1

    return {
        "sample": {
            "n": n,
            "n_high_confidence": len(hi),
            "n_low_confidence": n - len(hi),
            "checkpoint_n": CHECKPOINT_N,
            "below_checkpoint": n < CHECKPOINT_N,
        },
        "tp_reachability": {"tp1_rate": _rate(tp1, n), "tp2_rate": _rate(tp2, n),
                            "tp3_rate": _rate(tp3, n), "n": n},
        "rr_quality": {
            "avg_planned_rr_tp1": _avg(rr1),
            "median_planned_rr_tp1": _median(rr1),
            "sub_1_rr_count": sub1,
            "sub_1_rr_pct": _rate(sub1, len(rr1)),
            "n": len(rr1),
        },
        "excursion_high_conf": {"avg_mfe_r": avg_mfe_r, "avg_mae_r": avg_mae_r, "n": len(hi)},
        "degenerate": {
            "null_r_with_bars": null_r_with_bars,
            "sl_dist_zero": sl_dist_zero,
            "atr_pct_zero": atr_zero,
            "_note": "atr_pct_zero > 0 would mean BUG-1 (flat-ATR collapse) fired before the fix",
        },
        "give_back": {"after_tp1_count": gave_back, "after_tp1_pct": _rate(gave_back, len(tp1_hit_rows)),
                      "n_tp1_hit": len(tp1_hit_rows)},
        "timing": {"avg_bars_to_tp1": avg_bars_tp1, "n": len(tp1_hit_rows)},
        "confidence_caveats": {"intrabar_ambiguous": intrabar, "still_forming": still_forming,
                               "legacy_contradictory_live_sl": legacy_contra_live_sl},
        "resolution_source_mix": src,
    }


def compute_risk_scale_audit(pairs: Sequence[Tuple[Any, Any]]) -> Dict[str, Any]:
    """Prove Signal.risk_score stays on the canonical 1-10 scale (D1 / BUG-4).

    pairs: iterable of (risk_score, risk_level_str).
    """
    scores: List[float] = []
    medium_outside = 0
    for rs, rl in pairs:
        if rs is None:
            continue
        s = float(rs)
        scores.append(s)
        rlv = rl.value if hasattr(rl, "value") else (str(rl) if rl is not None else None)
        if rlv == "medium" and not (4.0 <= s < 6.0):
            medium_outside += 1

    n = len(scores)
    out_of_range = sum(1 for s in scores if s < 1.0 or s > 10.0)
    hist = {"1-2": 0, "3-4": 0, "5-6": 0, "7-8": 0, "9-10": 0, "out": 0}
    for s in scores:
        if s < 1 or s > 10:
            hist["out"] += 1
        elif s < 3:
            hist["1-2"] += 1
        elif s < 5:
            hist["3-4"] += 1
        elif s < 7:
            hist["5-6"] += 1
        elif s < 9:
            hist["7-8"] += 1
        else:
            hist["9-10"] += 1

    return {
        "n": n,
        "min": round(min(scores), 2) if scores else None,
        "max": round(max(scores), 2) if scores else None,
        "histogram": hist,
        "out_of_1_10_count": out_of_range,
        "canonical_1_10": out_of_range == 0,   # True proves the D1 contract holds in data
        "medium_with_score_outside_4_6": medium_outside,
    }
