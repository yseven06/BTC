"""
Market Regime detector.

Pure function of OHLCV — no network, no DB — so it can run cheaply inside
every signal scan and inside backtests identically.

The regime is derived from three orthogonal measurements:

  • Trend strength      → ADX(14). ADX doesn't care about direction, only
                          how *strong* the prevailing move is. >25 = trending,
                          <18 = no trend (range).
  • Trend direction     → sign of EMA(20) vs EMA(50) (only meaningful when ADX
                          says there IS a trend).
  • Volatility          → ATR(14) as a percentage of price, compared against
                          its own recent median, so "high volatility" is
                          relative to the asset's own normal — BTC's 1% and a
                          memecoin's 8% can both be "calm" for that asset.
  • Participation        → current volume vs its 20-bar average (thin tape =
                          low-volume regime, where signals are less reliable).

These combine into one of six regimes. The thresholds are intentionally
conservative; the goal is a robust coarse label, not a fragile fine-grained one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np
import pandas as pd


class MarketRegime(str, enum.Enum):
    """Coarse market-condition label."""

    TRENDING_BULL = "trending_bull"   # Strong directional up-move
    TRENDING_BEAR = "trending_bear"   # Strong directional down-move
    RANGING = "ranging"               # Sideways / mean-reverting
    VOLATILE_HIGH = "volatile_high"   # Whippy / panic — high ATR, no clean trend
    LOW_VOLUME = "low_volume"         # Thin tape — signals less reliable
    BREAKOUT = "breakout"             # Volatility + volume expansion out of a range
    UNKNOWN = "unknown"               # Not enough data


@dataclass
class RegimeResult:
    """Result of regime detection, including the raw metrics behind it so the
    snapshot can store *why* a regime was chosen, not just the label."""

    regime: MarketRegime
    adx: float
    atr_pct: float
    atr_pct_median: float
    volume_ratio: float          # current vol / 20-bar avg
    trend_direction: str         # "bullish" | "bearish" | "neutral"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "adx": round(self.adx, 2),
            "atr_pct": round(self.atr_pct, 4),
            "atr_pct_median": round(self.atr_pct_median, 4),
            "volume_ratio": round(self.volume_ratio, 3),
            "trend_direction": self.trend_direction,
            "notes": self.notes,
        }


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (same as an EMA with alpha = 1/period)."""
    return series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def _compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Average Directional Index — trend *strength* regardless of direction."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr = _wilder_smooth(tr, period)
    # Avoid divide-by-zero on flat candles
    atr_safe = atr.replace(0, np.nan)

    plus_di = 100.0 * _wilder_smooth(pd.Series(plus_dm, index=df.index), period) / atr_safe
    minus_di = 100.0 * _wilder_smooth(pd.Series(minus_dm, index=df.index), period) / atr_safe

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = _wilder_smooth(dx.fillna(0.0), period)

    latest = adx.iloc[-1]
    return float(latest) if pd.notna(latest) else 0.0


def detect_regime(df: pd.DataFrame, *, adx_period: int = 14) -> RegimeResult:
    """Classify the market regime from an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume. Returns UNKNOWN if there
    isn't enough data to compute the indicators reliably.
    """
    if df is None or len(df) < max(adx_period * 2, 30):
        return RegimeResult(
            regime=MarketRegime.UNKNOWN,
            adx=0.0, atr_pct=0.0, atr_pct_median=0.0,
            volume_ratio=1.0, trend_direction="neutral",
            notes=["insufficient data for regime detection"],
        )

    close = df["close"]
    price = float(close.iloc[-1])

    # --- Trend strength ---
    adx = _compute_adx(df, adx_period)

    # --- Trend direction (EMA20 vs EMA50) ---
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    if ema20 > ema50:
        trend_direction = "bullish"
    elif ema20 < ema50:
        trend_direction = "bearish"
    else:
        trend_direction = "neutral"

    # --- Volatility: ATR% now vs its own recent median ---
    high, low = df["high"], df["low"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_series = _wilder_smooth(tr, adx_period)
    atr_pct_series = (atr_series / close) * 100.0
    atr_pct = float(atr_pct_series.iloc[-1]) if pd.notna(atr_pct_series.iloc[-1]) else 0.0
    # Median over the last ~50 bars (excluding the current one) as the asset's
    # own "normal" volatility baseline.
    baseline_window = atr_pct_series.iloc[-51:-1].dropna()
    atr_pct_median = float(baseline_window.median()) if len(baseline_window) else atr_pct

    # --- Participation: current volume vs 20-bar average ---
    vol = df["volume"]
    vol_avg = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else float(vol.mean())
    cur_vol = float(vol.iloc[-1])
    volume_ratio = (cur_vol / vol_avg) if vol_avg > 0 else 1.0

    notes: list[str] = []

    # --- Classification (order matters: most specific first) ---
    high_vol = atr_pct_median > 0 and atr_pct > atr_pct_median * 1.6
    very_high_vol = atr_pct_median > 0 and atr_pct > atr_pct_median * 2.2
    thin_tape = volume_ratio < 0.5
    vol_expansion = volume_ratio > 1.8
    is_trending = adx >= 25
    is_ranging = adx < 18

    regime: MarketRegime

    if thin_tape and not is_trending:
        regime = MarketRegime.LOW_VOLUME
        notes.append(f"volume {volume_ratio:.2f}x of 20-bar avg (thin)")
    elif vol_expansion and high_vol and is_ranging:
        # Volatility + volume bursting out of a quiet range = breakout attempt
        regime = MarketRegime.BREAKOUT
        notes.append(f"vol {volume_ratio:.2f}x + ATR {atr_pct:.2f}% (>{atr_pct_median:.2f}% base)")
    elif very_high_vol and not is_trending:
        regime = MarketRegime.VOLATILE_HIGH
        notes.append(f"ATR {atr_pct:.2f}% >> base {atr_pct_median:.2f}%, no clean trend (ADX {adx:.0f})")
    elif is_trending:
        regime = (
            MarketRegime.TRENDING_BULL if trend_direction == "bullish"
            else MarketRegime.TRENDING_BEAR if trend_direction == "bearish"
            else MarketRegime.RANGING
        )
        notes.append(f"ADX {adx:.0f} (trending), {trend_direction}")
    elif is_ranging:
        regime = MarketRegime.RANGING
        notes.append(f"ADX {adx:.0f} (no trend)")
    else:
        # ADX in the 18-25 "transition" band — lean on volatility/direction
        if high_vol:
            regime = MarketRegime.VOLATILE_HIGH
            notes.append(f"transitional ADX {adx:.0f}, elevated ATR {atr_pct:.2f}%")
        else:
            regime = MarketRegime.RANGING
            notes.append(f"transitional ADX {adx:.0f}, calm")

    return RegimeResult(
        regime=regime,
        adx=adx,
        atr_pct=atr_pct,
        atr_pct_median=atr_pct_median,
        volume_ratio=volume_ratio,
        trend_direction=trend_direction,
        notes=notes,
    )
