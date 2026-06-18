"""
TradeMinds AI – Candle Range Theory (CRT) Engine

Analyzes higher timeframe candle ranges, sweeps, and range positions
to generate a CRT EngineResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.crt.analysis import analyse_crt, CRTResult, RangeZone, SweepDirection

logger = logging.getLogger(__name__)


class CRTEngine(BaseEngine):
    """Candle Range Theory (CRT) Engine.

    Weight: 0.10 (10 % of composite score).
    """

    @property
    def name(self) -> str:
        return "candle_range_theory"

    @property
    def weight(self) -> float:
        return 0.10

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        df: pd.DataFrame = ohlcv_data
        warnings: List[str] = []

        if len(df) < 15:
            warnings.append("Insufficient data for CRT analysis (<15 bars)")

        # Optional HTF boundaries passed via kwargs
        htf_high = kwargs.get("htf_high", None)
        htf_low = kwargs.get("htf_low", None)

        crt_res: CRTResult = analyse_crt(df, htf_high=htf_high, htf_low=htf_low)

        # --- Scoring Logic ---
        # Baseline score: 50.0 (neutral)
        score = 50.0
        confidence = 50.0

        # Check for sweep signals first (highest priority)
        if crt_res.signals:
            latest_signal = crt_res.signals[-1]
            sweep_ev = getattr(latest_signal, "sweep_event", None)
            ratio = getattr(sweep_ev, "volume_ratio", 1.0) if sweep_ev else 1.0
            confirmed = getattr(sweep_ev, "volume_confirmed", True) if sweep_ev else True
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)

            score_shift = latest_signal.confidence * 0.4 * multiplier
            if latest_signal.direction == "long":
                score = 50.0 + score_shift
            else:
                score = 50.0 - score_shift
            
            # Adjust confidence
            confidence = latest_signal.confidence
            if not confirmed:
                confidence = max(20.0, confidence - 20.0)
            elif ratio >= 1.5:
                confidence = min(98.0, confidence + 10.0)
        else:
            # Check range position if no signal is active
            if crt_res.range_position:
                pos = crt_res.range_position
                if pos.zone == RangeZone.DISCOUNT:
                    score += 15.0  # Buy pressure near low of HTF range
                elif pos.zone == RangeZone.LOWER_MID:
                    score += 5.0
                elif pos.zone == RangeZone.UPPER_MID:
                    score -= 5.0
                elif pos.zone == RangeZone.PREMIUM:
                    score -= 15.0  # Sell pressure near high of HTF range

            # Volatility range expansions adjust baseline slightly
            if crt_res.range_analysis.range_state == "expanding":
                # Expanding range increases directional conviction
                if score > 50.0:
                    score += 5.0
                elif score < 50.0:
                    score -= 5.0

        score = max(0.0, min(100.0, score))
        bias = self._score_to_bias(score)

        # --- Confidence adjusted for range structure ---
        if not crt_res.signals:
            # lower confidence when just using range position
            confidence = 50.0
            if crt_res.range_position:
                # If price is at extremes, confidence is higher
                if crt_res.range_position.zone in [RangeZone.DISCOUNT, RangeZone.PREMIUM]:
                    confidence += 10.0

        # --- Build Key Findings ---
        key_findings = self._build_findings(crt_res)

        # --- Supporting Data ---
        supporting_data: Dict[str, Any] = {
            "range_ratio": crt_res.range_analysis.range_ratio,
            "range_state": crt_res.range_analysis.range_state.value,
            "current_range": crt_res.range_analysis.current_range,
            "average_range": crt_res.range_analysis.average_range,
            "atr_value": crt_res.range_analysis.atr_value,
            "range_position": {
                "htf_high": crt_res.range_position.htf_high if crt_res.range_position else None,
                "htf_low": crt_res.range_position.htf_low if crt_res.range_position else None,
                "position_pct": crt_res.range_position.position_pct if crt_res.range_position else 50.0,
                "zone": crt_res.range_position.zone.value if crt_res.range_position else "normal",
            } if crt_res.range_position else None,
            "sweeps_count": len(crt_res.sweeps),
            "signals_count": len(crt_res.signals),
            "latest_signal_direction": crt_res.signals[-1].direction if crt_res.signals else None,
        }

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=key_findings,
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

    @staticmethod
    def _build_findings(crt_res: CRTResult) -> List[str]:
        findings: List[str] = []

        # 1. Range State
        r_state = crt_res.range_analysis.range_state.value.title()
        findings.append(f"Expected range state: {r_state} (Ratio: {crt_res.range_analysis.range_ratio})")

        # 2. Position
        if crt_res.range_position:
            pos = crt_res.range_position
            findings.append(f"Price sits at {pos.position_pct}% of HTF range ({pos.zone.value.replace('_', ' ').title()})")

        # 3. Sweeps & Signals
        if crt_res.signals:
            latest_sig = crt_res.signals[-1]
            findings.append(f"CRT SIGNAL: {latest_sig.direction.upper()} ({latest_sig.detail})")
        
        # Latest sweep event
        if crt_res.sweeps:
            latest_sweep = crt_res.sweeps[-1]
            if latest_sweep.direction == SweepDirection.SWEEP_HIGH:
                findings.append(f"Swept HTF liquidity above high ({latest_sweep.sweep_price:.4f})")
            else:
                findings.append(f"Swept HTF liquidity below low ({latest_sweep.sweep_price:.4f})")

        return findings

