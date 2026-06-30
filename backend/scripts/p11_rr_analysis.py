"""P11-2 R:R MEASUREMENT (no behaviour change) — aggregates backtest trades across
liquid assets and answers: TP1-based real R:R distribution, would_downgrade rate at
several thresholds, reach-rate, realized-R, whether low-R:R trades actually perform
worse, and a threshold-impact simulation (what filtering at T would do to the kept set).

All inputs are the P11-0 additive fields already on each trade (planned_rr_tp1,
realized_r, reached_tp1/2/3, outcome). Pure read/aggregate — emits NO signal, changes
NOTHING. Run: PYTHONPATH=. python scripts/p11_rr_analysis.py
"""
import asyncio
import logging
import statistics as st

logging.getLogger("app").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

from app.collectors.binance_collector import BinanceCollector
from app.backtesting.engine import BacktestEngine

ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
          "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT"]
THRESHOLDS = [0.8, 1.0, 1.2]


def _rate(num, den):
    return round(num / den * 100.0, 1) if den else 0.0


def _wr(rows):
    res = [r for r in rows if r["outcome"] in ("win", "loss", "breakeven")]
    wins = sum(1 for r in res if r["outcome"] == "win")
    return _rate(wins, len(res))


async def main():
    b = BinanceCollector()
    eng = BacktestEngine()
    trades = []
    try:
        for sym in ASSETS:
            try:
                df = await b.fetch_ohlcv(sym, "1d", limit=450)
                rep = await eng.run_backtest(symbol=sym, timeframe="1d", df=df,
                                             initial_capital=10000.0, risk_pct=2.0, max_age=30)
                trades.extend([t for t in rep.trades_log if t.get("planned_rr_tp1") is not None])
            except Exception as e:
                print(f"{sym}: FAIL {e}")
    finally:
        await b.close()

    n = len(trades)
    print(f"\n==== P11-2 R:R ANALYSIS · {n} trades over {len(ASSETS)} assets (1d, 450 bars) ====")
    prr = [t["planned_rr_tp1"] for t in trades]
    rr_real = [t["realized_r"] for t in trades if t.get("realized_r") is not None]
    print(f"planned_rr_tp1: avg={round(st.mean(prr),3)} median={round(st.median(prr),3)} "
          f"min={round(min(prr),3)} max={round(max(prr),3)}")
    print(f"realized_R overall: avg={round(st.mean(rr_real),4)} median={round(st.median(rr_real),4)}")
    print(f"reach: tp1={_rate(sum(1 for t in trades if t.get('reached_tp1')),n)}% "
          f"tp2={_rate(sum(1 for t in trades if t.get('reached_tp2')),n)}% "
          f"tp3={_rate(sum(1 for t in trades if t.get('reached_tp3')),n)}%")

    print("\n-- planned_rr_tp1 distribution --")
    edges = [(0,0.5),(0.5,0.8),(0.8,1.0),(1.0,1.5),(1.5,2.0),(2.0,99)]
    for lo, hi in edges:
        bucket = [t for t in trades if lo <= t["planned_rr_tp1"] < hi]
        if not bucket:
            print(f"  [{lo:.1f},{hi:.1f}): 0"); continue
        rr = [t["realized_r"] for t in bucket if t.get("realized_r") is not None]
        print(f"  [{lo:.1f},{hi:.1f}): n={len(bucket)} ({_rate(len(bucket),n)}%) "
              f"win={_wr(bucket)}% avg_realR={round(st.mean(rr),3) if rr else None} "
              f"tp1reach={_rate(sum(1 for t in bucket if t.get('reached_tp1')),len(bucket))}%")

    print("\n-- KEY: do low-R:R trades perform worse? (realized-R is the truer measure) --")
    for T in THRESHOLDS:
        low = [t for t in trades if t["planned_rr_tp1"] < T]
        high = [t for t in trades if t["planned_rr_tp1"] >= T]
        lr = [t["realized_r"] for t in low if t.get("realized_r") is not None]
        hr = [t["realized_r"] for t in high if t.get("realized_r") is not None]
        print(f"  T={T}: LOW(<T) n={len(low)} win={_wr(low)}% avg_realR={round(st.mean(lr),4) if lr else None} "
              f"| HIGH(>=T) n={len(high)} win={_wr(high)}% avg_realR={round(st.mean(hr),4) if hr else None}")

    print("\n-- threshold-impact simulation (filter = downgrade planned_rr<T to HOLD) --")
    base_real = st.mean(rr_real)
    for T in THRESHOLDS:
        kept = [t for t in trades if t["planned_rr_tp1"] >= T]
        kr = [t["realized_r"] for t in kept if t.get("realized_r") is not None]
        dropped_pct = _rate(n - len(kept), n)
        kept_avg = round(st.mean(kr), 4) if kr else None
        print(f"  T={T}: would_downgrade={dropped_pct}% kept={len(kept)} "
              f"kept_win={_wr(kept)}% kept_avg_realR={kept_avg} (baseline avg_realR={round(base_real,4)})")


if __name__ == "__main__":
    asyncio.run(main())
