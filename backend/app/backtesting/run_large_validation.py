"""
TradeMinds AI – Large Scale walk-forward validation script.
Runs 3-year walk-forward backtesting simulations for BTCUSDT, ETHUSDT, THYAO.IS, and GARAN.IS.
Outputs institutional-grade metrics: Win Rate, Profit Factor, Sharpe, Sortino, Drawdown, Expectancy, and Monthly Breakdown.
"""

from __future__ import annotations

import asyncio
import os
import sys
import json
import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np

# Add backend directory to system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector
from app.backtesting.engine import BacktestEngine, BacktestReport

# Configure logger
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Suppress debug logs from internal libraries
logging.getLogger("app").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)


def compute_monthly_breakdown(equity_curve_list: list) -> dict:
    """Compute calendar monthly performance percentage return matrix."""
    if not equity_curve_list:
        return {}
    
    df_eq = pd.DataFrame(equity_curve_list)
    df_eq["time"] = pd.to_datetime(df_eq["time"])
    df_eq.set_index("time", inplace=True)
    
    # Resample to end of month
    monthly = df_eq["capital"].resample("M").last()
    
    # Calculate monthly percentage returns
    monthly_returns = monthly.pct_change() * 100.0
    
    # Initialize the first month's return relative to the starting capital
    if len(monthly) > 0:
        first_val = df_eq["capital"].iloc[0]
        monthly_returns.iloc[0] = ((monthly.iloc[0] - first_val) / first_val) * 100.0
        
    breakdown = {}
    for date, ret in monthly_returns.items():
        year_str = str(date.year)
        month_str = date.strftime("%B")
        if year_str not in breakdown:
            breakdown[year_str] = {}
        breakdown[year_str][month_str] = round(ret, 2)
        
    return breakdown


async def main():
    print("================================================================")
    print("      TRADEMINDS AI - INSTITUTIONAL SCALE VALIDATION            ")
    print("================================================================\n")
    print("Initializing collectors and backtest engine...")

    binance = BinanceCollector()
    yahoo = YahooCollector()
    engine = BacktestEngine()

    # Define validation target assets (3 years daily OHLCV ~ 1000 candles)
    assets = [
        {"symbol": "BTCUSDT", "collector": binance, "limit": 1000},
        {"symbol": "ETHUSDT", "collector": binance, "limit": 1000},
        {"symbol": "THYAO.IS", "collector": yahoo, "limit": 1000},
        {"symbol": "GARAN.IS", "collector": yahoo, "limit": 1000},
    ]

    results_db = {}

    for asset in assets:
        symbol = asset["symbol"]
        collector = asset["collector"]
        limit = asset["limit"]

        print(f"\n--> Fetching {limit} daily bars (~3 years) for {symbol}...")
        try:
            df = await collector.fetch_ohlcv(symbol, "1d", limit=limit)
        except Exception as e:
            print(f"    [ERROR] Failed to fetch data for {symbol}: {str(e)}")
            continue

        if df.empty or len(df) < 100:
            print(f"    [WARNING] Insufficient data returned for {symbol} (count: {len(df)})")
            continue

        print(f"    Loaded {len(df)} candles. Running walk-forward simulation...")

        try:
            # Run simulation using Neutral execution model to be mathematically balanced
            report: BacktestReport = await engine.run_backtest(
                symbol=symbol,
                timeframe="1d",
                df=df,
                initial_capital=10000.0,
                risk_pct=2.0,
                max_age=30,  # Max holding period of 30 days per trade
                execution_model="neutral"
            )

            # Calculate Sortino & Expectancy
            returns = [t["return_pct"] for t in report.trades_log]
            avg_return = np.mean(returns) if returns else 0.0
            
            # Sortino denominator: standard deviation of negative returns
            downside_returns = [r for r in returns if r < 0]
            downside_std = np.std(downside_returns) if downside_returns else 0.001
            sortino = round(avg_return / downside_std, 3) if downside_std > 0 else 0.0

            monthly_performance = compute_monthly_breakdown(report.equity_curve)

            results_db[symbol] = {
                "symbol": symbol,
                "total_trades": report.total_trades,
                "wins": report.wins,
                "losses": report.losses,
                "breakevens": report.breakevens,
                "expired": report.expired,
                "win_rate": report.win_rate,
                "profit_factor": report.profit_factor,
                "sharpe": report.sharpe_ratio,
                "sortino": sortino,
                "max_drawdown": report.max_drawdown_pct,
                "expectancy": report.expectancy_pct,
                "avg_return_pct": report.average_return_pct,
                "final_capital": report.equity_curve[-1]["capital"] if report.equity_curve else 10000.0,
                "monthly_breakdown": monthly_performance,
                "equity_curve": report.equity_curve,
                "trades": report.trades_log
            }

            print(f"    [COMPLETED] Sim resolved {report.total_trades} trades. Win rate: {report.win_rate}%. Profit Factor: {report.profit_factor}")

        except Exception as e:
            print(f"    [ERROR] Simulation crashed for {symbol}: {str(e)}")
            import traceback
            traceback.print_exc()

    await binance.close()
    await yahoo.close()

    # Save to json file
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "large_validation_results.json")
    with open(output_path, "w") as f:
        json.dump(results_db, f, indent=2)

    # Print summary table
    print("\n" + "=" * 115)
    print(f"{'Asset':<12} | {'Trades':<6} | {'Win Rate':<8} | {'PF':<6} | {'Sharpe':<6} | {'Sortino':<7} | {'Max DD':<7} | {'Expectancy':<10} | {'End Capital':<11}")
    print("-" * 115)
    for sym, res in results_db.items():
        print(
            f"{sym:<12} | "
            f"{res['total_trades']:<6} | "
            f"{res['win_rate']:<7}% | "
            f"{res['profit_factor']:<6} | "
            f"{res['sharpe']:<6} | "
            f"{res['sortino']:<7} | "
            f"-{res['max_drawdown']:<6}% | "
            f"{res['expectancy']:<9}% | "
            f"${res['final_capital']:,.2f}"
        )
    print("===================================================================================================\n")
    print(f"Validation reports successfully exported to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
