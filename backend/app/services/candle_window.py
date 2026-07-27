"""Closed-candle analysis windows — F1.

WHY THIS EXISTS
---------------
Every signal job fires 1-3 minutes into a fresh candle (scheduler.py:801/810/819/828),
and Binance's klines endpoint always returns the candle currently forming. Nothing in
the decision path dropped it, so every indicator, every engine and the regime detector
were scoring a bar that was 2/15, 1/60 or 2/240 complete.

The arithmetic signature was measured on 1 998 production candidate rows: the median
`volume_ratio` was 0.1109 on 15m (2/15 = 0.1333 expected), 0.0341 on 1h (1/60) and
0.0081 on 4h (2/240). `thin_tape` (< 0.5) therefore fired on 83.6 % / 93.3 % / 98.2 %
of evaluations, and BREAKOUT — which needs volume > 1.8x — occurred once in 3 375
snapshots across 40 days. The regime was not misclassifying; it was being fed a
fraction of a bar.

WHAT THIS DOES NOT DO
---------------------
It does not drop the last row. A bar that has genuinely closed is kept — the whole
point is that "last" and "still forming" are different questions, and only a UTC
close-time comparison answers the second one. A blind `iloc[:-1]` would silently
discard a closed bar whenever the job ran late, which is exactly the failure mode
this module exists to prevent.

It also never touches the caller's frame. The full frame stays authoritative for the
chart (prices.py:139), for the tracker's deliberate use of the forming candle
(tracker.py:294-311) and for the live price that anchors entry/SL/TP geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

# Bar durations. Keys match the timeframe strings the collector already accepts
# (binance_collector.py:48-51); anything outside this map is a programming error
# rather than something to guess a duration for.
TIMEFRAME_DURATIONS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

# The column Binance sends as kline field 6. The collector keeps it (F1); frames
# from other sources (Yahoo) do not have it and fall back to open_time + duration.
CLOSE_TIME_COLUMN = "close_time"

# Columns the engines consume. Kept explicit so the analysis view never carries
# bookkeeping columns into code that iterates the frame.
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class UnknownTimeframeError(ValueError):
    """Raised rather than guessing a bar duration.

    Guessing would produce a window that is silently wrong — too long and a
    forming bar survives, too short and a closed bar is discarded — and neither
    is visible downstream.
    """


@dataclass(frozen=True)
class AnalysisWindow:
    """The closed-candle view of a frame, plus the facts needed to record it.

    `df` is safe to hand to indicators and engines. The timestamps describe the
    last bar in it, so a candidate row can state exactly which bar it was scored
    on instead of leaving that to be inferred.
    """

    df: pd.DataFrame
    last_bar_open_time: Optional[datetime]
    last_bar_close_time: Optional[datetime]
    dropped_forming: int
    timeframe: str

    @property
    def last_bar_closed(self) -> bool:
        """Always True for a non-empty window — it is what the window selects for.

        Present so callers can record the fact without asserting it themselves,
        and so an empty window reports False rather than raising.
        """
        return not self.df.empty

    @property
    def analysis_close_price(self) -> Optional[float]:
        if self.df.empty:
            return None
        return float(self.df["close"].iloc[-1])


def timeframe_duration(timeframe: str) -> timedelta:
    try:
        return TIMEFRAME_DURATIONS[timeframe]
    except KeyError as exc:
        raise UnknownTimeframeError(
            f"unknown timeframe {timeframe!r}; known: {sorted(TIMEFRAME_DURATIONS)}"
        ) from exc


def _utc_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Index as tz-aware UTC.

    A naive index is treated as UTC rather than rejected: that is what the
    Binance collector produced before F1 and what Yahoo's non-UTC path can still
    produce, and failing here would take down signal generation for a difference
    that is purely notational.
    """
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        return idx.tz_localize("UTC")
    return idx.tz_convert("UTC")


def _close_times(df: pd.DataFrame, idx: pd.DatetimeIndex, timeframe: str) -> pd.DatetimeIndex:
    """When each bar closes — from the exchange when available, derived otherwise.

    Binance's own close_time is preferred because it is authoritative for the
    venue's bar boundaries; deriving from open_time + duration assumes a
    perfectly regular series, which is true for Binance but is an assumption
    rather than a fact.
    """
    if CLOSE_TIME_COLUMN in df.columns:
        raw = pd.to_datetime(df[CLOSE_TIME_COLUMN], utc=True, errors="coerce")
        ct = pd.DatetimeIndex(raw)
        if not ct.isna().any():
            return ct
        # A partially-populated column is worse than none: fall through so the
        # whole frame uses one consistent rule instead of a mixture.
    return idx + timeframe_duration(timeframe)


def analysis_window(
    df: Optional[pd.DataFrame],
    timeframe: str,
    *,
    now: Optional[datetime] = None,
) -> AnalysisWindow:
    """The bars that had definitively closed at `now`, in chronological order.

    Ordering and de-duplication happen before the close-time cut, so a frame that
    arrives out of order or with a repeated bar still yields the right window
    rather than one determined by arrival order. On a duplicate open_time the
    last occurrence wins — for a still-forming bar re-sent by the exchange that
    is the more complete copy.
    """
    duration = timeframe_duration(timeframe)          # validate before anything else
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    if df is None or len(df) == 0:
        return AnalysisWindow(
            df=df.copy() if df is not None else pd.DataFrame(),
            last_bar_open_time=None, last_bar_close_time=None,
            dropped_forming=0, timeframe=timeframe,
        )

    work = df.copy()                                   # never mutate the caller's frame
    work.index = _utc_index(work)
    work = work[~work.index.duplicated(keep="last")]
    work = work.sort_index()

    closes = _close_times(work, pd.DatetimeIndex(work.index), timeframe)
    closed_mask = closes <= now
    closed = work[closed_mask]

    dropped = len(work) - len(closed)
    if closed.empty:
        return AnalysisWindow(
            df=closed, last_bar_open_time=None, last_bar_close_time=None,
            dropped_forming=dropped, timeframe=timeframe,
        )

    last_open = closed.index[-1].to_pydatetime()
    last_close = pd.Timestamp(closes[closed_mask][-1]).to_pydatetime()
    return AnalysisWindow(
        df=closed, last_bar_open_time=last_open, last_bar_close_time=last_close,
        dropped_forming=dropped, timeframe=timeframe,
    )


def closed_candles(
    df: Optional[pd.DataFrame],
    timeframe: str,
    *,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """`analysis_window(...).df` — for callers that only need the frame."""
    return analysis_window(df, timeframe, now=now).df
