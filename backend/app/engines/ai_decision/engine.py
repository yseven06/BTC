"""
TradeMinds AI – AI Decision Engine Orchestrator

Coordinates the execution of all specialized analysis engines in parallel,
aggregates their results, and passes them to the Signal Generator and
Explanation Generator.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from app.engines.base import BaseEngine, EngineResult
from app.engines.technical.engine import TechnicalAnalysisEngine
from app.engines.market_structure.engine import MarketStructureEngine
from app.engines.smc.engine import SMCEngine
from app.engines.crt.engine import CRTEngine
from app.engines.volume.engine import VolumeAnalysisEngine
from app.engines.risk.engine import RiskManagementEngine
from app.engines.fundamental.engine import FundamentalAnalysisEngine
from app.engines.onchain.engine import OnchainEngine
from app.engines.macro.engine import MacroEngine

from app.engines.ai_decision.signal_generator import generate_signal
from app.engines.ai_decision.explanation_generator import generate_explanation
from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector

logger = logging.getLogger(__name__)


# Mapping from a given timeframe to how many of its candles make up one
# higher-timeframe candle.  CRT is always performed inside the immediately
# higher timeframe candle, so a 1h chart is analysed inside the 4h candle,
# a 4h chart inside the daily, etc.
_HTF_CANDLE_COUNTS: dict = {
    "1m":  15,   # 1m  → 15m HTF
    "5m":  12,   # 5m  → 1h  HTF
    "15m": 4,    # 15m → 1h  HTF
    "30m": 8,    # 30m → 4h  HTF
    "1h":  4,    # 1h  → 4h  HTF
    "2h":  6,    # 2h  → 12h HTF
    "4h":  6,    # 4h  → 1d  HTF
    "6h":  4,    # 6h  → 1d  HTF
    "8h":  3,    # 8h  → 1d  HTF
    "12h": 2,    # 12h → 1d  HTF
    "1d":  7,    # 1d  → 1w  HTF
}


def _derive_htf_boundaries(df: pd.DataFrame, timeframe: str) -> tuple:
    """Return (htf_high, htf_low) for the containing higher-timeframe candle.

    We approximate the HTF candle by aggregating the last N bars of the
    current timeframe, where N is the number of LTF bars that fit in one
    HTF candle.  This is not a live HTF feed, but it is semantically
    correct for the CRT premise and eliminates the placeholder "last 24
    bars" heuristic that was mixing same-TF data.
    """
    n = _HTF_CANDLE_COUNTS.get(timeframe.lower(), 4)
    window = min(n, len(df))
    subset = df.iloc[-window:]
    htf_high = float(subset["high"].max())
    htf_low  = float(subset["low"].min())
    return htf_high, htf_low


def calculate_trend_bias(df: pd.DataFrame) -> str:
    """Helper to calculate trend bias using a fast/slow EMA combination."""
    if df.empty or len(df) < 5:
        return "neutral"
    
    ema_period = min(50, len(df))
    close = df["close"]
    ema = close.ewm(span=ema_period, adjust=False).mean()
    latest_close = float(close.iloc[-1])
    latest_ema = float(ema.iloc[-1])
    
    if latest_close > latest_ema:
        return "bullish"
    elif latest_close < latest_ema:
        return "bearish"
    return "neutral"


class AIDecisionEngine:
    """The master orchestrator that runs all sub-engines in parallel and combines them."""

    def __init__(self) -> None:
        # Initialize all sub-engines
        self.engines: List[BaseEngine] = [
            TechnicalAnalysisEngine(),
            MarketStructureEngine(),
            SMCEngine(),
            CRTEngine(),
            VolumeAnalysisEngine(),
            RiskManagementEngine(),
            FundamentalAnalysisEngine(),
            OnchainEngine(),
            MacroEngine(),
        ]

    async def analyze_and_decide(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Orchestrate full analysis suite in parallel and compile trade decision.

        Args:
            symbol: Trade symbol (e.g. BTCUSDT, THYAO.IS)
            timeframe: Timeframe of the data (e.g. 1h, 1d)
            ohlcv_data: Dataframe containing OHLCV records
            **kwargs: Extra settings (portfolio size, risk pct, etc.)

        Returns:
            Dict containing the final decision, signals, engine results,
            and explanations.
        """
        logger.info(f"Starting TradeMinds analysis suite for {symbol} ({timeframe})")

        # Determine asset type
        asset_type = kwargs.get("asset_type", None)
        if asset_type is None:
            if symbol.endswith(".IS") or len(symbol) == 5:
                asset_type = "stock"
            else:
                asset_type = "crypto"
        kwargs["asset_type"] = asset_type

        # Pre-compute the HTF boundaries once and inject them into kwargs so
        # the CRT engine receives real higher-timeframe H/L values instead of
        # falling back to its same-timeframe "last 24 bars" heuristic.
        htf_high, htf_low = _derive_htf_boundaries(ohlcv_data, timeframe)
        kwargs.setdefault("htf_high", htf_high)
        kwargs.setdefault("htf_low", htf_low)

        # Run all analysis engines concurrently
        tasks = []
        active_engines = []

        for engine in self.engines:
            active_engines.append(engine)
            tasks.append(
                self._safe_run_engine(engine, symbol, timeframe, ohlcv_data, **kwargs)
            )

        # Run multi-timeframe trend checks in parallel with engines
        mtf_trends = {}
        if kwargs.get("is_backtest", False):
            # Backtesting mode: Slice pre-loaded mtf_data up to current timestamp
            mtf_dfs = kwargs.get("mtf_data", {})
            current_time = ohlcv_data.index[-1]
            for tf, mtf_df in mtf_dfs.items():
                sliced_df = mtf_df[mtf_df.index <= current_time]
                if not sliced_df.empty:
                    mtf_trends[tf] = calculate_trend_bias(sliced_df)
        else:
            # Live mode: Fetch 15m, 1h, 4h timeframes concurrently
            binance = BinanceCollector()
            yahoo = YahooCollector()
            try:
                async def fetch_tf_trend(tf: str):
                    try:
                        if asset_type == "stock" or symbol.endswith(".IS"):
                            df_tf = await yahoo.fetch_ohlcv(symbol, tf, limit=60)
                        else:
                            df_tf = await binance.fetch_ohlcv(symbol, tf, limit=60)
                        return tf, calculate_trend_bias(df_tf)
                    except Exception as ex:
                        logger.warning(f"Failed to fetch TF {tf} trend: {str(ex)}")
                        return tf, "neutral"
                
                tf_results = await asyncio.gather(
                    fetch_tf_trend("15m"),
                    fetch_tf_trend("1h"),
                    fetch_tf_trend("4h")
                )
                mtf_trends = dict(tf_results)
            except Exception as e:
                logger.error(f"Error checking MTF alignment: {str(e)}")
            finally:
                await binance.close()

        # Await all tasks parallel
        results: List[EngineResult] = await asyncio.gather(*tasks)

        # Compile results
        engine_results_dict = {res.engine_name: res for res in results}

        # Calculate entries, targets, and signal type in the deterministic signal generator
        signal_data = generate_signal(symbol, timeframe, ohlcv_data, results, mtf_trends=mtf_trends)

        # Generate structured explanations in TR and EN
        explanations = generate_explanation(signal_data, results, asset_type)

        # Assemble full output matching our DB and schema representations
        decision_payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_type": signal_data.signal_type,
            "confidence_score": signal_data.confidence_score,
            "probability_score": signal_data.probability_score,
            "risk_score": signal_data.risk_score,
            "risk_level": signal_data.risk_level,
            "direction": signal_data.direction,
            "entry_zone_low": signal_data.entry_zone_low,
            "entry_zone_high": signal_data.entry_zone_high,
            "stop_loss": signal_data.stop_loss,
            "tp1": signal_data.tp1,
            "tp2": signal_data.tp2,
            "tp3": signal_data.tp3,
            "invalidation_conditions": signal_data.invalidation_conditions,
            "engine_results": [res.model_dump() for res in results],
            "explanation_tr": explanations["tr"],
            "explanation_en": explanations["en"],
            "generated_at": pd.Timestamp.now().isoformat(),
            "mtf_trends": mtf_trends,
        }

        return decision_payload

    async def _safe_run_engine(
        self,
        engine: BaseEngine,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
        **kwargs: Any,
    ) -> EngineResult:
        """Runs a single engine catching any potential failures to keep the system robust."""
        try:
            return await engine.analyze(symbol, timeframe, ohlcv_data, **kwargs)
        except Exception as e:
            logger.error(f"Error running engine {engine.name} on {symbol}: {str(e)}", exc_info=True)
            # Return a neutral result with warnings rather than crashing the orchestrator
            from app.engines.base import SignalBias
            return EngineResult(
                engine_name=engine.name,
                score=50.0,
                bias=SignalBias.NEUTRAL,
                confidence=30.0,
                key_findings=[f"Failed to execute engine {engine.name} due to internal error"],
                supporting_data={},
                warnings=[f"Engine error: {str(e)}"],
            )

