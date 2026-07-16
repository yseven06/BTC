"""
TradeMinds AI – Signal Performance Tracker

Fetches active signals, checks subsequent price action using live data from the
Binance collector (crypto-only), and resolves trade outcomes in the DB.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, defer

from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.models.price_data import Timeframe
from app.models.asset import Asset
from app.backtesting import labels
from app.backtesting import lifecycle
from app.engines.market_regime import detect_regime
from app.engines.market_structure.structure import analyse_market_structure
from app.services.coin_memory import update_coin_memory, update_trade_mgmt_stats
from app.services.lifecycle_log import make_event
from app.notifications.service import notify_lifecycle, LIFECYCLE_ALERT_STATES
from app.backtesting.trade_path import compute_trade_path
from app.engines.ai_decision.entry_telemetry import build_entry_telemetry
from app.backtesting.resolution_core import resolve_trade_path
from app.models.intelligence import SignalSnapshot


async def _write_trade_path_failopen(db, signal, perf, *, entry, sl, tp1, tp2, tp3,
                                     mfe_pct, mae_pct, bars_total, mfe_bar_idx, mae_bar_idx,
                                     tp1_bar_idx, post_tp1_mfe, post_tp1_mae, intrabar_ambiguous,
                                     still_forming, realized_return, outcome_val, detail_label,
                                     resolved_by_sl=False, is_expired_flag=False, df=None):
    """Fail-open: build + persist one SignalTradePath row. ANY error is swallowed
    (logged) so trade-path instrumentation can NEVER block trade resolution,
    change an outcome, or affect signal_performance / coin_memory."""
    try:
        snap = (await db.execute(
            select(SignalSnapshot).where(SignalSnapshot.signal_id == signal.id)
        )).scalar_one_or_none()
        atr_pct = float(snap.atr_pct) if snap and snap.atr_pct is not None else None
        vol_ratio = float(snap.volatility_ratio) if snap and snap.volatility_ratio is not None else None
        regime = snap.regime if snap else None
        # Resolution provenance (cheap, from the bar-walk result; pure observation).
        if perf.hit_tp1:
            sl_before_tp = False          # a TP was reached before any (breakeven) SL
        elif resolved_by_sl and not intrabar_ambiguous:
            sl_before_tp = True           # clean SL, no TP and no same-bar ambiguity
        else:
            sl_before_tp = None           # ambiguous, or expired with neither hit
        tp_touched_but_sl_won = bool(intrabar_ambiguous and resolved_by_sl)
        resolution_source = "expiry" if is_expired_flag else "bar_walk"
        ez_low = float(signal.entry_zone_low) if signal.entry_zone_low is not None else None
        ez_high = float(signal.entry_zone_high) if signal.entry_zone_high is not None else None
        birth = snap.extra.get("birth") if (snap and isinstance(snap.extra, dict)) else None
        # CP-1 PASSIVE entry-detection telemetry (inside the fail-open envelope;
        # read by NOTHING — pure shadow-analysis material at extra["entry"]).
        entry_tel = build_entry_telemetry(signal, df)
        row = compute_trade_path(
            signal_id=signal.id, asset_id=signal.asset_id,
            symbol=(signal.asset.symbol if signal.asset else None),
            timeframe=_map_db_timeframe(signal.timeframe),
            direction=signal.direction.value, regime=regime,
            resolved_at=perf.closed_at, outcome=outcome_val, detail_label=detail_label,
            entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
            mfe_pct=round(max(0.0, mfe_pct), 4), mae_pct=round(max(0.0, mae_pct), 4),
            bars_total=bars_total, mfe_bar_idx=mfe_bar_idx, mae_bar_idx=mae_bar_idx,
            atr_pct=atr_pct, volatility_ratio=vol_ratio, generated_at=signal.generated_at,
            reached_tp1=perf.hit_tp1, reached_tp2=perf.hit_tp2, reached_tp3=perf.hit_tp3,
            bars_to_tp1=tp1_bar_idx if tp1_bar_idx is None else tp1_bar_idx + 1,
            post_tp1_mae_pct=round(post_tp1_mae, 4) if perf.hit_tp1 else None,
            post_tp1_mfe_pct=round(post_tp1_mfe, 4) if perf.hit_tp1 else None,
            gave_back_after_tp1=(bool(perf.hit_tp1) and not bool(perf.hit_tp2)),
            realized_return=round(realized_return, 4),
            intrabar_ambiguous=intrabar_ambiguous, still_forming_resolution=still_forming,
            sl_before_tp=sl_before_tp, resolution_source=resolution_source,
            tp_touched_but_sl_won=tp_touched_but_sl_won,
            entry_zone_low=ez_low, entry_zone_high=ez_high, birth=birth,
            entry_telemetry=entry_tel,
        )
        db.add(row)
        # Coin Memory v2 rollup (also inside the fail-open envelope) — derivable
        # cache over signal_trade_path; does not touch weight/decision logic.
        await update_trade_mgmt_stats(db, row)
    except Exception as tp_exc:
        logger.warning("TradePath instrumentation failed for %s (fail-open, ignored): %s",
                       getattr(signal, "id", "?"), tp_exc)


async def _write_trade_path_live_sl_failopen(db, signal, perf, *, entry, sl, live_price,
                                             realized_return, gave_back_after_tp1=None, df=None):
    """Fail-open trade-path write for the LIVE-SL shortcut (mid-candle stop).
    No bar-walk here, so most path metrics are genuinely UNMEASURED → kept NULL
    (never 0), so the learning layer can tell 'not measured' from '0 happened'.
    Only what we truly observe is recorded: MAE from the actual breach price,
    realized return, TP flags already on perf, context, prices. Marked
    still_forming_resolution=True (mid-candle, lower confidence)."""
    try:
        snap = (await db.execute(
            select(SignalSnapshot).where(SignalSnapshot.signal_id == signal.id)
        )).scalar_one_or_none()
        atr_pct = float(snap.atr_pct) if snap and snap.atr_pct is not None else None
        vol_ratio = float(snap.volatility_ratio) if snap and snap.volatility_ratio is not None else None
        regime = snap.regime if snap else None
        # Observed adverse excursion at the breach (real measurement); favorable
        # excursion is unknown on this path → leave MFE NULL.
        mae_pct = None
        if entry and entry != 0 and live_price is not None:
            adverse = (entry - live_price) / entry * 100.0 if signal.direction.value == "bullish" \
                else (live_price - entry) / entry * 100.0
            mae_pct = round(max(0.0, adverse), 4)
        # CP-1 PASSIVE entry-detection telemetry (fail-open envelope; read by NOTHING).
        entry_tel = build_entry_telemetry(signal, df)
        row = compute_trade_path(
            signal_id=signal.id, asset_id=signal.asset_id,
            symbol=(signal.asset.symbol if signal.asset else None),
            timeframe=_map_db_timeframe(signal.timeframe),
            direction=signal.direction.value, regime=regime,
            resolved_at=perf.closed_at, outcome=perf.outcome.value, detail_label=perf.detail_label,
            entry=entry, sl=sl,
            tp1=float(signal.tp1) if signal.tp1 is not None else None,
            tp2=float(signal.tp2) if signal.tp2 is not None else None,
            tp3=float(signal.tp3) if signal.tp3 is not None else None,
            mfe_pct=None,            # UNMEASURED on live-SL path → NULL (not 0)
            mae_pct=mae_pct,         # measured from breach price
            bars_total=None, mfe_bar_idx=None, mae_bar_idx=None,
            atr_pct=atr_pct, volatility_ratio=vol_ratio, generated_at=signal.generated_at,
            reached_tp1=perf.hit_tp1, reached_tp2=perf.hit_tp2, reached_tp3=perf.hit_tp3,
            bars_to_tp1=None,
            post_tp1_mae_pct=None, post_tp1_mfe_pct=None,
            gave_back_after_tp1=gave_back_after_tp1,   # KEY1-d: set when TP1 banked (scale-out)
            realized_return=round(realized_return, 4),
            intrabar_ambiguous=False, sl_before_tp=None, still_forming_resolution=True,
            resolution_source="live_sl",
            entry_zone_low=(float(signal.entry_zone_low) if signal.entry_zone_low is not None else None),
            entry_zone_high=(float(signal.entry_zone_high) if signal.entry_zone_high is not None else None),
            birth=(snap.extra.get("birth") if (snap and isinstance(snap.extra, dict)) else None),
            entry_telemetry=entry_tel,
            source="live",
        )
        db.add(row)
        await update_trade_mgmt_stats(db, row)
    except Exception as tp_exc:
        logger.warning("TradePath(live_sl) instrumentation failed for %s (fail-open, ignored): %s",
                       getattr(signal, "id", "?"), tp_exc)


# Canonical scale-out fractions — MUST match resolution_core.step_bar (TP1 0.50,
# TP2 0.30). Kept local (not imported) to honor KEY1-d's scope (resolution_core
# untouched); any divergence is caught by tests/test_live_sl_scaleout.py.
_LIVE_TP1_PORTION = 0.50
_LIVE_TP2_PORTION = 0.30


def live_sl_realized(direction, entry, original_sl, tp1, tp2, hit_tp1, hit_tp2):
    """Realized return (share-weighted fraction) + effective stop + gave_back for a
    LIVE-SL resolution that HONORS the stored TP1/TP2 scale-out (KEY1-d / BUG-6/7/8).

    If TP1 was banked, the position is already partially closed (50% at TP1, +30% at
    TP2) and the effective stop is BREAKEVEN (entry) — so only the REMAINING share
    closes at breakeven (≈0), NOT the full position at the original stop. Mirrors
    step_bar's scale-out accounting (same 0.50/0.30 fractions, single source).

    Returns (realized_frac, effective_stop, gave_back_after_tp1).
    TP1-not-hit → full size at the original stop (UNCHANGED, byte-identical to before)."""
    is_bull = direction == "bullish"

    def ret(level):
        return (level - entry) / entry if is_bull else (entry - level) / entry

    if not hit_tp1:
        return ret(original_sl), original_sl, None  # full size @ original stop (unchanged)

    realized = _LIVE_TP1_PORTION * ret(tp1)
    remaining = 1.0 - _LIVE_TP1_PORTION
    if hit_tp2:
        realized += _LIVE_TP2_PORTION * ret(tp2)
        remaining -= _LIVE_TP2_PORTION
    realized += remaining * ret(entry)  # remaining closes at breakeven (entry) -> 0
    return realized, entry, (hit_tp1 and not hit_tp2)


def _resolve_signal_bar_walk(*, direction, entry, stop_loss, tp1, tp2, tp3,
                             opens, highs, lows, closes, times, sig_time_aware,
                             execution_model="conservative"):
    """Bar-walk resolution via the single-source resolution_core, mapped to the
    live tracker's result fields + clamped hit timestamps. PURE (no DB / no clock).

    Byte-identical to the prior inline bar-walk — geometry locked by
    tests/test_resolution_equivalence.py, mapping locked by test_resolution_mapping.
    The WALL-CLOCK expiry decision stays in the caller; this only walks the bars it
    is given (conservative == the live SL-wins inside-bar rule)."""
    n = len(times)
    bars = [(float(opens[k]), float(highs[k]), float(lows[k]), float(closes[k])) for k in range(n)]
    res = resolve_trade_path(
        direction=direction, entry=entry, sl=stop_loss, tp1=tp1, tp2=tp2, tp3=tp3,
        bars=bars, execution_model=execution_model,
    )

    def _clamp(idx):
        # Re-attach UTC + floor at sig_time (mirrors the tracker's _aware()).
        if idx is None:
            return None
        ts = pd.Timestamp(times[idx])
        ts = ts.tz_localize(timezone.utc) if ts.tzinfo is None else ts
        return max(ts, sig_time_aware)

    return {
        "resolved": res.resolved,
        "resolved_by_sl": res.resolved_by_sl,
        "hit_tp1": res.hit_tp1, "hit_tp2": res.hit_tp2, "hit_tp3": res.hit_tp3,
        "max_favorable": res.mfe_pct, "max_drawdown": res.mae_pct,
        "mfe_bar_idx": res.mfe_bar_idx, "mae_bar_idx": res.mae_bar_idx,
        "tp1_bar_idx": res.tp1_bar_idx,
        "post_tp1_mfe": res.post_tp1_mfe_pct, "post_tp1_mae": res.post_tp1_mae_pct,
        "intrabar_ambiguous": res.intrabar_ambiguous,
        "bars_to_outcome": res.bars_walked,
        "realized_pnl_capital": res.realized_return_frac,
        "remaining_share": res.remaining_share,
        "closed_at": _clamp(res.closed_bar_idx),
        "tp1_hit_at": _clamp(res.tp1_bar_idx),
        "tp2_hit_at": _clamp(res.tp2_bar_idx),
        "tp3_hit_at": _clamp(res.tp3_bar_idx),
    }


def _post_signal_bars(signal, df):
    """The bars a pass may walk for `signal`: everything strictly after
    generated_at, plus the still-forming candle collapsed to its live close.

    VERBATIM extraction of what the tracking loop did inline — CP-F0-1H needs this
    exact frame in a second place (the live-SL shortcut), and re-implementing the
    birth-candle rule there would be the surest way to let the two drift apart.
    The rule itself is untouched; see the comments below, which came with it.
    """
    # We filter for candles that happened *after* signal generation time
    # Parse signal.generated_at to pandas datetime (naive or timezone-aware matching)
    sig_time = pd.to_datetime(signal.generated_at).tz_localize(None)
    df_naive_idx = df.index.tz_localize(None)
    df_after = df[df_naive_idx > sig_time]

    # The candle still forming when the signal was generated opened
    # *before* sig_time, so the strict `> sig_time` filter above drops
    # it entirely — but its live high/low already reflect everything
    # that's happened since (Binance's klines endpoint returns the
    # in-progress candle with continuously-updated high/low). Without
    # this, a TP/SL touch happening in that very candle stayed
    # invisible until the next candle opened — for 1h/4h/1d signals
    # that's up to a full timeframe period of "still active" lag
    # even after price had genuinely already hit the level.
    last_candle_time = df_naive_idx[-1]
    if last_candle_time not in df_after.index.tz_localize(None):
        # This candle opened before the signal existed, so we don't
        # know whether its high/low wick happened before or after
        # sig_time — OHLCV has no intra-candle ordering. A signal
        # created mid-candle can be reacting to a wick that already
        # passed, with price since pulling back toward/through entry;
        # treating that wick as a post-signal TP/SL touch produces a
        # false positive (e.g. "TP1 alındı" while the chart shows the
        # signal arrow sitting after the only candle that ever
        # touched TP1). Collapse high/low to the live close here so
        # only confirmed since-the-signal price action can trigger a
        # hit; once the candle closes, the next pass resumes normal
        # high/low checks on it as a completed bar.
        still_forming = df.iloc[[-1]].copy()
        still_forming["high"] = still_forming["close"]
        still_forming["low"] = still_forming["close"]
        df_after = pd.concat([df_after, still_forming])
    return df_after


def _sig_time_aware(signal):
    ts = pd.Timestamp(signal.generated_at)
    return ts.tz_localize(timezone.utc) if ts.tzinfo is None else ts


def _window_reaches_generation(signal, df) -> bool:
    """Does the fetched frame reach back to the signal's birth? PURE.

    The walk can only see what was fetched. If the OLDEST bar in the frame opens
    after generated_at, the bars in between were never fetched: a TP/SL that
    happened there is invisible, the walk reports nothing, and the signal falls
    through to the wall-clock expiry check — which then books an outcome on
    evidence it does not have. A fetch that FAILS is fail-safe (df is None, the
    caller skips, the signal stays ACTIVE); a fetch that comes back SHORT is not,
    because it looks like a perfectly good frame.

    CP-F0-1B scales the request to the signal's age, so this should not happen. It
    still can if a gap outruns Binance's 1000-candle ceiling (~8.4 days of downtime
    on M15) or the exchange returns fewer bars than asked for (a data gap, a halt).
    Neither has ever been observed — the longest outage on record is 2.55 days, and
    no signal has ever come close to the cap. This reports the condition rather
    than resolving quietly, so that if the assumption ever breaks it says so.

    The bar CONTAINING generated_at opens at or before it, so `<=` is full
    coverage; a signal born exactly on a bar open counts as covered.
    """
    if df is None or getattr(df, "empty", True):
        return True                      # not this check's question — caller skips these
    first = pd.Timestamp(df.index[0])
    first = first.tz_localize(timezone.utc) if first.tzinfo is None else first
    return first <= _sig_time_aware(signal)


def _live_ladder_walk(signal, df):
    """CP-F0-1H/1A: what THIS pass's bars say about the live-SL shortcut's trade —
    the bar-walk result, or None when the bars cannot answer, in which case the
    caller falls back to the stored flags (the pre-CP behaviour).

    F0-1H used only hit_tp1/hit_tp2 from this; F0-1A also reads closed_at off it for
    hit_time, so it returns the whole walk rather than replaying the bars twice.

    The live-SL shortcut books against perf.hit_tp1, which is only as fresh as the
    last pass that ran. Across a gap (the machine was off) nothing updated it, so a
    trade that banked TP1 inside the gap and then broke its stop still reads
    hit_tp1=False and gets booked as a FULL original-stop loss instead of 50% at
    TP1 plus the remainder at breakeven. CP-F0-1B widened the fetch window so the
    walk can now see into that gap; this hands the shortcut what the walk sees.

    Deliberately NOT changed: _check_live_sl_hit's own effective-stop threshold
    still uses the stored flag. A stale False there is conservative — it makes the
    check fire later (on the original stop rather than breakeven), and a check that
    doesn't fire falls through to the walk, which resolves correctly on its own.
    """
    if df is None or getattr(df, "empty", True):
        return None
    if signal.tp1 is None or signal.tp2 is None or signal.tp3 is None:
        return None
    if signal.entry_zone_low is None or signal.entry_zone_high is None:
        return None
    entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0
    if entry <= 0:
        return None
    try:
        bars = _post_signal_bars(signal, df)
        if bars.empty:
            return None
        bw = _resolve_signal_bar_walk(
            direction=signal.direction.value, entry=entry,
            stop_loss=float(signal.stop_loss),
            tp1=float(signal.tp1), tp2=float(signal.tp2), tp3=float(signal.tp3),
            opens=bars["open"].values, highs=bars["high"].values,
            lows=bars["low"].values, closes=bars["close"].values,
            times=bars.index.tolist(), sig_time_aware=_sig_time_aware(signal),
        )
    except Exception as exc:
        # Never let the ladder probe block a resolution: fall back to the stored
        # flags, i.e. exactly the pre-CP behaviour.
        logger.warning("[Tracker] ladder replay failed for %s (using stored flags): %s",
                       getattr(signal, "id", "?"), exc)
        return None
    return bw


# Timeframe → seconds, for scaling the lifecycle min-state-duration.
_TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}

# ── CP-F0-1B: fetch window ───────────────────────────────────────────────────
# Floor. detect_regime needs >= 30 bars and takes its ATR baseline from the last
# 50, so this is a correctness floor, not a nicety. It is also what keeps the
# fetch — and therefore everything downstream of it — unchanged for every signal
# whose age already fits inside it.
_MIN_FETCH_BARS = 100
# Binance /klines hard API maximum.
_MAX_FETCH_BARS = 1000
# Birth candle + still-forming candle + bar-alignment skew + margin.
_FETCH_BUFFER_BARS = 5
# The observation/lifecycle read stays on the pre-CP window (see the df_obs use
# below): tail(_OBS_BARS) of a widened frame IS the frame the old fetch returned.
_OBS_BARS = 100


def _recovery_fetch_limit(timeframe_str: str, generated_at: Any, now: datetime) -> int:
    """Candles to fetch so the resolution walk can cover generated_at → now.

    PURE: no I/O, clock injected. A fixed 100 bars spans only 25h on M15 while a
    signal lives 48h, so a TP/SL landing in the uncovered gap (i.e. after any
    downtime long enough to age the signal past the window) was invisible to the
    bar-walk and the signal fell through to EXPIRED instead. Scale to age.

    Returns exactly _MIN_FETCH_BARS whenever the age fits — true for every
    timeframe except M15 past ~23.75h — so the request is byte-identical to the
    pre-CP one for effectively the whole book.
    """
    tf_seconds = _TF_SECONDS.get(timeframe_str, 3600)
    gen = pd.Timestamp(generated_at)
    gen = gen.tz_localize(timezone.utc) if gen.tzinfo is None else gen
    ref = pd.Timestamp(now)
    ref = ref.tz_localize(timezone.utc) if ref.tzinfo is None else ref
    age_seconds = max(0.0, (ref - gen).total_seconds())
    needed = math.ceil(age_seconds / tf_seconds) + _FETCH_BUFFER_BARS
    return min(max(_MIN_FETCH_BARS, needed), _MAX_FETCH_BARS)


def _recent_structure_event(df, max_age_bars: int = 15) -> str | None:
    """Most-recent BOS/CHoCH event string (e.g. 'choch_bearish') if it occurred
    within the last `max_age_bars` candles, else None. Cheap, reuses the
    market-structure analyser on the OHLCV the tracker already holds. A stale
    break from 80 bars ago is irrelevant to a signal's current health."""
    try:
        res = analyse_market_structure(df)
    except Exception:
        return None
    recent_floor = len(df) - max_age_bars
    candidates = [e for e in (res.latest_bos, res.latest_choch) if e is not None]
    if not candidates:
        return None
    latest = max(candidates, key=lambda e: e.index)
    if latest.index < recent_floor:
        return None
    return latest.event.value
from app.collectors.binance_collector import BinanceCollector

logger = logging.getLogger(__name__)


# ── CP-F0-1E: single-flight ──────────────────────────────────────────────────
# Three callers reach the tracker — the */2min cron job, the admin "Şimdi
# Çalıştır" button (trigger_job_now, which fires a raw asyncio task and so is NOT
# covered by APScheduler's max_instances=1), and POST /signals/track-performance
# (any authenticated user, in the request's own session). Two of the three had no
# overlap protection at all, so a pass could run concurrently with another: both
# SELECT is_active signals (no row lock), both walk, both write. Today the damage
# is contained by accident — signal_trade_path.signal_id is UNIQUE, so the second
# pass's INSERT collides at commit and its whole transaction rolls back — but that
# is fragile (it depends on a constraint nobody added for this reason), it costs a
# wasted pass plus a false "error" on the admin job board, and it does not cover
# the non-resolving path at all (duplicate lifecycle events and Telegram alerts).
#
# A plain module flag, not asyncio.Lock: a Lock makes the second caller WAIT, and
# we want it to SKIP — the pass repeats every 2 minutes, so skipped work is never
# lost, whereas queueing ticks behind a slow pass piles them up. There is no await
# between the read and the write below, and asyncio is single-threaded, so the
# check-and-set is atomic by construction (a Lock's .locked() + acquire is not).
#
# In-memory is sufficient *because* the deployment is pinned to one replica with
# --workers 1 (docs/DEPLOYMENT.md, railway.json numReplicas: 1, Procfile) — the
# same constraint APScheduler already relies on. If the scheduler is ever pulled
# out into its own worker, this guard must become a cross-process one.
_tracking_in_flight = False


async def track_and_resolve_active_signals(db: AsyncSession) -> Dict[str, Any]:
    """Single-flight wrapper — at most one tracking pass runs at a time.

    A concurrent caller returns immediately with ``skipped`` instead of waiting.
    The successful path's return value is unchanged (no extra keys), so every
    existing caller keeps reading the same contract.
    """
    global _tracking_in_flight
    if _tracking_in_flight:
        logger.info("[Tracker] a pass is already in flight — skipping this call")
        return {"processed": 0, "resolved": 0, "details": [], "skipped": True}
    _tracking_in_flight = True
    try:
        return await _track_and_resolve_active_signals_impl(db)
    finally:
        # finally, not a trailing assignment: a pass that raises (a failed commit,
        # a collector blowing up) must not leave the flag stuck True and wedge
        # every future pass for the lifetime of the process.
        _tracking_in_flight = False


async def _track_and_resolve_active_signals_impl(db: AsyncSession) -> Dict[str, Any]:
    """Scans all active signals, checks subsequent market action, and updates database outcomes."""
    logger.info("Initializing active signal performance tracking run")

    # 1. Fetch all active signals with asset relations
    # Egress optimization (Öncelik 1): the tracker never reads these heavy
    # columns (engines_data ~4.2 KB, explanations ~3.6 KB, invalidation), yet
    # they were shipped for every active signal every 2-minute pass (~190 MB/day).
    # Defer them so the SELECT skips them entirely. Lifecycle logic is unchanged
    # — it only uses levels/status/perf/asset.
    query = (
        select(Signal)
        .options(
            selectinload(Signal.asset),
            selectinload(Signal.performance),
            defer(Signal.engines_data),
            defer(Signal.explanation_tr),
            defer(Signal.explanation_en),
            defer(Signal.invalidation_conditions),
        )
        .where(Signal.is_active == True)
    )
    result = await db.execute(query)
    active_signals = result.scalars().all()
    
    if not active_signals:
        logger.info("No active signals found in the database")
        return {"processed": 0, "resolved": 0, "details": []}

    # Instantiate collectors (crypto-only: Binance is the sole data source).
    binance = BinanceCollector()

    processed_count = 0
    resolved_count = 0
    details = []

    try:
        # ── Pass 1: Live ticker check ────────────────────────────────────────
        # Mum kapanışını beklemeden anlık SL kırılmasını yakala. Bu sayede
        # kullanıcı saatlerce "AKTİF SL altında" görmek yerine birkaç saniye
        # içinde "PATLADI" durumunu görür.
        live_tasks = [
            _check_live_sl_hit(signal, binance)
            for signal in active_signals
        ]
        live_results = await asyncio.gather(*live_tasks, return_exceptions=True)
        live_hit_by_sig: Dict[Any, Dict[str, Any]] = {}
        for res in live_results:
            if isinstance(res, dict) and res.get("hit"):
                live_hit_by_sig[res["signal_id"]] = res

        # Fetch pricing history for all active signals concurrently (for TP/SL bar checks).
        # return_exceptions=True so one bad signal/symbol can't take down the
        # whole pass — without it, every other active signal (including ones
        # that had already blown through their stop-loss) silently stopped
        # getting re-checked the moment any single task raised.
        tasks = [
            _fetch_market_data_for_signal(signal, binance)
            for signal in active_signals
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dfs_by_signal_id: Dict[Any, pd.DataFrame | None] = {}
        for signal, res in zip(active_signals, results):
            if isinstance(res, BaseException):
                logger.error("Market data fetch raised for signal %s: %s", signal.id, res)
                dfs_by_signal_id[signal.id] = None
            else:
                sig_id, df = res
                dfs_by_signal_id[sig_id] = df

        # P1.2: collect real lifecycle transitions into alert states during the loop;
        # dispatched AFTER commit (outside the DB session), fire-and-forget.
        lifecycle_alerts: List[Dict[str, Any]] = []

        for signal in active_signals:
            processed_count += 1
            asset: Asset = signal.asset
            symbol = asset.symbol

            # ── Live SL hit shortcut: anlık fiyat zaten SL'yi geçti ──
            live_hit = live_hit_by_sig.get(signal.id)
            if live_hit:
                entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0
                perf = signal.performance
                if not perf:
                    perf = SignalPerformance(signal_id=signal.id, outcome=SignalOutcome.ACTIVE)
                    db.add(perf)
                # KEY1-d: honor the TP1/TP2 scale-out. A TP1-banked trade closes
                # its REMAINING share at breakeven (entry), not the full position at the
                # original stop (BUG-6/7/8). TP1-not-hit is UNCHANGED (full original-stop
                # loss). Single source: live_sl_realized mirrors step_bar's 0.50/0.30 + BE.
                # CP-F0-1H: read the scale-out from THIS pass's bars, not from perf —
                # perf is only as fresh as the last pass that ran, so a TP1 banked
                # during a gap reads False and books a full loss (see _live_ladder_walk).
                # No bars to answer with → stored flags, i.e. the pre-CP behaviour.
                _bw_live = _live_ladder_walk(signal, dfs_by_signal_id.get(signal.id))
                _hit1, _hit2 = ((bool(_bw_live["hit_tp1"]), bool(_bw_live["hit_tp2"]))
                                if _bw_live else (bool(perf.hit_tp1), bool(perf.hit_tp2)))
                realized_frac, effective_sl, gave_back = live_sl_realized(
                    signal.direction.value, entry, float(signal.stop_loss),
                    float(signal.tp1) if signal.tp1 is not None else entry,
                    float(signal.tp2) if signal.tp2 is not None else entry,
                    _hit1, _hit2,
                )
                pnl_pct = realized_frac * 100.0
                signal.is_active = False
                if pnl_pct > 0.5:
                    perf.outcome = SignalOutcome.WIN
                elif pnl_pct < -0.5:
                    perf.outcome = SignalOutcome.LOSS
                else:
                    perf.outcome = SignalOutcome.BREAKEVEN
                perf.actual_return = pnl_pct
                perf.closed_at = datetime.now(timezone.utc)
                # F0-1A: closed_at above is the WALL CLOCK on this path — the ticker
                # says the stop is broken now, and after a gap "now" can be hours
                # after the break. Record the split beside it: hit_time is the bar
                # the walk points at, but only when the walk agrees this was a stop.
                # A mid-candle break no bar shows yet leaves it NULL — there is no
                # bar to name, and NULL means "not recorded", never a guess.
                perf.hit_time = (_bw_live["closed_at"]
                                 if _bw_live and _bw_live["resolved_by_sl"] else None)
                perf.detected_at = perf.closed_at
                perf.detail_label = labels.LIVE_SL_HIT
                # F1-d: who resolved it, under which semantics. Telemetry only.
                perf.resolution_source = labels.RES_SRC_LIVE_SL
                perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION
                try:
                    await update_coin_memory(db, signal, perf, symbol.upper())
                except Exception as mem_exc:
                    logger.warning("CoinMemory update failed for %s: %s", symbol, mem_exc)
                db.add(make_event(
                    signal_id=signal.id, from_status=signal.live_status,
                    to_status="closed", kind="resolution",
                    reason=labels.label_tr(perf.detail_label), outcome=perf.outcome.value,
                    price=live_hit["live_price"],
                ))
                # Trade-path instrumentation for the live-SL path (fail-open;
                # unmeasured metrics stay NULL — see helper).
                await _write_trade_path_live_sl_failopen(
                    db, signal, perf, entry=entry, sl=effective_sl,
                    live_price=live_hit["live_price"], realized_return=pnl_pct,
                    gave_back_after_tp1=gave_back, df=dfs_by_signal_id.get(signal.id),
                )
                resolved_count += 1
                details.append({
                    "signal_id": str(signal.id),
                    "symbol": symbol,
                    "outcome": perf.outcome.value,
                    "return": round(pnl_pct, 2),
                    "trigger": "live_sl",
                    "live_price": live_hit["live_price"],
                })
                logger.info(
                    "Signal %s (%s) PATLADI via live ticker — live=%.6f effSL=%.6f PnL=%.2f%%",
                    signal.id, symbol, live_hit["live_price"], effective_sl, pnl_pct,
                )
                continue

            # Same None-guard as _fetch_market_data_for_signal above: a HOLD
            # signal has no entry_zone_low/high (both NULL), and this used to
            # compute `entry` before checking signal_type — `None + None`
            # crashed this whole function (and, before the gather() fix
            # above, the entire tracking pass) the instant a HOLD signal
            # showed up anywhere in the active set.
            if signal.signal_type.value == "HOLD" or signal.entry_zone_high is None or signal.entry_zone_low is None:
                entry = 0.0
            else:
                entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0
            if signal.signal_type.value == "HOLD" or entry <= 0:
                # Silently handle expiration/deactivation for HOLD signals
                now_utc = datetime.now(timezone.utc)
                expires = signal.expires_at.replace(tzinfo=timezone.utc) if signal.expires_at else None
                if expires and now_utc >= expires:
                    signal.is_active = False
                    perf = signal.performance
                    if perf:
                        perf.outcome = SignalOutcome.EXPIRED
                        perf.is_expired = True
                        perf.closed_at = now_utc
                        # F0-1A: a HOLD has no trade plan, so there is no level to
                        # hit — hit_time stays NULL by definition, not by omission.
                        perf.detected_at = now_utc
                        # F1-d: who resolved it, under which semantics. Telemetry
                        # only — the EXPIRED-enum-with-NULL-label shape this path
                        # shares with the admin paths is now distinguishable.
                        perf.resolution_source = labels.RES_SRC_HOLD_EXPIRY
                        perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION
                    resolved_count += 1
                continue

            df = dfs_by_signal_id.get(signal.id)
            if df is None or df.empty:
                logger.warning(f"No price data returned for {symbol}")
                continue

            # Post-generation bars + the birth-candle rule — single source, shared
            # with the live-SL shortcut's ladder replay (CP-F0-1H). Policy unchanged.
            df_after = _post_signal_bars(signal, df)

            # CP-F0-1F: report — do NOT act on — a frame that does not reach back to
            # generated_at. Resolution below is deliberately unchanged: the condition
            # has never been observed, so leaving signals ACTIVE for it would be a
            # behaviour change bought with no evidence. This only makes it visible.
            # cap-bound (len == the ceiling) means downtime outran the 1000-candle
            # limit; short of it means the exchange had no data to give.
            if not _window_reaches_generation(signal, df):
                logger.warning(
                    "[Tracker] %s (%s) signal %s: fetched window starts at %s but the "
                    "signal was generated at %s — %d bars, cap-bound=%s. The walk cannot "
                    "see a TP/SL before that first bar, so an unresolved signal may reach "
                    "the expiry check on incomplete evidence.",
                    symbol, _map_db_timeframe(signal.timeframe), signal.id,
                    df.index[0], signal.generated_at, len(df),
                    len(df) >= _MAX_FETCH_BARS,
                )

            if df_after.empty:
                logger.info(f"No new price bars recorded since signal generation for {symbol}")
                continue

            # Analyze subsequent bars step-by-step
            stop_loss = float(signal.stop_loss)
            tp1 = float(signal.tp1)
            tp2 = float(signal.tp2)
            tp3 = float(signal.tp3)
            entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0  # approximate entry
            
            # Check performance properties
            perf = signal.performance
            if not perf:
                perf = SignalPerformance(signal_id=signal.id, outcome=SignalOutcome.ACTIVE)
                db.add(perf)

            resolved = False
            outcome = SignalOutcome.ACTIVE
            pnl_pct = 0.0
            max_drawdown = 0.0
            max_favorable = 0.0   # MFE: best in-our-favour move (% of entry)
            bars_to_outcome = 0
            resolved_by_sl = False
            is_expired_flag = False
            # Observation-only (Trade Management Faz1 instrumentation) — these
            # NEVER affect any resolution decision; pure path facts.
            mfe_bar_idx = 0
            mae_bar_idx = 0
            tp1_bar_idx = None
            post_tp1_mfe = 0.0
            post_tp1_mae = 0.0
            intrabar_ambiguous = False
            
            hit_tp1 = False
            hit_tp2 = False
            hit_tp3 = False
            tp1_hit_at = None
            tp2_hit_at = None
            tp3_hit_at = None

            closed_at = None

            sig_time_aware = pd.Timestamp(signal.generated_at)
            if sig_time_aware.tzinfo is None:
                sig_time_aware = sig_time_aware.tz_localize(timezone.utc)

            def _aware(ts: Any) -> Any:
                """times[] entries are tz-naive (we stripped tz to compare against
                sig_time) but the DB column is TIMESTAMP WITH TIME ZONE — asyncpg
                rejects naive datetimes outright. Re-attach UTC before saving.

                Also floors the result at sig_time: the "still-forming candle"
                appended above (see comment near df_after) opened *before* the
                signal existed, so its bar_time can be earlier than
                generated_at. A TP/SL hit timestamp before the signal's own
                creation time reads as a contradiction in the UI (e.g. a closed
                signal chart showing the resolution marker to the left of the
                "signal started" marker) — clamp it forward instead."""
                ts = pd.Timestamp(ts)
                ts = ts.tz_localize(timezone.utc) if ts.tzinfo is None else ts
                return max(ts, sig_time_aware)

            opens = df_after["open"].values
            highs = df_after["high"].values
            lows = df_after["low"].values
            closes = df_after["close"].values
            times = df_after.index.tolist()

            # Single-source resolution (byte-identical to the prior inline bar-walk —
            # locked by tests/test_resolution_equivalence.py + test_resolution_mapping).
            # The wall-clock expiry decision below is unchanged.
            _bw = _resolve_signal_bar_walk(
                direction=signal.direction.value, entry=entry,
                stop_loss=stop_loss, tp1=tp1, tp2=tp2, tp3=tp3,
                opens=opens, highs=highs, lows=lows, closes=closes,
                times=times, sig_time_aware=sig_time_aware,
            )
            resolved = _bw["resolved"]
            resolved_by_sl = _bw["resolved_by_sl"]
            hit_tp1, hit_tp2, hit_tp3 = _bw["hit_tp1"], _bw["hit_tp2"], _bw["hit_tp3"]
            max_favorable = _bw["max_favorable"]
            max_drawdown = _bw["max_drawdown"]
            mfe_bar_idx = _bw["mfe_bar_idx"]
            mae_bar_idx = _bw["mae_bar_idx"]
            tp1_bar_idx = _bw["tp1_bar_idx"]
            post_tp1_mfe = _bw["post_tp1_mfe"]
            post_tp1_mae = _bw["post_tp1_mae"]
            intrabar_ambiguous = _bw["intrabar_ambiguous"]
            bars_to_outcome = _bw["bars_to_outcome"]
            realized_pnl_capital = _bw["realized_pnl_capital"]
            remaining_share = _bw["remaining_share"]
            if _bw["closed_at"] is not None:
                closed_at = _bw["closed_at"]
            if _bw["tp1_hit_at"] is not None:
                tp1_hit_at = _bw["tp1_hit_at"]
            if _bw["tp2_hit_at"] is not None:
                tp2_hit_at = _bw["tp2_hit_at"]
            if _bw["tp3_hit_at"] is not None:
                tp3_hit_at = _bw["tp3_hit_at"]

            # If not resolved by high/low, check for signal expiration
            if not resolved:
                now_utc = datetime.now(timezone.utc)
                expires = signal.expires_at.replace(tzinfo=timezone.utc) if signal.expires_at else None
                
                if expires and now_utc >= expires:
                    resolved = True
                    is_expired_flag = True
                    bars_to_outcome = len(df_after)
                    last_close = float(closes[-1])
                    closed_at = _aware(times[-1])
                    
                    ret_close = ((last_close - entry) / entry) if signal.direction.value == "bullish" else ((entry - last_close) / entry)
                    realized_pnl_capital += remaining_share * ret_close
                    remaining_share = 0.0

            # Save resolution if found
            if resolved:
                pnl_pct = realized_pnl_capital * 100.0
                resolved_count += 1
                signal.is_active = False
                
                if pnl_pct > 0.5:
                    outcome = SignalOutcome.WIN
                elif pnl_pct < -0.5:
                    outcome = SignalOutcome.LOSS
                else:
                    outcome = SignalOutcome.BREAKEVEN
                
                perf.outcome = outcome
                perf.actual_return = pnl_pct
                perf.max_drawdown = max(0.0, max_drawdown)
                perf.mfe_pct = max(0.0, max_favorable)
                perf.bars_to_outcome = bars_to_outcome
                perf.hit_tp1 = hit_tp1
                perf.hit_tp2 = hit_tp2
                perf.hit_tp3 = hit_tp3
                perf.tp1_hit_at = tp1_hit_at
                perf.tp2_hit_at = tp2_hit_at
                perf.tp3_hit_at = tp3_hit_at
                perf.closed_at = closed_at
                # F0-1A: closed_at above is the hit bar when the walk resolved, but
                # the LAST bar when the wall-clock expiry claimed the signal — two
                # meanings in one column. Split them: _bw["closed_at"] is non-None
                # exactly when the walk resolved, so it is the hit, and NULL reads
                # as "expired, there was no hit". detected_at is when we wrote it —
                # on a live system that trails the bar by up to one pass, after
                # downtime by the whole outage.
                perf.hit_time = _bw["closed_at"]
                perf.detected_at = datetime.now(timezone.utc)
                perf.is_expired = is_expired_flag
                perf.detail_label = labels.classify_resolution(
                    hit_tp1=hit_tp1, hit_tp2=hit_tp2, hit_tp3=hit_tp3,
                    resolved_by_sl=resolved_by_sl, is_expired=is_expired_flag,
                    pnl_pct=pnl_pct, mfe_pct=max(0.0, max_favorable),
                    entry=entry, tp1=tp1,
                )
                # F1-d: who resolved it, under which semantics. Telemetry only —
                # the same expiry-vs-walk split the trade-path row records, but
                # on the source of truth (trade-path writes are fail-open).
                perf.resolution_source = (labels.RES_SRC_EXPIRY if is_expired_flag
                                          else labels.RES_SRC_BAR_WALK)
                perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION
                # Fold this resolution into the coin's learned memory.
                try:
                    await update_coin_memory(db, signal, perf, symbol.upper())
                except Exception as mem_exc:
                    logger.warning("CoinMemory update failed for %s: %s", symbol, mem_exc)
                # Observability: close the lifecycle timeline with the outcome.
                db.add(make_event(
                    signal_id=signal.id, from_status=signal.live_status,
                    to_status="closed", kind="resolution",
                    reason=labels.label_tr(perf.detail_label), outcome=outcome.value,
                    price=float(closes[-1]),
                ))
                # Trade-path instrumentation (fail-open — never blocks resolution).
                await _write_trade_path_failopen(
                    db, signal, perf, entry=entry, sl=stop_loss, tp1=tp1, tp2=tp2, tp3=tp3,
                    mfe_pct=max_favorable, mae_pct=max_drawdown, bars_total=bars_to_outcome,
                    mfe_bar_idx=mfe_bar_idx, mae_bar_idx=mae_bar_idx, tp1_bar_idx=tp1_bar_idx,
                    post_tp1_mfe=post_tp1_mfe, post_tp1_mae=post_tp1_mae,
                    intrabar_ambiguous=intrabar_ambiguous,
                    still_forming=False, realized_return=pnl_pct,
                    outcome_val=outcome.value, detail_label=perf.detail_label,
                    resolved_by_sl=resolved_by_sl, is_expired_flag=is_expired_flag,
                    df=df,
                )

                details.append({
                    "signal_id": str(signal.id),
                    "symbol": symbol,
                    "outcome": outcome.value,
                    "detail_label": perf.detail_label,
                    "return": round(pnl_pct, 2),
                    "max_drawdown": round(max_drawdown, 2),
                    "mfe": round(max_favorable, 2),
                    "bars": bars_to_outcome,
                    "is_expired": is_expired_flag,
                })
                logger.info(f"Signal {signal.id} ({symbol}) resolved as {outcome.value} (PnL: {pnl_pct:.2f}%, Expired: {is_expired_flag})")
            else:
                # Update partial target hits — TP1/TP2 can trigger while the
                # position is still open (scaled out, riding to TP3/SL), so
                # record their hit times now rather than waiting for the
                # eventual full close.
                # CP-F0-1H: write the flag and its timestamp from the SAME walk
                # result. They used to disagree: the flag was overwritten every
                # pass while the timestamp was only ever written when truthy, so a
                # TP1 that one pass saw and the next did not left hit_tp1=False
                # beside a populated tp1_hit_at (5 such rows exist). The resolved
                # branch above already writes both unconditionally; this makes the
                # two branches agree. Safe to clear now that CP-F0-1B removed the
                # truncated-window case — what a later walk drops is a stale
                # reading it no longer supports, not data it simply failed to see.
                perf.hit_tp1 = hit_tp1
                perf.hit_tp2 = hit_tp2
                perf.hit_tp3 = hit_tp3
                perf.tp1_hit_at = tp1_hit_at
                perf.tp2_hit_at = tp2_hit_at
                perf.tp3_hit_at = tp3_hit_at
                perf.max_drawdown = max(0.0, max_drawdown)
                perf.mfe_pct = max(0.0, max_favorable)
                perf.bars_to_outcome = bars_to_outcome

                # Live lifecycle status v2 — "is this signal still valid right
                # now?". Cheap (no engine re-run, no extra network): regime +
                # structure (BOS/CHoCH) + momentum, all from the OHLCV already
                # fetched. Structure is confirmation only; INVALIDATING needs
                # price retrace AND structure+momentum together. Hysteresis and
                # a timeframe-scaled min-state-duration damp pass-to-pass
                # flip-flop (escalation toward danger stays immediate).
                # CP-F0-1B: the fetch window now scales with signal age so the
                # bar-walk above can cover generated_at → now. Everything in THIS
                # block reads indicators off the WHOLE frame — detect_regime's
                # EMA/Wilder recursion and analyse_market_structure's swing scan
                # both shift when handed more history — so a widened frame would
                # silently move regime/structure, and with them live_status. That
                # is a lifecycle change this CP explicitly does not make. Pin the
                # observation read to the pre-CP window: tail(_OBS_BARS) of the
                # widened frame IS the frame the old fetch returned, so regime,
                # structure and momentum stay byte-identical. Only the resolution
                # walk (df_after) sees the extra history.
                df_obs = df.tail(_OBS_BARS)
                try:
                    cur_regime = detect_regime(df_obs).regime.value
                except Exception:
                    cur_regime = None
                structure_event = _recent_structure_event(df_obs)
                # Immediate momentum (INVALIDATING confirmed-cluster path) +
                # v2.2 persistence-filtered momentum (WEAKENING trigger only,
                # N=2 consecutive bars) to damp single-bar active↔weakening churn.
                momentum_dir = lifecycle.momentum_direction(df_obs)
                momentum_dir_weak = lifecycle.momentum_direction(df_obs, persist=2)

                now_eval = datetime.now(timezone.utc)
                prev_status = signal.live_status
                seconds_in_state = None
                if signal.live_status_since is not None:
                    since = signal.live_status_since
                    if since.tzinfo is None:
                        since = since.replace(tzinfo=timezone.utc)
                    seconds_in_state = (now_eval - since).total_seconds()
                bar_seconds = _TF_SECONDS.get(_map_db_timeframe(signal.timeframe), 3600)
                min_state_seconds = max(180, int(bar_seconds * 0.25))

                lc = lifecycle.evaluate_lifecycle(
                    direction=signal.direction.value,
                    entry=entry, stop_loss=stop_loss, tp1=tp1,
                    current_price=float(closes[-1]),
                    current_regime=cur_regime,
                    structure_event=structure_event,
                    momentum_dir=momentum_dir,
                    momentum_dir_weak=momentum_dir_weak,
                    prev_status=prev_status,
                    seconds_in_state=seconds_in_state,
                    min_state_seconds=min_state_seconds,
                )
                signal.live_status = lc.status
                signal.status_reason = lc.reason
                signal.status_updated_at = now_eval

                # Observability: a guard blocked a real candidate change → bump
                # the prevented-flip-flop counter (no history row for these).
                if lc.suppressed:
                    signal.flipflop_prevented_count = (signal.flipflop_prevented_count or 0) + 1

                # Real transition (incl. first-ever) → advance since + log ONE
                # history row. A pass with no change writes nothing.
                if prev_status != lc.status or signal.live_status_since is None:
                    signal.live_status_since = now_eval
                    db.add(make_event(
                        signal_id=signal.id,
                        from_status=prev_status,
                        to_status=lc.status,
                        kind="birth" if prev_status is None else "transition",
                        reason=lc.reason,
                        regime=cur_regime,
                        price=float(closes[-1]),
                        retrace_to_sl=lc.retrace_to_sl,
                        progress_to_tp=lc.progress_to_tp,
                        structure_event=structure_event,
                        momentum_dir=momentum_dir,
                    ))

                    # P1.2: queue a proactive alert for a REAL transition (not birth)
                    # INTO an alert state. Opt-in users only; dispatched after commit.
                    # Purely additive — detection/persist above are unchanged.
                    if prev_status is not None and lc.status in LIFECYCLE_ALERT_STATES:
                        lifecycle_alerts.append({
                            "symbol": symbol,
                            "timeframe": signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe),
                            "direction": signal.direction.value,
                            "old_status": prev_status,
                            "new_status": lc.status,
                            "reason": lc.reason,
                            "price": float(closes[-1]),
                        })

        # Commit DB updates
        await db.commit()

        # P1.2: dispatch queued lifecycle alerts AFTER commit, OUTSIDE the DB session
        # (fire-and-forget; notify_lifecycle is opt-in gated + fail-open, so this can
        # never block or roll back a tracking pass).
        for _alert in lifecycle_alerts:
            try:
                await notify_lifecycle(**_alert)
            except Exception as _exc:
                logger.warning("[Tracker] lifecycle alert dispatch failed: %s", _exc)

    finally:
        await binance.close()

    return {
        "processed": processed_count,
        "resolved": resolved_count,
        "details": details,
    }


def _map_db_timeframe(db_tf: Timeframe) -> str:
    """Map database Timeframe enum to collector string timeframes."""
    mapping = {
        Timeframe.M1: "1m",
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
        Timeframe.D1: "1d",
        Timeframe.W1: "1w",
    }
    return mapping.get(db_tf, "1h")


async def _check_live_sl_hit(
    signal: Signal, binance: BinanceCollector,
) -> Dict[str, Any] | None:
    """
    Fetch the current ticker price and immediately resolve the signal as LOSS
    if the live price has already breached the stop-loss. This catches mid-candle
    invalidations that the bar-close tracker would otherwise miss.
    """
    if signal.signal_type.value == "HOLD":
        return {"signal_id": signal.id, "hit": False}
    if not signal.stop_loss or not signal.entry_zone_low or not signal.entry_zone_high:
        return {"signal_id": signal.id, "hit": False}

    asset: Asset = signal.asset
    symbol = asset.symbol
    try:
        ticker = await binance.fetch_ticker(symbol)
        live_price = float(ticker.get("current_price", 0))
    except Exception as exc:
        logger.debug("Live ticker fetch failed for %s: %s", symbol, exc)
        return {"signal_id": signal.id, "hit": False}

    if live_price <= 0:
        return {"signal_id": signal.id, "hit": False}

    direction = signal.direction.value
    # Effective stop honors the stored scale-out (KEY1-d): once TP1 is banked the live
    # stop is BREAKEVEN (entry), not the original stop — so a TP1-banked trade resolves
    # at BE, never as a full original-stop loss. TP1-not-hit → original stop (unchanged).
    perf = signal.performance
    if perf and perf.hit_tp1 and signal.entry_zone_low is not None and signal.entry_zone_high is not None:
        effective_sl = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0  # breakeven = entry
    else:
        effective_sl = float(signal.stop_loss)
    # LONG: anlık fiyat etkin-SL'nin altındaysa stop kırıldı; SHORT: üstündeyse.
    hit = (direction == "bullish" and live_price <= effective_sl) or \
          (direction == "bearish" and live_price >= effective_sl)
    return {"signal_id": signal.id, "hit": hit, "live_price": live_price}


async def _fetch_market_data_for_signal(
    signal: Signal, binance: BinanceCollector
) -> tuple[Any, pd.DataFrame | None]:
    # A HOLD signal has no real trade plan, so entry_zone_low/high are NULL
    # (see scheduler.py) — `None + None` raises TypeError, and this runs
    # inside asyncio.gather() without return_exceptions=True, so one HOLD
    # signal in the active set used to crash the *entire* tracking pass:
    # every other active signal (including ones that had genuinely already
    # blown through their stop-loss) silently never got re-checked again
    # until this function stopped throwing. Guard the None case before
    # touching the values at all.
    if signal.signal_type.value == "HOLD" or signal.entry_zone_high is None or signal.entry_zone_low is None:
        return signal.id, None
    entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0
    if entry <= 0:
        return signal.id, None

    asset: Asset = signal.asset
    symbol = asset.symbol
    timeframe_str = _map_db_timeframe(signal.timeframe)
    logger.info(f"Checking performance for signal {signal.id} - {symbol} ({signal.timeframe.value})")
    try:
        limit = _recovery_fetch_limit(
            timeframe_str, signal.generated_at, datetime.now(timezone.utc)
        )
        if limit > _MIN_FETCH_BARS:
            logger.info(
                "[Tracker] %s (%s) is older than the default window — fetching %d bars "
                "so the walk covers generated_at → now", symbol, timeframe_str, limit,
            )
        df = await binance.fetch_ohlcv(symbol, timeframe_str, limit=limit)
        return signal.id, df
    except Exception as e:
        logger.error(f"Failed to fetch market data for {symbol} during tracking: {str(e)}")
        return signal.id, None

