"""
TradeMinds AI – Candle Range Theory (CRT) Analysis

Analyses higher-timeframe candle ranges for intraday trading signals.

Features:
    * Range analysis (ATR-based expected range)
    * Range position (premium / discount within HTF candle)
    * Sweep detection (price sweeps above/below HTF range then reverses)
    * Expansion vs contraction classification
    * CRT entry signals on sweeps
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class RangeZone(str, Enum):
    PREMIUM = "premium"       # top 25 %
    UPPER_MID = "upper_mid"   # 50-75 %
    LOWER_MID = "lower_mid"   # 25-50 %
    DISCOUNT = "discount"     # bottom 25 %


class RangeState(str, Enum):
    EXPANDING = "expanding"
    CONTRACTING = "contracting"
    NORMAL = "normal"


class SweepDirection(str, Enum):
    SWEEP_HIGH = "sweep_high"
    SWEEP_LOW = "sweep_low"


@dataclass
class RangeAnalysis:
    """Range metrics for the current / HTF candle."""

    current_range: float
    average_range: float  # based on ATR / historical
    range_ratio: float    # current / average
    range_state: RangeState
    atr_value: float


@dataclass
class RangePosition:
    """Where price sits within the HTF range."""

    htf_high: float
    htf_low: float
    htf_range: float
    current_price: float
    position_pct: float  # 0 = at low, 100 = at high
    zone: RangeZone


@dataclass
class SweepEvent:
    """A detected sweep of the HTF candle high / low."""

    direction: SweepDirection
    sweep_price: float
    reversal_price: float
    sweep_index: int
    reversal_index: int
    detail: str = ""
    volume_confirmed: bool = True
    volume_ratio: float = 1.0


@dataclass
class CRTSignal:
    """A CRT entry signal generated from a sweep + reversal."""

    direction: str  # "long" or "short"
    entry_zone_high: float
    entry_zone_low: float
    sweep_event: SweepEvent
    confidence: float  # 0-100
    detail: str = ""


@dataclass
class CRTResult:
    """Aggregated CRT analysis output."""

    range_analysis: RangeAnalysis
    range_position: Optional[RangePosition]
    sweeps: List[SweepEvent]
    signals: List[CRTSignal]


# ═══════════════════════════════════════════════════════════════════════════
# Range Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyse_range(
    df: pd.DataFrame,
    atr_period: int = 14,
) -> RangeAnalysis:
    """Calculate the current candle range vs historical average.

    The "range" of a candle is simply ``high - low``.  We compare the
    latest bar's range against the ATR and a rolling average to
    classify expansion / contraction.
    """
    ranges = df["high"] - df["low"]
    current_range = float(ranges.iloc[-1]) if len(ranges) > 0 else 0.0

    # ATR
    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean()
    atr_val = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else current_range

    # Average range over lookback
    avg_range = float(ranges.rolling(window=min(20, len(ranges)), min_periods=1).mean().iloc[-1])
    if np.isnan(avg_range) or avg_range == 0:
        avg_range = atr_val if atr_val > 0 else current_range

    ratio = current_range / avg_range if avg_range > 0 else 1.0

    if ratio > 1.3:
        state = RangeState.EXPANDING
    elif ratio < 0.7:
        state = RangeState.CONTRACTING
    else:
        state = RangeState.NORMAL

    return RangeAnalysis(
        current_range=current_range,
        average_range=avg_range,
        range_ratio=round(ratio, 3),
        range_state=state,
        atr_value=atr_val,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Range Position
# ═══════════════════════════════════════════════════════════════════════════

def compute_range_position(
    df: pd.DataFrame,
    htf_high: float | None = None,
    htf_low: float | None = None,
) -> Optional[RangePosition]:
    """Determine where current price sits within the HTF candle range.

    If *htf_high* / *htf_low* are not provided, we use the most recent
    day (last 24 bars for 1h, or similar heuristic).
    """
    if htf_high is None or htf_low is None:
        # Fallback: use last 24 bars as proxy for "HTF candle"
        window = min(24, len(df))
        htf_high = float(df["high"].iloc[-window:].max())
        htf_low = float(df["low"].iloc[-window:].min())

    rng = htf_high - htf_low
    if rng <= 0:
        return None

    current = float(df["close"].iloc[-1])
    pct = ((current - htf_low) / rng) * 100.0

    if pct >= 75:
        zone = RangeZone.PREMIUM
    elif pct >= 50:
        zone = RangeZone.UPPER_MID
    elif pct >= 25:
        zone = RangeZone.LOWER_MID
    else:
        zone = RangeZone.DISCOUNT

    return RangePosition(
        htf_high=htf_high,
        htf_low=htf_low,
        htf_range=rng,
        current_price=current,
        position_pct=round(pct, 2),
        zone=zone,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Sweep Detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_sweeps(
    df: pd.DataFrame,
    htf_high: float | None = None,
    htf_low: float | None = None,
    lookback: int = 10,
    reversal_bars: int = 3,
) -> List[SweepEvent]:
    """Detect when price sweeps above / below the HTF range boundary and
    then reverses.

    A "sweep" occurs when price exceeds the boundary (wick) but closes
    back inside within *reversal_bars*.
    """
    if htf_high is None or htf_low is None:
        window = min(24, len(df))
        htf_high = float(df["high"].iloc[-window:].max())
        htf_low = float(df["low"].iloc[-window:].min())

    sweeps: List[SweepEvent] = []
    start = max(0, len(df) - lookback)
    
    vol_sma = df["volume"].rolling(window=min(20, len(df)), min_periods=1).mean().values

    for i in range(start, len(df)):
        h = float(df["high"].iat[i])
        l = float(df["low"].iat[i])
        c = float(df["close"].iat[i])

        # Calculate volume confirmation parameters at sweep index i
        sma_val = vol_sma[i] if i < len(vol_sma) else (vol_sma[-1] if len(vol_sma) > 0 else 0.0)
        curr_vol = df["volume"].iat[i]
        vol_ratio = (curr_vol / sma_val) if sma_val > 0 else 1.0
        vol_confirmed = vol_ratio >= 1.2

        # Sweep high: wick above htf_high but close below
        if h > htf_high and c < htf_high:
            # Check for reversal in following bars
            for j in range(i + 1, min(i + reversal_bars + 1, len(df))):
                if df["close"].iat[j] < df["open"].iat[j]:  # bearish close
                    sweeps.append(SweepEvent(
                        direction=SweepDirection.SWEEP_HIGH,
                        sweep_price=h,
                        reversal_price=float(df["close"].iat[j]),
                        sweep_index=i,
                        reversal_index=j,
                        detail=f"Price swept HTF high {htf_high:.4f} to {h:.4f}, reversed bearish (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                    break

        # Sweep low: wick below htf_low but close above
        if l < htf_low and c > htf_low:
            for j in range(i + 1, min(i + reversal_bars + 1, len(df))):
                if df["close"].iat[j] > df["open"].iat[j]:  # bullish close
                    sweeps.append(SweepEvent(
                        direction=SweepDirection.SWEEP_LOW,
                        sweep_price=l,
                        reversal_price=float(df["close"].iat[j]),
                        sweep_index=i,
                        reversal_index=j,
                        detail=f"Price swept HTF low {htf_low:.4f} to {l:.4f}, reversed bullish (Volume ratio: {vol_ratio:.2f})",
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                    break

    return sweeps


# ═══════════════════════════════════════════════════════════════════════════
# CRT Signal Generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_crt_signals(
    sweeps: List[SweepEvent],
    range_pos: Optional[RangePosition],
    range_analysis: RangeAnalysis,
) -> List[CRTSignal]:
    """Generate entry signals based on sweeps.

    When price sweeps one side of the HTF range and reverses, signal
    an entry in the reversal direction.
    """
    signals: List[CRTSignal] = []
    for sweep in sweeps:
        if sweep.direction == SweepDirection.SWEEP_HIGH:
            # Sweep high + reversal → short signal
            confidence = 60.0
            if range_pos and range_pos.zone == RangeZone.PREMIUM:
                confidence += 15.0
            if range_analysis.range_state == RangeState.EXPANDING:
                confidence += 10.0
            signals.append(CRTSignal(
                direction="short",
                entry_zone_high=sweep.reversal_price,
                entry_zone_low=sweep.reversal_price - range_analysis.atr_value * 0.3,
                sweep_event=sweep,
                confidence=min(95.0, confidence),
                detail="Sweep of HTF high followed by bearish reversal – short entry",
            ))

        elif sweep.direction == SweepDirection.SWEEP_LOW:
            confidence = 60.0
            if range_pos and range_pos.zone == RangeZone.DISCOUNT:
                confidence += 15.0
            if range_analysis.range_state == RangeState.EXPANDING:
                confidence += 10.0
            signals.append(CRTSignal(
                direction="long",
                entry_zone_high=sweep.reversal_price + range_analysis.atr_value * 0.3,
                entry_zone_low=sweep.reversal_price,
                sweep_event=sweep,
                confidence=min(95.0, confidence),
                detail="Sweep of HTF low followed by bullish reversal – long entry",
            ))

    return signals


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def analyse_crt(
    df: pd.DataFrame,
    htf_high: float | None = None,
    htf_low: float | None = None,
) -> CRTResult:
    """Run full Candle Range Theory analysis.

    Args:
        df: OHLCV DataFrame (ideally lower timeframe within an HTF candle).
        htf_high: Higher-timeframe candle high (auto-detected if None).
        htf_low: Higher-timeframe candle low (auto-detected if None).

    Returns:
        :class:`CRTResult` with range analysis, position, sweeps, signals.
    """
    range_analysis = analyse_range(df)
    range_pos = compute_range_position(df, htf_high, htf_low)
    sweeps = detect_sweeps(df, htf_high, htf_low)
    signals = generate_crt_signals(sweeps, range_pos, range_analysis)

    return CRTResult(
        range_analysis=range_analysis,
        range_position=range_pos,
        sweeps=sweeps,
        signals=signals,
    )
