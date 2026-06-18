"""
TradeMinds AI – Market Structure Engine

Combines swing-point / trend-structure analysis with support-resistance
identification to produce a composite :class:`EngineResult`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.market_structure.structure import (
    MarketStructureResult,
    StructureEvent,
    TrendState,
    analyse_market_structure,
)
from app.engines.market_structure.support_resistance import (
    SupportResistanceResult,
    analyse_support_resistance,
)

logger = logging.getLogger(__name__)


class MarketStructureEngine(BaseEngine):
    """Analyses market structure: swings, BOS/CHoCH, S/R levels.

    Weight: 0.20 (20 % of composite score).
    """

    @property
    def name(self) -> str:
        return "market_structure"

    @property
    def weight(self) -> float:
        return 0.20

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        df: pd.DataFrame = ohlcv_data
        warnings: List[str] = []
        lookback = kwargs.get("swing_lookback", 5)

        if len(df) < 30:
            warnings.append("Limited data for market structure analysis")

        # --- Run sub-analysers ---
        ms: MarketStructureResult = analyse_market_structure(df, lookback=lookback)
        sr: SupportResistanceResult = analyse_support_resistance(df, lookback=lookback)

        # --- Score ---
        structure_score = self._score_structure(ms, df)
        sr_score = self._score_sr(sr, df)
        composite = structure_score * 0.60 + sr_score * 0.40
        composite = max(0.0, min(100.0, composite))

        bias = self._score_to_bias(composite)

        # --- Confidence ---
        confidence = 60.0
        if ms.current_trend != TrendState.RANGE:
            confidence += 15.0
        if ms.latest_bos or ms.latest_choch:
            confidence += 10.0
        if len(ms.swing_points) >= 6:
            confidence += 10.0
        confidence = min(100.0, confidence)

        # --- Findings ---
        key_findings = self._build_findings(ms, sr, df)

        # --- Supporting data ---
        supporting_data: Dict[str, Any] = {
            "structure_score": structure_score,
            "sr_score": sr_score,
            "current_trend": ms.current_trend.value,
            "hh": ms.hh_count,
            "hl": ms.hl_count,
            "lh": ms.lh_count,
            "ll": ms.ll_count,
            "swing_count": len(ms.swing_points),
            "bos_events": [
                {"event": e.event.value, "price": e.price, "index": e.index, "detail": e.detail}
                for e in ms.events
            ],
            "horizontal_sr": [
                {"price": lv.price, "type": lv.level_type.value, "strength": lv.strength,
                 "touches": lv.touches, "label": lv.label}
                for lv in sr.horizontal_levels[:10]
            ],
            "dynamic_sr": [
                {"price": lv.price, "type": lv.level_type.value, "label": lv.label}
                for lv in sr.dynamic_levels
            ],
            "fibonacci": [
                {"price": lv.price, "label": lv.label, "ratio": lv.extra.get("ratio")}
                for lv in sr.fibonacci_levels
            ],
            "nearest_support": sr.nearest_support.price if sr.nearest_support else None,
            "nearest_resistance": sr.nearest_resistance.price if sr.nearest_resistance else None,
        }

        return EngineResult(
            engine_name=self.name,
            score=round(composite, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=key_findings[:8],
            supporting_data=supporting_data,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_structure(ms: MarketStructureResult, df: pd.DataFrame) -> float:
        """Score from trend state + BOS / CHoCH."""
        score = 50.0  # neutral baseline

        if ms.current_trend == TrendState.UPTREND:
            score += 20.0
        elif ms.current_trend == TrendState.DOWNTREND:
            score -= 20.0

        # Swing-point bias
        bull_events = ms.hh_count + ms.hl_count
        bear_events = ms.lh_count + ms.ll_count
        total = bull_events + bear_events or 1
        score += (bull_events - bear_events) / total * 15.0

        # BOS / CHoCH with Volume Confirmation multiplier
        if ms.latest_bos:
            # Multiplier: 0.3 if unconfirmed, 1.2 if strongly confirmed (ratio >= 1.5), 1.0 otherwise
            ratio = getattr(ms.latest_bos, "volume_ratio", 1.0)
            confirmed = getattr(ms.latest_bos, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            
            if ms.latest_bos.event == StructureEvent.BOS_BULLISH:
                score += 10.0 * multiplier
            else:
                score -= 10.0 * multiplier

        if ms.latest_choch:
            ratio = getattr(ms.latest_choch, "volume_ratio", 1.0)
            confirmed = getattr(ms.latest_choch, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)

            if ms.latest_choch.event == StructureEvent.CHOCH_BULLISH:
                score += 15.0 * multiplier
            else:
                score -= 15.0 * multiplier

        return max(0.0, min(100.0, score))

    @staticmethod
    def _score_sr(sr: SupportResistanceResult, df: pd.DataFrame) -> float:
        """Score based on proximity to S/R levels."""
        current_price = float(df["close"].iloc[-1])
        score = 50.0

        if sr.nearest_support and sr.nearest_resistance:
            sup = sr.nearest_support.price
            res = sr.nearest_resistance.price
            rng = res - sup if res > sup else 1.0
            position = (current_price - sup) / rng  # 0=at support, 1=at resistance
            # Closer to support → bullish (higher score), closer to resistance → bearish
            score = max(0.0, min(100.0, (1.0 - position) * 80.0 + 10.0))

        return score

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
    def _build_findings(
        ms: MarketStructureResult,
        sr: SupportResistanceResult,
        df: pd.DataFrame,
    ) -> List[str]:
        findings: List[str] = []

        # Trend
        findings.append(f"Market structure: {ms.current_trend.value.replace('_', ' ').title()}")
        findings.append(f"Swing counts – HH:{ms.hh_count} HL:{ms.hl_count} LH:{ms.lh_count} LL:{ms.ll_count}")

        # BOS
        if ms.latest_bos:
            findings.append(f"Break of Structure: {ms.latest_bos.detail}")

        # CHoCH
        if ms.latest_choch:
            findings.append(f"Change of Character: {ms.latest_choch.detail}")

        # S/R
        if sr.nearest_support:
            findings.append(f"Nearest support: {sr.nearest_support.price:.4f} ({sr.nearest_support.label})")
        if sr.nearest_resistance:
            findings.append(f"Nearest resistance: {sr.nearest_resistance.price:.4f} ({sr.nearest_resistance.label})")

        # Fib
        if sr.fibonacci_levels:
            fib_labels = ", ".join(f.label for f in sr.fibonacci_levels[:3])
            findings.append(f"Key Fibonacci levels: {fib_labels}")

        return findings

