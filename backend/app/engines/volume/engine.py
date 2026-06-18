"""
TradeMinds AI – Volume Analysis Engine

Analyzes volume profile, volume spikes, divergences, and accumulation/distribution
to output a Volume Analysis EngineResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.volume.analysis import analyze_volume, VolumeAnalysisResult, VolumeDivergence

logger = logging.getLogger(__name__)


class VolumeAnalysisEngine(BaseEngine):
    """Volume Analysis Engine.

    Weight: 0.15 (15 % of composite score).
    """

    @property
    def name(self) -> str:
        return "volume_analysis"

    @property
    def weight(self) -> float:
        return 0.15

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        df: pd.DataFrame = ohlcv_data
        warnings: List[str] = []

        if len(df) < 20:
            warnings.append("Insufficient data for Volume analysis (<20 bars)")

        vol_res: VolumeAnalysisResult = analyze_volume(df)

        # --- Scoring Logic ---
        # Baseline score: 50.0 (neutral)
        score = 50.0

        # 1. Accumulation / Distribution Score (adds up to +/- 20 points)
        # score comes in as -100 to 100
        score += (vol_res.accumulation_score * 0.20)

        # 2. Volume-Price Divergence (adds up to +/- 15 points)
        if vol_res.divergence == VolumeDivergence.BULLISH_DIVERGENCE:
            score += 15.0  # Selling pressure fading, bullish sign
        elif vol_res.divergence == VolumeDivergence.BEARISH_DIVERGENCE:
            score -= 15.0  # Buying pressure fading, bearish sign

        # 3. Volume Climax / Spikes (exhaustion vs continuation check)
        current_close = float(df["close"].iloc[-1])
        current_open = float(df["open"].iloc[-1])
        is_bullish_bar = current_close > current_open

        if vol_res.is_volume_spike or vol_res.is_climax_volume:
            multiplier = 1.5 if vol_res.is_climax_volume else 1.0
            if is_bullish_bar:
                # If price is up on high volume, it can indicate a strong breakout (+10)
                # But if it is extremely overextended, it could be a buying climax (-5)
                score += 10.0 * multiplier
            else:
                # If price is down on high volume, it indicates heavy selling (-10)
                # Or panic selling climax leading to bottom (which we handle as potential buy if accumulation is high)
                score -= 10.0 * multiplier

        # 4. Position Relative to POC (adds up to +/- 10 points)
        current_price = float(df["close"].iloc[-1])
        poc = vol_res.volume_profile.poc_price
        val = vol_res.volume_profile.value_area_low
        vah = vol_res.volume_profile.value_area_high

        if current_price > poc:
            score += 5.0  # Trading above point of control is bullish
            if current_price > vah:
                score += 5.0  # Breakout of value area high
        else:
            score -= 5.0  # Trading below point of control is bearish
            if current_price < val:
                score -= 5.0  # Breakout below value area low

        score = max(0.0, min(100.0, score))
        bias = self._score_to_bias(score)

        # --- Confidence Calculation ---
        # Starts at 65%. Increases if volume confirms the price action (i.e. high volume on breakouts, low volume on pullbacks)
        confidence = 65.0
        
        # If there's a strong volume spike, we have more data conviction
        if vol_res.is_volume_spike:
            confidence += 10.0
        if vol_res.is_climax_volume:
            confidence += 5.0

        # If divergence is active, it indicates warning but also directional conviction
        if vol_res.divergence != VolumeDivergence.NONE:
            confidence += 10.0

        confidence = max(30.0, min(95.0, confidence))

        # --- Supporting Data ---
        supporting_data: Dict[str, Any] = {
            "volume_trend_ratio": vol_res.volume_trend_ratio,
            "is_volume_spike": vol_res.is_volume_spike,
            "is_climax_volume": vol_res.is_climax_volume,
            "divergence": vol_res.divergence.value,
            "accumulation_score": vol_res.accumulation_score,
            "volume_profile": {
                "poc_price": vol_res.volume_profile.poc_price,
                "value_area_high": vol_res.volume_profile.value_area_high,
                "value_area_low": vol_res.volume_profile.value_area_low,
            }
        }

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=vol_res.key_findings,
            supporting_data=supporting_data,
            warnings=warnings,
        )

    @staticmethod
    def _score_to_bias(score: float) -> SignalBias:
        if score >= 75:
            return SignalBias.STRONG_BULLISH
        if score >= 60:
            return SignalBias.BULLISH
        if score >= 40:
            return SignalBias.NEUTRAL
        if score >= 25:
            return SignalBias.BEARISH
        return SignalBias.STRONG_BEARISH

