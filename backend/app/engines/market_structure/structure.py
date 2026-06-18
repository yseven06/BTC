"""
TradeMinds AI – Market Structure Analysis

Detects:
    * Swing Highs / Swing Lows (configurable lookback)
    * Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), Lower Lows (LL)
    * Trend structure: Uptrend / Downtrend / Range
    * Break of Structure (BOS)
    * Change of Character (CHoCH)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SwingType(str, Enum):
    HIGH = "swing_high"
    LOW = "swing_low"


class TrendState(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"


class StructureEvent(str, Enum):
    HH = "higher_high"
    HL = "higher_low"
    LH = "lower_high"
    LL = "lower_low"
    BOS_BULLISH = "bos_bullish"
    BOS_BEARISH = "bos_bearish"
    CHOCH_BULLISH = "choch_bullish"
    CHOCH_BEARISH = "choch_bearish"


@dataclass
class SwingPoint:
    """A confirmed swing high or swing low."""

    swing_type: SwingType
    price: float
    index: int  # position in the DataFrame
    timestamp: str = ""


@dataclass
class StructureEventRecord:
    """A recorded BOS or CHoCH event."""

    event: StructureEvent
    price: float
    index: int
    broken_swing: SwingPoint
    detail: str = ""
    volume_confirmed: bool = True
    volume_ratio: float = 1.0


@dataclass
class MarketStructureResult:
    """Aggregated output of the market-structure analyser."""

    swing_points: List[SwingPoint]
    events: List[StructureEventRecord]
    current_trend: TrendState
    hh_count: int = 0
    hl_count: int = 0
    lh_count: int = 0
    ll_count: int = 0
    latest_bos: Optional[StructureEventRecord] = None
    latest_choch: Optional[StructureEventRecord] = None


# ═══════════════════════════════════════════════════════════════════════════
# Swing Point Detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_swing_points(
    df: pd.DataFrame,
    lookback: int = 5,
) -> List[SwingPoint]:
    """Identify swing highs and lows using a symmetric *lookback* window.

    A candle at index *i* is a **swing high** when its ``high`` is the
    maximum of ``high[i-lookback : i+lookback+1]``, and vice-versa for
    swing lows.

    Args:
        df: OHLCV DataFrame.
        lookback: Number of bars either side of the candidate.

    Returns:
        Chronologically ordered list of :class:`SwingPoint`.
    """
    swings: List[SwingPoint] = []
    n = len(df)
    if n < 2 * lookback + 1:
        return swings

    highs = df["high"].values
    lows = df["low"].values

    timestamps = df.index.astype(str).tolist() if hasattr(df.index, "astype") else [""] * n

    for i in range(lookback, n - lookback):
        window_high = highs[i - lookback: i + lookback + 1]
        window_low = lows[i - lookback: i + lookback + 1]

        if highs[i] == window_high.max() and np.sum(window_high == highs[i]) == 1:
            swings.append(SwingPoint(SwingType.HIGH, float(highs[i]), i, timestamps[i]))

        if lows[i] == window_low.min() and np.sum(window_low == lows[i]) == 1:
            swings.append(SwingPoint(SwingType.LOW, float(lows[i]), i, timestamps[i]))

    # Sort by index
    swings.sort(key=lambda s: s.index)
    return swings


# ═══════════════════════════════════════════════════════════════════════════
# HH / HL / LH / LL classification
# ═══════════════════════════════════════════════════════════════════════════

def _classify_swings(swings: List[SwingPoint]) -> List[Tuple[SwingPoint, StructureEvent]]:
    """Compare consecutive swing highs and consecutive swing lows."""
    classified: List[Tuple[SwingPoint, StructureEvent]] = []
    last_high: Optional[SwingPoint] = None
    last_low: Optional[SwingPoint] = None

    for sp in swings:
        if sp.swing_type == SwingType.HIGH:
            if last_high is not None:
                evt = StructureEvent.HH if sp.price > last_high.price else StructureEvent.LH
                classified.append((sp, evt))
            last_high = sp
        else:
            if last_low is not None:
                evt = StructureEvent.HL if sp.price > last_low.price else StructureEvent.LL
                classified.append((sp, evt))
            last_low = sp

    return classified


# ═══════════════════════════════════════════════════════════════════════════
# BOS / CHoCH Detection
# ═══════════════════════════════════════════════════════════════════════════

def _detect_bos_choch(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    current_trend: TrendState,
) -> Tuple[List[StructureEventRecord], TrendState]:
    """Detect Break of Structure and Change of Character with volume confirmation.

    BOS (Break of Structure):
        * In an uptrend, price breaking above the most-recent swing high.
        * In a downtrend, price breaking below the most-recent swing low.

    CHoCH (Change of Character):
        * In an uptrend, price breaking below the most-recent swing low.
        * In a downtrend, price breaking above the most-recent swing high.

    The previous implementation broke out of the loop after the very first
    event, meaning only one BOS/CHoCH was ever detected per analysis window
    and any subsequent structure breaks (which define the continuing trend)
    were silently ignored.  We now walk through the swing sequence and update
    the reference points as each event is confirmed, building a complete
    picture of structure evolution over the lookback window.
    """
    events: List[StructureEventRecord] = []
    highs = df["high"].values
    lows = df["low"].values
    trend = current_trend

    # Calculate 20-period volume SMA once for the full DataFrame
    vol_series = df["volume"].values
    vol_sma = df["volume"].rolling(window=min(20, len(df)), min_periods=1).mean().values

    # Walk through swings in chronological order, maintaining a rolling
    # reference to the most recent confirmed swing high and swing low.
    active_sh: Optional[SwingPoint] = None
    active_sl: Optional[SwingPoint] = None

    for sp in swings:
        if sp.swing_type == SwingType.HIGH:
            active_sh = sp
        else:
            active_sl = sp

        # After the first confirmed high AND low are known, scan candles
        # between this swing and the next to detect breaks.
        if active_sh is None or active_sl is None:
            continue

        # The scan window starts just after the most recently confirmed swing
        scan_start = sp.index + 1

        # Find where the next swing begins so we don't scan beyond it
        # (the outer loop will advance active_sh/sl when we get there)
        scan_end = len(df)
        sp_idx_in_list = swings.index(sp)
        if sp_idx_in_list + 1 < len(swings):
            scan_end = swings[sp_idx_in_list + 1].index

        for i in range(scan_start, scan_end):
            sma_val = vol_sma[i] if i < len(vol_sma) else (vol_sma[-1] if len(vol_sma) > 0 else 0.0)
            curr_vol = vol_series[i]
            vol_ratio = (curr_vol / sma_val) if sma_val > 0 else 1.0
            vol_confirmed = vol_ratio >= 1.2

            # --- Bullish break above active swing high ---
            if highs[i] > active_sh.price:
                if trend in (TrendState.UPTREND, TrendState.RANGE):
                    events.append(StructureEventRecord(
                        StructureEvent.BOS_BULLISH, float(highs[i]), i, active_sh,
                        detail=f"BOS: Price broke above swing high {active_sh.price:.4f} (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                else:
                    events.append(StructureEventRecord(
                        StructureEvent.CHOCH_BULLISH, float(highs[i]), i, active_sh,
                        detail=f"CHoCH: Price broke above swing high {active_sh.price:.4f} in downtrend (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                trend = TrendState.UPTREND
                # Advance the active swing high reference so repeated candles
                # at this level don't generate duplicate events.
                active_sh = SwingPoint(SwingType.HIGH, float(highs[i]), i)
                break  # move to next swing reference

            # --- Bearish break below active swing low ---
            if lows[i] < active_sl.price:
                if trend in (TrendState.DOWNTREND, TrendState.RANGE):
                    events.append(StructureEventRecord(
                        StructureEvent.BOS_BEARISH, float(lows[i]), i, active_sl,
                        detail=f"BOS: Price broke below swing low {active_sl.price:.4f} (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                else:
                    events.append(StructureEventRecord(
                        StructureEvent.CHOCH_BEARISH, float(lows[i]), i, active_sl,
                        detail=f"CHoCH: Price broke below swing low {active_sl.price:.4f} in uptrend (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                trend = TrendState.DOWNTREND
                active_sl = SwingPoint(SwingType.LOW, float(lows[i]), i)
                break  # move to next swing reference

    return events, trend


# ═══════════════════════════════════════════════════════════════════════════
# Trend Determination
# ═══════════════════════════════════════════════════════════════════════════

def _determine_initial_trend(classified: List[Tuple[SwingPoint, StructureEvent]]) -> TrendState:
    """Determine trend from the most recent swing-point classifications.

    Uses a rolling window of the last 6 events:
        * Mostly HH + HL → uptrend
        * Mostly LH + LL → downtrend
        * Mixed → range
    """
    if not classified:
        return TrendState.RANGE

    recent = classified[-6:]
    bullish = sum(1 for _, e in recent if e in (StructureEvent.HH, StructureEvent.HL))
    bearish = sum(1 for _, e in recent if e in (StructureEvent.LH, StructureEvent.LL))

    if bullish >= bearish + 2:
        return TrendState.UPTREND
    if bearish >= bullish + 2:
        return TrendState.DOWNTREND
    return TrendState.RANGE


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def analyse_market_structure(
    df: pd.DataFrame,
    lookback: int = 5,
) -> MarketStructureResult:
    """Full market-structure analysis on *df*.

    Args:
        df: OHLCV DataFrame.
        lookback: Swing-detection lookback window.

    Returns:
        :class:`MarketStructureResult` with all detected swing points,
        structure events, and the current trend state.
    """
    swings = detect_swing_points(df, lookback=lookback)
    classified = _classify_swings(swings)
    trend = _determine_initial_trend(classified)

    hh = sum(1 for _, e in classified if e == StructureEvent.HH)
    hl = sum(1 for _, e in classified if e == StructureEvent.HL)
    lh = sum(1 for _, e in classified if e == StructureEvent.LH)
    ll = sum(1 for _, e in classified if e == StructureEvent.LL)

    bos_choch_events, trend = _detect_bos_choch(df, swings, trend)

    latest_bos = None
    latest_choch = None
    for evt in reversed(bos_choch_events):
        if evt.event in (StructureEvent.BOS_BULLISH, StructureEvent.BOS_BEARISH) and latest_bos is None:
            latest_bos = evt
        if evt.event in (StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH) and latest_choch is None:
            latest_choch = evt

    return MarketStructureResult(
        swing_points=swings,
        events=bos_choch_events,
        current_trend=trend,
        hh_count=hh,
        hl_count=hl,
        lh_count=lh,
        ll_count=ll,
        latest_bos=latest_bos,
        latest_choch=latest_choch,
    )
