"""
TM v2 Phase 1 — Replay policy-comparison report (OFFLINE, DB-READ ONLY).

Replays every registered policy over the reconstructable signal_trade_path set
and prints a comparison table (global + per regime) with FixedCurrent as the
baseline. Writes nothing, touches no live path.

Step 4: only FixedCurrent (baseline) is registered. Step 5 appends Hard-BE /
Trailing / Adaptive Scale-out to `policies` and they show up here automatically.

Run:  python -m scripts.tm_replay_report
"""

import asyncio
import logging

from app.database import async_session_factory
from app.trade_mgmt.path_reader import load_paths
from app.trade_mgmt.policies.catalog import registered_policies
from app.trade_mgmt.scoring import compare_policies, compare_segments

logging.disable(logging.CRITICAL)

_HDR = f"  {'policy':16s} {'n':>4} {'exp_R':>7} {'med':>6} {'p25':>6} {'win%':>5} {'PF':>6} {'gb%':>5} {'conf':>5} | {'Δexp':>7} {'Δgb%':>6} {'Δp25':>7}"


def _fmt_pf(pf):
    return "  inf" if pf is None else f"{pf:.2f}"


def _row(entry):
    s = entry["score"]
    u = entry["uplift_vs_baseline"] or {}
    de = u.get("expectancy_r"); dg = u.get("giveback_rate"); dp = u.get("p25_r")
    du = "  base" if (de == 0 and dg == 0 and dp == 0) else f"{de:+7.4f} {dg:+6.1f} {dp:+7.4f}"
    print(f"  {s.policy:16s} {s.n:>4} {s.expectancy_r:>7.4f} {s.median_r:>6.3f} "
          f"{s.p25_r:>6.3f} {s.win_rate:>5.1f} {_fmt_pf(s.profit_factor):>6} "
          f"{s.giveback_rate:>5.1f} {s.mean_confidence:>5.2f} | {du}")


async def main() -> None:
    async with async_session_factory() as db:
        records = await load_paths(db)  # READ ONLY

    policies = registered_policies()

    print("=" * 96)
    print("TM v2 — REPLAY POLICY COMPARISON  (baseline = FixedCurrent)")
    print("=" * 96)

    glob = compare_policies(records, policies)
    print(f"\nGLOBAL  (reconstructable n={glob['n']} / toplam {len(records)})")
    print(_HDR)
    for entry in glob["rows"]:
        _row(entry)

    print("\nREGIME  (n azalan):")
    segs = compare_segments(records, policies, lambda r: r.regime or "(null)")
    for regime, table in segs.items():
        print(f"\n  [{regime}]  n={table['n']}")
        print(_HDR)
        for entry in table["rows"]:
            _row(entry)

    print(f"\nNOT: {len(policies)} politika (baseline=FixedCurrent). Δ sütunları baseline'a göre.")
    print("Yönsel karşılaştırma (n küçük); parametre optimizasyonu veri checkpoint'inde (~250-300).")


if __name__ == "__main__":
    asyncio.run(main())
