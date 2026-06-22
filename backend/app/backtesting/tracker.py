"""
TradeMinds AI – Signal Performance Tracker

Fetches active signals, checks subsequent price action using live data feeds
from Binance and Yahoo Finance collectors, and resolves trade outcomes in the DB.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.signal import Signal, SignalOutcome, SignalPerformance
from app.models.price_data import Timeframe
from app.models.asset import Asset
from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector

logger = logging.getLogger(__name__)


async def track_and_resolve_active_signals(db: AsyncSession) -> Dict[str, Any]:
    """Scans all active signals, checks subsequent market action, and updates database outcomes."""
    logger.info("Initializing active signal performance tracking run")

    # 1. Fetch all active signals with asset relations
    query = (
        select(Signal)
        .options(selectinload(Signal.asset), selectinload(Signal.performance))
        .where(Signal.is_active == True)
    )
    result = await db.execute(query)
    active_signals = result.scalars().all()
    
    if not active_signals:
        logger.info("No active signals found in the database")
        return {"processed": 0, "resolved": 0, "details": []}

    # Instantiate collectors
    binance = BinanceCollector()
    yahoo = YahooCollector()

    processed_count = 0
    resolved_count = 0
    details = []

    try:
        # ── Pass 1: Live ticker check ────────────────────────────────────────
        # Mum kapanışını beklemeden anlık SL kırılmasını yakala. Bu sayede
        # kullanıcı saatlerce "AKTİF SL altında" görmek yerine birkaç saniye
        # içinde "PATLADI" durumunu görür.
        live_tasks = [
            _check_live_sl_hit(signal, binance, yahoo)
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
            _fetch_market_data_for_signal(signal, binance, yahoo)
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

        for signal in active_signals:
            processed_count += 1
            asset: Asset = signal.asset
            symbol = asset.symbol

            # ── Live SL hit shortcut: anlık fiyat zaten SL'yi geçti ──
            live_hit = live_hit_by_sig.get(signal.id)
            if live_hit:
                entry = float(signal.entry_zone_high + signal.entry_zone_low) / 2.0
                sl = float(signal.stop_loss)
                ret_sl = ((sl - entry) / entry) if signal.direction.value == "bullish" else ((entry - sl) / entry)
                pnl_pct = ret_sl * 100.0
                perf = signal.performance
                if not perf:
                    perf = SignalPerformance(signal_id=signal.id, outcome=SignalOutcome.ACTIVE)
                    db.add(perf)
                signal.is_active = False
                perf.outcome = SignalOutcome.LOSS if pnl_pct < -0.5 else SignalOutcome.BREAKEVEN
                perf.actual_return = pnl_pct
                perf.closed_at = datetime.now(timezone.utc)
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
                    "Signal %s (%s) PATLADI via live ticker — live=%.6f SL=%.6f PnL=%.2f%%",
                    signal.id, symbol, live_hit["live_price"], sl, pnl_pct,
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
                    resolved_count += 1
                continue

            df = dfs_by_signal_id.get(signal.id)
            if df is None or df.empty:
                logger.warning(f"No price data returned for {symbol}")
                continue

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
                df_after = pd.concat([df_after, df.iloc[[-1]]])

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
            is_expired_flag = False
            
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

            remaining_share = 1.0
            realized_pnl_capital = 0.0
            current_sl = stop_loss

            for k in range(len(df_after)):
                bar_open = float(opens[k])
                bar_high = float(highs[k])
                bar_low = float(lows[k])
                bar_close = float(closes[k])
                bar_time = times[k]

                # Update drawdown
                if signal.direction.value == "bullish":
                    drawdown = ((entry - bar_low) / entry) * 100.0 if entry > 0 else 0.0
                    max_drawdown = max(max_drawdown, drawdown)
                else:
                    drawdown = ((bar_high - entry) / entry) * 100.0 if entry > 0 else 0.0
                    max_drawdown = max(max_drawdown, drawdown)

                # Check SL hit
                sl_hit = bar_low <= current_sl if signal.direction.value == "bullish" else bar_high >= current_sl
                
                # Check TP hits
                if signal.direction.value == "bullish":
                    tp1_triggered = bar_high >= tp1 and not hit_tp1
                    tp2_triggered = bar_high >= tp2 and not hit_tp2
                    tp3_triggered = bar_high >= tp3 and not hit_tp3
                else:
                    tp1_triggered = bar_low <= tp1 and not hit_tp1
                    tp2_triggered = bar_low <= tp2 and not hit_tp2
                    tp3_triggered = bar_low <= tp3 and not hit_tp3
                
                tp_hit = tp1_triggered or tp2_triggered or tp3_triggered
                
                # Inside-bar ambiguity resolution (conservative: SL wins)
                if sl_hit and tp_hit:
                    tp_hit = False
                    tp1_triggered = tp2_triggered = tp3_triggered = False

                # Process
                if sl_hit:
                    ret_sl = ((current_sl - entry) / entry) if signal.direction.value == "bullish" else ((entry - current_sl) / entry)
                    realized_pnl_capital += remaining_share * ret_sl
                    remaining_share = 0.0
                    resolved = True
                    closed_at = _aware(bar_time)
                    break
                elif tp_hit:
                    if tp1_triggered:
                        hit_tp1 = True
                        tp1_hit_at = _aware(bar_time)
                        portion = 0.50
                        ret_tp1 = ((tp1 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp1) / entry)
                        realized_pnl_capital += portion * ret_tp1
                        remaining_share -= portion
                        current_sl = entry

                    if tp2_triggered and remaining_share > 0:
                        hit_tp2 = True
                        tp2_hit_at = _aware(bar_time)
                        portion = min(0.30, remaining_share)
                        ret_tp2 = ((tp2 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp2) / entry)
                        realized_pnl_capital += portion * ret_tp2
                        remaining_share -= portion

                    if tp3_triggered and remaining_share > 0:
                        hit_tp3 = True
                        tp3_hit_at = _aware(bar_time)
                        portion = remaining_share
                        ret_tp3 = ((tp3 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp3) / entry)
                        realized_pnl_capital += portion * ret_tp3
                        remaining_share = 0.0
                        resolved = True
                        closed_at = _aware(bar_time)
                        break

                    # After TP hit, check if same candle hits the new SL (BE)
                    if remaining_share > 0:
                        sl_hit_after_tp = bar_low <= current_sl if signal.direction.value == "bullish" else bar_high >= current_sl
                        if sl_hit_after_tp:
                            ret_sl = ((current_sl - entry) / entry) if signal.direction.value == "bullish" else ((entry - current_sl) / entry)
                            realized_pnl_capital += remaining_share * ret_sl
                            remaining_share = 0.0
                            resolved = True
                            closed_at = _aware(bar_time)
                            break

            # If not resolved by high/low, check for signal expiration
            if not resolved:
                now_utc = datetime.now(timezone.utc)
                expires = signal.expires_at.replace(tzinfo=timezone.utc) if signal.expires_at else None
                
                if expires and now_utc >= expires:
                    resolved = True
                    is_expired_flag = True
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
                perf.hit_tp1 = hit_tp1
                perf.hit_tp2 = hit_tp2
                perf.hit_tp3 = hit_tp3
                perf.tp1_hit_at = tp1_hit_at
                perf.tp2_hit_at = tp2_hit_at
                perf.tp3_hit_at = tp3_hit_at
                perf.closed_at = closed_at
                perf.is_expired = is_expired_flag

                details.append({
                    "signal_id": str(signal.id),
                    "symbol": symbol,
                    "outcome": outcome.value,
                    "return": round(pnl_pct, 2),
                    "max_drawdown": round(max_drawdown, 2),
                    "is_expired": is_expired_flag,
                })
                logger.info(f"Signal {signal.id} ({symbol}) resolved as {outcome.value} (PnL: {pnl_pct:.2f}%, Expired: {is_expired_flag})")
            else:
                # Update partial target hits — TP1/TP2 can trigger while the
                # position is still open (scaled out, riding to TP3/SL), so
                # record their hit times now rather than waiting for the
                # eventual full close.
                perf.hit_tp1 = hit_tp1
                perf.hit_tp2 = hit_tp2
                perf.hit_tp3 = hit_tp3
                if tp1_hit_at:
                    perf.tp1_hit_at = tp1_hit_at
                if tp2_hit_at:
                    perf.tp2_hit_at = tp2_hit_at
                if tp3_hit_at:
                    perf.tp3_hit_at = tp3_hit_at
                perf.max_drawdown = max(0.0, max_drawdown)

        # Commit DB updates
        await db.commit()

    finally:
        await binance.close()
        await yahoo.close()

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
    signal: Signal, binance: BinanceCollector, yahoo: YahooCollector,
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
        if asset.asset_type.value == "stock" or symbol.endswith(".IS"):
            ticker = await yahoo.fetch_ticker(symbol)
        else:
            ticker = await binance.fetch_ticker(symbol)
        live_price = float(ticker.get("current_price", 0))
    except Exception as exc:
        logger.debug("Live ticker fetch failed for %s: %s", symbol, exc)
        return {"signal_id": signal.id, "hit": False}

    if live_price <= 0:
        return {"signal_id": signal.id, "hit": False}

    sl = float(signal.stop_loss)
    direction = signal.direction.value
    # LONG: anlık fiyat SL'nin altındaysa stop kırıldı
    # SHORT: anlık fiyat SL'nin üstündeyse stop kırıldı
    hit = (direction == "bullish" and live_price <= sl) or \
          (direction == "bearish" and live_price >= sl)
    return {"signal_id": signal.id, "hit": hit, "live_price": live_price}


async def _fetch_market_data_for_signal(
    signal: Signal, binance: BinanceCollector, yahoo: YahooCollector
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
        if asset.asset_type.value == "stock" or symbol.endswith(".IS"):
            df = await yahoo.fetch_ohlcv(symbol, timeframe_str, limit=100)
        else:
            df = await binance.fetch_ohlcv(symbol, timeframe_str, limit=100)
        return signal.id, df
    except Exception as e:
        logger.error(f"Failed to fetch market data for {symbol} during tracking: {str(e)}")
        return signal.id, None

