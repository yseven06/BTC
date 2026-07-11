"""Entry-detection ("entry") telemetry for a resolved signal — CP-1 (PASSIVE).

PURE, PASSIVE observability. From the OHLC bars the tracker ALREADY fetched, it
answers: did price ever reach the assumed entry (Reading A: entry-zone midpoint =
the live tracker's fill reference), WHEN, how deep did it pull into the zone, and
how long it waited.

CP-1 SCOPE = MEASURE ONLY. Nothing reads this back — not the live decision path,
not win-rate, not Adaptive Learning, Coin Memory, reports or UI. It is passive raw
material for a FUTURE shadow measurement (CP-2, reserved at extra["shadow"]).

"Died before entry" note: under Reading A (pullback-gate) the stop-loss sits BEYOND
the entry (LONG: below the midpoint), so price structurally always reaches entry
before SL → an "invalidated_before_entry" flag would be ~always False (dead noise).
It is therefore OMITTED here; the meaningful "setup died without a fill" signal on a
resolved row is simply ``never_entered`` (the shadow step joins it with ``outcome``).
A real invalidation-before-entry flag only becomes meaningful under Reading B (entries
at limit levels away from price) and is deferred to that phase.

Behaviour contract:
  * Byte-identical: reads nothing from / writes nothing to the DB; a pure function
    of (signal, df). Stored additively at SignalTradePath.extra["entry"].
  * Fail-open: callers wrap in try/except so a telemetry error can NEVER block
    signal generation, trade_path, notification or the tracker.
  * Bar-granularity: OHLC has no intra-bar ordering, so "reached" is resolved at
    candle resolution (documented limitation, good enough for shadow).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

ENTRY_TELEMETRY_VERSION = 1


def build_entry_telemetry(signal, df: Optional["pd.DataFrame"]) -> Optional[Dict[str, Any]]:
    """Observe whether/when price reached the entry (zone midpoint) after birth.

    Returns None when there is no trade idea to measure (HOLD / NULL entry zone).
    Never raises for expected-shape inputs; the caller additionally wraps this in
    try/except as a hard fail-open guarantee.
    """
    ez_low = signal.entry_zone_low
    ez_high = signal.entry_zone_high
    if ez_low is None or ez_high is None:
        return None  # HOLD / no trade idea — nothing to measure

    ez_low = float(ez_low)
    ez_high = float(ez_high)
    entry_level = (ez_low + ez_high) / 2.0           # Reading A: midpoint = tracker fill ref (D2)
    is_long = getattr(signal.direction, "value", signal.direction) == "bullish"
    zone_span = ez_high - ez_low

    base: Dict[str, Any] = {
        "telemetry_version": ENTRY_TELEMETRY_VERSION,
        "entry_level": entry_level,
        "data_available": False,          # False => no post-birth bars to observe (≠ never entered)
        "entry_reached": None,
        "entry_reached_at": None,         # ISO of first bar reaching entry_level
        "bars_to_entry": None,
        "wait_seconds": None,             # birth → entry (or birth → last bar if never entered)
        "max_zone_penetration_pct": None,  # 0 = only market edge, 1 = far (support/resistance) edge
        "never_entered": None,
    }

    # Post-generation bars only — mirror the tracker's df_after filter EXACTLY.
    try:
        if df is None or getattr(df, "empty", True):
            return base
        gen_dt = pd.to_datetime(signal.generated_at).tz_localize(None)
        idx = df.index.tz_localize(None)
        df_after = df[idx > gen_dt]
        if df_after.empty:
            return base
    except Exception:
        # Unexpected index/time shape — stay passive, report "no data".
        return base

    highs = df_after["high"].astype(float)
    lows = df_after["low"].astype(float)
    times = df_after.index

    base["data_available"] = True

    # First bar the price reaches the entry level (LONG: dips to it · SHORT: rises to it).
    touched = (lows <= entry_level) if is_long else (highs >= entry_level)
    entry_pos = int(touched.values.argmax()) if bool(touched.any()) else None

    if entry_pos is not None:
        entry_time = pd.to_datetime(times[entry_pos]).tz_localize(None)
        base["entry_reached"] = True
        base["never_entered"] = False
        base["bars_to_entry"] = entry_pos + 1
        base["entry_reached_at"] = entry_time.isoformat()
        base["wait_seconds"] = int((entry_time - gen_dt).total_seconds())
    else:
        last_time = pd.to_datetime(times[-1]).tz_localize(None)
        base["entry_reached"] = False
        base["never_entered"] = True
        base["wait_seconds"] = int((last_time - gen_dt).total_seconds())

    # Deepest pull into the zone (clamped 0..1). Undefined for a degenerate zone.
    if zone_span > 0:
        pen = ((ez_high - float(lows.min())) / zone_span) if is_long \
            else ((float(highs.max()) - ez_low) / zone_span)
        base["max_zone_penetration_pct"] = round(max(0.0, min(1.0, pen)), 4)

    return base
