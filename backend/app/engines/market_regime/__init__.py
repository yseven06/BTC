"""
TradeMinds AI – Market Regime detection.

Classifies the current market into a regime (trending / ranging / volatile /
low-volume / breakout) so the rest of the system can adapt its behaviour —
most importantly so the Adaptive Weight Engine can shift engine weights to
match the conditions each engine is actually good at.
"""

from app.engines.market_regime.detector import (
    MarketRegime,
    RegimeResult,
    detect_regime,
)

__all__ = ["MarketRegime", "RegimeResult", "detect_regime"]
