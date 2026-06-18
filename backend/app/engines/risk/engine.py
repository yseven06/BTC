"""
TradeMinds AI – Risk Management Engine

Analyzes volatility, drawdowns, risk levels, and returns a safety score
and risk assessment as an EngineResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.risk.analysis import analyze_risk, RiskAnalysisResult

logger = logging.getLogger(__name__)


class RiskManagementEngine(BaseEngine):
    """Risk Management Engine.

    Weight: 0.10 (10 % of composite score).
    """

    @property
    def name(self) -> str:
        return "risk_management"

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
            warnings.append("Insufficient data for Risk analysis (<15 bars)")

        # Auto-detect asset class based on symbol suffix
        asset_type = "crypto"
        if symbol.endswith(".IS") or len(symbol) == 5:
            # e.g., THYAO.IS is stock
            asset_type = "stock"

        # Extract parameters if provided
        portfolio_size = kwargs.get("portfolio_size", 10000.0)
        risk_pct = kwargs.get("risk_pct", 2.0)
        entry = kwargs.get("entry", None)
        stop_loss = kwargs.get("stop_loss", None)
        take_profit = kwargs.get("take_profit", None)

        risk_res: RiskAnalysisResult = analyze_risk(
            df=df,
            asset_type=asset_type,
            portfolio_size=portfolio_size,
            risk_pct=risk_pct,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        # --- Scoring Logic ---
        # A higher engine score means "low risk / high trade safety" (favorable/bullish).
        # We invert the 1-10 risk score to a 0-100 safety score.
        score = 100.0 - (risk_res.risk_score * 10.0)
        score = max(0.0, min(100.0, score))
        
        bias = self._score_to_bias(score)

        # Risk parameters are deterministic, so confidence is high
        confidence = 90.0

        # --- Supporting Data ---
        supporting_data: Dict[str, Any] = {
            "volatility_class": risk_res.volatility_class.value,
            "atr_pct": risk_res.atr_pct,
            "risk_score_raw": risk_res.risk_score,
            "risk_level": risk_res.risk_level.value,
            "recommended_position_pct": risk_res.recommended_position_pct,
            "max_drawdown_pct": risk_res.max_drawdown_pct,
            "rr_ratio": risk_res.rr_ratio,
        }

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=confidence,
            key_findings=risk_res.key_findings,
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

