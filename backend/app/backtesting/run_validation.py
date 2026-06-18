"""
TradeMinds AI – Validation Backtest Script

Runs walk-forward backtesting for BTCUSDT, ETHUSDT, THYAO.IS, and GARAN.IS
for both 6-month and 12-month periods, outputting key performance metrics
and a list of example trade signals.
"""

import asyncio
import os
import sys
import json
import logging
from typing import Dict, Any, List
import pandas as pd

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector
from app.backtesting.engine import BacktestEngine

# Suppress debug logs
logging.getLogger("app").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)


async def main():
    print("====================================================")
    print("      TRADEMINDS AI - HISTORICAL VALIDATION         ")
    print("====================================================\n")

    binance = BinanceCollector()
    yahoo = YahooCollector()
    engine = BacktestEngine()

    assets = [
        {"symbol": "BTCUSDT", "collector": binance, "is_crypto": True},
        {"symbol": "ETHUSDT", "collector": binance, "is_crypto": True},
        {"symbol": "THYAO.IS", "collector": yahoo, "is_crypto": False},
        {"symbol": "GARAN.IS", "collector": yahoo, "is_crypto": False},
    ]

    results_summary = []
    all_signals_log = []

    for asset in assets:
        sym = asset["symbol"]
        coll = asset["collector"]
        print(f"--> Fetching data for {sym}...")
        
        try:
            # Fetch 450 daily bars to cover 12 months (365 days) + 60 lookback bars
            df = await coll.fetch_ohlcv(sym, "1d", limit=450)
        except Exception as e:
            print(f"Failed to fetch data for {sym}: {e}")
            continue

        if df.empty or len(df) < 100:
            print(f"Insufficient data for {sym} ({len(df)} bars)")
            continue

        # Periods to backtest: 6 Months (last 180 bars + 60 lookback = 240) and 12 Months (all 450 bars)
        runs = [
            {"name": "6 Months", "df": df.tail(240)},
            {"name": "12 Months", "df": df}
        ]

        for run in runs:
            run_name = run["name"]
            run_df = run["df"]
            print(f"   Running backtest for {sym} ({run_name}, {len(run_df)} bars)...")
            
            try:
                report = await engine.run_backtest(
                    symbol=sym,
                    timeframe="1d",
                    df=run_df,
                    initial_capital=10000.0,
                    risk_pct=2.0,
                    max_age=30 # 30 days maximum trade duration
                )
                
                results_summary.append({
                    "symbol": sym,
                    "period": run_name,
                    "total_trades": report.total_trades,
                    "win_rate": report.win_rate,
                    "loss_rate": report.loss_rate,
                    "profit_factor": report.profit_factor,
                    "sharpe_ratio": report.sharpe_ratio,
                    "max_drawdown": report.max_drawdown_pct,
                    "final_capital": report.equity_curve[-1]["capital"] if report.equity_curve else 10000.0
                })

                # Capture signals logs
                for t in report.trades_log[:10]: # take first 10 trades as examples per asset/period
                    all_signals_log.append({
                        "symbol": sym,
                        "period": run_name,
                        "trade_id": t["trade_id"],
                        "direction": t["direction"],
                        "entry": t["entry_price"],
                        "exit": t["exit_price"],
                        "return_pct": t["return_pct"],
                        "outcome": t["outcome"],
                        "time": t["entry_time"]
                    })

            except Exception as e:
                print(f"   Backtest failed for {sym} ({run_name}): {e}")

    await binance.close()
    await yahoo.close()

    # Output Results as JSON for validation report
    output = {
        "summary": results_summary,
        "signals": all_signals_log[:40] # cap example signals
    }
    
    with open("validation_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n====================================================")
    print("                 METRICS SUMMARY                    ")
    print("====================================================")
    print(f"{'Asset':<12} | {'Period':<10} | {'Trades':<6} | {'Win Rate':<8} | {'Profit Factor':<12} | {'Sharpe':<6} | {'Max DD':<7} | {'End Capital':<10}")
    print("-" * 92)
    for r in results_summary:
        print(f"{r['symbol']:<12} | {r['period']:<10} | {r['total_trades']:<6} | {r['win_rate']}%     | {r['profit_factor']:<12} | {r['sharpe_ratio']:<6} | -{r['max_drawdown']}% | ${r['final_capital']:.2f}")
    print("====================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
