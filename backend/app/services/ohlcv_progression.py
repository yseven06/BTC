"""The durable OHLCV fairness progression primitive. NOTHING calls this yet.

It lives in its own module on purpose. `ohlcv_collector_job` carries an A3/A4
boundary guard asserting the collector never grows an upsert — that guard is
about BAR writes (revising history is A4's job, not A3's) and it is correct, so
the progression upsert is kept out of that module rather than the guard loosened
to accommodate it.
"""

from __future__ import annotations

import logging
import zlib
from contextlib import asynccontextmanager

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ohlcv_progress import OhlcvCollectionProgress
from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress

log = logging.getLogger(__name__)

# --- ADVISORY LOCK NAMESPACES (A3H8) ----------------------------------------
#
# TWO lock classes with two DIFFERENT lifetimes coordinate this module, and they
# must never be able to conflict with each other:
#
#   RUN   - session-scoped, held on a DEDICATED connection for the whole
#           collection run, so "this source is busy" outlives the claim.
#   CLAIM - transaction-scoped, held on whichever POOLED connection is running
#           `select_partition`, released by that transaction's COMMIT.
#
# A3H8 measured what happens if they share a key: the run's own CLAIM lock
# BLOCKS against its own RUN lock, because advisory locks belong to a session
# and these two live on different connections. So the two classes get explicitly
# separated namespaces via PostgreSQL's two-key advisory API, never an accidental
# integer difference. (Measured: same key -> BLOCKED; separated -> acquired.)
#
# The values are arbitrary but FIXED - 'OHC1'/'OHC2' as int4 - and must never be
# recomputed from anything environmental.
RUN_OWNERSHIP_LOCK_NAMESPACE = 0x4F484331
CLAIM_LOCK_NAMESPACE = 0x4F484332

# `pg_locks` distinguishes the two advisory key spaces ONLY by objsubid: the
# single-bigint form reports 1, the two-key form reports 2. Measured directly on
# PostgreSQL 17 rather than assumed — both forms decompose to the same
# classid/objid pair, so the first draft of this constant was inverted and it is
# easy to invert again by inspection. It is used only to VERIFY ownership, so a
# wrong value fails CLOSED: the run refuses to start rather than believing it
# owns a source it does not.
_TWO_KEY_OBJSUBID = 2


def source_lock_key(source: str) -> int:
    """Deterministic int4 advisory key for a source. NEVER Python `hash()`.

    `hash()` is salted per process (PYTHONHASHSEED), so two backend processes
    would derive DIFFERENT keys and neither would exclude the other - the exact
    failure this lock exists to prevent, and the same trap that already cost this
    track a rewrite when it was used for timeframe rotation. `zlib.crc32` is
    fixed by the algorithm: stable across processes, restarts and versions.

    The result is masked to 31 bits so it is a positive int4. PostgreSQL's
    two-key advisory API takes int4, and keeping the key positive means it can be
    compared directly against `pg_locks.objid` without two's-complement games.

    COLLISION BEHAVIOUR, STATED RATHER THAN IGNORED. Two source names sharing a
    31-bit CRC would share a run lock, so one would decline while the other
    collects. That is OVER-exclusion: a liveness cost, never a correctness
    violation, and it can never cause two runs to overlap. Sources are a
    hand-maintained set of a few venue names, so the probability is negligible;
    if a venue is ever added the constant-key guard test will still hold and only
    throughput would suffer.
    """
    src = (source or "").strip()
    if not src:
        raise ValueError("source must be a non-empty string")
    return zlib.crc32(src.encode("utf-8")) & 0x7FFFFFFF


async def _ownership_visible(conn, key: int) -> bool:
    """Is the run lock actually held by THIS backend, seen from a LATER statement?

    Not paranoia. Production reaches PostgreSQL through Supavisor in SESSION
    mode, where one client connection maps to one server backend for its whole
    life, which is what makes a session-scoped advisory lock mean anything. Under
    a TRANSACTION-mode pooler the next statement can land on a different backend,
    the lock would be invisible, and this module would happily "own" a source it
    does not own. So ownership is confirmed from a second statement on the same
    connection before any work is allowed to start.
    """
    return bool((await conn.execute(
        text("SELECT count(*) FROM pg_locks"
             " WHERE locktype = 'advisory' AND granted"
             "   AND classid = :ns AND objid = :key AND objsubid = :sub"
             "   AND pid = pg_backend_pid()"),
        {"ns": RUN_OWNERSHIP_LOCK_NAMESPACE, "key": key,
         "sub": _TWO_KEY_OBJSUBID})).scalar())


@asynccontextmanager
async def source_run_ownership(bind, source: str):
    """Own a source for a WHOLE collection run. Yields True if this run may run.

    WHY THIS EXISTS AT ALL. A3H7 classified the concurrency defect as L2, an
    OWNERSHIP-LIFETIME GAP: `select_partition`'s row locks are real and behave
    exactly as documented, but they end at its COMMIT while the work they are
    meant to protect - Binance fetches, per-item persistence - runs for the rest
    of the collection. Reproduced with ZERO transaction concurrency: one full
    ceil(N/K) cycle after a run claims its partition, a later claim is handed the
    same symbols while the first run is provably still in flight. No lock placed
    INSIDE the claim transaction can close that, because the gap is after it.

    NON-BLOCKING BY CONSTRUCTION. `pg_try_advisory_lock` returns immediately.
    A second run must DECLINE, not queue: queuing would pile runs up behind a
    slow one and deliver them all at once against the same cadence and the same
    exchange rate limit. Declining costs one cadence of data; queuing costs a
    stampede.

    SESSION-SCOPED, ON A DEDICATED CONNECTION. The lock is owned by a PostgreSQL
    session, so it lives exactly as long as the connection holding it. That
    connection is checked out for the whole run and never handed back mid-run -
    returning it to the pool would leave a pooled connection silently owning the
    source. It costs one connection out of the engine's ceiling for the run's
    bounded duration (<= the job budget).

    AND YET NO TRANSACTION STAYS OPEN. The acquire commits immediately. A session
    advisory lock SURVIVES that commit, which is the whole reason this shape was
    chosen over holding a transaction open across the network - the shape that
    has already produced idle-in-transaction incidents against the pooler here.

    CRASH RECOVERY IS POSTGRESQL'S, NOT OURS. Lose the connection - process
    death, restart, deploy, network drop - and the server releases the lock. No
    lease column, no expiry, no reaper, and above all NO CLOCK in the correctness
    path. That is the decisive advantage over a durable lease row.

    RELEASE IS UNCONDITIONAL. On the way out the lock is released explicitly; if
    that fails for ANY reason, including a cancellation arriving during cleanup,
    the connection is INVALIDATED rather than returned to the pool, so the server
    releases it by closing the session. A `finally` that merely awaits an unlock
    is not enough - the await itself can be interrupted.
    """
    src = (source or "").strip()
    if not src:
        raise ValueError("source must be a non-empty string")
    key = source_lock_key(src)

    conn = await bind.connect()
    acquired = False
    try:
        acquired = bool((await conn.execute(
            text("SELECT pg_try_advisory_lock(:ns, :key)"),
            {"ns": RUN_OWNERSHIP_LOCK_NAMESPACE, "key": key})).scalar())
        confirmed = acquired and await _ownership_visible(conn, key)

        # END THE TRANSACTION, AND END IT AFTER THE LAST STATEMENT. A session
        # advisory lock is not transactional at all: it belongs to the session
        # and neither COMMIT nor ROLLBACK releases it, so ROLLBACK is the honest
        # verb for a read-only confirmation.
        #
        # THE ORDER HERE IS THE WHOLE POINT AND IT WAS WRONG ONCE. Committing
        # straight after the acquire and only then running the confirmation left
        # that confirmation opening a SECOND transaction which nothing closed —
        # so the owner connection sat `idle in transaction` for the entire run,
        # the precise failure this design was chosen to avoid. It was caught by
        # asking PostgreSQL for the OWNER's state; asking from the owner itself
        # always answers 'active', because that connection is busy running the
        # question.
        await conn.rollback()

        if acquired and not confirmed:
            # A misconfigured pooler must not read as "another run is busy".
            raise RuntimeError(
                "OHLCV run ownership could not be confirmed on the connection "
                "that took it; a transaction-mode connection pooler cannot "
                "carry a session advisory lock")

        if not acquired:
            log.info("OHLCV run declined: source=%s is already owned by a run "
                     "in flight", src)
        yield acquired
    finally:
        released = False
        if acquired:
            try:
                released = bool((await conn.execute(
                    text("SELECT pg_advisory_unlock(:ns, :key)"),
                    {"ns": RUN_OWNERSHIP_LOCK_NAMESPACE, "key": key})).scalar())
                # Same reasoning as the acquire: the unlock is not transactional,
                # and the connection must not go back to the pool mid-transaction.
                await conn.rollback()
            except BaseException:      # noqa: BLE001 - cancellation included
                released = False
        if acquired and not released:
            # Physically drop it. Returning a still-locked connection to the pool
            # would hand the next borrower an unowned source it cannot release.
            await conn.invalidate()
        await conn.close()


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

    TWO LOCKS, AND THE SECOND ONE WAS NOT OPTIONAL. `FOR UPDATE SKIP LOCKED`
    stops a claimant taking rows another claimant is HOLDING, and it does that
    correctly - measured directly: with one transaction holding the oldest five,
    a second gets the next five. What it does NOT do is stop a claimant whose
    scan began before that holder committed, because the ranking came from its
    own snapshot and the qual recheck still admits the row. Measured at roughly
    5% of cold-pool invocations before the claim lock was added, 0 after. So the
    transaction advisory lock above is what actually makes concurrent claimants
    disjoint; SKIP LOCKED remains as the correct behaviour for genuinely
    contended rows.

    AN EARLIER VERSION OF THIS DOCSTRING CLAIMED DISJOINTNESS FROM SKIP LOCKED
    ALONE. That claim was false and was measured false; it is recorded here
    rather than quietly deleted, because the same reasoning would be reinvented
    otherwise.

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

    7. max_instances=1 IS NOT LOAD-BEARING FOR CORRECTNESS, and this is now
       true by construction rather than by assertion. Claim-level disjointness
       comes from the transaction advisory lock plus the predicate; RUN-level
       exclusivity comes from `source_run_ownership`, which is server-side and
       therefore covers the admin run-now path, a second backend process and a
       deploy overlap - none of which APScheduler's process-local
       `max_instances` can see. It stays as an operational convenience.

    8. WHAT THIS PRIMITIVE DOES NOT PROMISE. It claims symbols; it does not
       own them for the duration of the WORK. `last_attempt_run_seq = R` means
       "run R attempted this", past tense - it is not a lease, and contract (4)
       deliberately lets a later run take a row whose token is below its own
       sequence. In-flight exclusivity is `source_run_ownership`'s job, and a
       caller that skips it gets fair claims with no protection against a
       concurrent run fetching the same symbol.
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
        # 0. SERIALISE THE CLAIM (B1). Transaction-scoped, released by the COMMIT
        #    below, in its own namespace so it can never meet the run-ownership
        #    lock (measured: sharing a key makes a run block against itself).
        #
        #    WHY IT IS NEEDED DESPITE `FOR UPDATE SKIP LOCKED`. Row locks are
        #    taken by the LockRows node, which sits ABOVE the sort - so the
        #    ranking is computed from the statement's snapshot. Measured on
        #    PostgreSQL 17: a scan that starts before another claimant commits
        #    sorts that claimant's rows as still-oldest, then locks them AFTER
        #    the commit released them, and the row still satisfies
        #    `last_attempt_run_seq < run_seq` because the other claim's token is
        #    below this run's sequence. Both claimants returned the same five
        #    symbols while twenty older rows sat untouched, so it is not
        #    exhaustion and SKIP LOCKED is not at fault: nothing was locked by
        #    the time the second scan reached them.
        #
        #    BLOCKING, NOT `try`, AND DELIBERATELY SO. This transaction holds no
        #    network call and completes in milliseconds, so waiting is cheap and
        #    correct - a claimant that skipped would silently claim nothing.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {"ns": CLAIM_LOCK_NAMESPACE, "key": source_lock_key(src)})

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
