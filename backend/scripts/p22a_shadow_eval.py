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
  * Writes shadow_* columns, plus an additive merge into `extra` under the single
    key `shadow_passb`. `_assert_write_targets` is asserted against the COMPLETE
    value set of every UPDATE — including `extra` — so a future edit cannot
    quietly widen the blast radius to a decision column.
  * Dry-run is the DEFAULT. `--write` has to be passed by name before any
    statement other than a SELECT is issued.
  * `WHERE shadow_evaluated_at IS NULL` makes a re-run idempotent: an
    already-evaluated candidate is never re-scored, and two concurrent runs
    cannot both claim the same row.
  * Prints candidate ids and summary counts. Never a connection string, never a
    full row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import JSON, and_, case, func, or_, select, text, update  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402

from app.collectors.binance_collector import BinanceCollector  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.decision_candidate import (  # noqa: E402
    EVALUABLE_DIRECTIONS,
    SHADOW_PERMANENT_REASONS,
    SHADOW_REASON_DATA_UNAVAILABLE,
    SHADOW_RETRYABLE_REASONS,
    SHADOW_REASON_NO_DIRECTION,
    SHADOW_REASON_NO_GEOMETRY,
    SHADOW_TERMINAL_REASONS,
    SHADOW_UNDECIDABLE,
    SignalDecisionCandidate,
)
from app.services.shadow_eval import (  # noqa: E402
    SHADOW_HORIZON,
    clip_to_window,
    evaluate_candidate_shadow,
    expected_horizon_bars,
    historical_window,
    shadow_passb_provenance,
)

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("p22a")

# A candidate needs bars AFTER it to be judgeable; signals expire at 48h, so a
# row younger than that cannot have a settled verdict yet. Taken from the shadow
# module rather than restated: the maturity gate and the walk horizon are the
# same 48 hours, and two copies could drift into measuring different windows.
MIN_AGE = SHADOW_HORIZON

# How long a row may stay unresolved before it is worth an operator's attention.
#
# It NO LONGER retires anything (CP-SHADOW-PASSB-B-SAFETY, blocker 3). Age was
# being used to promote "the fetch failed" into a permanent, irreversible
# `shadow_evaluated_at` stamp, which recorded an absence of data that had never
# been established: a single 429 on a batch of week-old rows would have retired
# every one of them. The two things age cannot decide are exactly the two the
# retryable set names — a network failure and a window that has not finished.
# Terminal outcomes are now reached only by evidence: the exchange answering that
# it has nothing (data_unavailable), or the row's own shape (pass A).
#
# Kept as a reporting threshold, and still shorter than the 14-day observation
# gate so a stuck row surfaces well before that count is used.
MAX_RETRY_AGE = timedelta(days=7)

# Reasons that can never change on a later run: they are properties of the STORED
# ROW, not of the bars. A HOLD candidate will not acquire a direction tomorrow.
# Shared with the runtime logger, which stamps new rows with the same reasons at
# birth — the strings must not drift between the two paths.
PERMANENT_REASONS = SHADOW_PERMANENT_REASONS

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


# `extra` is written too, but as a MERGE expression rather than a value, so it
# cannot live in _WRITABLE (which is compared against a payload of plain values).
# Named separately and admitted explicitly, so the guard still sees every column
# the UPDATE touches instead of being bypassed by a sibling keyword argument.
_WRITABLE_EXTRA = {"extra"}


def _assert_write_targets(payload: dict, *, allow_extra: bool = False) -> None:
    allowed = _WRITABLE | (_WRITABLE_EXTRA if allow_extra else set())
    stray = set(payload) - allowed
    if stray:
        raise RuntimeError(f"refusing to write non-shadow columns: {sorted(stray)}")


async def _fetch_bars(collector, symbol: str, timeframe: str, bar_time):
    """The candidate's OWN 48 hours, not the exchange's most recent 48.

    Returns (df, requested_limit, fetch_failed). `fetch_failed` separates "the
    call did not complete" (transient, retry) from "the exchange answered and had
    nothing for this window" (permanent, data_unavailable) — collapsing the two
    is what would make a delisted symbol retry forever.

    An unsupported timeframe is a per-row failure, not a batch one:
    `historical_window` raises for it, and the whole loop runs inside a single
    transaction, so letting that escape would discard every verdict the run had
    already computed.
    """
    try:
        _start, window_end, limit = historical_window(bar_time, timeframe)
    except ValueError as exc:
        log.warning("  %s %s: %s", symbol, timeframe, exc)
        return None, 0, True
    try:
        df = await collector.fetch_ohlcv(
            symbol, timeframe, limit=limit,
            # Inclusive of the bar containing it, so the horizon bar is covered.
            end_time_ms=int(window_end.timestamp() * 1000),
        )
        return df, limit, False
    except Exception as exc:  # noqa: BLE001
        log.warning("  bar fetch failed for %s %s: %s", symbol, timeframe, type(exc).__name__)
        return None, limit, True


def extra_merge_expression(provenance: dict):
    """`extra || {"shadow_passb": ...}` — a MERGE, never an assignment.

    `extra` already carries the F1 decision-input contract, F1-D adaptive state
    and the engine-execution telemetry. Assigning to the column would delete all
    of them, so the new key is concatenated onto whatever is there. Cast through
    jsonb because the column is `json`, which has no `||` operator.

    KNOWN, ACCEPTED SIDE EFFECT: the json->jsonb->json round trip re-renders the
    whole document in jsonb's canonical form — object keys reordered, whitespace
    dropped, numbers re-emitted (1e-05 becomes 0.00001). No key and no value is
    lost, and every reader in the repo goes through .get(), so nothing downstream
    depends on the text form. It is done in SQL rather than as a read-modify-write
    in Python deliberately: the merge stays atomic, so a concurrent writer to
    `extra` cannot be silently clobbered by a stale in-process copy.
    """
    return func.coalesce(
        SignalDecisionCandidate.extra.cast(JSONB), text("'{}'::jsonb")
    ).concat(
        func.jsonb_build_object("shadow_passb", func.cast(json.dumps(provenance), JSONB))
    ).cast(JSON)


def _window_is_complete(bar_time, now) -> bool:
    """Has the candidate's 48h actually elapsed? Until it has, an empty window is
    'not yet', never 'never'."""
    return (now - bar_time) >= SHADOW_HORIZON


def _exchange_has_nothing(df, bar_time, timeframe) -> bool:
    """True when the exchange answered but its data ends before this window opens.

    The delisted case: MATICUSDT and FTMUSDT still return klines, they just stop
    in 2024/2025. Waiting cannot fix that, so it is decided here rather than left
    to age out of the retry window unmeasured.
    """
    if df is None or getattr(df, "empty", True):
        return False                      # no answer at all -> transient, not proof
    _start, window_end, _limit = historical_window(bar_time, timeframe)
    last = df.index[-1]
    ref = bar_time if getattr(df.index, "tz", None) is not None else bar_time.replace(tzinfo=None)
    try:
        return bool(last <= ref)
    except TypeError:
        return False


def evaluable_predicate():
    """Rows the evaluator CAN reach a verdict on: a real direction and complete
    geometry. This is the pass-B selection."""
    return and_(
        SignalDecisionCandidate.engine_direction.in_(EVALUABLE_DIRECTIONS),
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
        SignalDecisionCandidate.engine_direction.notin_(EVALUABLE_DIRECTIONS),
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
        # Direction first, geometry second — the same priority classify_birth_shadow
        # applies in Python. A test walks a truth table across both paths.
        "shadow_resolution_reason": case(
            (or_(SignalDecisionCandidate.engine_direction.is_(None),
                 SignalDecisionCandidate.engine_direction.notin_(EVALUABLE_DIRECTIONS)),
             SHADOW_REASON_NO_DIRECTION),
            else_=SHADOW_REASON_NO_GEOMETRY,
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


async def _finalise_undecidable(db, cand, reason: str, dry_run: bool = True) -> None:
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
    if dry_run:
        return
    await db.execute(
        update(SignalDecisionCandidate)
        .where(SignalDecisionCandidate.id == cand.id)
        .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
        .values(**payload)
    )


async def evaluate(limit: int, dry_run: bool = True) -> Counter:
    """PASS B. Default is dry_run: the write path must be asked for, not defaulted
    into. Every branch below computes exactly the same verdict either way; the
    only difference is whether the UPDATE is issued."""
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
                # Reported, never acted on: a row this old that is still unresolved
                # is an operations signal, not grounds for calling it undecidable.
                if (now - cand.evaluated_bar_time) > MAX_RETRY_AGE:
                    stats["stale_beyond_retry_age"] += 1

                raw, requested_limit, fetch_failed = await _fetch_bars(
                    collector, cand.symbol or "", cand.timeframe, cand.evaluated_bar_time)

                if fetch_failed:
                    # The call did not complete: 429, timeout, DNS, connection
                    # reset, 5xx. That is an absence of an answer, never an answer
                    # of absence, and age says nothing about it — a row seven days
                    # old whose fetch just timed out has exactly as much market
                    # data behind it as one that is one day old. Retiring it here
                    # (which this used to do via `too_old`) recorded "there is
                    # nothing to find" when the truth was "we could not look",
                    # and the stamp is irreversible. Always retryable now
                    # (CP-SHADOW-PASSB-B-SAFETY, blocker 3).
                    stats["transient_fetch_error_retry"] += 1
                    continue

                # The exchange answered and its data ends before this window even
                # opens: delisted, or never listed at that time. Waiting cannot
                # change it, so it is claimed now with its own reason instead of
                # ageing out indistinguishable from "still coming".
                if _exchange_has_nothing(raw, cand.evaluated_bar_time, cand.timeframe):
                    await _finalise_undecidable(db, cand, SHADOW_REASON_DATA_UNAVAILABLE,
                                                dry_run=dry_run)
                    stats["data_unavailable"] += 1
                    continue

                # The evaluator does not truncate for us — the caller owns the
                # window. clip_to_window bounds it on BOTH sides: strictly after
                # the decision bar (so the bar the call was made on is never
                # walked) and no later than the 48h horizon (so a touch that
                # happened after the trade would have closed cannot count as an
                # entry). It also sorts and de-duplicates, because exchange
                # ordering and uniqueness are not a contract.
                df = clip_to_window(raw, cand.evaluated_bar_time, cand.timeframe)
                if len(df) == 0:
                    # Empty AFTER a successful fetch. If the window has not fully
                    # elapsed this is simply "not yet"; the SQL maturity filter
                    # should already have excluded those, and this is the guard
                    # for when it does not.
                    # A completed fetch that returned data, none of it inside a
                    # window that HAS elapsed, is the exchange saying there is
                    # nothing there — the same statement _exchange_has_nothing
                    # makes from the other side, so it earns the same reason
                    # rather than a look-alike of its own.
                    if _window_is_complete(cand.evaluated_bar_time, now):
                        await _finalise_undecidable(db, cand, SHADOW_REASON_DATA_UNAVAILABLE,
                                                    dry_run=dry_run)
                        stats["data_unavailable"] += 1
                    else:
                        stats["window_not_elapsed_retry"] += 1
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
                    # Lets the evaluator refuse `expiry` and `never_entered` on a
                    # window that never finished — both are claims about bars that
                    # are missing (PASSB-B-SAFETY, blocker 2).
                    timeframe=cand.timeframe,
                )

                # Only TRANSIENT undecidables can reach here — pass B's SQL filter
                # already excluded every permanent one, and pass A retires those.
                # The TERMINAL arm is a DRIFT GUARD, not the primary path: if
                # evaluable_predicate() and the evaluator's own notion of
                # "unevaluable" ever disagree, this catches the row rather than
                # letting it retry forever.
                if out["shadow_outcome"] == "undecidable":
                    reason = out.get("shadow_resolution_reason") or "unknown"
                    # `too_old` no longer promotes anything on its own. Age is a
                    # fact about the market, not about whether the data exists or
                    # the window finished, and the reasons in
                    # SHADOW_RETRYABLE_REASONS are exactly the ones it cannot
                    # settle. Only a genuinely terminal reason retires a row.
                    if reason in SHADOW_TERMINAL_REASONS:
                        await _finalise_undecidable(db, cand, reason, dry_run=dry_run)
                        stats["undecidable_terminal"] += 1
                    elif reason in SHADOW_RETRYABLE_REASONS:
                        stats[f"{reason}_retry"] += 1
                    else:
                        stats["undecidable_retry"] += 1
                    continue

                # Provenance: which window was asked for, what came back, and
                # whether the walk had to break an inside-bar tie. Built here
                # because only the caller knows the request; additive to `extra`
                # and read by nothing in the decision path.
                prov = shadow_passb_provenance(
                    bar_time=cand.evaluated_bar_time, timeframe=cand.timeframe,
                    requested_limit=requested_limit, df=df, dry_run=dry_run,
                    intrabar_ambiguous=out.get("intrabar_ambiguous"),
                    entry_bar_walked=out.get("entry_bar_walked"),
                    entry_bar_tp_withheld=out.get("entry_bar_tp_withheld"),
                )
                if prov.get("intrabar_ambiguous"):
                    stats["intrabar_ambiguous"] += 1
                if prov.get("entry_bar_tp_withheld"):
                    stats["entry_bar_tp_withheld"] += 1
                if not prov.get("window_complete"):
                    stats["resolved_on_partial_window"] += 1

                payload = {k: v for k, v in out.items() if k in _WRITABLE}
                payload["shadow_evaluated_at"] = datetime.now(timezone.utc)
                # The guard has to see EVERY column the statement touches. Adding
                # `extra` as a sibling keyword to .values() after asserting the
                # payload would leave the widest column in the UPDATE outside the
                # only thing stopping a future edit from reaching a decision column.
                values = {**payload, "extra": extra_merge_expression(prov)}
                _assert_write_targets(values, allow_extra=True)

                if not dry_run:
                    await db.execute(
                        update(SignalDecisionCandidate)
                        .where(SignalDecisionCandidate.id == cand.id)
                        .where(SignalDecisionCandidate.shadow_evaluated_at.is_(None))
                        .values(**values)
                    )
                stats[out["shadow_outcome"]] += 1

            if dry_run:
                # Nothing was issued, but roll back anyway: SQLAlchemy autobegins
                # on the first SELECT, and leaving that transaction open is what
                # shows up as `idle in transaction` on the pooler.
                await db.rollback()
            else:
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
    # CP-SHADOW-PASSB-A inverted the default. Writing was what you got by running
    # the script with no flags, which makes the destructive mode the easiest thing
    # to do by accident — including from a shell-history recall of a report run.
    # Now the write path has to be asked for by name.
    ap.add_argument("--write", action="store_true",
                    help="ACTUALLY WRITE. Without this the run is a dry-run: both "
                         "passes compute exactly the same verdicts and issue no "
                         "UPDATE at all")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit no-op flag; dry-run is already the default and "
                         "this only makes the intent visible in shell history")
    ap.add_argument("--pass-a-only", action="store_true",
                    help="retire permanently-unevaluable rows and STOP: pass B is "
                         "never called, so no bars are fetched and no evaluable "
                         "candidate is written")
    ap.add_argument("--limit", type=int, default=500,
                    help="bounds EACH pass separately — without --pass-a-only a "
                         "single run can therefore touch up to 2x this many rows")
    args = ap.parse_args()

    dry_run = not args.write
    if not args.report:
        mode = "DRY-RUN (yazim YOK)" if dry_run else "WRITE"
        print(f"mod: {mode}")

        # Pass A first: retiring the unevaluable rows costs one bounded UPDATE and
        # no network, and it keeps `shadow_evaluated_at IS NULL` meaning exactly
        # "still to be measured" for every count that follows.
        async with async_session_factory() as db:
            retired = await retire_permanent(db, args.limit, dry_run=dry_run)
            if dry_run:
                await db.rollback()
            else:
                await db.commit()
        verb = "emekli edilecekti" if dry_run else "emekli edildi"
        print(f"pass A: {retired} kalici degerlendirilemez satir {verb} (fetch yok)")

        # The separation is structural, not a filter inside pass B: evaluate() is
        # simply never called, and BinanceCollector is constructed inside it, so
        # --pass-a-only cannot reach the network even if the eligibility window
        # later fills up. `--limit` bounds each pass on its own, so without this
        # flag one run writes up to 2x the limit; with it, exactly up to limit.
        if args.pass_a_only:
            print("pass B: --pass-a-only verildi — hic calistirilmadi "
                  "(bar fetch yok, degerlendirilebilir adaya yazim yok)")
        else:
            stats = await evaluate(args.limit, dry_run=dry_run)
            print("\npass B degerlendirme:", dict(stats))

    await report()


if __name__ == "__main__":
    asyncio.run(main())
