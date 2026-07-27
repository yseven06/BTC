"""Shadow evaluation of candidate decisions — the read side of P2.2-a.

Answers, for a candidate that was NEVER published, what would have happened to
it. PURE: no DB, no clock, no fetches — deterministic in (levels, bars). The
offline runner does the I/O; everything decidable lives here so it is testable
without a database.

WHY IT REUSES THE PRODUCTION WALK
---------------------------------
`resolve_trade_path` (resolution_core) is the single source of the per-bar
SL / TP scale-out / break-even / inside-bar geometry, shared by the live tracker
and the backtest portfolio loop. A shadow result computed any other way would not
be comparable to the 2 900 real rows it has to be compared against, which is the
entire point of the exercise. It is called verbatim.

THE ONE THING THAT IS **NOT** DELEGATED: THE ENTRY GATE
-------------------------------------------------------
`resolve_trade_path` starts from the assumption that the trade is already open at
`entry`. That assumption — fill at the entry-zone midpoint — is exactly what this
sprint set out to test. So the entry gate runs HERE, in the caller, before the
walk is entered. Handing an unfilled setup to `resolve_trade_path` would silently
re-import the assumption under test and report a loss on a trade nobody took.

TWO ENTRY READINGS, BOTH RECORDED, NEITHER CHANGED
--------------------------------------------------
Reading A (canonical, unchanged): entry = the zone MIDPOINT. This is the price
the whole P&L machinery already pretends the fill happened at, so measuring
against it answers "was that assumption ever physically true".

Reading B-lite (measurement only): did price reach the FAR edge of the zone.
This exists because under Reading A the stop sits beyond the midpoint, so price
must pass entry to reach SL and a midpoint-based "stopped before entry" flag
would be structurally ~always False — entry_telemetry.py:12-18 documents exactly
this and omits the flag for that reason. The far-edge reading is the one that can
actually discriminate. Nothing here alters lifecycle or outcome semantics for
real signals.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.backtesting.resolution_core import resolve_trade_path
from app.engines.ai_decision.entry_telemetry import build_entry_telemetry
from app.models.decision_candidate import (
    SHADOW_EXPIRY,
    SHADOW_NO_FILL,
    SHADOW_STOP,
    SHADOW_TP1,
    SHADOW_TP2,
    SHADOW_TP3,
    SHADOW_UNDECIDABLE,
)

PATH_BAR_WALK = "bar_walk"
PATH_EXPIRY = "expiry"
PATH_NO_FILL = "no_fill"


def _first_touch(bars: Sequence[Tuple[float, float, float, float]],
                 level: float, from_below: bool) -> Optional[int]:
    """Index of the first bar whose range reaches `level`, else None.

    `from_below=True` means price has to fall to it (a long's entry or stop);
    False means it has to rise to it.
    """
    for k, (_o, high, low, _c) in enumerate(bars):
        if (low <= level) if from_below else (high >= level):
            return k
    return None


def evaluate_candidate_shadow(
    *,
    direction: Optional[str],
    entry_zone_low: Optional[float],
    entry_zone_high: Optional[float],
    stop_loss: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    tp3: Optional[float],
    df: Any,
    bar_time: datetime,
) -> Dict[str, Any]:
    """Evaluate one candidate against the bars that followed it.

    `df` must already be truncated to the window under test — the caller owns the
    frame. (build_entry_telemetry's own window spans the whole fetched frame,
    which would otherwise let a touch that happened AFTER the trade closed count
    as an entry; truncating upstream neutralises that for shadow rows without
    changing the helper and breaking the live rows that depend on it.)
    """
    out: Dict[str, Any] = {
        "shadow_outcome": SHADOW_UNDECIDABLE,
        "shadow_resolution_path": None,
        "shadow_resolution_reason": None,
        "shadow_return_pct": None,
        "shadow_r_multiple": None,
        "shadow_mfe_pct": None,
        "shadow_mae_pct": None,
        "shadow_bars_walked": None,
        "shadow_entry_reached": None,
        "shadow_entry_reached_at": None,
        "shadow_bars_to_entry": None,
        "shadow_never_entered": None,
        "shadow_max_zone_penetration_pct": None,
        "shadow_zone_far_edge_reached": None,
        "shadow_stop_before_valid_entry": None,
        "shadow_invalidated_before_entry": None,
    }

    if direction not in ("bullish", "bearish"):
        out["shadow_resolution_reason"] = "no_direction"
        return out
    if entry_zone_low is None or entry_zone_high is None or stop_loss is None:
        out["shadow_resolution_reason"] = "no_geometry"
        return out

    ez_low, ez_high = float(entry_zone_low), float(entry_zone_high)
    sl = float(stop_loss)
    entry_mid = (ez_low + ez_high) / 2.0
    is_bull = direction == "bullish"

    # --- entry gate: reuse the existing detector, do not write a second one ----
    # build_entry_telemetry touches only four attributes and is fully duck-typed,
    # so a candidate that has no Signal row can be measured with a shim.
    shim = SimpleNamespace(entry_zone_low=ez_low, entry_zone_high=ez_high,
                           direction=direction, generated_at=bar_time)
    tel = build_entry_telemetry(shim, df) or {}

    if not tel.get("data_available"):
        # Explicitly UNDECIDABLE, never imputed as "did not enter": no post-bar
        # data is an absence of evidence, not evidence of absence.
        out["shadow_resolution_reason"] = "no_post_bars"
        return out

    out["shadow_entry_reached"] = tel.get("entry_reached")
    out["shadow_entry_reached_at"] = tel.get("entry_reached_at")
    out["shadow_bars_to_entry"] = tel.get("bars_to_entry")
    out["shadow_never_entered"] = tel.get("never_entered")
    pen = tel.get("max_zone_penetration_pct")
    out["shadow_max_zone_penetration_pct"] = pen
    # Reading B-lite: 1.0 == the far (support/resistance) edge was reached.
    out["shadow_zone_far_edge_reached"] = (pen >= 1.0) if pen is not None else None

    bars = _bars_after(df, bar_time)

    # Reading-B-lite discrimination: did the stop print before the far edge, and
    # before the midpoint? Both measured honestly rather than assumed — the
    # midpoint variant is expected to be ~always False under the current geometry
    # and the data is what should say so.
    far_edge = ez_low if is_bull else ez_high
    sl_idx = _first_touch(bars, sl, from_below=is_bull)
    far_idx = _first_touch(bars, far_edge, from_below=is_bull)
    mid_idx = _first_touch(bars, entry_mid, from_below=is_bull)
    if sl_idx is not None:
        out["shadow_stop_before_valid_entry"] = far_idx is None or sl_idx < far_idx
        out["shadow_invalidated_before_entry"] = mid_idx is None or sl_idx < mid_idx
    else:
        out["shadow_stop_before_valid_entry"] = False
        out["shadow_invalidated_before_entry"] = False

    if tel.get("never_entered"):
        # TERMINAL, and deliberately NOT a loss: the setup never took a trade.
        # No walk is run — running one would book a stop on a position that was
        # never opened, which is the specific distortion this sprint exists to
        # expose.
        out["shadow_outcome"] = SHADOW_NO_FILL
        out["shadow_resolution_path"] = PATH_NO_FILL
        out["shadow_resolution_reason"] = "entry_never_reached"
        out["shadow_bars_walked"] = 0
        return out

    # --- walk, from the entry bar onward --------------------------------------
    entry_pos = (tel.get("bars_to_entry") or 1) - 1
    walk_bars = bars[entry_pos:]
    if not walk_bars:
        out["shadow_resolution_reason"] = "no_bars_after_entry"
        return out

    res = resolve_trade_path(
        direction=direction, entry=entry_mid, sl=sl,
        tp1=float(tp1) if tp1 is not None else sl,
        tp2=float(tp2) if tp2 is not None else sl,
        tp3=float(tp3) if tp3 is not None else sl,
        bars=walk_bars, execution_model="conservative",
    )

    total_frac = res.realized_return_frac
    if res.remaining_share > 0:
        # Not fully closed within the window — book the remainder at the last
        # close, the same convention the live tracker uses for wall-clock expiry.
        last_close = walk_bars[-1][3]
        move = ((last_close - entry_mid) / entry_mid) if is_bull else ((entry_mid - last_close) / entry_mid)
        total_frac += res.remaining_share * move
        path = PATH_EXPIRY
    else:
        path = PATH_BAR_WALK

    return_pct = round(total_frac * 100.0, 4)

    # R is normalised by the ORIGINAL stop distance, never by an effective stop
    # that break-even moved to entry. P2.1 hit this directly: using the effective
    # distance makes it zero for every TP1-banked trade, so those rows drop out
    # of the average and drag measured expectancy down by ~0.11R.
    sl_dist_pct = abs(entry_mid - sl) / entry_mid * 100.0 if entry_mid else None
    out["shadow_r_multiple"] = round(return_pct / sl_dist_pct, 4) if sl_dist_pct else None

    if res.hit_tp3:
        outcome = SHADOW_TP3
    elif res.hit_tp2:
        outcome = SHADOW_TP2
    elif res.hit_tp1:
        outcome = SHADOW_TP1
    elif res.resolved_by_sl:
        outcome = SHADOW_STOP
    else:
        outcome = SHADOW_EXPIRY

    out.update({
        "shadow_outcome": outcome,
        "shadow_resolution_path": path,
        "shadow_resolution_reason": "resolved_by_sl" if res.resolved_by_sl else path,
        "shadow_return_pct": return_pct,
        "shadow_mfe_pct": round(res.mfe_pct, 4),
        "shadow_mae_pct": round(res.mae_pct, 4),
        "shadow_bars_walked": res.bars_walked,
    })
    return out


def _bars_after(df: Any, bar_time: datetime) -> List[Tuple[float, float, float, float]]:
    """(open, high, low, close) tuples strictly after `bar_time`.

    Mirrors build_entry_telemetry's own filter so the entry index it reports lines
    up with this list. Returns [] rather than raising on an unexpected frame.
    """
    try:
        import pandas as pd

        if df is None or getattr(df, "empty", True):
            return []
        # Compare tz-naive on both sides. `bar_time` is stored UTC-aware and the
        # frames come back UTC-aware, so dropping the zone on both is lossless —
        # and it is what build_entry_telemetry does (entry_telemetry.py:72-73),
        # which is what makes its reported entry index line up with this list.
        gen = pd.to_datetime(bar_time)
        gen = gen.tz_convert(None) if gen.tzinfo is not None else gen
        idx = df.index
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        after = df[idx > gen]
        if after.empty:
            return []
        return [
            (float(o), float(h), float(l), float(c))
            for o, h, l, c in zip(after["open"], after["high"], after["low"], after["close"])
        ]
    except Exception:  # noqa: BLE001 — a malformed frame is "undecidable", not fatal
        return []
