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

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select

from app.models.asset import Asset, AssetType
from app.services.ohlcv_writer import (DEFAULT_FETCH_RETRIES,
                                       DEFAULT_FETCH_TIMEOUT, WriteResult,
                                       collect_and_persist, normalise_timeframe)

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
        was designed to avoid.
        """
        return (not self.universe_overflow
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

    for symbol in selected:
        res.symbols_attempted += 1
        symbol_ok = True
        for tf in tfs:
            res.timeframes_attempted += 1
            try:
                # A FRESH session per item. Created here, but the writer touches
                # it only after the fetch returns, so no connection is checked
                # out while the network call is in flight.
                async with session_factory() as db:
                    r = await collect_and_persist(
                        db, collector, symbol, tf,
                        limit=limit, end_time_ms=None,      # LIVE window only
                        timeout=timeout, retries=retries)
                    await db.commit()
                res.absorb(r)
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
        else:
            res.symbols_failed += 1

    return res
