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
from typing import Any, Awaitable, Dict

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

# Job-status board for the admin "Sistem & Scheduler" panel. Without this,
# a job silently failing every run (as perf_tracking did for days due to the
# tz-naive closed_at bug) is invisible until someone notices stale data —
# this surfaces last-run time/result/error directly.
_JOB_LABELS: Dict[str, str] = {
    "signals_1h": "1 Saatlik Sinyal Üretimi",
    "signals_4h": "4 Saatlik Sinyal Üretimi",
    "signals_15m": "15 Dakikalık Sinyal Üretimi",
    "signals_1d": "Günlük Sinyal Üretimi",
    "perf_tracking": "Performans Takibi",
    "startup_check": "Başlangıç Kontrolü",
}
_JOB_STATUS: Dict[str, Dict[str, Any]] = {}


def get_job_status() -> Dict[str, Dict[str, Any]]:
    """Snapshot of every tracked job's last run — used by the admin API."""
    out: Dict[str, Dict[str, Any]] = {}
    for job_id, label in _JOB_LABELS.items():
        out[job_id] = {"label": label, "running": False, "last_run_at": None,
                        "last_status": None, "last_error": None, "last_result": None,
                        **_JOB_STATUS.get(job_id, {})}
    return out


async def _run_tracked(job_id: str, coro: Awaitable[Any]) -> Any:
    """Await `coro` while recording start/end/result/error for `job_id`."""
    _JOB_STATUS[job_id] = {
        **_JOB_STATUS.get(job_id, {}),
        "label": _JOB_LABELS.get(job_id, job_id),
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = await coro
        _JOB_STATUS[job_id].update({
            "running": False,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": "ok",
            "last_result": result if isinstance(result, (dict, list, str, int, float, type(None))) else str(result),
            "last_error": None,
        })
        return result
    except Exception as exc:
        logger.error("[Scheduler] Job %s failed: %s", job_id, exc, exc_info=True)
        _JOB_STATUS[job_id].update({
            "running": False,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": "error",
            "last_error": str(exc),
        })
        raise


async def _job_signals_1h() -> None:
    await _run_tracked("signals_1h", _run_all_signals(timeframe="1h"))


async def _job_signals_4h() -> None:
    await _run_tracked("signals_4h", _run_all_signals(timeframe="4h"))


async def _job_signals_15m() -> None:
    await _run_tracked("signals_15m", _run_all_signals(timeframe="15m"))


async def _job_signals_1d() -> None:
    await _run_tracked("signals_1d", _run_all_signals(timeframe="1d"))


async def _job_perf_tracking() -> None:
    await _run_tracked("perf_tracking", _run_performance_tracking())


async def trigger_job_now(job_id: str) -> bool:
    """
    Fire a job immediately in the background (admin "Şimdi Çalıştır" button).
    Returns False for an unknown job_id. Signal sweeps can take minutes
    (90+ assets, throttled), so this doesn't block the HTTP request — the
    caller polls get_job_status() for completion.
    """
    job_map: Dict[str, Awaitable[Any]] = {
        "signals_1h": _run_all_signals(timeframe="1h"),
        "signals_4h": _run_all_signals(timeframe="4h"),
        "signals_15m": _run_all_signals(timeframe="15m"),
        "signals_1d": _run_all_signals(timeframe="1d"),
        "perf_tracking": _run_performance_tracking(),
    }
    coro = job_map.get(job_id)
    if coro is None:
        return False
    asyncio.create_task(_run_tracked(job_id, coro))
    return True

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

            now = datetime.now(timezone.utc)

            # Deactivate old signals for this asset+timeframe. A fresh signal
            # supersedes the old trade plan, so its performance must be closed
            # here too — otherwise it stays "ACTIVE" forever since the tracker
            # only scans is_active=True signals (this caused thousands of
            # zombie "active" signals inflating the dashboard count).
            old_res = await db.execute(
                select(Signal)
                .where(Signal.asset_id == asset.id)
                .where(Signal.timeframe == db_tf)
                .where(Signal.is_active == True)
                .options(joinedload(Signal.performance))
            )
            for old in old_res.unique().scalars().all():
                old.is_active = False
                old_perf = old.performance
                if old_perf and old_perf.outcome == SignalOutcome.ACTIVE:
                    old_perf.outcome = SignalOutcome.EXPIRED
                    old_perf.is_expired = True
                    old_perf.closed_at = now
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


async def generate_signal_now(symbol: str, asset_type: str, timeframe: str = "1h") -> None:
    """Public wrapper so the admin panel can force-regenerate a single
    symbol's signal on demand, outside the regular cron cadence."""
    await _generate_signal(symbol, asset_type, timeframe)


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


async def _run_performance_tracking() -> Dict[str, Any]:
    """Resolve active signals that hit TP/SL. Raises on failure — the cron
    wrapper and trigger_job_now() both route through _run_tracked, which is
    what actually records/logs the error; swallowing it here would hide
    failures from the admin job-status panel, which is exactly how the
    tz-naive closed_at bug went unnoticed for days."""
    async with async_session_factory() as db:
        summary = await track_and_resolve_active_signals(db)
        logger.info("[Scheduler] Performance sweep: %s", summary)
        return summary


async def _startup_generate_if_empty() -> None:
    """
    On startup, ensure each timeframe (1h, 4h, 1d) has fresh signals.
    For each TF, regenerate if no active signal exists OR the newest one
    is older than the timeframe's expected refresh interval.
    """
    from sqlalchemy import func

    # Refresh threshold per timeframe (seconds)
    THRESHOLDS = {
        "1h": 90 * 60,        # > 1.5 hours old = stale
        "4h": 5 * 3600,       # > 5 hours old = stale
        "1d": 26 * 3600,      # > 26 hours old = stale
    }

    for tf, max_age in THRESHOLDS.items():
        async with async_session_factory() as db:
            res = await db.execute(
                select(func.max(Signal.generated_at))
                .where(Signal.is_active == True)
                .where(Signal.timeframe == DBTimeframe(tf.replace("1d", "1d").upper().replace("1H", "H1").replace("4H", "H4").replace("1D", "D1")) if False else None)
            )
            # Simpler: just check newest of any active signal per tf
            # We'll match by string comparison since Timeframe is an enum
            from app.models.price_data import Timeframe as _Tf
            tf_enum_map = {"1h": _Tf.H1, "4h": _Tf.H4, "1d": _Tf.D1}
            tf_enum = tf_enum_map[tf]
            res2 = await db.execute(
                select(func.max(Signal.generated_at))
                .where(Signal.is_active == True)
                .where(Signal.timeframe == tf_enum)
            )
            newest = res2.scalar_one_or_none()

        needs_refresh = newest is None
        if newest is not None:
            now = datetime.now(timezone.utc)
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=timezone.utc)
            age_sec = (now - newest).total_seconds()
            needs_refresh = age_sec > max_age
            if needs_refresh:
                logger.info("[Scheduler] %s signals are %.1f hours old (>%.1fh threshold) — regenerating.",
                            tf, age_sec / 3600, max_age / 3600)
            else:
                logger.info("[Scheduler] %s signals fresh (%.1fh old) — skipping.", tf, age_sec / 3600)
        else:
            logger.info("[Scheduler] No active %s signals — generating now.", tf)

        if needs_refresh:
            await _run_all_signals(tf)


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
        _job_signals_1h,
        CronTrigger(minute=1),
        id="signals_1h",
        replace_existing=True,
        name="Hourly 1h signal refresh",
    )

    # 4h signals: regenerate at minute 2 of every 4th hour
    _scheduler.add_job(
        _job_signals_4h,
        CronTrigger(hour="0,4,8,12,16,20", minute=2),
        id="signals_4h",
        replace_existing=True,
        name="4h signal refresh",
    )

    # 15m signals: every 15 minutes at minute 2
    _scheduler.add_job(
        _job_signals_15m,
        CronTrigger(minute="2,17,32,47"),
        id="signals_15m",
        replace_existing=True,
        name="15m signal refresh",
    )

    # 1d signals: regenerate once a day at 00:03 UTC
    _scheduler.add_job(
        _job_signals_1d,
        CronTrigger(hour=0, minute=3),
        id="signals_1d",
        replace_existing=True,
        name="Daily 1d signal refresh",
    )

    # Performance tracking: every 2 minutes (fast invalidation detection)
    _scheduler.add_job(
        _job_perf_tracking,
        CronTrigger(minute="*/2"),
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
