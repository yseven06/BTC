"""
Zate Trade – AI Decision Engine Orchestrator

Coordinates the execution of all specialized analysis engines in parallel,
aggregates their results, and passes them to the Signal Generator and
Explanation Generator.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
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
from app.services import dependency_health as dh
from app.services.candle_window import analysis_window, closed_candles

logger = logging.getLogger(__name__)


# --- engine failure fallback (CP-OBS-ENGINE-ERR) ---------------------------
#
# What _safe_run_engine substitutes when an engine raises. Named rather than
# inlined so the telemetry below reports the values that were actually used
# instead of a second copy that could drift from them. The numbers themselves
# are unchanged: 50.0 is neutral on every consensus threshold (neither the
# bullish >53/<40 pair nor the bearish <47/>60 pair), so an outage can neither
# confirm nor conflict.
ENGINE_FALLBACK_SCORE = 50.0
ENGINE_FALLBACK_BIAS = SignalBias.NEUTRAL
ENGINE_FALLBACK_CONFIDENCE = 30.0

ENGINE_EXECUTION_TELEMETRY_VERSION = "engine_execution_v1"


def _error_fingerprint(engine_name: str, exc: BaseException) -> str:
    """A stable, redacted identity for one failure mode.

    Deliberately hashed rather than stored plain. The inputs are the engine, the
    exception's fully-qualified type and the source location that raised — the
    last of which is repo-relative but still goes through the digest, so nothing
    reconstructable reaches the database. `str(exc)` is never an input: an
    exception message is arbitrary text that can carry a URL with a token in it,
    and a fingerprint that changed with the message would not group failures
    anyway. The full traceback is already in the logs via exc_info=True; this
    field exists to count and group, not to diagnose.
    """
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    where = ""
    if tb is not None:
        path = tb.tb_frame.f_code.co_filename.replace("\\", "/")
        # Repo-relative: an absolute path leaks the deploy layout into the digest
        # input and would make the same bug fingerprint differently per machine.
        if "/app/" in path:
            path = "app/" + path.split("/app/", 1)[1]
        where = f"{path}:{tb.tb_lineno}"
    raw = f"{engine_name}|{type(exc).__module__}.{type(exc).__qualname__}|{where}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_engine_execution_telemetry(
    engine_count: int, failures: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Summarise one analysis run's engine outcomes. Pure; no I/O.

    A crashed engine and a genuinely neutral one are indistinguishable in the
    candidate log today: only {score, bias, confidence} is persisted, and the
    fallback (50.0, neutral, 30.0) shares its score and bias with macro_analysis
    on 100% of candidates and with risk_management on 90%. The only separator is
    a confidence value nothing queries. This records the distinction directly.
    """
    failed = list(failures or [])
    return {
        "version": ENGINE_EXECUTION_TELEMETRY_VERSION,
        "engine_count": int(engine_count),
        "successful_engine_count": int(engine_count) - len(failed),
        "failed_engine_count": len(failed),
        "failed_engines": failed,
        "fallback_used": bool(failed),
    }


def _engine_execution_or_none(engine_count: int, failures: List[Dict[str, Any]]):
    """Fail-open wrapper. Telemetry that can break a decision is not telemetry."""
    try:
        return build_engine_execution_telemetry(engine_count, failures)
    except Exception as exc:  # noqa: BLE001 — never let observability decide
        logger.warning("[EngineTelemetry] summary not built (ignored): %s", exc)
        return None


def _dependency_health_or_none(engines, mtf_status, engine_execution):
    """Fail-open wrapper for the dependency record (CP-DEP-HEALTH-1).

    Collects each engine's `_dependency_health` — set by the engine on itself
    during this run, absent on engines that do not consult an external source
    and absent on any engine that raised (that case is already covered by
    `engine_execution_telemetry`). Same contract as the wrapper above: if
    anything here fails, the decision proceeds untouched and the record is None.
    """
    try:
        entries = {}
        for engine in engines or ():
            entry = getattr(engine, "_dependency_health", None)
            if entry:
                entries[getattr(engine, "name", "")] = entry
        return dh.build_dependency_health(
            engines=entries, mtf=mtf_status,
            engine_execution_telemetry=engine_execution,
        )
    except Exception as exc:  # noqa: BLE001 — never let observability decide
        logger.warning("[DepHealth] record not built (ignored): %s", exc)
        return None


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

        # CP-OBS-ENGINE-ERR: a per-call list, not instance state — two symbols
        # analysed concurrently must not accumulate into the same collector.
        engine_failures: List[Dict[str, Any]] = []

        for engine in self.engines:
            active_engines.append(engine)
            tasks.append(
                self._safe_run_engine(engine, symbol, timeframe, analysis_df,
                                      failures=engine_failures, **kwargs)
            )

        # Run multi-timeframe trend checks in parallel with engines
        mtf_trends = {}
        # CP-DEP-HEALTH-1 — per-timeframe fetch outcome. Written by the live
        # branch below; the backtest branch works off pre-loaded frames and makes
        # no network call, so it is left empty rather than filled with a guess.
        mtf_status: Dict[str, str] = {}
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
                        mtf_status[tf] = dh.OK
                        return tf, calculate_trend_bias(tf_closed if not tf_closed.empty else df_tf)
                    except Exception as ex:
                        logger.warning(f"Failed to fetch TF {tf} trend: {str(ex)}")
                        # CP-DEP-HEALTH-1 — this path is FAIL-OPEN: "neutral" is
                        # skipped by the MTF layer, so a failed fetch REMOVES a
                        # penalty instead of adding one. The returned value is
                        # unchanged; only the reason is now recorded.
                        mtf_status[tf] = dh.classify_exception(ex)
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

        # Built once and shared by the two telemetry keys below, so the crash
        # summary and the dependency record can never disagree with each other.
        engine_execution = _engine_execution_or_none(len(active_engines), engine_failures)

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
            # CP-OBS-ENGINE-ERR — which engines actually ran, and which returned
            # the crash fallback. Observation only; nothing branches on it. Built
            # in its own try/except because a telemetry error must never be able
            # to take down a decision that has already been made.
            "engine_execution_telemetry": engine_execution,
            # CP-DEP-HEALTH-1 — which external dependency did what while this
            # decision was being made. Observation only; nothing branches on it,
            # and it is built in its own fail-open wrapper for the same reason
            # the line above is. Read off the engine instances rather than off
            # EngineResult so it cannot reach `engines_data` / `/api/reports`.
            "dependency_health": _dependency_health_or_none(
                self.engines, mtf_status, engine_execution),
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
        *,
        failures: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> EngineResult:
        """Runs a single engine catching any potential failures to keep the system robust.

        `failures` is an out-parameter: a per-call list the orchestrator owns, so
        two symbols analysed concurrently cannot see each other's entries. It is
        appended to, never read here, and nothing in the returned result depends
        on whether it was passed — the substituted values are identical either
        way (CP-OBS-ENGINE-ERR is observation only).
        """
        try:
            return await engine.analyze(symbol, timeframe, ohlcv_data, **kwargs)
        except Exception as e:
            logger.error(f"Error running engine {engine.name} on {symbol}: {str(e)}", exc_info=True)
            if failures is not None:
                # Redacted by construction: the exception TYPE and a digest, never
                # str(e) and never the traceback. The message can carry a URL with
                # a token in it; the log above already has the full detail.
                try:
                    failures.append({
                        "engine": engine.name,
                        "error_type": type(e).__name__,
                        "error_fingerprint": _error_fingerprint(engine.name, e),
                        "fallback_score": ENGINE_FALLBACK_SCORE,
                        "fallback_bias": ENGINE_FALLBACK_BIAS.value,
                        "fallback_confidence": ENGINE_FALLBACK_CONFIDENCE,
                    })
                except Exception as tel_exc:  # noqa: BLE001 — telemetry never decides
                    logger.warning("[EngineTelemetry] failure not recorded (ignored): %s", tel_exc)
            # Return a neutral result with warnings rather than crashing the orchestrator
            return EngineResult(
                engine_name=engine.name,
                score=ENGINE_FALLBACK_SCORE,
                bias=ENGINE_FALLBACK_BIAS,
                confidence=ENGINE_FALLBACK_CONFIDENCE,
                key_findings=[f"Failed to execute engine {engine.name} due to internal error"],
                supporting_data={},
                warnings=[f"Engine error: {str(e)}"],
            )

