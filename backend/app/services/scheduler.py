"""
TradeMinds AI – Background Scheduler

APScheduler-based background worker that:
  • Regenerates signals at candle close for each active asset
  • Tracks and resolves active signal performance
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import async_session_factory
from app.models.asset import Asset
from app.models.signal import Signal, SignalOutcome, SignalPerformance, SignalType, Direction, RiskLevel
from app.models.price_data import Timeframe as DBTimeframe
from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector
from app.engines.ai_decision.engine import AIDecisionEngine
from app.backtesting.tracker import track_and_resolve_active_signals
from app.notifications.service import notify_signal

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Timeframe → DB enum
TF_ENUM = {
    "1m": DBTimeframe.M1, "5m": DBTimeframe.M5,
    "15m": DBTimeframe.M15, "1h": DBTimeframe.H1,
    "4h": DBTimeframe.H4, "1d": DBTimeframe.D1, "1w": DBTimeframe.W1,
}
SIG_TYPE_MAP = {
    "STRONG_BUY": SignalType.STRONG_BUY, "BUY": SignalType.BUY,
    "HOLD": SignalType.HOLD, "SELL": SignalType.SELL, "STRONG_SELL": SignalType.STRONG_SELL,
}
DIR_MAP = {
    "bullish": Direction.BULLISH, "bearish": Direction.BEARISH, "neutral": Direction.NEUTRAL,
}
RISK_MAP = {
    "low": RiskLevel.LOW, "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH, "very_high": RiskLevel.VERY_HIGH,
}


async def _generate_signal(symbol: str, asset_type: str, timeframe: str = "1h") -> None:
    """Fetch live data, run AI engines, persist new signal."""
    logger.info("[Scheduler] Generating signal: %s %s", symbol, timeframe)
    binance = BinanceCollector()
    yahoo = YahooCollector()
    try:
        if asset_type == "stock" or symbol.upper().endswith(".IS"):
            df = await yahoo.fetch_ohlcv(symbol, timeframe, limit=100)
        else:
            df = await binance.fetch_ohlcv(symbol, timeframe, limit=100)
    except Exception as exc:
        logger.error("[Scheduler] Data fetch failed for %s: %s", symbol, exc)
        return
    finally:
        await binance.close()
        await yahoo.close()

    try:
        engine = AIDecisionEngine()
        decision = await engine.analyze_and_decide(
            symbol=symbol, timeframe=timeframe,
            ohlcv_data=df, asset_type=asset_type,
        )
    except Exception as exc:
        logger.error("[Scheduler] Engine failed for %s: %s", symbol, exc)
        return

    db_tf = TF_ENUM.get(timeframe, DBTimeframe.H1)

    async with async_session_factory() as db:
        try:
            # Lookup asset
            res = await db.execute(select(Asset).where(Asset.symbol == symbol.upper()))
            asset = res.scalar_one_or_none()
            if asset is None:
                logger.warning("[Scheduler] Asset not found: %s", symbol)
                return

            # Deactivate old signals for this asset+timeframe
            old_res = await db.execute(
                select(Signal)
                .where(Signal.asset_id == asset.id)
                .where(Signal.timeframe == db_tf)
                .where(Signal.is_active == True)
            )
            for old in old_res.scalars().all():
                old.is_active = False

            now = datetime.now(timezone.utc)
            new_sig = Signal(
                asset_id=asset.id,
                signal_type=SIG_TYPE_MAP.get(decision["signal_type"], SignalType.HOLD),
                confidence_score=decision["confidence_score"],
                probability_score=decision["probability_score"],
                risk_score=decision["risk_score"],
                risk_level=RISK_MAP.get(decision["risk_level"].lower(), RiskLevel.MEDIUM),
                direction=DIR_MAP.get(decision["direction"], Direction.NEUTRAL),
                entry_zone_low=decision["entry_zone_low"],
                entry_zone_high=decision["entry_zone_high"],
                stop_loss=decision["stop_loss"],
                tp1=decision["tp1"],
                tp2=decision["tp2"],
                tp3=decision["tp3"],
                invalidation_conditions=decision["invalidation_conditions"],
                engines_data=decision["engine_results"],
                explanation_tr=decision["explanation_tr"],
                explanation_en=decision["explanation_en"],
                is_active=True,
                timeframe=db_tf,
                generated_at=now,
                expires_at=now + timedelta(hours=48),
            )
            db.add(new_sig)
            await db.flush()
            db.add(SignalPerformance(signal_id=new_sig.id, outcome=SignalOutcome.ACTIVE))
            await db.commit()
            logger.info("[Scheduler] Signal saved: %s → %s (conf=%.1f%%)",
                        symbol, decision["signal_type"], decision["confidence_score"])
        except Exception as exc:
            await db.rollback()
            logger.error("[Scheduler] DB error for %s: %s", symbol, exc)
            return

    # Dispatch notification (outside DB session; never blocks signal flow)
    await notify_signal(decision, symbol, timeframe)


async def _run_all_signals(timeframe: str = "1h") -> None:
    """Regenerate signals for all active assets, with rate-limit spacing."""
    async with async_session_factory() as db:
        res = await db.execute(select(Asset).where(Asset.is_active == True))
        assets = res.scalars().all()

    logger.info("[Scheduler] Generating %s signals for %d assets", timeframe, len(assets))
    for i, asset in enumerate(assets):
        try:
            await _generate_signal(asset.symbol, asset.asset_type.value, timeframe)
        except Exception as exc:
            # _generate_signal already logs and absorbs exceptions, but belt-and-braces:
            logger.error("[Scheduler] _generate_signal raised for %s: %s", asset.symbol, exc)
        # Brief spacing so a multi-asset sweep doesn't hammer Binance/Yahoo
        if i < len(assets) - 1:
            await asyncio.sleep(1.0)
    logger.info("[Scheduler] %s sweep complete", timeframe)


async def _run_performance_tracking() -> None:
    """Resolve active signals that hit TP/SL."""
    try:
        async with async_session_factory() as db:
            summary = await track_and_resolve_active_signals(db)
            logger.info("[Scheduler] Performance sweep: %s", summary)
    except Exception as exc:
        logger.error("[Scheduler] Performance sweep failed: %s", exc)


async def _startup_generate_if_empty() -> None:
    """On startup: if no active signals exist, generate them immediately."""
    async with async_session_factory() as db:
        res = await db.execute(select(Signal).where(Signal.is_active == True).limit(1))
        has_active = res.scalar_one_or_none() is not None

    if not has_active:
        logger.info("[Scheduler] No active signals found on startup — generating now...")
        await _run_all_signals("1h")
    else:
        logger.info("[Scheduler] Active signals exist — skipping startup generation.")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    # coalesce: skip pending duplicate triggers; misfire_grace_time: still run if
    # backend was briefly down at trigger time but came back within 5 min.
    _scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 300,
        },
    )

    # 1h signals: regenerate at minute 1 of every hour
    _scheduler.add_job(
        _run_all_signals,
        CronTrigger(minute=1),
        kwargs={"timeframe": "1h"},
        id="signals_1h",
        replace_existing=True,
        name="Hourly 1h signal refresh",
    )

    # 4h signals: regenerate at minute 2 of every 4th hour
    _scheduler.add_job(
        _run_all_signals,
        CronTrigger(hour="0,4,8,12,16,20", minute=2),
        kwargs={"timeframe": "4h"},
        id="signals_4h",
        replace_existing=True,
        name="4h signal refresh",
    )

    # 15m signals: every 15 minutes at minute 2
    _scheduler.add_job(
        _run_all_signals,
        CronTrigger(minute="2,17,32,47"),
        kwargs={"timeframe": "15m"},
        id="signals_15m",
        replace_existing=True,
        name="15m signal refresh",
    )

    # Performance tracking: every 15 minutes
    _scheduler.add_job(
        _run_performance_tracking,
        CronTrigger(minute="5,20,35,50"),
        id="perf_tracking",
        replace_existing=True,
        name="Performance tracking sweep",
    )

    # Run startup check as a one-time job 5 seconds after start
    _scheduler.add_job(
        _startup_generate_if_empty,
        "date",
        id="startup_check",
        replace_existing=True,
        name="Startup signal check",
    )

    _scheduler.start()
    logger.info("[Scheduler] Started. Jobs: %s", [j.name for j in _scheduler.get_jobs()])
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
