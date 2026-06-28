"""
TM v2 Phase 1 — Fidelity report runner (OFFLINE, DB-READ ONLY).

Loads real signal_trade_path rows, replays FixedCurrent, and prints how exactly
the reconstruction reproduces the tracker's observed results. Writes nothing,
touches no live path.

Run (from backend/, venv active):  python -m scripts.tm_fidelity_report
"""

import asyncio
import logging

from app.database import async_session_factory
from app.trade_mgmt.fidelity import run_fidelity
from app.trade_mgmt.path_reader import load_paths

logging.disable(logging.CRITICAL)  # silence SQL echo for a clean report


def _line(label, s):
    print(f"  {label:10s} n={s['n']:4d} | realized %{s['realized_rate']:5} "
          f"| outcome %{s['outcome_rate']:5} | give-back %{s['giveback_rate']:5} "
          f"| mean|err|R={s['mean_abs_err_r']} max={s['max_abs_err_r']}")


async def main() -> None:
    async with async_session_factory() as db:
        records = await load_paths(db)  # READ ONLY

    rep = run_fidelity(records)
    print("=" * 72)
    print("TM v2 — FIDELITY CHECK  (replay(FixedCurrent) vs tracker)")
    print("=" * 72)
    print(f"toplam kayıt = {rep['total']} | eligible = {rep['eligible']['n']} "
          f"| excluded = {rep['excluded_total']}")
    if rep["excluded_breakdown"]:
        print("excluded (yeniden-üretilemez, ilkeli dışlama):")
        for reason, n in sorted(rep["excluded_breakdown"].items(), key=lambda kv: -kv[1]):
            print(f"    {reason:24s} {n}")
    print("\nEŞLEŞME ORANLARI:")
    _line("ELIGIBLE", rep["eligible"])
    _line("ALL", rep["all"])

    ms = rep["mismatches"]
    print(f"\nELIGIBLE uyumsuzluk = {len(ms)}")
    for x in ms[:20]:
        print(f"  - {x.signal_id[:8]} obs_r={x.observed_r} replay_r={x.replay_r} "
              f"err={x.abs_err_r} | out obs={x.observed_outcome}/rep={x.replay_outcome} "
              f"gb obs={x.observed_giveback}/rep={x.replay_giveback} | {x.exit_reason} | {x.detail_label}")

    print("\n" + ("KARAR: 🟢 KABUL — fidelity geçti." if rep["accept"]
                  else "KARAR: 🔴 RED — kök neden incelenmeli (yukarıdaki uyumsuzluklar)."))


if __name__ == "__main__":
    asyncio.run(main())
