"""
TradeMinds AI – Support & Resistance Analysis

Identifies:
    * Horizontal S/R from price pivots (touch counting + recency weighting)
    * Dynamic S/R from EMAs
    * Fibonacci retracement levels
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

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

class LevelType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"
    FIBONACCI = "fibonacci"
    DYNAMIC = "dynamic"


@dataclass
class SRLevel:
    """A support or resistance level with a strength score."""

    price: float
    level_type: LevelType
    strength: float  # 0-100
    touches: int = 0
    label: str = ""
    extra: Dict[str, float] = field(default_factory=dict)


@dataclass
class SupportResistanceResult:
    """Aggregated S/R output."""

    horizontal_levels: List[SRLevel]
    dynamic_levels: List[SRLevel]
    fibonacci_levels: List[SRLevel]
    nearest_support: Optional[SRLevel] = None
    nearest_resistance: Optional[SRLevel] = None


# ═══════════════════════════════════════════════════════════════════════════
# Horizontal S/R from pivots
# ═══════════════════════════════════════════════════════════════════════════

def _cluster_levels(
    prices: List[Tuple[float, int]],
    tolerance_pct: float = 0.5,
) -> List[Tuple[float, int, int]]:
    """Group nearby prices into clusters.

    Args:
        prices: ``(price, bar_index)`` pairs.
        tolerance_pct: Maximum percentage distance to consider two
            prices part of the same cluster.

    Returns:
        ``(avg_price, touch_count, latest_index)`` per cluster, sorted
        by price ascending.
    """
    if not prices:
        return []

    sorted_prices = sorted(prices, key=lambda x: x[0])
    clusters: List[List[Tuple[float, int]]] = []
    current_cluster: List[Tuple[float, int]] = [sorted_prices[0]]

    for p, idx in sorted_prices[1:]:
        cluster_avg = np.mean([cp for cp, _ in current_cluster])
        if abs(p - cluster_avg) / cluster_avg * 100 <= tolerance_pct:
            current_cluster.append((p, idx))
        else:
            clusters.append(current_cluster)
            current_cluster = [(p, idx)]
    clusters.append(current_cluster)

    result: List[Tuple[float, int, int]] = []
    for cl in clusters:
        avg_price = float(np.mean([cp for cp, _ in cl]))
        touch_count = len(cl)
        latest_idx = max(idx for _, idx in cl)
        result.append((avg_price, touch_count, latest_idx))

    return sorted(result, key=lambda x: x[0])


def identify_horizontal_sr(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    tolerance_pct: float = 0.5,
) -> List[SRLevel]:
    """Derive horizontal S/R levels from swing points.

    Strength is a function of:
        * Number of touches (more is stronger)
        * Recency (recent touches weight more)
    """
    current_price = float(df["close"].iloc[-1])
    n = len(df)

    prices_with_idx = [(sp.price, sp.index) for sp in swings]
    clusters = _cluster_levels(prices_with_idx, tolerance_pct)

    levels: List[SRLevel] = []
    for avg_price, touches, latest_idx in clusters:
        # Recency factor: 1.0 if latest touch is the most recent bar, decays
        recency = max(0.0, 1.0 - (n - latest_idx) / max(n, 1))
        strength = min(100.0, touches * 20.0 + recency * 30.0)

        if avg_price < current_price:
            level_type = LevelType.SUPPORT
            label = f"Support @ {avg_price:.4f} ({touches} touches)"
        else:
            level_type = LevelType.RESISTANCE
            label = f"Resistance @ {avg_price:.4f} ({touches} touches)"

        levels.append(SRLevel(
            price=avg_price,
            level_type=level_type,
            strength=strength,
            touches=touches,
            label=label,
        ))

    return sorted(levels, key=lambda lv: -lv.strength)


# ═══════════════════════════════════════════════════════════════════════════
# Dynamic S/R from EMAs
# ═══════════════════════════════════════════════════════════════════════════

def identify_dynamic_sr(
    df: pd.DataFrame,
    ema_periods: List[int] | None = None,
) -> List[SRLevel]:
    """EMA values act as dynamic support/resistance."""
    ema_periods = ema_periods or [21, 50, 200]
    current_price = float(df["close"].iloc[-1])
    levels: List[SRLevel] = []

    for period in ema_periods:
        if len(df) < period:
            continue
        ema = df["close"].ewm(span=period, adjust=False).mean()
        ema_val = float(ema.iloc[-1])

        # Strength based on how important the EMA is
        strength_map = {200: 90.0, 50: 70.0, 21: 50.0}
        strength = strength_map.get(period, 40.0)

        if ema_val < current_price:
            level_type = LevelType.SUPPORT
        else:
            level_type = LevelType.RESISTANCE

        levels.append(SRLevel(
            price=ema_val,
            level_type=level_type,
            strength=strength,
            label=f"EMA({period}) dynamic {'support' if level_type == LevelType.SUPPORT else 'resistance'}",
            extra={"ema_period": float(period)},
        ))

    return levels


# ═══════════════════════════════════════════════════════════════════════════
# Fibonacci Retracement
# ═══════════════════════════════════════════════════════════════════════════

FIBONACCI_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]


def compute_fibonacci_retracements(
    df: pd.DataFrame,
    swings: List[SwingPoint] | None = None,
) -> List[SRLevel]:
    """Compute Fibonacci retracement levels from the most recent
    significant swing high to swing low (or vice-versa).

    Returns levels at 0.236, 0.382, 0.5, 0.618, 0.786.
    """
    if swings is None:
        swings = detect_swing_points(df)

    swing_highs = [s for s in swings if s.swing_type == SwingType.HIGH]
    swing_lows = [s for s in swings if s.swing_type == SwingType.LOW]

    if not swing_highs or not swing_lows:
        return []

    # Use the most recent significant high & low
    recent_high = max(swing_highs[-5:], key=lambda s: s.price)
    recent_low = min(swing_lows[-5:], key=lambda s: s.price)

    high_price = recent_high.price
    low_price = recent_low.price
    price_range = high_price - low_price

    if price_range <= 0:
        return []

    current_price = float(df["close"].iloc[-1])

    # Determine direction: if high came after low → upswing retracement
    upswing = recent_high.index > recent_low.index

    levels: List[SRLevel] = []
    for ratio in FIBONACCI_LEVELS:
        if upswing:
            fib_price = high_price - ratio * price_range
        else:
            fib_price = low_price + ratio * price_range

        lt = LevelType.SUPPORT if fib_price < current_price else LevelType.RESISTANCE
        levels.append(SRLevel(
            price=fib_price,
            level_type=LevelType.FIBONACCI,
            strength=65.0 if ratio in (0.5, 0.618) else 50.0,
            label=f"Fib {ratio:.3f} @ {fib_price:.4f}",
            extra={"ratio": ratio, "swing_high": high_price, "swing_low": low_price},
        ))

    return levels


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def analyse_support_resistance(
    df: pd.DataFrame,
    lookback: int = 5,
    tolerance_pct: float = 0.5,
) -> SupportResistanceResult:
    """Run full S/R analysis.

    Returns:
        :class:`SupportResistanceResult` with horizontal, dynamic, and
        Fibonacci levels plus the nearest support and resistance.
    """
    swings = detect_swing_points(df, lookback=lookback)
    horizontal = identify_horizontal_sr(df, swings, tolerance_pct)
    dynamic = identify_dynamic_sr(df)
    fib = compute_fibonacci_retracements(df, swings)

    current_price = float(df["close"].iloc[-1])

    # Find nearest support and resistance across all levels
    all_levels = horizontal + dynamic + fib
    supports = [lv for lv in all_levels if lv.price < current_price]
    resistances = [lv for lv in all_levels if lv.price > current_price]

    nearest_support = max(supports, key=lambda lv: lv.price) if supports else None
    nearest_resistance = min(resistances, key=lambda lv: lv.price) if resistances else None

    return SupportResistanceResult(
        horizontal_levels=horizontal,
        dynamic_levels=dynamic,
        fibonacci_levels=fib,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
    )

