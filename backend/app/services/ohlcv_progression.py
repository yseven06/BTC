"""The durable OHLCV fairness progression primitive. NOTHING calls this yet.

It lives in its own module on purpose. `ohlcv_collector_job` carries an A3/A4
boundary guard asserting the collector never grows an upsert — that guard is
about BAR writes (revising history is A4's job, not A3's) and it is correct, so
the progression upsert is kept out of that module rather than the guard loosened
to accommodate it.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ohlcv_progress import OhlcvCollectionProgress
from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress

log = logging.getLogger(__name__)


async def acquire_run_sequence(session_factory, source: str) -> int:
    """Durably claim the next run sequence for `source`. ONE statement, ONE commit.

    MEANING. The returned value says "a collection run for this source has
    STARTED" — never that it succeeded, completed, attempted every symbol or
    persisted a bar. A run that claims a sequence and dies immediately has still
    consumed it, and that is deliberate: it is what stops a crash-looping run from
    replaying the same prefix of the universe forever. Measured on the previous
    architecture, advancing only on completion left a run that always died after
    two symbols reaching 2 of 57 symbols across 200 runs; advancing at the start
    reached 57 of 57.

    WHY A SINGLE STATEMENT AND NOT read-modify-write. A SELECT followed by an
    UPDATE is a lost-update race the moment two runs overlap, and the collector
    must not depend on `max_instances=1` for its own correctness. `INSERT ...
    ON CONFLICT (source) DO UPDATE SET run_seq = <table>.run_seq + 1 RETURNING`
    performs the read, the increment and the write inside one statement: the
    conflicting row is locked for the duration, so concurrent callers serialise and
    every caller receives a distinct value.

    WHY ITS OWN SHORT-LIVED SESSION. The transaction must commit BEFORE the first
    item and must never be open across a Binance request — the pool ceiling is 10
    and a transaction held across the network is exactly the idle-in-transaction
    shape this codebase has been bitten by before.

    FAILURE IS NOT SWALLOWED. If this cannot commit, the caller must not pretend
    fairness progression happened; the exception propagates and the run does not
    start.
    """
    src = (source or "").strip()
    if not src:
        # An empty source would key progression under a namespace that no watermark
        # read or row write could ever match.
        raise ValueError("source must be a non-empty string")

    stmt = (pg_insert(OhlcvCollectionProgress)
            .values(source=src, run_seq=1)
            .on_conflict_do_update(
                index_elements=[OhlcvCollectionProgress.source],
                set_={"run_seq": OhlcvCollectionProgress.run_seq + 1,
                      "updated_at": func.now()})
            .returning(OhlcvCollectionProgress.run_seq))

    async with session_factory() as db:
        result = await db.execute(stmt)
        seq = result.scalar_one()
        await db.commit()
    return int(seq)

# --- PER-SYMBOL PARTITION (A3F) ---------------------------------------------
#
# WHY A SECOND PRIMITIVE. `acquire_run_sequence` above makes the traversal ORDER
# fair but bounds nothing - the run still attempts all 228 items. The first
# genuine production run proved that unaffordable: 148.196 s for 50 of 228
# items, cancelled at the 150 s budget. So a run must cover a SUBSET, and the
# subset must still be fair.
#
# WHY NOT AN INDEX CURSOR. A3D cut the subset with `run_seq mod ceil(N/K)`.
# Modelling killed it: with a universe oscillating 57/58/57/250 only
# ceil(N/K)/gcd(period, ceil(N/K)) blocks are reachable - 25 of 50 at K=5, i.e.
# 95 of 250 symbols never selected. That is the wall-clock defect again with N
# in the clock's seat, and it generalises: ANY pure function of (run_seq, N) is
# phase-lockable when N is periodic in run_seq. No modulus, prime or hash
# escapes it. So fairness moved into SYMBOL space, keyed by the unique
# Asset.symbol.

# THE ADMISSION POLICY - ratified as "materialised current-1" after two
# empirically falsified alternatives. Read this before changing a character of
# the ranking, because all three candidates look almost identical in code.
#
#   FALSIFIED - effective token = current run_seq for rowless symbols.
#     An unseen symbol NEVER AGES: its priority is recomputed relative to every
#     run, so a symbol already claimed (holding an EARLIER run_seq) permanently
#     outranks it. Measured on a stable N=10/K=3 universe: the same first three
#     symbols selected forever, 7 of 10 permanently starved.
#
#   REJECTED - unseen ranks first (-infinity, "never attempted is oldest").
#     Exact on stable universes, and it is what the A3E numbers actually
#     measured - but it loses the decisive attack: with new symbol identities
#     arriving at >= K per run, newcomers fill every slot forever and a
#     continuously-active incumbent is never selected again. Measured STARVED at
#     K = 1,2,3,4,5,6,10. UNIVERSE_CAP does not save it: the cap bounds
#     CONCURRENTLY ACTIVE symbols, not how many distinct identities may appear.
#
#   RATIFIED - materialise every active rowless symbol at max(run_seq - 1, 0).
#     The seed is WRITTEN, so it ages like every other row; a newcomer joins one
#     generation behind the claim this run is about to make, which puts it
#     behind every overdue incumbent and ahead of nobody. Same attack, same K
#     range: the incumbent's worst wait is 50/25/16/12/10/8/5 for K=1..10 -
#     bounded and proportional to ceil(N/K).
#
# MATERIALISATION IS THE LOAD-BEARING HALF, NOT THE SEED VALUE. A mutation that
# keeps `current - 1` but computes it as an effective token instead of writing
# it reproduces the falsified failure exactly (measured: 5 of 57 symbols ever
# selected). Never reintroduce a virtual unseen row.
UNSEEN_MATERIALISES_ONE_GENERATION_BEHIND = True


async def select_partition(session_factory, source: str,
                           active_symbols, k: int, run_seq: int):
    """Claim the K oldest-attempted ACTIVE symbols for THIS run.

    Returns them in the deterministic order they will be traversed.

    ONE SHORT TRANSACTION, THREE STATEMENTS, NO NETWORK. Materialise, select,
    advance, commit - all before the first Binance request. The pool ceiling is
    10 and a transaction held across a network call is the idle-in-transaction
    shape this codebase has already been bitten by.

    THE CLAIM IS PART OF THE SELECTION. A partition is consumed even if the
    process dies, the run is cancelled at the outer deadline, Binance returns
    418, or every persist fails - the same deliberate choice
    `acquire_run_sequence` makes, and for the same reason: a run that always
    dies after two symbols must not replay the same two forever. The token means
    ATTEMPTED, never succeeded, persisted, or covered.

    FOR UPDATE SKIP LOCKED, and it is not decoration. `acquire_run_sequence`
    already refuses to depend on APScheduler's max_instances=1 for correctness,
    and this primitive holds itself to the same standard: two overlapping runs
    get distinct run_seq values but would otherwise read the same K oldest rows
    and claim the same partition twice, wasting a cadence. Skipping locked rows
    makes the second run take the NEXT K instead, so two concurrent claims cover
    2K distinct symbols and never collide.

    ORDERING IS TOTAL: (last_attempt_run_seq ASC, symbol ASC). The tie-break is
    the symbol itself - Asset.symbol is unique=True - so equal tokens never
    resolve by plan order, arrival order, hash or clock.

    THE CONTRACT, STATED AS SEPARATE CLAIMS
    ---------------------------------------
    1. DUPLICATE-CLAIM SAFETY. Eligibility requires
       `last_attempt_run_seq < run_seq`, so a stale or equal run cannot reclaim
       rows whose durable token has already reached its sequence. Without it,
       reproduced from a clean ledger at r+1 -> r -> r+2: r+1 seeds every row
       at r, the stale r wrote r onto rows already at r - a claim that advanced
       nothing - and r+2 handed out the same five symbols again.

    2. TOKEN MONOTONICITY. A successful claim never decreases a stored token.

    3. SERIAL FAIRNESS. With monotonically increasing run_seq over a stable,
       continuously-active universe, coverage completes within ceil(N/K)
       successful executions. Measured exactly at N=20/K=5, 57/5 and 57/4.

    4. OUT-OF-ORDER FAIRNESS - a DIFFERENT and weaker bound. Runs take a
       monotonic run_seq but may COMPLETE out of order. Measured:
       coverage <= ceil(N/K) + stale_runs_before_completion, confirmed over
       r+1,r,r+2 / r+2,r,r+1,r+3 / r+3,r+1,r+2,r,r+4 and sustained
       fresh/stale alternation (57/57 covered, no starvation). ceil(N/K) is
       NOT claimed for arbitrary invocation ordering.

    5. STALE RUNS. A run whose sequence is not above the stored tokens finds
       nothing eligible and returns []. That is normal ordering behaviour, not
       degradation or failure: it is what bounds (4) to one extra execution per
       stale run instead of corrupting the queue.

    6. NEWCOMER ADMISSION is unaffected. seed = max(run_seq - 1, 0) < run_seq,
       so a freshly materialised symbol is eligible on the very run that
       created it. This is why the operator is `<` and never `<=`: with `<=` a
       run would re-select rows it had already claimed itself.

    7. max_instances=1 IS NOT LOAD-BEARING FOR CORRECTNESS. Duplicate-claim
       safety and token monotonicity come from the predicate and the durable
       token, and are proven against real PostgreSQL with concurrent claimants.
       APScheduler's max_instances=1 only reduces how often runs overlap at
       all; it is an operational convenience, not part of this contract.
    """
    src = (source or "").strip()
    if not src:
        raise ValueError("source must be a non-empty string")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if run_seq < 0:
        raise ValueError(f"run_seq must be >= 0, got {run_seq}")

    active = [s for s in dict.fromkeys(active_symbols) if s and s.strip()]
    if not active:
        return []

    # One generation behind the claim this run is about to make. Floored at 0
    # because the column carries CHECK (last_attempt_run_seq >= 0) and the very
    # first executed run has run_seq = 1.
    seed = max(run_seq - 1, 0)

    async with session_factory() as db:
        # 1. MATERIALISE. Every active symbol becomes a durable queue member
        #    before ranking. Existing rows are untouched, so a relisted symbol
        #    keeps the history it had when it went inactive.
        await db.execute(
            pg_insert(OhlcvSymbolProgress)
            .values([{"source": src, "symbol": s,
                      "last_attempt_run_seq": seed} for s in active])
            .on_conflict_do_nothing(
                index_elements=[OhlcvSymbolProgress.source,
                                OhlcvSymbolProgress.symbol]))

        # 2. SELECT the oldest K among the ACTIVE set only. An inactive symbol
        #    keeps its row and simply does not compete.
        selected = list((await db.execute(
            select(OhlcvSymbolProgress.symbol)
            .where(OhlcvSymbolProgress.source == src,
                   OhlcvSymbolProgress.symbol.in_(active),
                   # ELIGIBILITY, AND IT IS NOT COSMETIC.
                   #
                   # Runs take a monotonic run_seq but can COMPLETE out of order.
                   # Reproduced from a clean ledger with the real code at
                   # r+1 -> r -> r+2: r+1 seeds every row at r+1-1 = r, claims
                   # five, and the stale r then wrote r onto rows ALREADY at r.
                   # That claim made no ordering progress, so those rows stayed
                   # tied with never-claimed rows and r+2 selected them again -
                   # two runs handed the same partition.
                   #
                   # `< run_seq` makes a claim that cannot advance a row
                   # impossible: a stale run finds nothing eligible and returns
                   # an empty partition rather than backdating the queue.
                   # Strictly `<`, never `<=`: the seed is run_seq-1, so `<`
                   # keeps a freshly materialised symbol eligible on the very
                   # run that created it, while `<=` would let a run re-claim
                   # rows it had already claimed itself.
                   OhlcvSymbolProgress.last_attempt_run_seq < run_seq)
            .order_by(OhlcvSymbolProgress.last_attempt_run_seq.asc(),
                      OhlcvSymbolProgress.symbol.asc())
            .limit(k)
            .with_for_update(skip_locked=True))).scalars().all())

        # 3. ADVANCE exactly those rows. Nothing else in the table moves.
        if selected:
            await db.execute(
                update(OhlcvSymbolProgress)
                .where(OhlcvSymbolProgress.source == src,
                       OhlcvSymbolProgress.symbol.in_(selected))
                .values(last_attempt_run_seq=run_seq, updated_at=func.now()))
        await db.commit()

    log.info("OHLCV partition claimed: source=%s run_seq=%s k=%s selected=%s "
             "active=%s seed=%s", src, run_seq, k, len(selected), len(active), seed)
    return selected
