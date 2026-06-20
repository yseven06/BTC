"""
TradeMinds AI – Volume Analysis Engine Helpers

Performs volume profile calculations, volume spike detection, volume-price
divergence checks, and climax volume analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class VolumeDivergence(str, Enum):
    BULLISH_DIVERGENCE = "bullish_divergence"  # Price down, volume up or price down, volume down exhaustion
    BEARISH_DIVERGENCE = "bearish_divergence"  # Price up, volume down
    NONE = "none"


@dataclass
class VolumeProfileNode:
    price_bin: float
    volume: float
    is_poc: bool = False


@dataclass
class VolumeProfileResult:
    poc_price: float
    value_area_high: float
    value_area_low: float
    profile: List[VolumeProfileNode] = field(default_factory=list)


@dataclass
class VolumeAnalysisResult:
    volume_profile: VolumeProfileResult
    volume_trend_ratio: float  # current volume / 20 SMA volume
    is_volume_spike: bool
    divergence: VolumeDivergence
    is_climax_volume: bool
    accumulation_score: float  # -100 to 100 (accumulation vs distribution)
    key_findings: List[str] = field(default_factory=list)


def calculate_volume_profile(
    df: pd.DataFrame,
    bins_count: int = 15,
) -> VolumeProfileResult:
    """Build a volume profile (Volume at Price) histogram.

    Identifies Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL).
    Value Area covers ~70% of total volume around the POC.
    """
    if len(df) < 5:
        return VolumeProfileResult(0.0, 0.0, 0.0)

    high = df["high"].max()
    low = df["low"].min()
    price_range = high - low
    if price_range == 0:
        return VolumeProfileResult(df["close"].iloc[-1], df["close"].iloc[-1], df["close"].iloc[-1])

    bin_width = price_range / bins_count
    bins = [low + i * bin_width for i in range(bins_count + 1)]
    bin_volumes = np.zeros(bins_count)

    # Distribute volume across bins
    for _, row in df.iterrows():
        c_low = row["low"]
        c_high = row["high"]
        c_vol = row["volume"]
        
        # Simple attribution: assign volume to the bin containing the close price
        # Or distribute over the high-low range
        p_close = row["close"]
        bin_idx = min(int((p_close - low) / bin_width), bins_count - 1)
        bin_volumes[bin_idx] += c_vol

    profile: List[VolumeProfileNode] = []
    max_vol = 0.0
    poc_idx = 0

    for i in range(bins_count):
        bin_center = bins[i] + (bin_width / 2.0)
        vol = float(bin_volumes[i])
        if vol > max_vol:
            max_vol = vol
            poc_idx = i
        profile.append(VolumeProfileNode(price_bin=bin_center, volume=vol))

    profile[poc_idx].is_poc = True
    poc_price = profile[poc_idx].price_bin

    # Calculate Value Area (~70% of total volume centered around POC)
    total_vol = sum(bin_volumes)
    target_vol = total_vol * 0.70
    
    current_vol = max_vol
    lower_idx = poc_idx
    upper_idx = poc_idx

    while current_vol < target_vol and (lower_idx > 0 or upper_idx < bins_count - 1):
        prev_vol_lower = bin_volumes[lower_idx - 1] if lower_idx > 0 else 0
        prev_vol_upper = bin_volumes[upper_idx + 1] if upper_idx < bins_count - 1 else 0

        if lower_idx > 0 and (upper_idx == bins_count - 1 or prev_vol_lower >= prev_vol_upper):
            current_vol += prev_vol_lower
            lower_idx -= 1
        elif upper_idx < bins_count - 1:
            current_vol += prev_vol_upper
            upper_idx += 1
        else:
            break

    vah = bins[upper_idx + 1] if upper_idx < bins_count - 1 else high
    val = bins[lower_idx]

    return VolumeProfileResult(
        poc_price=float(poc_price),
        value_area_high=float(vah),
        value_area_low=float(val),
        profile=profile,
    )


def analyze_volume(
    df: pd.DataFrame,
    vol_sma_period: int = 20,
) -> VolumeAnalysisResult:
    """Perform volume trend, climax, divergence, and accumulation analysis."""
    findings: List[str] = []
    
    if len(df) < vol_sma_period:
        # Fallback if insufficient data
        vol_sma_period = max(5, len(df))

    # 1. Volume Trend vs SMA
    vol_sma = df["volume"].rolling(window=vol_sma_period, min_periods=1).mean()
    current_vol = float(df["volume"].iloc[-1])
    avg_vol = float(vol_sma.iloc[-1]) if not np.isnan(vol_sma.iloc[-1]) else current_vol
    
    ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
    is_spike = ratio >= 2.0
    is_climax = ratio >= 3.0

    if is_climax:
        findings.append(f"Climax Volume detected ({ratio:.1f}x average volume)")
    elif is_spike:
        findings.append(f"Volume spike detected ({ratio:.1f}x average volume)")
    
    # 2. Volume-Price Divergence (last 5-10 bars)
    divergence = VolumeDivergence.NONE
    lookback = min(10, len(df) - 1)
    if lookback >= 3:
        price_change = float(df["close"].iloc[-1] - df["close"].iloc[-lookback])
        vol_change = float(df["volume"].iloc[-1] - df["volume"].iloc[-lookback])
        
        # Price up, Volume down -> Bearish Divergence (lack of conviction)
        if price_change > 0 and vol_change < 0:
            divergence = VolumeDivergence.BEARISH_DIVERGENCE
            findings.append("Bearish divergence: Price rising on declining volume")
        # Price down, Volume down -> Bullish Divergence/Exhaustion (selling pressure fading)
        elif price_change < 0 and vol_change < 0:
            divergence = VolumeDivergence.BULLISH_DIVERGENCE
            findings.append("Bullish exhaustion: Price falling on declining volume")

    # 3. Accumulation / Distribution Score (ADI / Chaikin Money Flow approximation)
    # Score goes from -100 to 100 based on money flow multiplier: ((Close - Low) - (High - Close)) / (High - Low) * Volume
    # We sum it over the last 14 bars and normalize
    norm_score = 0.0
    acc_lookback = min(14, len(df))
    if acc_lookback > 0:
        mf_vals = []
        for idx in range(-acc_lookback, 0):
            row = df.iloc[idx]
            h = row["high"]
            l = row["low"]
            c = row["close"]
            v = row["volume"]
            den = (h - l) if h != l else 1.0
            mf_multiplier = ((c - l) - (h - c)) / den
            mf_vals.append(mf_multiplier * v)
        
        total_v = df["volume"].iloc[-acc_lookback:].sum()
        if total_v > 0:
            norm_score = (sum(mf_vals) / total_v) * 100.0

    if norm_score > 20:
        findings.append(f"Smart Money accumulation phase (Accumulation score: {norm_score:.1f})")
    elif norm_score < -20:
        findings.append(f"Smart Money distribution phase (Distribution score: {abs(norm_score):.1f})")

    # Calculate Volume Profile
    vp_res = calculate_volume_profile(df)
    current_price = float(df["close"].iloc[-1])

    # Position relative to POC
    if current_price > vp_res.poc_price:
        findings.append(f"Price is trading above Volume POC ({vp_res.poc_price:.4f})")
    else:
        findings.append(f"Price is trading below Volume POC ({vp_res.poc_price:.4f})")

    return VolumeAnalysisResult(
        volume_profile=vp_res,
        volume_trend_ratio=round(ratio, 2),
        is_volume_spike=is_spike,
        divergence=divergence,
        is_climax_volume=is_climax,
        accumulation_score=round(norm_score, 2),
        key_findings=findings,
    )
