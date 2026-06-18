"""
TradeMinds AI - Analysis Engines Package

This package contains all analysis engines that power the TradeMinds AI
trading intelligence platform. Each engine inherits from BaseEngine and
provides a specific type of market analysis.

Engines:
    - TechnicalAnalysisEngine: Classical technical indicators and patterns
    - MarketStructureEngine: Swing points, BOS, CHoCH, trend structure
    - SMCEngine: Order blocks, FVGs, liquidity zones (SMC)
    - CRTEngine: HTF range analysis and sweep detection
    - VolumeAnalysisEngine: Volume profile, divergences, climax detection
    - RiskManagementEngine: Position sizing, volatility, drawdown analysis
    - FundamentalAnalysisEngine: Financial ratios and valuation metrics
    - OnchainEngine: On-chain metrics, sentiment, BTC network health
    - AIDecisionEngine: Orchestrator that combines all engine results
"""

from app.engines.base import BaseEngine, EngineResult, SignalBias

__all__ = [
    "BaseEngine",
    "EngineResult",
    "SignalBias",
]

