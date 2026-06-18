"""
TradeMinds AI – Candlestick Pattern Detection

Detects classical candlestick patterns on an OHLCV DataFrame.

Bullish patterns:
    Hammer, Morning Star, Bullish Engulfing, Three White Soldiers,
    Dragonfly Doji

Bearish patterns:
    Shooting Star, Evening Star, Bearish Engulfing, Three Black Crows,
    Gravestone Doji

Neutral patterns:
    Doji, Spinning Top

Each detector returns a list of :class:`PatternMatch` instances found in
the most recent N candles (default 5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class PatternStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass
class PatternMatch:
    """A single detected candlestick pattern."""

    name: str
    pattern_type: PatternType
    strength: PatternStrength
    candle_index: int  # index position in the DataFrame
    detail: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _body(o: float, c: float) -> float:
    return abs(c - o)


def _upper_shadow(h: float, o: float, c: float) -> float:
    return h - max(o, c)


def _lower_shadow(l: float, o: float, c: float) -> float:
    return min(o, c) - l


def _is_bullish_candle(o: float, c: float) -> bool:
    return c > o


def _is_bearish_candle(o: float, c: float) -> bool:
    return c < o


def _avg_body(df: pd.DataFrame, end: int, lookback: int = 14) -> float:
    """Average absolute body size over *lookback* candles ending at *end*."""
    start = max(0, end - lookback)
    bodies = (df["close"].iloc[start:end] - df["open"].iloc[start:end]).abs()
    return float(bodies.mean()) if len(bodies) > 0 else 0.0001


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE-CANDLE patterns
# ═══════════════════════════════════════════════════════════════════════════

def _detect_doji(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Doji – body ≤ 10 % of average body."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    if body <= avg_b * 0.1:
        return PatternMatch(
            name="Doji", pattern_type=PatternType.NEUTRAL,
            strength=PatternStrength.MODERATE, candle_index=idx,
            detail="Body is negligible – market indecision",
        )
    return None


def _detect_dragonfly_doji(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Dragonfly Doji – long lower shadow, no upper shadow, tiny body.  Bullish reversal."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    us = _upper_shadow(h, o, c)
    ls = _lower_shadow(l, o, c)
    total_range = h - l if h != l else 0.0001
    if body <= avg_b * 0.1 and us / total_range < 0.05 and ls / total_range > 0.60:
        return PatternMatch(
            name="Dragonfly Doji", pattern_type=PatternType.BULLISH,
            strength=PatternStrength.MODERATE, candle_index=idx,
            detail="Long lower shadow rejected lower prices",
        )
    return None


def _detect_gravestone_doji(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Gravestone Doji – long upper shadow, no lower shadow, tiny body.  Bearish reversal."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    us = _upper_shadow(h, o, c)
    ls = _lower_shadow(l, o, c)
    total_range = h - l if h != l else 0.0001
    if body <= avg_b * 0.1 and ls / total_range < 0.05 and us / total_range > 0.60:
        return PatternMatch(
            name="Gravestone Doji", pattern_type=PatternType.BEARISH,
            strength=PatternStrength.MODERATE, candle_index=idx,
            detail="Long upper shadow rejected higher prices",
        )
    return None


def _detect_hammer(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Hammer – small body near the top, long lower shadow ≥ 2× body.  Bullish in downtrend."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    if body < avg_b * 0.05:
        return None  # too tiny – better classified as doji
    ls = _lower_shadow(l, o, c)
    us = _upper_shadow(h, o, c)
    if ls >= 2 * body and us <= body * 0.5:
        return PatternMatch(
            name="Hammer", pattern_type=PatternType.BULLISH,
            strength=PatternStrength.MODERATE, candle_index=idx,
            detail="Long lower wick shows buying pressure",
        )
    return None


def _detect_shooting_star(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Shooting Star – small body near the bottom, long upper shadow.  Bearish in uptrend."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    if body < avg_b * 0.05:
        return None
    ls = _lower_shadow(l, o, c)
    us = _upper_shadow(h, o, c)
    if us >= 2 * body and ls <= body * 0.5:
        return PatternMatch(
            name="Shooting Star", pattern_type=PatternType.BEARISH,
            strength=PatternStrength.MODERATE, candle_index=idx,
            detail="Long upper wick shows selling pressure",
        )
    return None


def _detect_spinning_top(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Spinning Top – small body with relatively equal shadows."""
    o, h, l, c = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body = _body(o, c)
    us = _upper_shadow(h, o, c)
    ls = _lower_shadow(l, o, c)
    total_range = h - l if h != l else 0.0001
    body_ratio = body / total_range
    if 0.10 < body_ratio < 0.35 and us > body * 0.8 and ls > body * 0.8:
        return PatternMatch(
            name="Spinning Top", pattern_type=PatternType.NEUTRAL,
            strength=PatternStrength.WEAK, candle_index=idx,
            detail="Small body with long shadows – indecision",
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# TWO-CANDLE patterns
# ═══════════════════════════════════════════════════════════════════════════

def _detect_bullish_engulfing(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Bullish Engulfing – bearish candle followed by a larger bullish candle that engulfs it."""
    if idx < 1:
        return None
    o1, c1 = df["open"].iat[idx - 1], df["close"].iat[idx - 1]
    o2, c2 = df["open"].iat[idx], df["close"].iat[idx]
    if _is_bearish_candle(o1, c1) and _is_bullish_candle(o2, c2):
        if o2 <= c1 and c2 >= o1:
            strength = PatternStrength.STRONG if _body(o2, c2) > avg_b * 1.5 else PatternStrength.MODERATE
            return PatternMatch(
                name="Bullish Engulfing", pattern_type=PatternType.BULLISH,
                strength=strength, candle_index=idx,
                detail="Bullish candle fully engulfs prior bearish candle",
            )
    return None


def _detect_bearish_engulfing(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Bearish Engulfing – bullish candle followed by a larger bearish candle."""
    if idx < 1:
        return None
    o1, c1 = df["open"].iat[idx - 1], df["close"].iat[idx - 1]
    o2, c2 = df["open"].iat[idx], df["close"].iat[idx]
    if _is_bullish_candle(o1, c1) and _is_bearish_candle(o2, c2):
        if o2 >= c1 and c2 <= o1:
            strength = PatternStrength.STRONG if _body(o2, c2) > avg_b * 1.5 else PatternStrength.MODERATE
            return PatternMatch(
                name="Bearish Engulfing", pattern_type=PatternType.BEARISH,
                strength=strength, candle_index=idx,
                detail="Bearish candle fully engulfs prior bullish candle",
            )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# THREE-CANDLE patterns
# ═══════════════════════════════════════════════════════════════════════════

def _detect_morning_star(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Morning Star – bearish candle, small body / doji, bullish candle closing above midpoint."""
    if idx < 2:
        return None
    o1, c1 = df["open"].iat[idx - 2], df["close"].iat[idx - 2]
    o2, c2 = df["open"].iat[idx - 1], df["close"].iat[idx - 1]
    o3, c3 = df["open"].iat[idx], df["close"].iat[idx]
    body1 = _body(o1, c1)
    body2 = _body(o2, c2)
    body3 = _body(o3, c3)
    mid1 = (o1 + c1) / 2.0

    if (
        _is_bearish_candle(o1, c1)
        and body1 > avg_b * 0.5
        and body2 < avg_b * 0.4
        and _is_bullish_candle(o3, c3)
        and body3 > avg_b * 0.5
        and c3 > mid1
    ):
        return PatternMatch(
            name="Morning Star", pattern_type=PatternType.BULLISH,
            strength=PatternStrength.STRONG, candle_index=idx,
            detail="Three-candle bullish reversal pattern",
        )
    return None


def _detect_evening_star(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Evening Star – bullish candle, small body / doji, bearish candle closing below midpoint."""
    if idx < 2:
        return None
    o1, c1 = df["open"].iat[idx - 2], df["close"].iat[idx - 2]
    o2, c2 = df["open"].iat[idx - 1], df["close"].iat[idx - 1]
    o3, c3 = df["open"].iat[idx], df["close"].iat[idx]
    body1 = _body(o1, c1)
    body2 = _body(o2, c2)
    body3 = _body(o3, c3)
    mid1 = (o1 + c1) / 2.0

    if (
        _is_bullish_candle(o1, c1)
        and body1 > avg_b * 0.5
        and body2 < avg_b * 0.4
        and _is_bearish_candle(o3, c3)
        and body3 > avg_b * 0.5
        and c3 < mid1
    ):
        return PatternMatch(
            name="Evening Star", pattern_type=PatternType.BEARISH,
            strength=PatternStrength.STRONG, candle_index=idx,
            detail="Three-candle bearish reversal pattern",
        )
    return None


def _detect_three_white_soldiers(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Three White Soldiers – three consecutive bullish candles with higher closes."""
    if idx < 2:
        return None
    candles = []
    for i in range(idx - 2, idx + 1):
        o, c = df["open"].iat[i], df["close"].iat[i]
        candles.append((o, c))

    all_bullish = all(_is_bullish_candle(o, c) for o, c in candles)
    higher_closes = candles[0][1] < candles[1][1] < candles[2][1]
    higher_opens = candles[0][0] < candles[1][0] < candles[2][0]
    decent_bodies = all(_body(o, c) > avg_b * 0.4 for o, c in candles)

    if all_bullish and higher_closes and higher_opens and decent_bodies:
        return PatternMatch(
            name="Three White Soldiers", pattern_type=PatternType.BULLISH,
            strength=PatternStrength.STRONG, candle_index=idx,
            detail="Three consecutive strong bullish candles",
        )
    return None


def _detect_three_black_crows(df: pd.DataFrame, idx: int, avg_b: float) -> PatternMatch | None:
    """Three Black Crows – three consecutive bearish candles with lower closes."""
    if idx < 2:
        return None
    candles = []
    for i in range(idx - 2, idx + 1):
        o, c = df["open"].iat[i], df["close"].iat[i]
        candles.append((o, c))

    all_bearish = all(_is_bearish_candle(o, c) for o, c in candles)
    lower_closes = candles[0][1] > candles[1][1] > candles[2][1]
    lower_opens = candles[0][0] > candles[1][0] > candles[2][0]
    decent_bodies = all(_body(o, c) > avg_b * 0.4 for o, c in candles)

    if all_bearish and lower_closes and lower_opens and decent_bodies:
        return PatternMatch(
            name="Three Black Crows", pattern_type=PatternType.BEARISH,
            strength=PatternStrength.STRONG, candle_index=idx,
            detail="Three consecutive strong bearish candles",
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

ALL_DETECTORS = [
    _detect_doji,
    _detect_dragonfly_doji,
    _detect_gravestone_doji,
    _detect_hammer,
    _detect_shooting_star,
    _detect_spinning_top,
    _detect_bullish_engulfing,
    _detect_bearish_engulfing,
    _detect_morning_star,
    _detect_evening_star,
    _detect_three_white_soldiers,
    _detect_three_black_crows,
]


def detect_patterns(df: pd.DataFrame, lookback: int = 5) -> List[PatternMatch]:
    """Scan the last *lookback* candles for candlestick patterns.

    Args:
        df: OHLCV DataFrame (must have ``open, high, low, close`` columns).
        lookback: How many recent candles to scan.

    Returns:
        A list of :class:`PatternMatch` instances (may be empty).
    """
    if len(df) < 3:
        return []

    matches: List[PatternMatch] = []
    start = max(0, len(df) - lookback)

    for idx in range(start, len(df)):
        avg_b = _avg_body(df, idx)
        for detector in ALL_DETECTORS:
            try:
                result = detector(df, idx, avg_b)
                if result is not None:
                    matches.append(result)
            except Exception:
                logger.debug("Pattern detector %s failed at idx %d", detector.__name__, idx, exc_info=True)

    return matches
