"""
TradeMinds AI – Technical Analysis Engine

Orchestrates all technical sub-analysers (indicators + candlestick patterns)
and returns a composite :class:`EngineResult`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.technical.indicators import (
    IndicatorResult,
    IndicatorSignal,
    compute_all_indicators,
)
from app.engines.technical.patterns import (
    PatternMatch,
    PatternType,
    detect_patterns,
)

logger = logging.getLogger(__name__)


class TechnicalAnalysisEngine(BaseEngine):
    """Classical technical analysis: indicators + candlestick patterns.

    Weight: 0.20 (20 % of composite score).
    """

    @property
    def name(self) -> str:
        return "technical_analysis"

    @property
    def weight(self) -> float:
        return 0.20

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        """Run all technical indicators and pattern detectors.

        Args:
            symbol: Ticker / pair (e.g. ``"BTCUSDT"``).
            timeframe: Candle timeframe.
            ohlcv_data: pandas DataFrame with OHLCV columns.

        Returns:
            :class:`EngineResult` summarising technical outlook.
        """
        df: pd.DataFrame = ohlcv_data
        warnings: List[str] = []

        if len(df) < 30:
            warnings.append("Insufficient data for reliable technical analysis (<30 bars)")

        # 1. Indicators
        indicator_groups = compute_all_indicators(df)

        # 2. Candlestick patterns
        patterns = detect_patterns(df, lookback=5)

        # 3. Score each category
        trend_score, trend_findings = self._score_trend(indicator_groups.get("trend", []))
        momentum_score, momentum_findings = self._score_momentum(indicator_groups.get("momentum", []))
        volatility_info = self._interpret_volatility(indicator_groups.get("volatility", []))
        volume_score, volume_findings = self._score_volume(indicator_groups.get("volume", []))
        pattern_score, pattern_findings = self._score_patterns(patterns)

        # 4. Composite score (weighted average of sub-scores)
        composite = (
            trend_score * 0.30
            + momentum_score * 0.25
            + volume_score * 0.15
            + pattern_score * 0.30
        )
        composite = max(0.0, min(100.0, composite))

        # 5. Bias
        bias = self._score_to_bias(composite)

        # 6. Confidence – based on agreement between sub-scores
        scores = [trend_score, momentum_score, volume_score, pattern_score]
        mean_s = sum(scores) / len(scores)
        variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
        agreement = max(0.0, 100.0 - variance ** 0.5)  # lower variance → higher confidence
        confidence = min(100.0, agreement)

        # 7. Key findings
        key_findings = trend_findings + momentum_findings + volume_findings + pattern_findings
        if volatility_info:
            key_findings.append(volatility_info)

        # 8. Supporting data
        supporting_data: Dict[str, Any] = {
            "trend_score": trend_score,
            "momentum_score": momentum_score,
            "volume_score": volume_score,
            "pattern_score": pattern_score,
            "indicators": {
                cat: [{"name": r.name, "value": r.value, "signal": r.signal.value, "detail": r.detail}
                      for r in results]
                for cat, results in indicator_groups.items()
            },
            "patterns": [
                {"name": p.name, "type": p.pattern_type.value, "strength": p.strength.value,
                 "index": p.candle_index, "detail": p.detail}
                for p in patterns
            ],
        }

        return EngineResult(
            engine_name=self.name,
            score=round(composite, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=key_findings[:10],  # cap at 10
            supporting_data=supporting_data,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _signal_to_score(signal: IndicatorSignal) -> float:
        """Map signal enum to a 0-100 score component."""
        if signal == IndicatorSignal.BULLISH:
            return 75.0
        if signal == IndicatorSignal.BEARISH:
            return 25.0
        return 50.0

    def _score_trend(self, results: List[IndicatorResult]) -> tuple[float, List[str]]:
        if not results:
            return 50.0, []
        scores = [self._signal_to_score(r.signal) for r in results]
        avg = sum(scores) / len(scores)
        bullish = sum(1 for r in results if r.signal == IndicatorSignal.BULLISH)
        bearish = sum(1 for r in results if r.signal == IndicatorSignal.BEARISH)
        findings: List[str] = []
        if bullish > bearish:
            findings.append(f"Trend indicators lean bullish ({bullish}/{len(results)} bullish)")
        elif bearish > bullish:
            findings.append(f"Trend indicators lean bearish ({bearish}/{len(results)} bearish)")
        else:
            findings.append("Trend indicators are mixed")
        return avg, findings

    def _score_momentum(self, results: List[IndicatorResult]) -> tuple[float, List[str]]:
        if not results:
            return 50.0, []
        scores = [self._signal_to_score(r.signal) for r in results]
        avg = sum(scores) / len(scores)
        findings: List[str] = []
        for r in results:
            if r.signal != IndicatorSignal.NEUTRAL:
                findings.append(f"{r.name.upper()}: {r.detail} → {r.signal.value}")
        return avg, findings[:4]

    def _interpret_volatility(self, results: List[IndicatorResult]) -> str:
        for r in results:
            if r.name == "atr":
                pct = r.extra.get("atr_pct", 0)
                if pct > 5:
                    return f"High volatility (ATR {pct:.1f}% of price)"
                elif pct > 2:
                    return f"Moderate volatility (ATR {pct:.1f}% of price)"
                else:
                    return f"Low volatility (ATR {pct:.1f}% of price)"
        return ""

    def _score_volume(self, results: List[IndicatorResult]) -> tuple[float, List[str]]:
        if not results:
            return 50.0, []
        scores = [self._signal_to_score(r.signal) for r in results]
        avg = sum(scores) / len(scores)
        findings: List[str] = []
        for r in results:
            if r.signal != IndicatorSignal.NEUTRAL:
                findings.append(f"{r.name}: {r.signal.value}")
        return avg, findings

    def _score_patterns(self, patterns: List[PatternMatch]) -> tuple[float, List[str]]:
        if not patterns:
            return 50.0, []
        bullish_pts = sum(1 for p in patterns if p.pattern_type == PatternType.BULLISH)
        bearish_pts = sum(1 for p in patterns if p.pattern_type == PatternType.BEARISH)
        total = bullish_pts + bearish_pts or 1
        score = 50.0 + (bullish_pts - bearish_pts) / total * 40.0
        findings = [f"Pattern: {p.name} ({p.pattern_type.value}, {p.strength.value})" for p in patterns]
        return max(0.0, min(100.0, score)), findings

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

