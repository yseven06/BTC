"""
TradeMinds AI – Signal Performance Tracker

Fetches active signals, checks subsequent price action using live data feeds
from Binance and Yahoo Finance collectors, and resolves trade outcomes in the DB.
"""

from __future__ import annotations

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
        for signal in active_signals:
            processed_count += 1
            asset: Asset = signal.asset
            
            # Fetch pricing history since signal generation
            symbol = asset.symbol
            timeframe_str = _map_db_timeframe(signal.timeframe)
            
            logger.info(f"Checking performance for signal {signal.id} - {symbol} ({signal.timeframe.value})")

            # Choose corresponding data collector
            try:
                if asset.asset_type.value == "stock" or symbol.endswith(".IS"):
                    df = await yahoo.fetch_ohlcv(symbol, timeframe_str, limit=100)
                else:
                    df = await binance.fetch_ohlcv(symbol, timeframe_str, limit=100)
            except Exception as e:
                logger.error(f"Failed to fetch market data for {symbol} during tracking: {str(e)}")
                continue

            if df.empty:
                logger.warning(f"No price data returned for {symbol}")
                continue

            # We filter for candles that happened *after* signal generation time
            # Parse signal.generated_at to pandas datetime (naive or timezone-aware matching)
            sig_time = pd.to_datetime(signal.generated_at).tz_localize(None)
            df_after = df[df.index.tz_localize(None) > sig_time]

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
            
            closed_at = None

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
                    closed_at = bar_time
                    break
                elif tp_hit:
                    if tp1_triggered:
                        hit_tp1 = True
                        portion = 0.50
                        ret_tp1 = ((tp1 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp1) / entry)
                        realized_pnl_capital += portion * ret_tp1
                        remaining_share -= portion
                        current_sl = entry
                        
                    if tp2_triggered and remaining_share > 0:
                        hit_tp2 = True
                        portion = min(0.30, remaining_share)
                        ret_tp2 = ((tp2 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp2) / entry)
                        realized_pnl_capital += portion * ret_tp2
                        remaining_share -= portion
                        
                    if tp3_triggered and remaining_share > 0:
                        hit_tp3 = True
                        portion = remaining_share
                        ret_tp3 = ((tp3 - entry) / entry) if signal.direction.value == "bullish" else ((entry - tp3) / entry)
                        realized_pnl_capital += portion * ret_tp3
                        remaining_share = 0.0
                        resolved = True
                        closed_at = bar_time
                        break

                    # After TP hit, check if same candle hits the new SL (BE)
                    if remaining_share > 0:
                        sl_hit_after_tp = bar_low <= current_sl if signal.direction.value == "bullish" else bar_high >= current_sl
                        if sl_hit_after_tp:
                            ret_sl = ((current_sl - entry) / entry) if signal.direction.value == "bullish" else ((entry - current_sl) / entry)
                            realized_pnl_capital += remaining_share * ret_sl
                            remaining_share = 0.0
                            resolved = True
                            closed_at = bar_time
                            break

            # If not resolved by high/low, check for signal expiration
            if not resolved:
                now_utc = datetime.now(timezone.utc)
                expires = signal.expires_at.replace(tzinfo=timezone.utc) if signal.expires_at else None
                
                if expires and now_utc >= expires:
                    resolved = True
                    is_expired_flag = True
                    last_close = float(closes[-1])
                    closed_at = times[-1]
                    
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
                # Update partial target hits
                perf.hit_tp1 = hit_tp1
                perf.hit_tp2 = hit_tp2
                perf.max_drawdown = max(0.0, max_drawdown)

        # Commit DB updates
        await db.commit()

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

