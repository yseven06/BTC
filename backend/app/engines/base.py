"""
TradeMinds AI - Base Engine Abstract Class

Defines the abstract interface that all analysis engines must implement.
Provides common types (SignalBias, EngineResult) used across the platform.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalBias(str, Enum):
    """Directional bias produced by an analysis engine."""

    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


class EngineResult(BaseModel):
    """Standardised output returned by every analysis engine.

    Attributes:
        engine_name: Identifier matching the engine's ``name`` property.
        score: Composite score on a 0-100 scale (100 = extremely bullish).
        bias: Directional interpretation of the score.
        confidence: How confident the engine is in its own result (0-100).
        key_findings: Human-readable bullet points summarising the analysis.
        supporting_data: Raw / structured data consumed by the explanation
            engine or downstream callers.
        warnings: Optional list of caveats or data-quality issues.
    """

    engine_name: str
    score: float = Field(..., ge=0, le=100)
    bias: SignalBias
    confidence: float = Field(..., ge=0, le=100)
    key_findings: list[str]
    supporting_data: dict
    warnings: list[str] = Field(default_factory=list)


class BaseEngine(ABC):
    """Abstract base class for all TradeMinds analysis engines.

    Every concrete engine **must** provide:
    * ``name``  – unique string identifier
    * ``weight`` – float weight used by the AI Decision Engine when computing
      a composite score (all weights across engines should sum to 1.0).
    * ``analyze`` – the async entry-point that performs the analysis and
      returns an :class:`EngineResult`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this engine."""
        ...

    @property
    @abstractmethod
    def weight(self) -> float:
        """Weight of this engine in the composite score (0.0 – 1.0)."""
        ...

    @abstractmethod
    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        """Run the analysis and return an :class:`EngineResult`.

        Args:
            symbol: Trading pair or ticker (e.g. ``"BTCUSDT"``).
            timeframe: Candle timeframe (e.g. ``"1h"``, ``"4h"``, ``"1d"``).
            ohlcv_data: A *pandas* DataFrame with columns
                ``['open', 'high', 'low', 'close', 'volume']`` and a
                DatetimeIndex.
            **kwargs: Engine-specific optional parameters.

        Returns:
            An :class:`EngineResult` instance.
        """
        ...
