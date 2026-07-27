"""
Zate Trade – AI Decision Engine Orchestrator

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
from app.services.candle_window import analysis_window, closed_candles

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


def _analysis_view(df: pd.DataFrame, timeframe: str, symbol: str = ""):
    """The frame the engines measure on, plus its provenance.

    A named function rather than three lines inline so the invariant it carries —
    "engines never see the forming candle" — can be asserted by calling it,
    instead of by reading the orchestrator's source and hoping the reading is
    faithful.
    """
    window = analysis_window(df, timeframe)
    if window.df.empty:
        # Refusing to score is worse than scoring what we were given: this only
        # happens when every bar in the frame has yet to close, which in
        # production means the fetch itself was wrong, not the market.
        logger.warning(
            "[F1] %s %s: no closed bars in frame — falling back to the full "
            "frame for this evaluation", symbol, timeframe,
        )
        return df, window
    return window.df, window


def _live_price(df: pd.DataFrame) -> Optional[float]:
    """The most recent traded price — the FULL frame's last close.

    Deliberately reads the frame including the candle still forming: that close
    is the live price, and pricing entry/SL/TP off the previous bar instead would
    place every level a full bar behind the market.
    """
    try:
        if df is None or len(df) == 0:
            return None
        return float(df["close"].iloc[-1])
    except Exception:  # noqa: BLE001 — a missing price must not abort the run
        return None


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
        logger.info(f"Starting ZateTrade analysis suite for {symbol} ({timeframe})")

        # Determine asset type
        asset_type = kwargs.get("asset_type", None)
        if asset_type is None:
            if symbol.endswith(".IS") or len(symbol) == 5:
                asset_type = "stock"
            else:
                asset_type = "crypto"
        kwargs["asset_type"] = asset_type

        # F1 — split the frame in two. Everything that MEASURES the market runs
        # on bars that have definitively closed; the live price the geometry
        # anchors on keeps coming from the full frame. Binance always returns the
        # candle currently forming and every job fires 1-3 minutes into one, so
        # without this the indicators were reading a bar that was a fraction
        # complete (measured: volume at 2/15 of a 15m bar, 2/240 of a 4h bar).
        analysis_df, window = _analysis_view(ohlcv_data, timeframe, symbol)

        # Pre-compute the HTF boundaries once and inject them into kwargs so
        # the CRT engine receives real higher-timeframe H/L values instead of
        # falling back to its same-timeframe "last 24 bars" heuristic.
        htf_high, htf_low = _derive_htf_boundaries(analysis_df, timeframe)
        kwargs.setdefault("htf_high", htf_high)
        kwargs.setdefault("htf_low", htf_low)

        # Run all analysis engines concurrently
        tasks = []
        active_engines = []

        for engine in self.engines:
            active_engines.append(engine)
            tasks.append(
                self._safe_run_engine(engine, symbol, timeframe, analysis_df, **kwargs)
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
                        # F1 — each MTF frame closes on ITS OWN boundary. Applying
                        # the primary timeframe's cut here would drop up to 16 valid
                        # 15m bars when the primary is 4h, and dropping the last row
                        # blindly would discard a 4h bar that had genuinely closed.
                        tf_closed = closed_candles(df_tf, tf)
                        return tf, calculate_trend_bias(tf_closed if not tf_closed.empty else df_tf)
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

        # Calculate entries, targets, and signal type in the deterministic signal
        # generator. engine_weights (regime/coin-adaptive) may be supplied by the
        # caller; when absent the generator falls back to its static base mix.
        # F1 — the generator measures on closed bars but anchors price on the
        # live one. Passing current_price explicitly keeps that a decision made
        # here rather than a side effect of which frame happened to be handed in.
        signal_data = generate_signal(
            symbol, timeframe, analysis_df, results,
            mtf_trends=mtf_trends,
            weights=kwargs.get("engine_weights"),
            current_price=_live_price(ohlcv_data),
        )

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
            "birth_telemetry": signal_data.birth_telemetry,
            # Consensus primitives for the candidate decision log (P2.2-a).
            # Observation only — no consumer of this payload branches on it.
            "consensus_telemetry": signal_data.consensus_telemetry,
            # F1 — which bar the features were measured on, and how far the live
            # price had already moved past it. Observation only.
            "decision_input_telemetry": {
                **(signal_data.decision_input_telemetry or {}),
                "last_analysis_bar_open_time": window.last_bar_open_time,
                "last_analysis_bar_close_time": window.last_bar_close_time,
                "last_analysis_bar_closed": window.last_bar_closed,
                "dropped_forming_bars": window.dropped_forming,
                "decision_current_price_source": "full_frame_last_close",
            },
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

