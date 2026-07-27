"""Offline shadow evaluation of recorded candidates (P2.2-a).

Reads `signal_decision_candidates` rows that have no shadow verdict yet, fetches
the bars that followed each one, and fills ONLY the shadow_* columns.

  python scripts/p22a_shadow_eval.py            # evaluate + report
  python scripts/p22a_shadow_eval.py --report   # report only, writes nothing
  python scripts/p22a_shadow_eval.py --limit 50

SAFETY POSTURE
--------------
  * Runs in its own session. It is never imported by the scheduler, the tracker
    or any APScheduler job, so it cannot participate in — or stall — a
    production transaction.
  * Writes shadow_* columns and nothing else. `_WRITABLE` is asserted against the
    payload of every UPDATE, so a future edit cannot quietly widen the blast
    radius to a decision column.
  * `WHERE shadow_evaluated_at IS NULL` makes a re-run idempotent: an
    already-evaluated candidate is never re-scored, and two concurrent runs
    cannot both claim the same row.
  * Prints candidate ids and summary counts. Never a connection string, never a
    full row.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update  # noqa: E402

from app.collectors.binance_collector import BinanceCollector  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.decision_candidate import SignalDecisionCandidate  # noqa: E402
from app.services.shadow_eval import evaluate_candidate_shadow  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("p22a")

# A candidate needs bars AFTER it to be judgeable; signals expire at 48h, so a
# row younger than that cannot have a settled verdict yet.
MIN_AGE = timedelta(hours=48)

# The only columns this script may ever write.
_WRITABLE = {
    "shadow_evaluated_at", "shadow_outcome", "shadow_detail_label",
    "shadow_return_pct", "shadow_r_multiple", "shadow_mfe_pct", "shadow_mae_pct",
    "shadow_bars_walked", "shadow_resolved_at", "shadow_resolution_path",
    "shadow_resolution_reason", "shadow_entry_reached", "shadow_entry_reached_at",
    "shadow_bars_to_entry", "shadow_never_entered", "shadow_max_zone_penetration_pct",
    "shadow_zone_far_edge_reached", "shadow_stop_before_valid_entry",
    "shadow_invalidated_before_entry",
}


def _assert_write_targets(payload: dict) -> None:
    stray = set(payload) - _WRITABLE
    if stray:
        raise RuntimeError(f"refusing to write non-shadow columns: {sorted(stray)}")


async def _fetch_bars(collector, symbol: str, timeframe: str, limit: int = 300):
    try:
        return await collector.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("  bar fetch failed for %s %s: %s", symbol, timeframe, type(exc).__name__)
        return None


async def evaluate(limit: int) -> Counter:
    stats: Counter = Counter()
    cutoff = datetime.now(timezone.utc) - MIN_AGE
    collector = BinanceCollector()

    try:
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(SignalDecisionCandidate)
                .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
                .where(SignalDecisionCandidate.evaluated_bar_time <= cutoff)
                .order_by(SignalDecisionCandidate.evaluated_bar_time)
                .limit(limit)
            )).scalars().all()

            print(f"aday: {len(rows)} (shadow'suz, >= 48 saat)")

            for cand in rows:
                df = await _fetch_bars(collector, cand.symbol or "", cand.timeframe)
                if df is None or len(df) == 0:
                    stats["fetch_failed"] += 1
                    continue

                # The evaluator does not truncate for us — the caller owns the
                # window. Cap it at the 48h life so a touch that happened after
                # the trade would have closed cannot count as an entry.
                horizon = cand.evaluated_bar_time + MIN_AGE
                try:
                    idx = df.index.tz_localize(None) if getattr(df.index, "tz", None) is None else df.index
                    df = df[idx <= horizon]
                except Exception:  # noqa: BLE001
                    pass

                out = evaluate_candidate_shadow(
                    direction=cand.engine_direction,
                    entry_zone_low=float(cand.entry_zone_low) if cand.entry_zone_low is not None else None,
                    entry_zone_high=float(cand.entry_zone_high) if cand.entry_zone_high is not None else None,
                    stop_loss=float(cand.stop_loss) if cand.stop_loss is not None else None,
                    tp1=float(cand.tp1) if cand.tp1 is not None else None,
                    tp2=float(cand.tp2) if cand.tp2 is not None else None,
                    tp3=float(cand.tp3) if cand.tp3 is not None else None,
                    df=df, bar_time=cand.evaluated_bar_time,
                )

                # UNDECIDABLE stays unclaimed so a later run can retry it once
                # more bars exist. Everything else is terminal.
                if out["shadow_outcome"] == "undecidable":
                    stats["undecidable"] += 1
                    continue

                payload = {k: v for k, v in out.items() if k in _WRITABLE}
                payload["shadow_evaluated_at"] = datetime.now(timezone.utc)
                _assert_write_targets(payload)

                await db.execute(
                    update(SignalDecisionCandidate)
                    .where(SignalDecisionCandidate.id == cand.id)
                    .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
                    .values(**payload)
                )
                stats[out["shadow_outcome"]] += 1

            await db.commit()
    finally:
        try:
            await collector.close()
        except Exception:  # noqa: BLE001
            pass

    return stats


async def report() -> None:
    async with async_session_factory() as db:
        rows = (await db.execute(select(SignalDecisionCandidate))).scalars().all()

    print(f"\ntoplam aday: {len(rows)}")
    print("\nverdict x shadow_outcome")
    grid: Counter = Counter((r.verdict, r.shadow_outcome or "-") for r in rows)
    for (verdict, outcome), n in sorted(grid.items()):
        print(f"  {verdict:<10} {outcome:<14} {n:>6}")

    print("\nreddetme nedeni")
    for reason, n in sorted(Counter(r.demotion_reason or "-" for r in rows).items()):
        print(f"  {reason:<24} {n:>6}")

    scored = [r for r in rows if r.shadow_outcome and r.shadow_outcome != "undecidable"]
    filled = [r for r in scored if r.shadow_outcome != "never_entered"]
    no_fill = [r for r in scored if r.shadow_outcome == "never_entered"]

    # never_entered is reported as its own rate and kept OUT of PF/expectancy:
    # a setup that never filled did not lose a trade, it never took one.
    print(f"\ndegerlendirilen: {len(scored)}  ·  dolan: {len(filled)}  ·  "
          f"hic dolmayan: {len(no_fill)}"
          + (f" (%{100.0*len(no_fill)/len(scored):.1f})" if scored else ""))

    rets = [float(r.shadow_return_pct) for r in filled if r.shadow_return_pct is not None]
    if rets:
        gain = sum(x for x in rets if x > 0)
        loss = abs(sum(x for x in rets if x < 0))
        print(f"  PF {gain/loss:.2f}" if loss else "  PF -")
        print(f"  ortalama getiri %{sum(rets)/len(rets):.4f}")
    rs = [float(r.shadow_r_multiple) for r in filled if r.shadow_r_multiple is not None]
    if rs:
        print(f"  beklenti {sum(rs)/len(rs):+.4f}R  (n={len(rs)})")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="report only, write nothing")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    if not args.report:
        stats = await evaluate(args.limit)
        print("\ndegerlendirme:", dict(stats))
    await report()


if __name__ == "__main__":
    asyncio.run(main())
