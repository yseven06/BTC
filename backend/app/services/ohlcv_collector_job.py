"""CP-OHLCV-A3b — the dormant OHLCV collector. NOTHING calls this.

There is no scheduler registration, no startup hook, no flag and no background
task here. Importing the module defines constants and functions and does nothing
else. Wiring is A3c's decision, and A3c is a separate, separately-reviewed
checkpoint.

WHY THIS DOES NOT REUSE THE SIGNAL SWEEP
----------------------------------------
The obvious design — hang OHLCV storage off `_run_all_signals` — was rejected in
the A3 preflight on two measured grounds:

  * `POST /api/v1/signals/generate-batch` (signals.py) is a SECOND entry into
    that sweep. It is tier-gated but ends in a bare `asyncio.create_task`, so it
    runs outside `_run_tracked` and outside APScheduler's `max_instances: 1`.
    Anything hooked into the sweep inherits a subscriber-triggerable, unguarded,
    possibly-concurrent write path.
  * The sweep is cut off by its own job budget (`signals_15m`: 600 s against a
    measured 259-320 s over 57 assets) and its asset query carries no ORDER BY,
    so WHICH symbols get dropped at the cut is plan-order dependent.

A durable store cannot be keyed on a set that is silently truncated in a
non-deterministic order. So the storage universe is owned here: an explicit
query, an explicit total order, an explicit cap, and an explicit overflow signal
when the population outgrows the cap.

SHAPE: strictly serial. One symbol, one timeframe, one Binance request, one DB
session at a time. No gather, no TaskGroup, no semaphore. That is not timidity —
the production pool ceiling is 10 (`pool_size=8 + max_overflow=2`) against a
measured scheduler peak of 6, and the existing signals sweeps are themselves
sequential. Serial adds exactly 1.

LIVE COLLECTION ONLY. `end_time_ms` is never set, so every request asks for the
most recent bars and the newest element is the still-forming candle, which the
writer excludes structurally. There is no paging, no end_time iteration and no
historical seeking: a gap wider than `limit x timeframe` is A4's problem, not
this module's.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import zlib
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import String, column, select, true, values

from app.collectors.binance_collector import BinanceCollector
from app.models.asset import Asset, AssetType
from app.models.ohlcv_bar import OhlcvBar
from app.services.ohlcv_progression import acquire_run_sequence
from app.services.ohlcv_writer import (DEFAULT_FETCH_RETRIES,
                                       DEFAULT_FETCH_TIMEOUT, SOURCE_BINANCE,
                                       WriteResult, collect_and_persist,
                                       normalise_symbol, normalise_timeframe)

log = logging.getLogger(__name__)

# THE STORAGE TIMEFRAMES. Exactly these four, in this order.
#
# Deliberately NOT the writer's admission set: `ohlcv_writer.normalise_timeframe`
# validates against `TIMEFRAME_DURATIONS`, which is seven wide and includes "1m"
# and "1w". The writer may accept those; A3 does not select them. 1m in
# particular is excluded on purpose — it is ~96x the row volume of 15m and a
# single limit=1000 fetch reaches only 16h40m of it, so it needs its own
# justification (a future intrabar/birth-candle requirement) rather than being
# switched on "for later".
STORAGE_TIMEFRAMES: Tuple[str, ...] = ("15m", "1h", "4h", "1d")

# The universe ceiling. Production currently holds 57 active crypto assets (59
# crypto rows in total), so this is >4x headroom while staying finite and
# explicit. It exists to bound a run, NOT to trim the universe: exceeding it is
# reported as `universe_overflow` and makes the run unhealthy rather than
# quietly processing the first N.
UNIVERSE_CAP = 250

# Live-window request shape. limit >= 2 is a hard requirement: with limit=1 the
# only returned bar is also the newest, the writer withholds it, and the run can
# never persist anything at all.
DEFAULT_FETCH_LIMIT = 500
MIN_FETCH_LIMIT = 2

# THE BOOTSTRAP CAP — how many bars a series that has NEVER been written may
# seed on its very first run.
#
# Derived from the 4-timeframe/cadence contract, not chosen for taste:
#   * the intended cadence is 15 minutes, which is exactly the period of the
#     finest storage timeframe, so one effective run produces one new 15m bar;
#   * APScheduler's `coalesce=True` + `max_instances=1` collapse consecutive
#     missed fires into a single run, so at most TWO cadence periods separate
#     two EFFECTIVE runs before `misfire_grace_time=300` drops the fire
#     entirely — an upper bound of 2 new 15m bars between effective runs;
#   * 4 = 2x that bound, one full doubling of margin on the finest timeframe.
# On 1h/4h/1d the same count buys strictly more wall-clock coverage (4h, 16h,
# 4d), so the finest timeframe is the binding case and 4 covers all four.
#
# This is a SEED, not history. It exists so the first run is bounded, and it is
# emphatically not a backfill: A4 still owns every bar older than the seed.
BOOTSTRAP_MAX_BARS = 4

# HEADROOM OVER THE SEED, AND WHY IT IS EXACTLY TWO.
#
# A bootstrap request is trimmed to the newest BOOTSTRAP_MAX_BARS, so the old
# behaviour — reusing the 500-bar catch-up window — fetched 125x what it kept.
# Measured on the one genuine production run: 24500 fetched, 24255 trimmed,
# 196 kept, i.e. every single request threw away 495 of 500 bars.
#
# But the naive repair (`limit = BOOTSTRAP_MAX_BARS`) is WRONG, and measurably
# so: `eligible_bars` runs with `drop_newest=True`, which discards the newest
# element of every response unconditionally, so a 4-bar request yields 3 usable
# closed bars and the series is silently under-seeded on its very first run.
#
#   +1 pays for that guaranteed drop — it is structural, not probabilistic.
#   +1 more is the spare: a duplicate collapsed by the de-duplicating index, a
#      malformed final candle, or a second not-yet-closed bar each cost one more
#      row, and with zero spare any one of them silently under-seeds again.
#
# Two is therefore the smallest headroom that survives one unexpected drop, and
# under-seeding is self-healing anyway (the watermark simply advances from
# wherever it lands), so a third spare would buy nothing.
BOOTSTRAP_FETCH_LIMIT = BOOTSTRAP_MAX_BARS + 2


def bootstrap_fetch_limit(bootstrap: int) -> int:
    """Request size for a series that has never been written.

    Derived from the caller's own bootstrap cap rather than read from the module
    constant, so a caller that overrides `bootstrap` (every test does) gets a
    request shaped for the value it actually passed.

    NO MIN_FETCH_LIMIT CLAMP, DELIBERATELY. One was written here and removed:
    `bootstrap >= 1` is enforced below, so the result is always >= 3, which is
    already above MIN_FETCH_LIMIT (2). A `max(MIN_FETCH_LIMIT, ...)` was
    therefore unreachable on every legal input — a mutation deleting it could
    not be killed by any test, because it changed nothing. Dead defence that
    cannot fail is worse than none: it implies a guard the reader will trust.
    The real guard is the ValueError, which IS reachable.
    """
    if bootstrap < 1:
        # limit=1 would return a single bar that is also the newest, which
        # `drop_newest` withholds — the series could never seed at all.
        raise ValueError(f"bootstrap must be >= 1, got {bootstrap}")
    return bootstrap + 2

# Symbols per watermark query. At the current cap of 250 this is ONE query for
# the whole run (250 x 4 = 1000 VALUES rows, 2000 bind parameters, comfortably
# under PostgreSQL's 65535 parameter ceiling). The chunk exists so that raising
# the cap degrades into a few bounded queries rather than one statement that
# eventually refuses to plan.
WATERMARK_CHUNK = 250

# Spacing between Binance requests, seconds.
#
# `/api/v3/klines` at limit=500 costs weight 2. A full run of 57 symbols x 4
# timeframes = 228 requests = 456 weight. At 0.2 s the burst rate is 5 req/s =
# 10 weight/s = 600 weight/min against the documented 1200/min IP ceiling — 50%
# headroom, while adding only ~46 s to a run inside a 900 s cadence. The signals
# sweep's 1.0 s would add 228 s for no measured benefit at this weight.
REQUEST_SPACING_SECONDS = 0.2

# HARD WALL-CLOCK BOUND PER (symbol, timeframe) ITEM.
#
# The outer job deadline alone is not enough. One item's worst case is measured
# from the deployed constants: 3 attempts x DEFAULT_FETCH_TIMEOUT(20s) plus
# backoff 1s + 2s = 63s, or 70s when a clamped Retry-After replaces the local
# schedule. Against a 600 s run budget that is 9.5 pathological items out of 228
# — and because the universe is ordered by a UNIQUE symbol, the truncation would
# always fall on the SAME alphabetical tail, every run. The signals sweep solved
# the identical problem with PER_ASSET_BUDGET_SECONDS; this is its counterpart.
#
# 25 s = one fetch timeout (20 s) + 5 s for backoff, parse, watermark filtering
# and the per-row savepoints. It bounds blast radius; the outer job budget is
# what still guarantees the cadence.
ITEM_BUDGET_SECONDS = 25.0

# REDUCED BOUND FOR THE REST OF A SYMBOL THAT HAS ALREADY FAILED THIS RUN.
#
# WHY THIS EXISTS AT ALL. The previous design ABANDONED a symbol's remaining
# timeframes after a terminal failure, to stop one sick symbol from burning four
# full item budgets. That bounded the cost, but it made TIMEFRAME ORDER decide
# REACHABILITY: whatever sat behind the broken timeframe was never attempted,
# and an independent review proved a healthy sibling could stay unattempted
# forever. Ordering fairness was then patched on top with a second rotation,
# which coupled to the symbol rotation and froze under budget truncation.
#
# THE FIX IS TO REMOVE THE DEPENDENCY, NOT TO RE-ORDER IT. Every timeframe of a
# reached symbol is now ALWAYS attempted; only the BUDGET degrades. Order can no
# longer determine whether an item is tried, so no timeframe rotation — and no
# rotation proof — is needed.
#
# SIZING. A healthy item is measured at ~1.7 s p95 (Binance klines p95 976 ms +
# ~5 database round trips at 141.6 ms). 5 s is ~3x that headroom, so a healthy
# sibling completes comfortably, while a sick one is capped well below the full
# slice. Worst pathological symbol = 25 + 3 x 5 = 40 s (1.6x one item budget)
# against the 100 s (4x) that abandon was introduced to prevent.
#
# This applies ONLY after a terminal failure on the SAME symbol in the SAME run.
# A healthy symbol always gets the full ITEM_BUDGET_SECONDS on every timeframe.
DEGRADED_ITEM_BUDGET_SECONDS = 5.0

# THE INTENDED CADENCE, used ONLY as the fairness clock. Declaring it here does
# not schedule anything; the activation checkpoint still owns registration.
DEFAULT_CADENCE_SECONDS = 1800.0


# ROTATION — the fairness mechanism, and the reason 600 s is survivable.
#
# THE PROBLEM IT SOLVES. The universe is a TOTAL order (Asset.symbol is unique),
# every run started at index 0, and the outer budget admits only about
# 600/25 = 24 items. Measured over four consecutive runs, three pathological
# low-order symbols consumed the entire budget every time and the SAME 17-symbol
# suffix was never attempted once. Deterministic starvation is worse than random
# starvation: the same symbols lose forever.
#
# THE MECHANISM. Rotate the starting symbol by a cadence-bucket index derived
# from wall-clock time:
#
#     bucket = floor(now / cadence);  offset = bucket mod len(symbols)
#     order  = symbols[offset:] + symbols[:offset]
#
# It is deterministic (same bucket, same order), stateless (no cursor, no DB, no
# process memory), and therefore untouched by restart or redeploy — the clock is
# the only input. Over any len(symbols) consecutive buckets every offset occurs
# exactly once, so a symbol at position p is reached in exactly as many runs as
# any other: if a run reaches k symbols, every symbol is reached k times per
# full rotation. No fixed suffix can starve while k >= 1.
#
# THE CLOCK IS A FAIRNESS INPUT ONLY. It never decides whether a candle is
# closed: closure remains the exchange response's job (the two gates in
# eligible_bars), and the watermark remains the persistence boundary. Rotation
# changes only the ORDER items are visited in.
#
# Idempotency is what makes reordering free: the natural key plus
# ON CONFLICT DO NOTHING means visiting a series in a different order can never
# duplicate a row.

# Bounds on what a single run may accumulate in memory before it is serialised.
MAX_FAILURES_RETAINED = 50
MAX_INVALID_REASONS = 25


@dataclass
class CollectionResult:
    """Aggregate collection health. Observability only.

    NOTHING in the trading path may read these. They describe whether we managed
    to copy bars off an exchange; they say nothing about a signal, an entry, or
    a trade, and wiring them into a decision would turn a network hiccup into a
    market opinion.
    """

    # universe
    symbols_discovered: int = 0     # eligible population, BEFORE the cap
    symbols_selected: int = 0       # what this run actually took
    universe_cap: int = UNIVERSE_CAP
    universe_overflow: bool = False

    symbols_attempted: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    symbols_skipped: int = 0
    timeframes_attempted: int = 0

    # fetch phase
    fetch_attempts: int = 0
    fetch_success: int = 0
    fetch_timeout: int = 0
    fetch_error: int = 0
    retry_recovered: int = 0
    retry_exhausted: int = 0
    malformed_response: int = 0
    fetch_rate_limited: int = 0
    fetch_ip_banned: int = 0

    # watermark phase
    # run identity / timing (telemetry, never a decision input)
    run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    # terminal disposition
    cancelled: bool = False            # outer job deadline cancelled the run
    aborted: bool = False              # run stopped itself (e.g. HTTP 418)
    abort_reason: str = ""
    items_deadline_exceeded: int = 0   # per-item wall-clock bound fired

    # staged-but-not-committed: rows the savepoints accepted and a failing
    # commit then discarded. Kept apart from bars_persisted so a committed count
    # can never be inflated by work that was rolled back.
    bars_staged_rolled_back: int = 0
    failures_dropped: int = 0

    # fairness / coverage accounting
    rotation_offset: int = 0   # where this run started in the total order
    run_seq: int = -1          # durable executed-run sequence; -1 = never claimed
    symbols_unattempted: int = 0       # selected but never reached (budget expired)
    symbols_degraded: int = 0          # had a terminal failure; rest of its timeframes ran on the reduced budget
    timeframes_degraded_after_failure: int = 0

    watermark_failed: bool = False     # the read FAILED; run degraded to bootstrap
    watermark_anomalies: int = 0       # the read SUCCEEDED and returned a future mark
    watermark_series_known: int = 0    # series that already had a stored bar
    series_bootstrapped: int = 0       # series seeded this run (no watermark)
    bars_below_watermark: int = 0      # already stored — never offered to the DB
    bars_bootstrap_trimmed: int = 0    # trimmed off an unbounded first load

    # bar phase
    bars_fetched: int = 0
    bars_eligible: int = 0
    bars_persisted: int = 0
    bars_duplicate: int = 0
    bars_invalid: int = 0
    bars_forming_or_not_closed: int = 0

    # persistence
    db_rejected: int = 0
    db_error: int = 0

    invalid_reasons: Dict[str, int] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """A run is healthy only if the universe fitted and nothing failed hard.

        `universe_overflow` counts as unhealthy on purpose — a truncated run that
        reports success is exactly the silent-coverage-loss failure this module
        was designed to avoid. `watermark_anomalies` likewise, and for a sharper
        reason: a series whose stored watermark is newer than anything the
        exchange has can never advance again, and without this term the run
        would report perfect health forever while that series stayed frozen.
        `watermark_failed` likewise: that run still
        collected, but it did so on the degraded bootstrap path, and a run that
        reports full health while re-offering seeds every cadence would hide a
        persistent database problem behind a working-looking result.
        """
        return (not self.universe_overflow
                and not self.cancelled
                and not self.aborted
                and self.items_deadline_exceeded == 0
                and not self.watermark_failed
                and self.watermark_anomalies == 0
                and self.symbols_failed == 0
                and self.db_error == 0
                and self.retry_exhausted == 0)

    def finalize_coverage(self) -> None:
        """Record what the run never reached. Safe to call more than once.

        Without this, a budget-truncated run is indistinguishable from a
        complete one: `symbols_skipped` deliberately means "reached, nothing
        new", so an unreached symbol would appear nowhere at all.
        """
        self.symbols_unattempted = max(0, self.symbols_selected - self.symbols_attempted)

    def as_dict(self) -> Dict[str, object]:
        """JSON-safe, bounded, stable-keyed witness.

        The scheduler's status surface does `result if isinstance(result, dict)
        else str(result)`, so a dataclass would be stored as a repr that nothing
        downstream can parse. Returning a real dict keeps the witness
        structured. Everything here is a primitive: no exception objects, no
        DataFrames, no raw exchange payloads, and both variable-length fields
        are capped at their source.
        """
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["failures"] = list(self.failures)          # already capped on append
        d["invalid_reasons"] = dict(self.invalid_reasons)
        d["healthy"] = self.healthy
        return d

    def note_failure(self, msg: str) -> None:
        """Record a failure string under a hard cap.

        A single watermark-read failure can stringify a 2000-parameter statement
        into ~28 KB. Unbounded, one bad cadence would put megabytes into an
        in-memory list that only exists to be read by an operator.
        """
        if len(self.failures) < MAX_FAILURES_RETAINED:
            self.failures.append(msg[:500])
        else:
            self.failures_dropped += 1

    def absorb(self, r: WriteResult) -> None:
        """Fold one (symbol, timeframe) WriteResult into the aggregate.

        ATTEMPT accounting only. `bars_persisted` is added separately by the
        caller once the commit has succeeded.
        """
        self.fetch_attempts += r.fetch_attempts
        self.fetch_success += r.fetch_success
        self.fetch_timeout += r.fetch_timeout
        self.fetch_error += r.fetch_error
        self.retry_recovered += r.retry_recovered
        self.retry_exhausted += r.retry_exhausted
        self.malformed_response += r.malformed_response
        self.fetch_rate_limited += r.fetch_rate_limited
        self.fetch_ip_banned += r.fetch_ip_banned
        self.bars_below_watermark += r.below_watermark
        self.watermark_anomalies += r.watermark_in_future
        self.bars_bootstrap_trimmed += r.bootstrap_trimmed
        self.bars_fetched += r.fetched
        self.bars_eligible += r.eligible
        # NOTE: bars_persisted is folded by the CALLER, only after the commit
        # that made those rows durable actually succeeded. absorb() deliberately
        # does not touch it — see _absorb_attempt/_absorb_committed at the call
        # site. Counting it here would report rows a failed commit discarded.
        self.bars_duplicate += r.duplicate
        self.bars_invalid += r.invalid
        self.bars_forming_or_not_closed += r.forming_or_not_closed
        self.db_rejected += r.db_rejected
        self.db_error += r.db_error
        for reason, n in r.invalid_reasons.items():
            if reason in self.invalid_reasons or len(self.invalid_reasons) < MAX_INVALID_REASONS:
                self.invalid_reasons[reason] = self.invalid_reasons.get(reason, 0) + n


async def load_universe(db, *, cap: int = UNIVERSE_CAP) -> Tuple[List[str], int, bool]:
    """The OHLCV storage universe: active crypto assets, ordered, capped.

    Returns (symbols, eligible_count, overflow).

    ORDER BY symbol, not id: `Asset.symbol` is `unique=True` so the ordering is
    TOTAL and stable across runs, whereas `Asset.id` is a random UUID whose order
    is arbitrary and tells you nothing. A deterministic order is what makes "the
    first N" a reproducible statement instead of a plan-order accident.

    The count is taken BEFORE the cap so overflow is detectable. Reading a fresh
    result on every call is what lets an asset be added or deactivated without a
    backend restart.
    """
    if cap < 1:
        raise ValueError(f"universe cap must be >= 1, got {cap}")

    stmt = (select(Asset.symbol)
            .where(Asset.is_active.is_(True))
            .where(Asset.asset_type == AssetType.CRYPTO)
            .order_by(Asset.symbol))
    rows = (await db.execute(stmt)).scalars().all()

    eligible = len(rows)
    overflow = eligible > cap
    return list(rows[:cap]), eligible, overflow


@dataclass(frozen=True)
class WatermarkSnapshot:
    """The newest persisted open_time per (symbol, timeframe), for ONE source.

    `source` is carried explicitly and checked on every lookup. The watermark
    for binance says nothing about any other provider's coverage, and a snapshot
    silently reused across sources would suppress a second source's bars
    entirely — a silent data loss that would look exactly like "nothing new".
    """

    source: str
    marks: Dict[Tuple[str, str], object]
    series_known: int

    def get(self, source: str, symbol: str, timeframe: str):
        if source != self.source:
            raise ValueError(
                f"watermark snapshot is for source {self.source!r}, "
                f"asked for {source!r}")
        return self.marks.get((symbol, timeframe))


async def load_watermarks(db, symbols: Sequence[str],
                          timeframes: Sequence[str], *,
                          source: str = SOURCE_BINANCE,
                          chunk: int = WATERMARK_CHUNK) -> WatermarkSnapshot:
    """ONE bounded query for the whole run — not one round trip per series.

    THE QUERY is a loose index scan, NOT the obvious aggregate:

        SELECT p.symbol, p.timeframe, m.open_time
        FROM (VALUES (sym, tf), ...) AS p(symbol, timeframe)
        CROSS JOIN LATERAL (
            SELECT open_time FROM ohlcv_bars b
            WHERE b.source = :source AND b.symbol = p.symbol
              AND b.timeframe = p.timeframe
            ORDER BY b.open_time DESC LIMIT 1) m

    WHY NOT `GROUP BY symbol, timeframe` + MAX(open_time). It was written that
    way first and MEASURED against an isolated PostgreSQL 17 loaded from this
    same ORM metadata. The planner refuses the index for it and takes a parallel
    sequential scan, because the WHERE clause selects essentially the entire
    table — every stored row is this source, one of these symbols and one of
    these timeframes, so there is nothing for an index to narrow:

        601 k rows   Parallel Seq Scan, 77 MB   196-235 ms
        2.63 M rows  Parallel Seq Scan          858-1287 ms

    That is a full table scan every 15 minutes, growing without bound.

    The LATERAL form asks 228 separate "newest one, please" questions, each an
    index descent, and PostgreSQL answers all of them in a single round trip:

        601 k rows   Index Only Scan Backward, Heap Fetches 0    9.97 ms
        2.63 M rows  Index Only Scan Backward, Heap Fetches 0    8.9-10.0 ms

    Flat against a 4.4x growth in rows: O(series x log n), not O(n). 20x to 100x
    cheaper, and the gap widens as the store fills.

    NO INDEX IS ADDED BY THIS CHECKPOINT. The scan uses `uq_ohlcv_bars_natural`
    (source, symbol, timeframe, open_time), which already exists in production
    — the descent keys on the leading three columns and reads the fourth
    backwards. The index is what made the whole design possible; it did not have
    to be created for it.

    ABSENCE IS NOT ZERO. A series with no rows simply produces no row here — an
    inner LATERAL join drops it. It maps to None, meaning "never written", which
    the caller turns into a bounded bootstrap, never into "start from the epoch".
    """
    marks: Dict[Tuple[str, str], object] = {}
    if not symbols or not timeframes:
        return WatermarkSnapshot(source=source, marks=marks, series_known=0)
    if chunk < 1:
        raise ValueError(f"chunk must be >= 1, got {chunk}")

    tfs = list(timeframes)
    syms = list(symbols)
    for i in range(0, len(syms), chunk):
        pairs = values(column("symbol", String), column("timeframe", String),
                       name="wm_pairs").data(
            [(s, t) for s in syms[i:i + chunk] for t in tfs])
        newest_q = (select(OhlcvBar.open_time)
                    .where(OhlcvBar.source == source,
                           OhlcvBar.symbol == pairs.c.symbol,
                           OhlcvBar.timeframe == pairs.c.timeframe)
                    .order_by(OhlcvBar.open_time.desc())
                    .limit(1)
                    .lateral("wm_newest"))
        stmt = (select(pairs.c.symbol, pairs.c.timeframe, newest_q.c.open_time)
                .select_from(pairs)
                .join(newest_q, true()))
        for sym, tf, newest_time in (await db.execute(stmt)).all():
            if newest_time is None:
                continue
            if getattr(newest_time, "tzinfo", None) is None:
                # Defensive: the column is timestamptz, so this should not
                # happen. If a driver ever hands back a naive value, comparing
                # it against a tz-aware candidate raises TypeError mid-run.
                newest_time = newest_time.replace(tzinfo=timezone.utc)
            marks[(sym, tf)] = newest_time

    return WatermarkSnapshot(source=source, marks=marks, series_known=len(marks))


def rotation_offset(count: int, run_seq: int) -> int:
    """Starting index for THIS executed run. No clock, by construction.

    WHY NOT A CADENCE BUCKET. Every previous version derived this offset from
    absolute time, and three reviews proved that family cannot carry a fairness
    proof: the offsets a `bucket % count` scheme can ever produce collapse to the
    coset generated by gcd(execution_stride, count) — at count = 56 with an
    every-fourth-cadence execution pattern, 42 of 56 symbols were measured as never
    reached. Projecting through a prime moved the hole to a single stride, and
    moving the prime moved it again (identical failure at 251, 257, 509, 65537).
    The environment chooses which buckets execute, and production enforces nothing
    about that choice — no persistent jobstore, no minimum-uptime invariant.

    So the offset counts the collector's OWN executions instead. `run_seq` comes
    from `acquire_run_sequence`, which advances by exactly one per executed run and
    is durable across restart, redeploy and arbitrary downtime.

    THE BOUND. run_seq advances by exactly 1 per executed run, so over any `count`
    consecutive executed runs `run_seq % count` takes every value in 0..count-1.
    Every symbol is therefore FIRST at least once within `count` executed runs —
    for EVERY wall-clock execution pattern, because the wall clock no longer
    appears in this function. There is no excluded stride, because there is no
    stride: a bucket that is never executed never advances the sequence.

    This is ATTEMPT fairness. It is not a claim that any run completes the
    universe, nor that any bar is persisted.
    """
    if count <= 0:
        return 0
    if run_seq < 0:
        raise ValueError(f"run_seq must be >= 0, got {run_seq}")
    return run_seq % count


async def collect_once(
    session_factory,
    collector,
    *,
    symbols: Optional[Sequence[str]] = None,
    timeframes: Sequence[str] = STORAGE_TIMEFRAMES,
    cap: int = UNIVERSE_CAP,
    limit: int = DEFAULT_FETCH_LIMIT,
    timeout: float = DEFAULT_FETCH_TIMEOUT,
    retries: int = DEFAULT_FETCH_RETRIES,
    source: str = SOURCE_BINANCE,
    bootstrap: int = BOOTSTRAP_MAX_BARS,
    spacing: float = REQUEST_SPACING_SECONDS,
    item_budget: float = ITEM_BUDGET_SECONDS,
    item_budget_degraded: float = DEGRADED_ITEM_BUDGET_SECONDS,
    cadence_seconds: float = DEFAULT_CADENCE_SECONDS,
    now: Optional[datetime] = None,
    run_seq: int = 0,
    result: Optional["CollectionResult"] = None,
) -> CollectionResult:
    """One serial pass over the storage universe. DORMANT — nothing calls this.

    `session_factory` rather than a session: each (symbol, timeframe) gets its
    own short-lived session that is opened around the writer call and committed
    immediately, so no transaction spans two items and none is held across the
    network. The writer itself never commits — that is the caller's job, and this
    is the caller.

    A failure on one item is recorded and the loop moves on. One unreachable
    symbol must not cost the other fifty-six.
    """
    if limit < MIN_FETCH_LIMIT:
        # With limit=1 the sole returned bar is also the newest, the writer
        # withholds it as possibly-forming, and the run persists nothing —
        # forever, silently. Refuse rather than run a guaranteed no-op.
        raise ValueError(f"limit must be >= {MIN_FETCH_LIMIT}, got {limit}")
    if bootstrap < 1:
        # A zero bootstrap would leave every never-written series permanently
        # empty: no rows means no watermark, no watermark means bootstrap, and
        # a bootstrap of 0 offers nothing. The series could never start.
        raise ValueError(f"bootstrap must be >= 1, got {bootstrap}")
    if spacing < 0:
        raise ValueError(f"spacing must be >= 0, got {spacing}")
    if item_budget <= 0:
        raise ValueError(f"item_budget must be > 0, got {item_budget}")
    if item_budget_degraded <= 0:
        # A zero or negative degraded budget would time out every sibling of a
        # failed timeframe instantly — coverage in name only, which is exactly
        # the starvation this design removed.
        raise ValueError(
            f"item_budget_degraded must be > 0, got {item_budget_degraded}")
    if not isinstance(source, str) or not source.strip():
        # An empty source would key the watermark under one name and, once
        # forwarded, stamp rows with the same empty name — a namespace that no
        # reader could ever ask for.
        raise ValueError(f"source must be a non-empty string, got {source!r}")

    tfs = [normalise_timeframe(t) for t in timeframes]   # raises on unknown
    if not tfs:
        raise ValueError("at least one timeframe is required")

    # CANCELLATION-SAFE OWNERSHIP. When the caller supplies `result`, it holds a
    # reference to the very object this run mutates. An outer deadline cancels
    # the task and CancelledError — a BaseException — unwinds past every
    # `except Exception`, so nothing can be RETURNED. The caller reading its own
    # object is the only mechanism that survives that, which is why ownership is
    # inverted rather than the exception being caught.
    res = result if result is not None else CollectionResult(universe_cap=cap)
    res.universe_cap = cap

    # UNIVERSE READ — its own session, closed before any network call.
    if symbols is None:
        async with session_factory() as db:
            selected, eligible, overflow = await load_universe(db, cap=cap)
        res.symbols_discovered = eligible
        res.universe_overflow = overflow
        if overflow:
            # Explicit and loud. The run continues over the capped slice so the
            # operator still gets data, but `healthy` is False and the numbers
            # say exactly how much of the universe was left out.
            log.error("OHLCV universe overflow: %d eligible > cap %d; %d symbols "
                      "not collected this run", eligible, cap, eligible - cap)
    else:
        selected = [s for s in symbols]
        res.symbols_discovered = len(selected)
    res.symbols_selected = len(selected)

    # FAIRNESS ROTATION. Applied after selection so the cap and the overflow
    # signal still describe the whole universe, and before any network call.
    #
    # THE PROGRESSION IS CLAIMED HERE — before the first item, in its own
    # committed transaction. It is durable the moment this returns, so a run that
    # dies one line later has still consumed its sequence value and the NEXT run
    # starts somewhere else. Advancing at the end instead would let a run that
    # always dies early replay the same prefix of the universe forever.
    #
    # A failure to claim is NOT swallowed: without a durable sequence there is no
    # fairness progression to speak of, so the run does not start.
    res.run_seq = run_seq
    off = rotation_offset(len(selected), run_seq)
    res.rotation_offset = off
    selected = list(selected[off:]) + list(selected[:off])

    # WATERMARK READ — one query, in its own session, closed before any network
    # call, exactly like the universe read above.
    #
    # A FAILURE HERE DEGRADES, IT DOES NOT ABORT. The watermark is an
    # optimisation, so losing it must not cost a whole cadence of data: the run
    # continues with an empty snapshot, which means every series takes the
    # BOOTSTRAP path and is therefore still bounded (228 x 4 bars, not 228 x
    # 499). The redundant offers are harmless because the insert is
    # ON CONFLICT DO NOTHING. What must not happen is this passing quietly, so
    # the run is marked unhealthy and the reason is recorded.
    try:
        async with session_factory() as db:
            snapshot = await load_watermarks(
                db, [normalise_symbol(s) for s in selected], tfs, source=source)
            await db.rollback()   # read-only; never leave a tx idle-in-transaction
    except Exception as exc:      # noqa: BLE001
        snapshot = WatermarkSnapshot(source=source, marks={}, series_known=0)
        res.watermark_failed = True
        res.note_failure(f"watermark read failed: {type(exc).__name__}: {exc}")
        log.error("OHLCV watermark read failed; degrading to bounded bootstrap "
                  "for all %d symbols", len(selected), exc_info=True)
    res.watermark_series_known = snapshot.series_known

    first_request = True
    for symbol in selected:
        if res.aborted:
            # A run-level abort (HTTP 418) stops the sweep. Symbols not reached
            # are simply not attempted — they are NOT counted as failures,
            # because nothing was tried on their behalf.
            break
        res.symbols_attempted += 1
        sym = normalise_symbol(symbol)
        symbol_ok = True
        symbol_anomaly = False
        symbol_new_bars = 0
        symbol_degraded = False
        # NO TIMEFRAME ROTATION, BY DESIGN. Every timeframe of a reached symbol
        # is attempted, so the ORDER cannot decide REACHABILITY and there is
        # nothing for a rotation to make fair. What degrades after a terminal
        # failure is the BUDGET, immediately below — not the coverage.
        for tf in tfs:
            if res.aborted:
                break
            # BOUNDED BLAST RADIUS WITHOUT STARVATION. This symbol already burned
            # a full item budget on a terminal failure, and its other timeframes
            # hit the same venue. They are still ATTEMPTED — a healthy sibling
            # needs ~1.7 s p95 and completes easily — but a sick one is now
            # capped at DEGRADED_ITEM_BUDGET_SECONDS instead of the full slice.
            # Worst pathological symbol: 25 + 3 x 5 = 40 s, against 100 s if the
            # cap were removed entirely.
            slice_budget = item_budget
            if symbol_degraded:
                res.timeframes_degraded_after_failure += 1
                slice_budget = min(item_budget_degraded, item_budget)
            res.timeframes_attempted += 1
            mark = snapshot.get(source, sym, tf)
            if mark is None:
                res.series_bootstrapped += 1
            try:
                # Spread requests over the run instead of hammering the exchange
                # as fast as the event loop allows. Skipped before the very
                # first request so the run does not open with a dead wait.
                if not first_request and spacing > 0:
                    await asyncio.sleep(spacing)
                first_request = False

                # PER-ITEM HARD BOUND. `asyncio.wait_for` converts an inner
                # overrun into TimeoutError and cancels the inner coroutine, so
                # a stalled item cannot outlive its slice. An OUTER cancellation
                # still propagates as CancelledError and is handled below — the
                # outer job deadline always wins over this one.
                # THE REQUEST SHAPE DEPENDS ON WHICH PATH THIS ITEM IS ON.
                # A bootstrap item throws away everything but the newest
                # `bootstrap` bars, so asking for the full catch-up window is
                # pure waste — measured in the first production run: 24500 bars
                # fetched, 24255 trimmed, 196 kept. An INCREMENTAL item still
                # gets `limit`, because that window is what lets a series catch
                # up after downtime (500 x 15m is ~5.2 days).
                r = await asyncio.wait_for(
                    _collect_item(session_factory, collector, symbol, tf,
                                  limit=(bootstrap_fetch_limit(bootstrap)
                                         if mark is None else limit),
                                  timeout=timeout, retries=retries,
                                  after=mark,
                                  max_bars=None if mark is not None else bootstrap,
                                  source=source, result=res),
                    timeout=slice_budget)

                symbol_new_bars += r.persisted + r.duplicate + r.db_rejected
                if r.abort_run:
                    # The exchange banned this IP. Every further request would
                    # extend the ban, so the run stops here rather than issuing
                    # the remaining ~200. Rows already committed stay committed.
                    res.aborted = True
                    res.abort_reason = r.abort_reason or "abort_requested"
                    res.note_failure(f"{symbol}/{tf}: RUN ABORTED: {r.error}")
                    log.error("OHLCV run aborted at %s/%s: %s", symbol, tf, r.error)
                elif r.watermark_in_future:
                    # NOT a failure — the fetch and the database both worked.
                    # It is a data-integrity anomaly, reported under its own
                    # name so it can never be read as a transient outage, and
                    # never silently absorbed into `symbols_skipped`.
                    symbol_anomaly = True
                    res.note_failure(f"{symbol}/{tf}: WATERMARK ANOMALY: {r.error}")
                    log.error("OHLCV watermark anomaly for %s/%s: %s", symbol, tf, r.error)
                elif r.retry_exhausted or r.db_error:
                    symbol_ok = False
                    symbol_degraded = True  # the venue is unhealthy for this symbol
                    res.note_failure(f"{symbol}/{tf}: {r.error or 'fetch failed'}")
            except asyncio.CancelledError:
                # THE OUTER JOB DEADLINE. Never swallowed and never relabelled:
                # the run is marked cancelled so the partial result the caller
                # already owns tells the truth, and the cancellation continues
                # to propagate so job_guard still sees a cancelled task.
                res.cancelled = True
                res.note_failure(f"{symbol}/{tf}: run cancelled at outer deadline")
                # Record coverage BEFORE unwinding: a cancelled run is exactly
                # the case where "which symbols were never reached" matters.
                res.finalize_coverage()
                raise
            except (asyncio.TimeoutError, TimeoutError):
                # This item burned its whole slice. Blast radius is one item.
                res.items_deadline_exceeded += 1
                symbol_ok = False
                symbol_degraded = True
                res.note_failure(
                    f"{symbol}/{tf}: item deadline exceeded after {slice_budget}s")
                log.warning("OHLCV item deadline exceeded for %s/%s", symbol, tf)
            except Exception as exc:      # noqa: BLE001 — isolation is the point
                symbol_ok = False
                symbol_degraded = True
                res.db_error += 1
                res.note_failure(f"{symbol}/{tf}: {type(exc).__name__}: {exc}")
                log.warning("OHLCV collect failed for %s/%s: %s",
                            symbol, tf, type(exc).__name__)
        if symbol_ok:
            res.symbols_succeeded += 1
            # SKIPPED means "nothing new was there", NOT "something went wrong".
            # Only a symbol whose every timeframe completed successfully and
            # yielded zero NEW bars counts. A fetch failure, a DB failure, a
            # malformed response, an item deadline or a capped universe can
            # never land here — those are failures and are counted as failures.
            # Note that skipped is a SUBSET of succeeded, deliberately: such a
            # symbol did succeed. `succeeded + failed == attempted` is the
            # partition.
            if symbol_new_bars == 0 and not symbol_anomaly:
                res.symbols_skipped += 1
        else:
            res.symbols_failed += 1
            if symbol_degraded:
                res.symbols_degraded += 1

    res.finalize_coverage()
    return res


async def _collect_item(session_factory, collector, symbol, tf, *, limit, timeout,
                        retries, after, max_bars, source, result):
    """One (symbol, timeframe) item: fetch, filter, persist, commit.

    ACCOUNTING ORDER IS THE POINT. `absorb` folds the ATTEMPT counters as soon
    as the writer returns, so a later commit failure can never erase the fact
    that the work was attempted. `bars_persisted` is folded ONLY after the
    commit that made those rows durable succeeded; if the commit raises, the
    same rows are recorded as `bars_staged_rolled_back` instead. A committed
    count is therefore never inflated by work the database discarded.

    A FRESH session per item, created here but first touched by the writer only
    after the fetch returns, so no connection is held across the network call.
    """
    async with session_factory() as db:
        r = await collect_and_persist(
            db, collector, symbol, tf,
            limit=limit, end_time_ms=None,      # LIVE window only
            timeout=timeout, retries=retries,
            after=after,                        # STRICTLY GREATER
            max_bars=max_bars,
            source=source)                      # read source == write source
        result.absorb(r)                        # attempt accounting, commit-independent
        try:
            await db.commit()
        except Exception:
            result.bars_staged_rolled_back += r.persisted
            raise
        result.bars_persisted += r.persisted    # durable: only now
    return r


async def run_collection_once(session_factory, **kwargs) -> CollectionResult:
    """Own a collector AND the result for exactly one run. STILL DORMANT.

    Nothing calls this. It exists because two ownership properties have to live
    somewhere, and leaving either to a future caller is how they get lost.

    COLLECTOR OWNERSHIP. `BinanceCollector.__init__` builds an
    `httpx.AsyncClient` and only `close()` releases it. Constructed inside the
    function — never at module level, so importing opens no socket — and closed
    in a `finally` that also runs on cancellation.

    RESULT OWNERSHIP. The result is created HERE and passed down, so it survives
    an outer-deadline cancellation. `job_guard.run_with_deadline` cancels the
    task; `CancelledError` derives from BaseException and unwinds past every
    `except Exception`, so a result that `collect_once` merely RETURNS is lost
    the moment the deadline fires — while the rows committed before it are
    still committed. Owning the object up here is what keeps those rows
    accounted for. The cancellation itself is re-raised untouched: job_guard
    must still see a cancelled task, and a deadline must never read as success.

    THE SHARED COLLECTOR IS USED AS-IS. An earlier draft widened it to carry
    quote_volume / trade_count / taker_buy_*, which the OHLCV schema has
    nullable columns for. That was reverted: the four fields are nullable, carry
    no CHECK constraint and are not validated, so they are not part of the first
    activation contract — and Pass-B's T14 guard exists precisely to keep the
    collector shared with the live scheduler out of a shadow store's reach.
    Those columns simply stay NULL until a checkpoint that actually needs them
    argues for the change on its own merits.
    """
    res = CollectionResult()
    res.run_id = uuid.uuid4().hex[:16]
    # DURABLE PROGRESSION IS CLAIMED HERE — the run boundary, before the collector
    # is even constructed and therefore before any item. It commits in its own
    # transaction, so a run that dies immediately afterwards has still consumed
    # its sequence and the NEXT run starts elsewhere. Failure is not swallowed:
    # without a durable sequence there is no fairness progression, so no run.
    if "run_seq" not in kwargs:
        kwargs["run_seq"] = await acquire_run_sequence(
            session_factory, kwargs.get("source", SOURCE_BINANCE))
    res.started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    collector = BinanceCollector()
    try:
        return await collect_once(session_factory, collector, result=res, **kwargs)
    except asyncio.CancelledError:
        res.cancelled = True
        raise
    finally:
        res.completed_at = datetime.now(timezone.utc).isoformat()
        res.duration_seconds = round(time.monotonic() - started, 3)
        # One structured line is the whole witness. Emitted from `finally` so a
        # cancelled or aborted run reports exactly like a completed one.
        log.info("OHLCV collection run: %s", res.as_dict())
        try:
            await collector.close()
        except Exception:      # noqa: BLE001
            # A failure to close must not mask the real outcome — neither the
            # result nor the original exception.
            log.warning("OHLCV collector close failed", exc_info=True)
