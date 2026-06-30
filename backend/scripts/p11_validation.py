"""P1.1 validation backtest — prints existing + P11-0 metrics per asset.

Reusable for P11 before/after diffs. Fetches real OHLCV (network), runs the
BacktestEngine, prints a compact metrics line. Extended in P11-2 with would_downgrade
+ threshold simulation.

Run:  PYTHONPATH=. python scripts/p11_validation.py [tag]
"""
import asyncio
import logging
import sys

logging.getLogger("app").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("yfinance").setLevel(logging.ERROR)

from app.collectors.binance_collector import BinanceCollector
from app.backtesting.engine import BacktestEngine

ASSETS = [("BTCUSDT", "1d"), ("ETHUSDT", "1d"), ("BNBUSDT", "1d"), ("SOLUSDT", "1d")]


async def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    b = BinanceCollector()
    eng = BacktestEngine()
    try:
        for sym, tf in ASSETS:
            try:
                df = await b.fetch_ohlcv(sym, tf, limit=450)
                rep = await eng.run_backtest(symbol=sym, timeframe=tf, df=df,
                                             initial_capital=10000.0, risk_pct=2.0, max_age=30)
            except Exception as e:
                print(f"{tag}|{sym}: FAIL {e}")
                continue
            print(f"{tag}|{sym} trades={rep.total_trades} win={rep.win_rate} pf={rep.profit_factor} "
                  f"exp={rep.expectancy_pct} avgRR_tp3={rep.average_rr} "
                  f"| planRR_tp1_avg={rep.avg_planned_rr_tp1} med={rep.median_planned_rr_tp1} "
                  f"sub1%={rep.sub_1_rr_pct} reach[{rep.tp1_reach_rate}/{rep.tp2_reach_rate}/{rep.tp3_reach_rate}] "
                  f"realR_avg={rep.avg_realized_r}")
    finally:
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
