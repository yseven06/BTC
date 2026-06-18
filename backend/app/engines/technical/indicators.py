"""
TradeMinds AI - Technical Indicators Module

Computes a comprehensive set of technical indicators on OHLCV DataFrames.
Each function returns the computed value(s) AND a signal interpretation
(bullish / bearish / neutral).

Categories:
    * Trend – EMA, SMA, VWAP
    * Momentum – RSI, MACD, Stochastic, CCI, Williams %R, MFI
    * Volatility – Bollinger Bands, ATR, Keltner Channel
    * Volume – OBV, Volume SMA, A/D Line
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
# Signal enum shared by all indicator helpers
# ---------------------------------------------------------------------------

class IndicatorSignal(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class IndicatorResult:
    """Container for a single indicator's output."""

    name: str
    value: Any
    signal: IndicatorSignal
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# TREND INDICATORS
# ═══════════════════════════════════════════════════════════════════════════

def compute_ema(df: pd.DataFrame, period: int) -> IndicatorResult:
    """Exponential Moving Average for *period*.

    Signal logic:
        * close > EMA  →  bullish
        * close < EMA  →  bearish
    """
    col = f"ema_{period}"
    ema = df["close"].ewm(span=period, adjust=False).mean()
    latest = float(ema.iloc[-1])
    close = float(df["close"].iloc[-1])
    signal = IndicatorSignal.BULLISH if close > latest else IndicatorSignal.BEARISH
    detail = f"EMA({period})={latest:.4f}  close={close:.4f}"
    return IndicatorResult(name=col, value=latest, signal=signal, detail=detail,
                           extra={"series": ema.tolist()})


def compute_all_emas(df: pd.DataFrame, periods: List[int] | None = None) -> List[IndicatorResult]:
    """Compute EMAs for standard periods."""
    periods = periods or [9, 21, 50, 200]
    return [compute_ema(df, p) for p in periods if len(df) >= p]


def compute_sma(df: pd.DataFrame, period: int) -> IndicatorResult:
    """Simple Moving Average for *period*."""
    sma = df["close"].rolling(window=period).mean()
    latest = float(sma.iloc[-1])
    close = float(df["close"].iloc[-1])
    signal = IndicatorSignal.BULLISH if close > latest else IndicatorSignal.BEARISH
    detail = f"SMA({period})={latest:.4f}  close={close:.4f}"
    return IndicatorResult(name=f"sma_{period}", value=latest, signal=signal, detail=detail,
                           extra={"series": sma.tolist()})


def compute_all_smas(df: pd.DataFrame, periods: List[int] | None = None) -> List[IndicatorResult]:
    periods = periods or [20, 50, 200]
    return [compute_sma(df, p) for p in periods if len(df) >= p]


def compute_vwap(df: pd.DataFrame) -> IndicatorResult:
    """Volume-Weighted Average Price (intraday proxy using cumulative calc).

    For daily / multi-day data the VWAP resets each day in production; here
    we compute a running cumulative VWAP over the supplied data.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap_series = cum_tp_vol / cum_vol
    latest = float(vwap_series.iloc[-1])
    close = float(df["close"].iloc[-1])
    signal = IndicatorSignal.BULLISH if close > latest else IndicatorSignal.BEARISH
    detail = f"VWAP={latest:.4f}  close={close:.4f}"
    return IndicatorResult(name="vwap", value=latest, signal=signal, detail=detail,
                           extra={"series": vwap_series.tolist()})


# ═══════════════════════════════════════════════════════════════════════════
# MOMENTUM INDICATORS
# ═══════════════════════════════════════════════════════════════════════════

def compute_rsi(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Relative Strength Index.

    Signal:
        * RSI > 70  →  bearish (overbought)
        * RSI < 30  →  bullish (oversold)
        * else      →  neutral
    """
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    latest = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0

    if latest >= 70:
        signal = IndicatorSignal.BEARISH
    elif latest <= 30:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"RSI({period})={latest:.2f}"
    return IndicatorResult(name="rsi", value=latest, signal=signal, detail=detail,
                           extra={"series": rsi.tolist(), "period": period})


def compute_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> IndicatorResult:
    """MACD (Moving Average Convergence Divergence).

    Signal:
        * MACD line > signal line  →  bullish
        * MACD line < signal line  →  bearish
    """
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    m = float(macd_line.iloc[-1])
    s = float(signal_line.iloc[-1])
    h = float(histogram.iloc[-1])

    signal = IndicatorSignal.BULLISH if m > s else IndicatorSignal.BEARISH
    detail = f"MACD={m:.4f}  Signal={s:.4f}  Hist={h:.4f}"
    return IndicatorResult(
        name="macd", value=m, signal=signal, detail=detail,
        extra={
            "macd_line": macd_line.tolist(),
            "signal_line": signal_line.tolist(),
            "histogram": histogram.tolist(),
            "latest_histogram": h,
        },
    )


def compute_stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
) -> IndicatorResult:
    """Stochastic Oscillator (%K, %D).

    Signal:
        * %K > 80  →  bearish (overbought)
        * %K < 20  →  bullish (oversold)
        * %K crosses above %D  →  bullish
    """
    low_min = df["low"].rolling(window=k_period).min()
    high_max = df["high"].rolling(window=k_period).max()
    k = 100.0 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(window=d_period).mean()

    k_val = float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else 50.0
    d_val = float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else 50.0

    if k_val > 80:
        signal = IndicatorSignal.BEARISH
    elif k_val < 20:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.BULLISH if k_val > d_val else IndicatorSignal.NEUTRAL

    detail = f"Stoch %K={k_val:.2f}  %D={d_val:.2f}"
    return IndicatorResult(
        name="stochastic", value=k_val, signal=signal, detail=detail,
        extra={"k": k.tolist(), "d": d.tolist()},
    )


def compute_cci(df: pd.DataFrame, period: int = 20) -> IndicatorResult:
    """Commodity Channel Index.

    Signal:
        * CCI > 100  →  bullish (strong trend)
        * CCI < -100  →  bearish
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    latest = float(cci.iloc[-1]) if not np.isnan(cci.iloc[-1]) else 0.0

    if latest > 100:
        signal = IndicatorSignal.BULLISH
    elif latest < -100:
        signal = IndicatorSignal.BEARISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"CCI({period})={latest:.2f}"
    return IndicatorResult(name="cci", value=latest, signal=signal, detail=detail,
                           extra={"series": cci.tolist()})


def compute_williams_r(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Williams %R.

    Signal:
        * %R > -20  →  bearish (overbought)
        * %R < -80  →  bullish (oversold)
    """
    high_max = df["high"].rolling(window=period).max()
    low_min = df["low"].rolling(window=period).min()
    wr = -100.0 * (high_max - df["close"]) / (high_max - low_min).replace(0, np.nan)
    latest = float(wr.iloc[-1]) if not np.isnan(wr.iloc[-1]) else -50.0

    if latest > -20:
        signal = IndicatorSignal.BEARISH
    elif latest < -80:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"Williams %R({period})={latest:.2f}"
    return IndicatorResult(name="williams_r", value=latest, signal=signal, detail=detail,
                           extra={"series": wr.tolist()})


def compute_mfi(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Money Flow Index.

    Signal:
        * MFI > 80  →  bearish (overbought)
        * MFI < 20  →  bullish (oversold)
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    rmf = tp * df["volume"]
    delta = tp.diff()
    pos_flow = rmf.where(delta > 0, 0.0).rolling(window=period).sum()
    neg_flow = rmf.where(delta <= 0, 0.0).rolling(window=period).sum()
    mfi = 100.0 - (100.0 / (1.0 + pos_flow / neg_flow.replace(0, np.nan)))
    latest = float(mfi.iloc[-1]) if not np.isnan(mfi.iloc[-1]) else 50.0

    if latest > 80:
        signal = IndicatorSignal.BEARISH
    elif latest < 20:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"MFI({period})={latest:.2f}"
    return IndicatorResult(name="mfi", value=latest, signal=signal, detail=detail,
                           extra={"series": mfi.tolist()})


# ═══════════════════════════════════════════════════════════════════════════
# VOLATILITY INDICATORS
# ═══════════════════════════════════════════════════════════════════════════

def compute_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> IndicatorResult:
    """Bollinger Bands.

    Signal:
        * close near / above upper band  →  bearish (overbought)
        * close near / below lower band  →  bullish (oversold)
        * bandwidth squeezing  →  neutral (breakout pending)
    """
    sma = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    bandwidth = ((upper - lower) / sma) * 100.0

    close = float(df["close"].iloc[-1])
    u = float(upper.iloc[-1])
    l = float(lower.iloc[-1])
    m = float(sma.iloc[-1])
    bw = float(bandwidth.iloc[-1]) if not np.isnan(bandwidth.iloc[-1]) else 0.0
    pct_b = (close - l) / (u - l) if (u - l) != 0 else 0.5

    if pct_b > 0.95:
        signal = IndicatorSignal.BEARISH
    elif pct_b < 0.05:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"BB({period},{std_dev}) Upper={u:.4f} Mid={m:.4f} Lower={l:.4f} %B={pct_b:.2f}"
    return IndicatorResult(
        name="bollinger_bands", value={"upper": u, "middle": m, "lower": l, "pct_b": pct_b},
        signal=signal, detail=detail,
        extra={
            "upper": upper.tolist(),
            "middle": sma.tolist(),
            "lower": lower.tolist(),
            "bandwidth": bandwidth.tolist(),
        },
    )


def compute_atr(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Average True Range – measures volatility magnitude.

    Signal is always neutral; ATR is used for position sizing / stop
    placement rather than directional signals.
    """
    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    latest = float(atr.iloc[-1])
    close = float(df["close"].iloc[-1])
    atr_pct = (latest / close) * 100.0 if close else 0.0

    detail = f"ATR({period})={latest:.4f}  ({atr_pct:.2f}% of price)"
    return IndicatorResult(
        name="atr", value=latest, signal=IndicatorSignal.NEUTRAL, detail=detail,
        extra={"series": atr.tolist(), "atr_pct": atr_pct},
    )


def compute_keltner_channel(
    df: pd.DataFrame,
    ema_period: int = 20,
    atr_period: int = 14,
    multiplier: float = 2.0,
) -> IndicatorResult:
    """Keltner Channel.

    Signal:
        * close above upper  →  strong bullish trend
        * close below lower  →  strong bearish trend
    """
    ema = df["close"].ewm(span=ema_period, adjust=False).mean()
    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean()

    upper = ema + multiplier * atr
    lower = ema - multiplier * atr

    close = float(df["close"].iloc[-1])
    u = float(upper.iloc[-1])
    l = float(lower.iloc[-1])

    if close > u:
        signal = IndicatorSignal.BULLISH
    elif close < l:
        signal = IndicatorSignal.BEARISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"Keltner({ema_period},{multiplier}) Upper={u:.4f} Lower={l:.4f}"
    return IndicatorResult(
        name="keltner_channel", value={"upper": u, "middle": float(ema.iloc[-1]), "lower": l},
        signal=signal, detail=detail,
        extra={"upper": upper.tolist(), "middle": ema.tolist(), "lower": lower.tolist()},
    )


# ═══════════════════════════════════════════════════════════════════════════
# VOLUME INDICATORS
# ═══════════════════════════════════════════════════════════════════════════

def compute_obv(df: pd.DataFrame) -> IndicatorResult:
    """On-Balance Volume.

    Signal:
        * OBV rising while price rising  →  bullish
        * OBV falling while price rising  →  bearish (divergence)
    """
    direction = np.sign(df["close"].diff()).fillna(0)
    obv = (direction * df["volume"]).cumsum()
    latest = float(obv.iloc[-1])

    # 5-period slope as a proxy for trend
    obv_slope = float(obv.iloc[-1] - obv.iloc[-min(5, len(obv))]) if len(obv) >= 2 else 0.0
    price_slope = float(df["close"].iloc[-1] - df["close"].iloc[-min(5, len(df))]) if len(df) >= 2 else 0.0

    if obv_slope > 0 and price_slope > 0:
        signal = IndicatorSignal.BULLISH
    elif obv_slope < 0 and price_slope < 0:
        signal = IndicatorSignal.BEARISH
    elif obv_slope < 0 and price_slope > 0:
        signal = IndicatorSignal.BEARISH  # bearish divergence
    elif obv_slope > 0 and price_slope < 0:
        signal = IndicatorSignal.BULLISH  # bullish divergence
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"OBV={latest:.0f}  slope(5)={obv_slope:.0f}"
    return IndicatorResult(name="obv", value=latest, signal=signal, detail=detail,
                           extra={"series": obv.tolist()})


def compute_volume_sma(df: pd.DataFrame, period: int = 20) -> IndicatorResult:
    """Volume SMA – flags above-average volume bars.

    Signal:
        * current volume > 2× SMA  →  bullish (high interest)
        * current volume < 0.5× SMA  →  neutral (low interest)
    """
    vol_sma = df["volume"].rolling(window=period, min_periods=1).mean()
    latest_vol = float(df["volume"].iloc[-1])
    latest_sma = float(vol_sma.iloc[-1]) if not np.isnan(vol_sma.iloc[-1]) else latest_vol
    ratio = latest_vol / latest_sma if latest_sma > 0 else 1.0

    if ratio > 2.0:
        signal = IndicatorSignal.BULLISH
    elif ratio < 0.5:
        signal = IndicatorSignal.NEUTRAL
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"Vol={latest_vol:.0f}  SMA({period})={latest_sma:.0f}  ratio={ratio:.2f}"
    return IndicatorResult(
        name="volume_sma", value=latest_sma, signal=signal, detail=detail,
        extra={"series": vol_sma.tolist(), "ratio": ratio},
    )


def compute_ad_line(df: pd.DataFrame) -> IndicatorResult:
    """Accumulation / Distribution Line.

    Signal mirrors OBV: divergences between A/D and price are meaningful.
    """
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (
        (df["high"] - df["low"]).replace(0, np.nan)
    )
    clv = clv.fillna(0)
    ad = (clv * df["volume"]).cumsum()
    latest = float(ad.iloc[-1])

    ad_slope = float(ad.iloc[-1] - ad.iloc[-min(5, len(ad))]) if len(ad) >= 2 else 0.0
    price_slope = float(df["close"].iloc[-1] - df["close"].iloc[-min(5, len(df))]) if len(df) >= 2 else 0.0

    if ad_slope > 0 and price_slope > 0:
        signal = IndicatorSignal.BULLISH
    elif ad_slope < 0 and price_slope > 0:
        signal = IndicatorSignal.BEARISH
    elif ad_slope > 0 and price_slope < 0:
        signal = IndicatorSignal.BULLISH
    else:
        signal = IndicatorSignal.NEUTRAL

    detail = f"A/D={latest:.0f}  slope(5)={ad_slope:.0f}"
    return IndicatorResult(name="ad_line", value=latest, signal=signal, detail=detail,
                           extra={"series": ad.tolist()})


# ═══════════════════════════════════════════════════════════════════════════
# AGGREGATE HELPER
# ═══════════════════════════════════════════════════════════════════════════

def compute_all_indicators(df: pd.DataFrame) -> Dict[str, List[IndicatorResult]]:
    """Run **every** indicator and group results by category.

    Returns:
        Dictionary with keys ``trend``, ``momentum``, ``volatility``, ``volume``.
    """
    results: Dict[str, List[IndicatorResult]] = {
        "trend": [],
        "momentum": [],
        "volatility": [],
        "volume": [],
    }

    # --- Trend ----------------------------------------------------------
    results["trend"].extend(compute_all_emas(df))
    results["trend"].extend(compute_all_smas(df))
    results["trend"].append(compute_vwap(df))

    # --- Momentum -------------------------------------------------------
    results["momentum"].append(compute_rsi(df))
    results["momentum"].append(compute_macd(df))
    results["momentum"].append(compute_stochastic(df))
    results["momentum"].append(compute_cci(df))
    results["momentum"].append(compute_williams_r(df))
    results["momentum"].append(compute_mfi(df))

    # --- Volatility -----------------------------------------------------
    results["volatility"].append(compute_bollinger_bands(df))
    results["volatility"].append(compute_atr(df))
    results["volatility"].append(compute_keltner_channel(df))

    # --- Volume ---------------------------------------------------------
    results["volume"].append(compute_obv(df))
    results["volume"].append(compute_volume_sma(df))
    results["volume"].append(compute_ad_line(df))

    return results
