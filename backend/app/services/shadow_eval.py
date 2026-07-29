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

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.backtesting.resolution_core import resolve_trade_path
from app.engines.ai_decision.entry_telemetry import build_entry_telemetry
from app.models.decision_candidate import (
    SHADOW_EXPIRY,
    SHADOW_NO_FILL,
    SHADOW_REASON_INCOMPLETE_WINDOW,
    SHADOW_STOP,
    SHADOW_TP1,
    SHADOW_TP2,
    SHADOW_TP3,
    SHADOW_UNDECIDABLE,
)
from app.services.candle_window import TIMEFRAME_DURATIONS

PATH_BAR_WALK = "bar_walk"
PATH_EXPIRY = "expiry"
PATH_NO_FILL = "no_fill"

# --- the window a candidate is judged over (CP-SHADOW-PASSB-A) ---------------
#
# A signal expires 48 hours after birth (scheduler.py / signals.py set
# `expires_at = generated_at + 48h`), so 48 hours is both how long a shadow trade
# may run AND the earliest a candidate can have a settled verdict. One constant
# for both, because they are the same fact seen from two sides; a test asserts it
# still matches the expiry the production path actually stamps.
SHADOW_HORIZON = timedelta(hours=48)

# Bars requested beyond the horizon. Binance's `endTime` is inclusive of the bar
# containing it and the first walked bar must be STRICTLY after the decision bar,
# so the query has to reach at least one bar either side of the window to
# guarantee it is fully covered. 20 is slack for that plus exchange-side gaps
# (halts, maintenance) which would otherwise silently shorten the window.
SHADOW_FETCH_SAFETY_BARS = 20

# Binance klines hard cap. Exceeding it does not error — it silently clamps, so
# the request would come back short and the shortfall would look like missing
# market data instead of a bad request.
EXCHANGE_MAX_LIMIT = 1000

SHADOW_PASSB_VERSION = "shadow_passb_v1"
SHADOW_EXECUTION_MODEL = "conservative"


def historical_window(bar_time: datetime, timeframe: str) -> Tuple[datetime, datetime, int]:
    """(window_start, window_end, request_limit) for ONE candidate's own 48 hours.

    This is the whole point of CP-SHADOW-PASSB-A. The previous runner asked the
    exchange for "the last 300 bars", which is a window anchored on *now* rather
    than on the candidate: at 15m, 300 bars span 3d3h, so once a 15m row aged past
    that it could never be covered again and was retired unmeasured. 685 of the
    979 evaluable rows are 15m.

    `window_start` is EXCLUSIVE — the decision bar itself is never walked.
    """
    dur = TIMEFRAME_DURATIONS.get(timeframe)
    if dur is None:
        raise ValueError(f"unsupported timeframe for shadow evaluation: {timeframe!r}")
    window_end = bar_time + SHADOW_HORIZON
    # Derived from the timeframe, never a shared constant: a single number would
    # be right for at most one timeframe and quietly wrong for the rest.
    needed = math.ceil(SHADOW_HORIZON / dur)
    limit = min(needed + SHADOW_FETCH_SAFETY_BARS, EXCHANGE_MAX_LIMIT)
    return bar_time, window_end, limit


def clip_to_window(df: Any, bar_time: datetime, timeframe: str) -> Any:
    """Bars strictly after the decision bar and no later than the horizon.

    Normalises first: the exchange's ordering and uniqueness are not a contract,
    and a duplicated bar would be walked twice while an out-of-order frame would
    make "first touch" meaningless. Returns an empty frame rather than raising on
    a shape it cannot compare — the caller decides what an empty window means.
    """
    if df is None or getattr(df, "empty", True):
        return df

    _start, window_end, _limit = historical_window(bar_time, timeframe)

    idx = df.index
    tz_aware = getattr(idx, "tz", None) is not None

    def _align(ts: datetime):
        if tz_aware:
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return ts.replace(tzinfo=None) if ts.tzinfo else ts

    lo, hi = _align(bar_time), _align(window_end)
    out = df[~df.index.duplicated(keep="first")].sort_index()
    try:
        # STRICTLY after the decision bar, up to and including the horizon bar.
        return out[(out.index > lo) & (out.index <= hi)]
    except TypeError:
        return out.iloc[0:0]


def shadow_passb_provenance(
    *,
    bar_time: datetime,
    timeframe: str,
    requested_limit: int,
    df: Any,
    dry_run: bool,
    intrabar_ambiguous: Optional[bool] = None,
    entry_bar_walked: Optional[bool] = None,
    entry_bar_tp_withheld: Optional[bool] = None,
) -> Dict[str, Any]:
    """How this shadow evaluation was produced, and what the walk noticed about
    its own reliability. Additive; never read by the evaluator or by a decision.
    """
    start, end, _ = historical_window(bar_time, timeframe)
    n = 0 if df is None or getattr(df, "empty", True) else int(len(df))
    first = last = None
    if n:
        first = df.index[0].isoformat()
        last = df.index[-1].isoformat()
    return {
        "policy_version": SHADOW_PASSB_VERSION,
        "evaluator_version": SHADOW_PASSB_VERSION,
        "execution_model": SHADOW_EXECUTION_MODEL,
        "horizon_hours": SHADOW_HORIZON.total_seconds() / 3600.0,
        "fetch_window_start": start.isoformat(),
        "fetch_window_end": end.isoformat(),
        "requested_limit": int(requested_limit),
        "actual_bar_count": n,
        "first_bar_time": first,
        "last_bar_time": last,
        "candidate_evaluated_bar_time": bar_time.isoformat(),
        # The conservative inside-bar rule is UNCHANGED — this only records that
        # it had to be applied, which is invisible in the outcome alone.
        "intrabar_ambiguous": intrabar_ambiguous,
        # PASSB-B-SAFETY: how many bars a whole 48h holds versus how many were
        # actually in the window, so a short window is visible in the row rather
        # than only in whether a verdict appeared. And whether the entry bar was
        # walked at all, or skipped because its take-profit ordering against the
        # fill could not be established.
        "expected_horizon_bars": expected_horizon_bars(timeframe),
        "window_complete": bool(n >= expected_horizon_bars(timeframe)),
        "entry_bar_walked": entry_bar_walked,
        "entry_bar_tp_withheld": entry_bar_tp_withheld,
        "dry_run": bool(dry_run),
    }


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


def _walk_start(entry_bar, entry_pos: int, entry_mid: float, sl: float,
                is_bull: bool) -> Tuple[int, bool, bool]:
    """Where the TP/SL walk may begin, and whether the entry bar was provable.

    Returns (start_index, entry_bar_walked, tp_withheld).

    THE PROBLEM. The fill instant on the entry bar is defined by that bar's LOW
    for a long (entry_telemetry.py: `lows <= entry_level`) and by its HIGH for a
    short. The take profits are then tested against the SAME bar's high/low.
    OHLC carries no intra-bar ordering, so a bar that both reaches the entry and
    reaches a TP cannot say which came first — and crediting the TP would book
    profit on movement that may have happened before anyone was in the trade.
    The bias is one-sided (see below), so it inflates return, R, TP-reach,
    expectancy and PF rather than adding symmetric noise.

    TWO EXCEPTIONS, BOTH PROVED RATHER THAN ASSUMED.

    1. THE FILL IS CERTAIN AT THE OPEN. Long: `open <= entry_mid` means price was
       already at or through the entry level at the bar's first tick, so the fill
       is the open and every subsequent tick in that bar is post-fill. The whole
       bar is then causally sound. Short mirrors it with `open >= entry_mid`.

    2. THE STOP IS CERTAIN EVEN WHEN THE FILL TIME IS NOT. Long: the stop sits
       BELOW the entry (sl < entry_mid). If the bar's low reaches the stop, then
       price was, at that instant, below the entry level too; by continuity it
       must have crossed the entry level on the way down, and the fill fires the
       first time price touches it. So the fill necessarily precedes the stop.
       This holds no matter where in the bar the low printed. Short mirrors it:
       sl > entry_mid, and the high reaching the stop implies the entry level was
       crossed upward first.

       The same argument does NOT hold for a take profit, because a TP sits on
       the far side of the entry from the stop: reaching it does not require
       having crossed the entry level first. That asymmetry is the whole reason
       fabricated losses are impossible here and fabricated wins are not.

    Otherwise the entry bar is skipped entirely and the walk starts on the next
    one. Skipping loses that bar's MFE/MAE, which is the conservative direction:
    unattributable extrema are dropped rather than credited.

    Pure and total: no I/O, no clock, and every branch returns.
    """
    if entry_bar is None:
        return entry_pos, False, False

    o, h, l, _c = entry_bar[0], entry_bar[1], entry_bar[2], entry_bar[3]

    # Exception 1 — fill certain at the open.
    if (o <= entry_mid) if is_bull else (o >= entry_mid):
        return entry_pos, True, False

    # Exception 2 — stop causally certain on the entry bar.
    if (l <= sl) if is_bull else (h >= sl):
        return entry_pos, True, False

    # Neither holds: any TP on this bar is unprovable, so the bar is not walked.
    return entry_pos + 1, False, True


def expected_horizon_bars(timeframe: str) -> int:
    """How many bars a complete 48h window contains for this timeframe.

    Deliberately NOT the fetch limit: that carries SHADOW_FETCH_SAFETY_BARS of
    slack so the request cannot come back short, and judging completeness against
    a padded number would let a window that really is short look full.
    """
    dur = TIMEFRAME_DURATIONS.get(timeframe)
    if dur is None:
        raise ValueError(f"unsupported timeframe for shadow evaluation: {timeframe!r}")
    return math.ceil(SHADOW_HORIZON / dur)


def window_is_complete(df: Any, timeframe: str) -> bool:
    """True when the clipped frame holds a whole 48 hours of bars.

    A partial window can still settle a trade that hit its stop or a take profit
    inside the bars we do have — the event happened, and later bars cannot unhappen
    it. What it cannot settle is `expiry` or `never_entered`, both of which are
    claims about the bars that are MISSING. `_terminal_needs_full_window` below is
    where that distinction is applied.
    """
    if df is None or getattr(df, "empty", True):
        return False
    return int(len(df)) >= expected_horizon_bars(timeframe)


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
    timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate one candidate against the bars that followed it.

    `df` must already be truncated to the window under test — the caller owns the
    frame. (build_entry_telemetry's own window spans the whole fetched frame,
    which would otherwise let a touch that happened AFTER the trade closed count
    as an entry; truncating upstream neutralises that for shadow rows without
    changing the helper and breaking the live rows that depend on it.)
    """
    out: Dict[str, Any] = {
        # NOT a writable column — it rides in extra.shadow_passb. Recorded because
        # a walk that had to break an inside-bar tie is less reliable than one that
        # did not, and the outcome alone cannot show that. None means "no walk ran".
        "intrabar_ambiguous": None,
        # CP-SHADOW-PASSB-B-SAFETY, both telemetry-only (not writable columns):
        # whether the entry bar itself was walked, and whether a take profit on it
        # was withheld because its ordering against the fill was unprovable.
        "entry_bar_walked": None,
        "entry_bar_tp_withheld": None,
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
        #
        # But it is a claim about bars that are ABSENT, so it needs the whole 48
        # hours to be true. On 4 of 192 bars "price never came back to the entry"
        # is not an observation, it is a gap (CP-SHADOW-PASSB-B-SAFETY).
        if timeframe is not None and not window_is_complete(df, timeframe):
            out["shadow_resolution_reason"] = SHADOW_REASON_INCOMPLETE_WINDOW
            return out
        out["shadow_outcome"] = SHADOW_NO_FILL
        out["shadow_resolution_path"] = PATH_NO_FILL
        out["shadow_resolution_reason"] = "entry_never_reached"
        out["shadow_bars_walked"] = 0
        return out

    # --- where the walk may start (CP-SHADOW-PASSB-B-SAFETY) ------------------
    entry_pos = (tel.get("bars_to_entry") or 1) - 1
    entry_bar = bars[entry_pos] if entry_pos < len(bars) else None
    start, entry_bar_walked, ambiguity = _walk_start(
        entry_bar, entry_pos, entry_mid, sl, is_bull)
    out["entry_bar_walked"] = entry_bar_walked
    out["entry_bar_tp_withheld"] = ambiguity

    walk_bars = bars[start:]
    if not walk_bars:
        # The entry bar was skipped as unprovable and nothing followed it inside
        # the horizon. Undecidable, not a result: the trade opened and we cannot
        # say what happened next.
        out["shadow_resolution_reason"] = (
            "entry_bar_ambiguous_no_following_bars" if ambiguity else "no_bars_after_entry")
        return out

    res = resolve_trade_path(
        direction=direction, entry=entry_mid, sl=sl,
        tp1=float(tp1) if tp1 is not None else sl,
        tp2=float(tp2) if tp2 is not None else sl,
        tp3=float(tp3) if tp3 is not None else sl,
        bars=walk_bars, execution_model=SHADOW_EXECUTION_MODEL,
    )
    # Surfaced, not acted on: the conservative tie-break already decided the
    # outcome and that decision is unchanged.
    out["intrabar_ambiguous"] = bool(res.intrabar_ambiguous)

    total_frac = res.realized_return_frac
    if res.remaining_share > 0:
        # Still open at the end of the bars we have. "The end" is only meaningful
        # if those bars are the whole 48 hours — otherwise the remainder is being
        # marked to a last close that is not the last close (PASSB-B-SAFETY).
        # A position that DID fully close needs no such guard: the stop or the
        # take profit happened inside the bars we saw, and later bars cannot
        # unhappen it, so a partial window still settles it honestly.
        if timeframe is not None and not window_is_complete(df, timeframe):
            out["shadow_resolution_reason"] = SHADOW_REASON_INCOMPLETE_WINDOW
            out["shadow_bars_walked"] = res.bars_walked
            return out
        # Book the remainder at the last close, the same convention the live
        # tracker uses for wall-clock expiry.
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
