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
from dataclasses import dataclass, field
from datetime import timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import String, column, select, true, values

from app.collectors.binance_collector import BinanceCollector
from app.models.asset import Asset, AssetType
from app.models.ohlcv_bar import OhlcvBar
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
    watermark_failed: bool = False     # the read failed; run degraded to bootstrap
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
        was designed to avoid. `watermark_failed` likewise: that run still
        collected, but it did so on the degraded bootstrap path, and a run that
        reports full health while re-offering seeds every cadence would hide a
        persistent database problem behind a working-looking result.
        """
        return (not self.universe_overflow
                and not self.watermark_failed
                and self.symbols_failed == 0
                and self.db_error == 0
                and self.retry_exhausted == 0)

    def absorb(self, r: WriteResult) -> None:
        """Fold one (symbol, timeframe) WriteResult into the aggregate."""
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
        self.bars_bootstrap_trimmed += r.bootstrap_trimmed
        self.bars_fetched += r.fetched
        self.bars_eligible += r.eligible
        self.bars_persisted += r.persisted
        self.bars_duplicate += r.duplicate
        self.bars_invalid += r.invalid
        self.bars_forming_or_not_closed += r.forming_or_not_closed
        self.db_rejected += r.db_rejected
        self.db_error += r.db_error
        for reason, n in r.invalid_reasons.items():
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

    tfs = [normalise_timeframe(t) for t in timeframes]   # raises on unknown
    if not tfs:
        raise ValueError("at least one timeframe is required")

    res = CollectionResult(universe_cap=cap)

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
        res.failures.append(f"watermark read failed: {type(exc).__name__}: {exc}")
        log.error("OHLCV watermark read failed; degrading to bounded bootstrap "
                  "for all %d symbols", len(selected), exc_info=True)
    res.watermark_series_known = snapshot.series_known

    first_request = True
    for symbol in selected:
        res.symbols_attempted += 1
        sym = normalise_symbol(symbol)
        symbol_ok = True
        symbol_new_bars = 0
        for tf in tfs:
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

                # A FRESH session per item. Created here, but the writer touches
                # it only after the fetch returns, so no connection is checked
                # out while the network call is in flight.
                async with session_factory() as db:
                    r = await collect_and_persist(
                        db, collector, symbol, tf,
                        limit=limit, end_time_ms=None,      # LIVE window only
                        timeout=timeout, retries=retries,
                        after=mark,                          # STRICTLY GREATER
                        max_bars=None if mark is not None else bootstrap)
                    await db.commit()
                res.absorb(r)
                symbol_new_bars += r.persisted + r.duplicate + r.db_rejected
                if r.retry_exhausted or r.db_error:
                    symbol_ok = False
                    res.failures.append(f"{symbol}/{tf}: {r.error or 'fetch failed'}")
            except Exception as exc:      # noqa: BLE001 — isolation is the point
                symbol_ok = False
                res.db_error += 1
                res.failures.append(f"{symbol}/{tf}: {type(exc).__name__}: {exc}")
                log.warning("OHLCV collect failed for %s/%s: %s",
                            symbol, tf, type(exc).__name__)
        if symbol_ok:
            res.symbols_succeeded += 1
            # SKIPPED means "nothing new was there", NOT "something went wrong".
            # Only a symbol whose every timeframe completed successfully and
            # yielded zero NEW bars counts. A fetch failure, a DB failure, a
            # malformed response or a capped universe can never land here —
            # those are failures and are counted as failures. Note that skipped
            # is a SUBSET of succeeded, deliberately: such a symbol did succeed.
            # `succeeded + failed == attempted` remains the partition.
            if symbol_new_bars == 0:
                res.symbols_skipped += 1
        else:
            res.symbols_failed += 1

    return res


async def run_collection_once(session_factory, **kwargs) -> CollectionResult:
    """Own a collector for exactly one run, then close it. STILL DORMANT.

    Nothing calls this. It exists because collector OWNERSHIP is a correctness
    property that has to live somewhere, and leaving it to a future caller is
    how an `httpx.AsyncClient` per run gets leaked: `BinanceCollector.__init__`
    constructs one and only `close()` releases it.

    Constructed inside the function, never at module level — importing this
    module must not open a socket, and a module-level client would.

    `finally`, not a trailing call: `collect_once` is long, serial and network
    bound, so the realistic exits are a cancellation at the job budget deadline
    or an unexpected raise. Both must still close the client.
    """
    collector = BinanceCollector()
    try:
        return await collect_once(session_factory, collector, **kwargs)
    finally:
        try:
            await collector.close()
        except Exception:      # noqa: BLE001
            # A failure to close must not mask the real outcome — neither the
            # result nor the original exception.
            log.warning("OHLCV collector close failed", exc_info=True)
