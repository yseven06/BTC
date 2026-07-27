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

from sqlalchemy import and_, case, or_, select, update  # noqa: E402

from app.collectors.binance_collector import BinanceCollector  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.decision_candidate import (  # noqa: E402
    SHADOW_UNDECIDABLE,
    SignalDecisionCandidate,
)
from app.services.shadow_eval import evaluate_candidate_shadow  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("p22a")

# A candidate needs bars AFTER it to be judgeable; signals expire at 48h, so a
# row younger than that cannot have a settled verdict yet.
MIN_AGE = timedelta(hours=48)

# After this age a still-undecidable row is retired instead of retried forever.
# 7 days, deliberately shorter than the 14-day observation gate: a row still
# unresolved when the gate is assessed would otherwise sit in the pending count
# at exactly the moment that count is used to decide whether P2.2-b may start.
# Retiring at 7 leaves a clear week of margin. Bars for a live symbol are always
# available, so reaching this bound at all means something is genuinely wrong.
MAX_RETRY_AGE = timedelta(days=7)

# Reasons that can never change on a later run: they are properties of the STORED
# ROW, not of the bars. A HOLD candidate will not acquire a direction tomorrow.
PERMANENT_REASONS = frozenset({"no_direction", "no_geometry"})

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


def evaluable_predicate():
    """Rows the evaluator CAN reach a verdict on: a real direction and complete
    geometry. This is the pass-B selection."""
    return and_(
        SignalDecisionCandidate.engine_direction.in_(("bullish", "bearish")),
        SignalDecisionCandidate.entry_zone_low.isnot(None),
        SignalDecisionCandidate.entry_zone_high.isnot(None),
        SignalDecisionCandidate.stop_loss.isnot(None),
    )


def unevaluable_predicate():
    """The exact complement: rows no amount of waiting can make evaluable.

    Written out rather than derived with NOT(), because SQL three-valued logic
    turns NOT(col IN (...)) into NULL — not TRUE — when col is NULL, and those
    rows would silently belong to neither half. A test asserts the two
    predicates partition the table exactly.
    """
    return or_(
        SignalDecisionCandidate.engine_direction.is_(None),
        SignalDecisionCandidate.engine_direction.notin_(("bullish", "bearish")),
        SignalDecisionCandidate.entry_zone_low.is_(None),
        SignalDecisionCandidate.entry_zone_high.is_(None),
        SignalDecisionCandidate.stop_loss.is_(None),
    )


async def retire_permanent(db, limit: int, dry_run: bool = False) -> int:
    """PASS A — retire permanently-unevaluable rows WITHOUT fetching any bars.

    Pass B filters these rows out in SQL, which fixes the queue starvation but
    leaves them with shadow_evaluated_at = NULL forever. That makes
    "shadow_evaluated_at IS NULL" mean two different things at once — "not yet
    measured" and "never measurable" — and 93.6 % of production rows fall in the
    second group. Any pending count, gate-progress figure or retention decision
    built on that column would be wrong by an order of magnitude.

    So they are claimed here, once, in a bounded batch: no bar fetch, no
    per-row loop, `LIMIT` honoured through an id sub-select so this can never
    become an unbounded full-table UPDATE. `shadow_outcome` stays `undecidable`
    — the row is RETIRED, not RESOLVED.
    """
    ids = (
        select(SignalDecisionCandidate.id)
        .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
        .where(unevaluable_predicate())
        .order_by(SignalDecisionCandidate.evaluated_bar_time)
        .limit(limit)
    )

    if dry_run:
        return len((await db.execute(ids)).scalars().all())

    payload = {
        "shadow_evaluated_at": datetime.now(timezone.utc),
        "shadow_outcome": SHADOW_UNDECIDABLE,
        # Which half of "unevaluable" this row is, decided in SQL so the reason
        # matches the predicate that selected it.
        "shadow_resolution_reason": case(
            (or_(SignalDecisionCandidate.engine_direction.is_(None),
                 SignalDecisionCandidate.engine_direction.notin_(("bullish", "bearish"))),
             "no_direction"),
            else_="no_geometry",
        ),
    }
    _assert_write_targets(payload)

    result = await db.execute(
        update(SignalDecisionCandidate)
        .where(SignalDecisionCandidate.id.in_(ids))
        .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))  # idempotent
        .values(**payload)
    )
    return result.rowcount or 0


async def _finalise_undecidable(db, cand, reason: str) -> None:
    """Retire a row that can never produce a verdict.

    Writing `shadow_evaluated_at` is the ONLY thing that removes a row from the
    oldest-first queue. Leaving a permanently-unevaluable row unclaimed does not
    make it evaluable later; it makes it a permanent blocker at the head of the
    queue, ahead of every row that could have been measured.

    `shadow_outcome` stays `undecidable` so no downstream analysis can mistake
    this for a result — the row is RETIRED, not RESOLVED. The `WHERE
    shadow_evaluated_at IS NULL` predicate keeps it single-claim under a
    concurrent run.
    """
    payload = {
        "shadow_evaluated_at": datetime.now(timezone.utc),
        "shadow_outcome": SHADOW_UNDECIDABLE,
        "shadow_resolution_reason": reason,
    }
    _assert_write_targets(payload)
    await db.execute(
        update(SignalDecisionCandidate)
        .where(SignalDecisionCandidate.id == cand.id)
        .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
        .values(**payload)
    )


async def evaluate(limit: int) -> Counter:
    stats: Counter = Counter()
    cutoff = datetime.now(timezone.utc) - MIN_AGE
    collector = BinanceCollector()

    try:
        async with async_session_factory() as db:
            # PASS B — only rows that CAN be evaluated. Measured on production:
            # 93.6 % of candidates carry engine_direction='neutral' (the engine
            # said HOLD). Excluding them here is what removes the queue
            # starvation and the one wasted Binance fetch per unevaluable row;
            # pass A is what stops them lingering as permanent NULLs.
            rows = (await db.execute(
                select(SignalDecisionCandidate)
                .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
                .where(SignalDecisionCandidate.evaluated_bar_time <= cutoff)
                .where(evaluable_predicate())
                .order_by(SignalDecisionCandidate.evaluated_bar_time)
                .limit(limit)
            )).scalars().all()

            print(f"aday: {len(rows)} (shadow'suz · >= 48 saat · yon ve geometri gecerli)")

            now = datetime.now(timezone.utc)

            for cand in rows:
                too_old = (now - cand.evaluated_bar_time) > MAX_RETRY_AGE

                df = await _fetch_bars(collector, cand.symbol or "", cand.timeframe)
                if df is None or len(df) == 0:
                    # Transient by assumption — the next run may get bars. But a
                    # row past MAX_RETRY_AGE has had a week of chances; keeping
                    # it unclaimed only blocks the queue.
                    if too_old:
                        await _finalise_undecidable(db, cand, "no_bars_after_retry_window")
                        stats["undecidable_terminal"] += 1
                    else:
                        stats["fetch_failed_retry"] += 1
                    continue

                # The evaluator does not truncate for us — the caller owns the
                # window. Cap it at the 48h life so a touch that happened after
                # the trade would have closed cannot count as an entry.
                #
                # Both sides must agree on tz-awareness. Comparing a tz-aware
                # horizon against a tz-naive index raises TypeError, and the
                # previous `except: pass` swallowed it — the cap silently did
                # not apply and lifetime extrema leaked into the measurement.
                horizon = cand.evaluated_bar_time + MIN_AGE
                idx = df.index
                if getattr(idx, "tz", None) is None:
                    cutoff_ts = horizon.replace(tzinfo=None) if horizon.tzinfo else horizon
                else:
                    cutoff_ts = horizon if horizon.tzinfo else horizon.replace(tzinfo=timezone.utc)
                try:
                    df = df[idx <= cutoff_ts]
                except TypeError as exc:
                    # Narrow and loud: a frame whose index is not comparable is a
                    # real problem, not something to silently measure around.
                    log.warning("  %s: horizon cap failed (%s) — candidate skipped",
                                cand.id, type(exc).__name__)
                    stats["horizon_error"] += 1
                    continue
                if len(df) == 0:
                    if too_old:
                        await _finalise_undecidable(db, cand, "no_bars_in_horizon")
                        stats["undecidable_terminal"] += 1
                    else:
                        stats["empty_after_cap_retry"] += 1
                    continue

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

                # Only TRANSIENT undecidables can reach here — pass B's SQL filter
                # already excluded every permanent one, and pass A retires those.
                # The PERMANENT_REASONS arm is a DRIFT GUARD, not the primary
                # path: if evaluable_predicate() and the evaluator's own notion of
                # "unevaluable" ever disagree, this catches the row rather than
                # letting it retry forever.
                if out["shadow_outcome"] == "undecidable":
                    reason = out.get("shadow_resolution_reason") or "unknown"
                    if reason in PERMANENT_REASONS or too_old:
                        await _finalise_undecidable(db, cand, reason)
                        stats["undecidable_terminal"] += 1
                    else:
                        stats["undecidable_retry"] += 1
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

    # "Pending" has to mean one thing. Before pass A runs, 93.6 % of unclaimed
    # rows are permanently unevaluable, and a raw NULL count would overstate the
    # gate's remaining work by more than an order of magnitude.
    pending = [r for r in rows if r.shadow_evaluated_at is None]
    pending_evaluable = [
        r for r in pending
        if r.engine_direction in ("bullish", "bearish")
        and r.entry_zone_low is not None and r.entry_zone_high is not None
        and r.stop_loss is not None
    ]
    print(f"\nbekleyen (shadow_evaluated_at NULL) : {len(pending)}")
    print(f"  degerlendirilebilir                : {len(pending_evaluable)}")
    print(f"  kalici degerlendirilemez (pass A)  : {len(pending) - len(pending_evaluable)}")

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
    ap.add_argument("--dry-run", action="store_true",
                    help="count what pass A would retire; writes nothing")
    ap.add_argument("--limit", type=int, default=500,
                    help="applied to each pass independently")
    args = ap.parse_args()

    if args.dry_run:
        async with async_session_factory() as db:
            would = await retire_permanent(db, args.limit, dry_run=True)
        print(f"pass A (DRY-RUN, yazim yok): {would} kalici degerlendirilemez satir emekli edilecekti")
    elif not args.report:
        # Pass A first: retiring the unevaluable rows costs one bounded UPDATE and
        # no network, and it keeps `shadow_evaluated_at IS NULL` meaning exactly
        # "still to be measured" for every count that follows.
        async with async_session_factory() as db:
            retired = await retire_permanent(db, args.limit)
            await db.commit()
        print(f"pass A: {retired} kalici degerlendirilemez satir emekli edildi (fetch yok)")

        stats = await evaluate(args.limit)
        print("\npass B degerlendirme:", dict(stats))

    await report()


if __name__ == "__main__":
    asyncio.run(main())
