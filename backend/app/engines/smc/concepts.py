"""
TradeMinds AI – Smart Money Concepts (SMC)

Detects:
    * Order Blocks (OB) – bullish & bearish, mitigated tracking
    * Fair Value Gaps (FVG / Imbalance) – bullish & bearish, fill tracking
    * Liquidity Zones – equal highs / lows clusters
    * Breaker Blocks – failed order blocks that flip into S/R
    * Premium / Discount Zones – based on swing range
    * Institutional Displacement – strong momentum candles
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engines.market_structure.structure import (
    SwingPoint,
    SwingType,
    detect_swing_points,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SMCType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass
class OrderBlock:
    """A detected order block zone."""

    ob_type: SMCType
    high: float
    low: float
    index: int
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    volume_confirmed: bool = True
    volume_ratio: float = 1.0


@dataclass
class FairValueGap:
    """A detected fair-value gap (imbalance)."""

    fvg_type: SMCType
    high: float  # top of gap
    low: float   # bottom of gap
    index: int   # middle candle index
    filled: bool = False
    filled_index: Optional[int] = None
    volume_confirmed: bool = True
    volume_ratio: float = 1.0


@dataclass
class LiquidityZone:
    """A cluster of equal highs or lows."""

    zone_type: str  # "equal_highs" or "equal_lows"
    price: float
    count: int
    indices: List[int] = field(default_factory=list)
    swept: bool = False


@dataclass
class BreakerBlock:
    """A failed order block that has become S/R."""

    bb_type: SMCType
    high: float
    low: float
    original_ob_index: int
    breaker_index: int
    volume_confirmed: bool = True
    volume_ratio: float = 1.0


@dataclass
class PremiumDiscount:
    """Premium / Discount zone classification."""

    swing_high: float
    swing_low: float
    equilibrium: float
    current_zone: str  # "premium", "discount", "equilibrium"
    position_pct: float  # 0 = swing low, 100 = swing high


@dataclass
class DisplacementCandle:
    """An institutional displacement candle."""

    direction: SMCType
    body_size: float
    body_pct_of_atr: float
    index: int


@dataclass
class SMCResult:
    """Aggregated SMC analysis output."""

    order_blocks: List[OrderBlock]
    fair_value_gaps: List[FairValueGap]
    liquidity_zones: List[LiquidityZone]
    breaker_blocks: List[BreakerBlock]
    premium_discount: Optional[PremiumDiscount]
    displacement_candles: List[DisplacementCandle]


# ═══════════════════════════════════════════════════════════════════════════
# Order Block Detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_order_blocks(
    df: pd.DataFrame,
    atr_multiplier: float = 1.5,
    lookback: int = 50,
) -> List[OrderBlock]:
    """Identify order blocks.

    Bullish OB: the last bearish candle before a strong bullish move.
    Bearish OB: the last bullish candle before a strong bearish move.

    A "strong move" is defined as a candle whose body exceeds
    ``atr_multiplier × ATR(14)``.
    """
    if len(df) < 20:
        return []

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values

    # ATR for "strong move" threshold
    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean().values

    # Volume SMA for confirmation
    vol_sma = df["volume"].rolling(window=min(20, len(df)), min_periods=1).mean().values

    obs: List[OrderBlock] = []
    start = max(1, len(df) - lookback)

    for i in range(start, len(df)):
        body = abs(closes[i] - opens[i])
        threshold = atr[i] * atr_multiplier if not np.isnan(atr[i]) else body * 2

        # Calculate volume confirmation parameters at breakout index i
        sma_val = vol_sma[i] if i < len(vol_sma) else (vol_sma[-1] if len(vol_sma) > 0 else 0.0)
        curr_vol = df["volume"].iat[i]
        vol_ratio = (curr_vol / sma_val) if sma_val > 0 else 1.0
        vol_confirmed = vol_ratio >= 1.2

        # Bullish OB: candle i is a strong bullish candle
        if closes[i] > opens[i] and body > threshold:
            # Look back for last bearish candle
            for j in range(i - 1, max(i - 6, start - 1), -1):
                if closes[j] < opens[j]:  # bearish
                    obs.append(OrderBlock(
                        ob_type=SMCType.BULLISH,
                        high=float(highs[j]),
                        low=float(lows[j]),
                        index=j,
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                    break

        # Bearish OB: candle i is a strong bearish candle
        if closes[i] < opens[i] and body > threshold:
            for j in range(i - 1, max(i - 6, start - 1), -1):
                if closes[j] > opens[j]:  # bullish
                    obs.append(OrderBlock(
                        ob_type=SMCType.BEARISH,
                        high=float(highs[j]),
                        low=float(lows[j]),
                        index=j,
                        volume_confirmed=vol_confirmed,
                        volume_ratio=float(vol_ratio),
                    ))
                    break

    # Mark mitigated OBs.
    # Mitigation occurs when price trades into the 50 % midpoint of the OB body
    # (the "Consequent Encroachment" / CEI level), not merely touches the wick.
    # Using the candle's open/close midpoint because OBs are defined by their
    # body, while high/low represent wicks that may briefly be pierced without
    # invalidating the zone.
    for ob in obs:
        ob_open  = float(opens[ob.index])
        ob_close = float(closes[ob.index])
        ob_mid   = (ob_open + ob_close) / 2.0  # 50 % of the OB candle body

        for k in range(ob.index + 1, len(df)):
            if ob.ob_type == SMCType.BULLISH and lows[k] <= ob_mid:
                ob.mitigated = True
                ob.mitigated_index = k
                break
            if ob.ob_type == SMCType.BEARISH and highs[k] >= ob_mid:
                ob.mitigated = True
                ob.mitigated_index = k
                break

    return obs


# ═══════════════════════════════════════════════════════════════════════════
# Fair Value Gap (FVG) Detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_fair_value_gaps(
    df: pd.DataFrame,
    lookback: int = 50,
) -> List[FairValueGap]:
    """Three-candle imbalance detection.

    Bullish FVG: candle_1.high < candle_3.low  (gap between candle 1 high
    and candle 3 low, with candle 2 being a strong move).

    Bearish FVG: candle_1.low > candle_3.high.
    """
    if len(df) < 3:
        return []

    highs = df["high"].values
    lows = df["low"].values

    fvgs: List[FairValueGap] = []
    start = max(0, len(df) - lookback)
    
    vol_sma = df["volume"].rolling(window=min(20, len(df)), min_periods=1).mean().values

    for i in range(start + 2, len(df)):
        # Calculate volume ratio at the middle FVG candle (index i - 1)
        sma_val = vol_sma[i - 1] if (i - 1) < len(vol_sma) else (vol_sma[-1] if len(vol_sma) > 0 else 0.0)
        curr_vol = df["volume"].iat[i - 1]
        vol_ratio = (curr_vol / sma_val) if sma_val > 0 else 1.0
        vol_confirmed = vol_ratio >= 1.2

        # Bullish FVG
        if highs[i - 2] < lows[i]:
            fvgs.append(FairValueGap(
                fvg_type=SMCType.BULLISH,
                high=float(lows[i]),
                low=float(highs[i - 2]),
                index=i - 1,
                volume_confirmed=vol_confirmed,
                volume_ratio=float(vol_ratio),
            ))

        # Bearish FVG
        if lows[i - 2] > highs[i]:
            fvgs.append(FairValueGap(
                fvg_type=SMCType.BEARISH,
                high=float(lows[i - 2]),
                low=float(highs[i]),
                index=i - 1,
                volume_confirmed=vol_confirmed,
                volume_ratio=float(vol_ratio),
            ))

    # Mark filled FVGs
    for fvg in fvgs:
        for k in range(fvg.index + 2, len(df)):
            if fvg.fvg_type == SMCType.BULLISH and lows[k] <= fvg.low:
                fvg.filled = True
                fvg.filled_index = k
                break
            if fvg.fvg_type == SMCType.BEARISH and highs[k] >= fvg.high:
                fvg.filled = True
                fvg.filled_index = k
                break

    return fvgs


# ═══════════════════════════════════════════════════════════════════════════
# Liquidity Zones (Equal Highs / Lows)
# ═══════════════════════════════════════════════════════════════════════════

def detect_liquidity_zones(
    df: pd.DataFrame,
    tolerance_pct: float = 0.1,
    min_touches: int = 2,
    lookback: int = 80,
) -> List[LiquidityZone]:
    """Cluster equal highs and equal lows where stop losses likely reside."""
    zones: List[LiquidityZone] = []
    start = max(0, len(df) - lookback)
    highs = df["high"].values[start:]
    lows = df["low"].values[start:]
    offset = start

    # --- Equal Highs ---
    high_clusters = _cluster_prices(highs, tolerance_pct, offset)
    for price, indices in high_clusters:
        if len(indices) >= min_touches:
            swept = bool(df["high"].values[-1] > price) if len(df) > 0 else False
            zones.append(LiquidityZone("equal_highs", price, len(indices), indices, swept))

    # --- Equal Lows ---
    low_clusters = _cluster_prices(lows, tolerance_pct, offset)
    for price, indices in low_clusters:
        if len(indices) >= min_touches:
            swept = bool(df["low"].values[-1] < price) if len(df) > 0 else False
            zones.append(LiquidityZone("equal_lows", price, len(indices), indices, swept))

    return zones


def _cluster_prices(
    prices: np.ndarray,
    tolerance_pct: float,
    offset: int,
) -> List[Tuple[float, List[int]]]:
    """Group prices within *tolerance_pct* %."""
    if len(prices) == 0:
        return []

    indexed = sorted(enumerate(prices, start=offset), key=lambda x: x[1])
    clusters: List[Tuple[float, List[int]]] = []
    cur_indices = [indexed[0][0]]
    cur_sum = indexed[0][1]

    for idx, price in indexed[1:]:
        avg = cur_sum / len(cur_indices)
        if abs(price - avg) / max(avg, 0.0001) * 100 <= tolerance_pct:
            cur_indices.append(idx)
            cur_sum += price
        else:
            clusters.append((cur_sum / len(cur_indices), cur_indices))
            cur_indices = [idx]
            cur_sum = price
    clusters.append((cur_sum / len(cur_indices), cur_indices))
    return clusters


# ═══════════════════════════════════════════════════════════════════════════
# Breaker Blocks
# ═══════════════════════════════════════════════════════════════════════════

def detect_breaker_blocks(
    df: pd.DataFrame,
    order_blocks: List[OrderBlock],
) -> List[BreakerBlock]:
    """Breaker blocks are mitigated order blocks that have failed and now
    serve as S/R zones in the opposite direction, confirmed by volume."""
    breakers: List[BreakerBlock] = []
    if len(df) < 20:
        return breakers

    vol_sma = df["volume"].rolling(window=min(20, len(df)), min_periods=1).mean().values

    for ob in order_blocks:
        if ob.mitigated and ob.mitigated_index is not None:
            # Calculate volume ratio at the mitigation index
            mit_idx = ob.mitigated_index
            sma_val = vol_sma[mit_idx] if mit_idx < len(vol_sma) else (vol_sma[-1] if len(vol_sma) > 0 else 0.0)
            curr_vol = df["volume"].iat[mit_idx]
            vol_ratio = (curr_vol / sma_val) if sma_val > 0 else 1.0
            vol_confirmed = vol_ratio >= 1.2

            # Flip type: a failed bullish OB becomes bearish breaker
            flipped = SMCType.BEARISH if ob.ob_type == SMCType.BULLISH else SMCType.BULLISH
            breakers.append(BreakerBlock(
                bb_type=flipped,
                high=ob.high,
                low=ob.low,
                original_ob_index=ob.index,
                breaker_index=ob.mitigated_index,
                volume_confirmed=vol_confirmed,
                volume_ratio=float(vol_ratio),
            ))
    return breakers


# ═══════════════════════════════════════════════════════════════════════════
# Premium / Discount Zones
# ═══════════════════════════════════════════════════════════════════════════

def compute_premium_discount(
    df: pd.DataFrame,
    swings: List[SwingPoint] | None = None,
) -> Optional[PremiumDiscount]:
    """Classify current price as premium, discount, or equilibrium based
    on the most recent swing range.

    Above 50 % of range = premium (sell zone).
    Below 50 % of range = discount (buy zone).
    """
    if swings is None:
        swings = detect_swing_points(df)

    swing_highs = [s for s in swings if s.swing_type == SwingType.HIGH]
    swing_lows = [s for s in swings if s.swing_type == SwingType.LOW]

    if not swing_highs or not swing_lows:
        return None

    sh = max(swing_highs[-5:], key=lambda s: s.price).price
    sl = min(swing_lows[-5:], key=lambda s: s.price).price
    rng = sh - sl
    if rng <= 0:
        return None

    eq = sl + rng * 0.5
    current = float(df["close"].iloc[-1])
    position_pct = ((current - sl) / rng) * 100.0

    if position_pct >= 75:
        zone = "premium"
    elif position_pct <= 25:
        zone = "discount"
    elif 45 <= position_pct <= 55:
        zone = "equilibrium"
    elif position_pct > 50:
        zone = "premium"
    else:
        zone = "discount"

    return PremiumDiscount(
        swing_high=sh,
        swing_low=sl,
        equilibrium=eq,
        current_zone=zone,
        position_pct=round(position_pct, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Institutional Displacement
# ═══════════════════════════════════════════════════════════════════════════

def detect_displacement(
    df: pd.DataFrame,
    atr_multiplier: float = 2.0,
    lookback: int = 20,
) -> List[DisplacementCandle]:
    """Detect strong displacement candles indicating institutional activity.

    A displacement candle has a body ≥ ``atr_multiplier × ATR(14)`` and
    minimal wicks relative to body.
    """
    if len(df) < 15:
        return []

    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean().values

    displacements: List[DisplacementCandle] = []
    start = max(14, len(df) - lookback)

    for i in range(start, len(df)):
        body = abs(df["close"].iat[i] - df["open"].iat[i])
        if np.isnan(atr[i]) or atr[i] == 0:
            continue
        body_pct = body / atr[i]
        if body_pct >= atr_multiplier:
            direction = SMCType.BULLISH if df["close"].iat[i] > df["open"].iat[i] else SMCType.BEARISH
            displacements.append(DisplacementCandle(
                direction=direction,
                body_size=body,
                body_pct_of_atr=round(body_pct, 2),
                index=i,
            ))

    return displacements


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def analyse_smc(
    df: pd.DataFrame,
    lookback: int = 50,
) -> SMCResult:
    """Run the complete Smart Money Concepts analysis.

    Returns:
        :class:`SMCResult` with all SMC data.
    """
    swings = detect_swing_points(df)
    obs = detect_order_blocks(df, lookback=lookback)
    fvgs = detect_fair_value_gaps(df, lookback=lookback)
    liq = detect_liquidity_zones(df, lookback=lookback)
    breakers = detect_breaker_blocks(df, obs)
    pd_zone = compute_premium_discount(df, swings)
    displacements = detect_displacement(df, lookback=min(20, lookback))

    return SMCResult(
        order_blocks=obs,
        fair_value_gaps=fvgs,
        liquidity_zones=liq,
        breaker_blocks=breakers,
        premium_discount=pd_zone,
        displacement_candles=displacements,
    )

