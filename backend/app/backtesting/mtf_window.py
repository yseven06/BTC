"""As-of multi-timeframe selection for the backtest — F1-C.

WHY THIS EXISTS
---------------
Production computes `mtf_trends` from a fixed 15m/1h/4h trio and feeds it into
`generate_signal`, where a disagreeing frame costs 15 confidence points and two
disagreeing frames force HOLD. The backtest never supplied `mtf_data`, so
`mtf_trends` was always `{}`, `mtf_penalty` was structurally 0.0, and every
backtest confidence came out systematically HIGHER than production's — by exactly
15.0 per disagreeing frame.

That is why a confidence gate could not be added on its own: reading a number
that is biased upward and comparing it to 65.0 lets through precisely the calls
production rejects. The MTF input has to be right first.

THE ONE THING THIS MODULE MUST NOT GET WRONG
--------------------------------------------
Selection is by CLOSE time, never by open time. The orchestrator's own backtest
slice (`ai_decision/engine.py:206`) compares `mtf_df.index <= current_time` —
open time against open time — which admits a higher-timeframe bar that opened
before the decision but closes long after it. A 4h bar opening at 08:00 closes at
11:59:59; a 15m decision at 08:15 must not see it. Frames handed to the
orchestrator are pre-filtered here so that bar is already gone and the second
slice cannot put it back.

Purity: no I/O, no DB, no collector. The caller fetches; this only selects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Mapping, Optional

import pandas as pd

from app.services.candle_window import CLOSE_TIME_COLUMN, timeframe_duration

# Production's list, verbatim. Both the producer (ai_decision/engine.py:230-234)
# and the consumer (signal_generator.py:246) hard-code these three, independent of
# the signal's own timeframe. Any other key is silently ignored downstream, so a
# typo here would be a no-op rather than an error — hence one shared constant.
MTF_TIMEFRAMES = ("15m", "1h", "4h")

# Production fetches `limit=60` per frame (ai_decision/engine.py:217/219).
# `calculate_trend_bias` seeds an EMA over whatever it is given, so the window
# length changes the result: a 300-bar slice and a 60-bar slice can disagree on
# the same instant. Matching the horizon is part of parity, not a detail.
MTF_BAR_LIMIT = 60


def _close_times(df: pd.DataFrame, timeframe: str) -> pd.DatetimeIndex:
    """Bar close instants — the exchange's own when present, derived otherwise."""
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    if CLOSE_TIME_COLUMN in df.columns:
        raw = pd.to_datetime(df[CLOSE_TIME_COLUMN], utc=True, errors="coerce")
        ct = pd.DatetimeIndex(raw)
        if not ct.isna().any():
            return ct
    return idx + timeframe_duration(timeframe)


def as_of_frame(
    df: Optional[pd.DataFrame],
    timeframe: str,
    as_of: datetime,
    *,
    limit: int = MTF_BAR_LIMIT,
) -> pd.DataFrame:
    """The bars of `df` that had closed at `as_of`, newest `limit` of them.

    Empty when nothing had closed yet — deliberately, so the caller drops the
    frame rather than substituting a bar that had not happened. Forward-filling
    or falling back to the raw frame would reintroduce exactly the leak this
    exists to prevent.
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)

    # The OPEN-time index is preserved — the orchestrator slices on it — while the
    # filter runs on close time. Sorting and de-duplicating first so an
    # out-of-order or re-sent frame yields the same window either way.
    work = df.copy()
    idx = pd.DatetimeIndex(work.index)
    work.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    work = work[~work.index.duplicated(keep="last")].sort_index()

    closes = _close_times(work, timeframe)
    closed = work[closes <= as_of]
    if closed.empty:
        return closed
    return closed.iloc[-limit:] if limit and len(closed) > limit else closed


def build_mtf_data(
    frames: Mapping[str, pd.DataFrame],
    as_of: datetime,
    *,
    limit: int = MTF_BAR_LIMIT,
) -> Dict[str, pd.DataFrame]:
    """`mtf_data` for one decision instant: every production timeframe, as-of.

    Frames with nothing closed yet are omitted entirely. The orchestrator treats a
    missing key as "no opinion" (`mtf_trends.get(tf, "neutral")`, and a neutral
    frame contributes no penalty), which is the correct reading of "we did not
    know yet" — the alternative, inventing a bias, would be a fabricated input.
    """
    out: Dict[str, pd.DataFrame] = {}
    for tf in MTF_TIMEFRAMES:
        src = frames.get(tf)
        if src is None:
            continue
        sliced = as_of_frame(src, tf, as_of, limit=limit)
        if not sliced.empty:
            out[tf] = sliced
    return out
