"""CP-OHLCV-A2 — the closed-bar writer primitive. DORMANT: nothing calls it.

Importing this module starts nothing. There is no scheduler job, no startup
hook, no flag that switches it on, and no module-level work beyond defining
constants. Wiring is A3's decision, not this file's.

WHY THIS IS A REWRITE AND NOT THE POC
-------------------------------------
The proof-of-concept persisted a page with ONE multi-row INSERT inside ONE
savepoint. Measured against the exact production DDL, a single malformed bar in
a page of seven then cost SIX valid bars and left the caller's transaction in
`InFailedSQLTransactionError` — every later statement rejected. The same matrix
run with one savepoint per row kept all six and left the session usable. That
measurement, not taste, is why persistence here is per row.

THE TWO INVARIANTS THAT MATTER
------------------------------
1. CLOSURE. `is_closed=True` in a payload proves nothing — the POC hardcoded it,
   which makes the schema's `CHECK (is_closed)` unreachable for writer rows. Real
   closure is decided here, from the exchange's own close_time, AND by never
   admitting the newest bar of a response. See `eligible_bars`.

2. FAILURE ISOLATION. One bad external candle must never cost a good one, and
   must never poison a transaction this module does not own.

TRANSACTION OWNERSHIP: the caller opens and closes the transaction. This module
issues no commit and no rollback of the outer transaction — only SAVEPOINT
rollbacks it created itself. `collect_and_persist` finishes ALL network work
before it touches the session, because production runs with
`idle_in_transaction_session_timeout = 180000` and a transaction held open
across a fetch is how that gets tripped.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ohlcv_bar import OhlcvBar
from app.services.candle_window import (CLOSE_TIME_COLUMN, TIMEFRAME_DURATIONS,
                                        timeframe_duration)

SOURCE_BINANCE = "binance"

# THE CONFLICT TARGET. Column list, never the constraint name: production
# materialised the natural key as a UNIQUE CONSTRAINT (the ORM path), while a
# migration-only database materialises it as a bare UNIQUE INDEX of the same
# name. `ON CONFLICT ON CONSTRAINT` works on the first and raises
# UndefinedObject on the second — measured both ways. The column list is the
# only construction-order-independent form.
CONFLICT_TARGET: Tuple[str, ...] = ("source", "symbol", "timeframe", "open_time")

# Bounded fetch. httpx bounds each I/O operation but has no total-request
# ceiling, so the wall-clock bound is applied here at the call site rather than
# inside BinanceCollector, which the live scheduler shares and whose semantics
# must not shift for a persistence concern.
DEFAULT_FETCH_TIMEOUT = 20.0
DEFAULT_FETCH_RETRIES = 2

# CLOCK SKEW. Deliberately ZERO, because the margin is not what makes this safe.
#
# `close_time <= now` alone is only as trustworthy as our clock: a server running
# ahead of the exchange would see a still-forming bar as closed, and no margin
# value is derivable from the code — any number would be invented.
#
# The structural rule is what removes the doubt. Binance returns klines in
# ascending open_time and the forming bar, when present, is ALWAYS the last
# element. Dropping the newest element of every response therefore excludes the
# forming bar without reference to any clock at all. The cost is one bar of
# latency: a bar becomes eligible on the next fetch instead of this one, and
# since the natural key makes re-persistence a no-op, nothing is lost.
#
# The margin stays as an operator dial for a knowingly bad clock. It is not
# needed for correctness and defaults to nothing.
DEFAULT_CLOSED_MARGIN = timedelta(0)


# ── result taxonomy ──────────────────────────────────────────────────────────
@dataclass
class WriteResult:
    """Deterministic counters. A duplicate is not an insert, a timeout is not a
    generic error, and an invalid external candle is not a database outage."""

    fetched: int = 0
    eligible: int = 0
    persisted: int = 0
    duplicate: int = 0
    invalid: int = 0
    forming_or_not_closed: int = 0
    fetch_success: int = 0
    fetch_timeout: int = 0
    fetch_error: int = 0
    retry_recovered: int = 0
    retry_exhausted: int = 0
    db_rejected: int = 0
    db_error: int = 0
    malformed_response: int = 0
    fetch_attempts: int = 0
    invalid_reasons: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None

    def note_invalid(self, reason: str) -> None:
        self.invalid += 1
        self.invalid_reasons[reason] = self.invalid_reasons.get(reason, 0) + 1


@dataclass(frozen=True)
class BarCandidate:
    """A normalised, validated, provably-closed bar. Only these reach the DB."""

    source: str
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None
    trade_count: Optional[int] = None
    taker_buy_base_volume: Optional[float] = None
    taker_buy_quote_volume: Optional[float] = None

    def as_row(self) -> Dict[str, Any]:
        d = {
            "source": self.source, "symbol": self.symbol, "timeframe": self.timeframe,
            "open_time": self.open_time, "close_time": self.close_time,
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
            "quote_volume": self.quote_volume, "trade_count": self.trade_count,
            "taker_buy_base_volume": self.taker_buy_base_volume,
            "taker_buy_quote_volume": self.taker_buy_quote_volume,
            # Set HERE, and only for a bar this module has already proven closed
            # by close_time AND by not being the newest of its response. The
            # column records that proof; it is never the source of it.
            "is_closed": True,
        }
        return d


# ── normalisation ────────────────────────────────────────────────────────────
def normalise_symbol(symbol: str) -> str:
    """`btc/usdt` -> `BTCUSDT`. Matches BinanceCollector.fetch_ohlcv exactly, so
    what we store is keyed the same way as what we asked for."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    return symbol.replace("/", "").strip().upper()


def normalise_timeframe(timeframe: str) -> str:
    """Reject an unknown timeframe LOUDLY rather than guessing a duration.

    BinanceCollector silently maps anything unknown to '1h' (binance_collector
    tf_map .get default), which would store bars under a timeframe the caller
    never asked for. Persistence cannot afford that."""
    if not isinstance(timeframe, str):
        raise ValueError("timeframe must be a string")
    tf = timeframe.strip().lower()
    if tf not in TIMEFRAME_DURATIONS:
        raise ValueError(
            f"unknown timeframe {timeframe!r}; known: {sorted(TIMEFRAME_DURATIONS)}")
    return tf


# ── validation: mirrors every production CHECK, cheaply, before the DB ───────
def validate_bar(c: BarCandidate) -> Optional[str]:
    """None when the bar may be persisted, else a short reason.

    Defense in depth, NOT a replacement: the database stays authoritative and
    its CHECKs are untouched. This exists so an invalid external candle is
    classified as `invalid` by us rather than surfacing as a DB rejection, and
    so the reason is specific enough to act on.
    """
    for name in ("source", "symbol", "timeframe"):
        v = getattr(c, name)
        if not isinstance(v, str) or not v:
            return f"missing_{name}"
    if not isinstance(c.open_time, datetime) or c.open_time.tzinfo is None:
        return "missing_open_time"
    if not isinstance(c.close_time, datetime) or c.close_time.tzinfo is None:
        return "missing_close_time"

    nums = {"open": c.open, "high": c.high, "low": c.low,
            "close": c.close, "volume": c.volume}
    for name, v in nums.items():
        if v is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            return f"non_numeric_{name}"
        if not math.isfinite(float(v)):
            return f"non_finite_{name}"

    # ck_ohlcv_bars_window
    if not c.close_time > c.open_time:
        return "close_time_not_after_open_time"
    # ck_ohlcv_bars_bounds
    if c.low > c.high:
        return "low_above_high"
    if not (c.low <= c.open <= c.high):
        return "open_outside_bounds"
    if not (c.low <= c.close <= c.high):
        return "close_outside_bounds"
    # ck_ohlcv_bars_volume — zero is REAL market data (a quiet minute), not
    # corruption, and the schema permits it. Only negative is rejected.
    if c.volume < 0:
        return "negative_volume"
    return None


# ── closure eligibility ──────────────────────────────────────────────────────
def eligible_bars(
    df: Optional[pd.DataFrame],
    symbol: str,
    timeframe: str,
    *,
    now: Optional[datetime] = None,
    margin: timedelta = DEFAULT_CLOSED_MARGIN,
    source: str = SOURCE_BINANCE,
    drop_newest: bool = True,
) -> Tuple[List[BarCandidate], WriteResult]:
    """Bars that are provably closed, normalised into candidates.

    TWO independent gates, both must pass:

      (1) `close_time <= now - margin`, where close_time is the EXCHANGE's own
          value when the frame carries it and `open_time + duration` otherwise.
          candle_window prefers the exchange value for the same reason: deriving
          assumes a perfectly regular series, which is true for Binance but is
          an assumption rather than a fact.

      (2) the bar is not the NEWEST row of the response. Binance returns klines
          in ascending open_time and the forming bar, when present, is always
          last. This gate needs no clock, so it holds even if ours is wrong.

    Gate (2) is what makes the rule safe; gate (1) is what makes it precise.
    """
    tf = normalise_timeframe(timeframe)          # raises before any other work
    sym = normalise_symbol(symbol)
    res = WriteResult()
    if df is None or len(df) == 0:
        return [], res

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    work = df.copy()
    idx = pd.DatetimeIndex(work.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    work.index = idx
    # Order and de-duplicate BEFORE the cut, so an out-of-order or re-sent frame
    # still yields the right window rather than one decided by arrival order.
    work = work[~work.index.duplicated(keep="last")].sort_index()
    res.fetched = len(work)

    closes = _close_times(work, timeframe=tf)
    threshold = now - margin
    newest_pos = len(work) - 1

    out: List[BarCandidate] = []
    for pos, (open_time, close_time) in enumerate(zip(work.index, closes)):
        if drop_newest and pos == newest_pos:
            res.forming_or_not_closed += 1
            continue
        ct = close_time.to_pydatetime() if hasattr(close_time, "to_pydatetime") else close_time
        if ct is None or pd.isna(close_time):
            res.malformed_response += 1
            continue
        if not ct <= threshold:
            # Strictly `<=`: a bar whose close_time equals the threshold HAS
            # ended (Binance's close_time is the bar's last millisecond), so it
            # is admitted. Documented because the boundary is a real decision.
            res.forming_or_not_closed += 1
            continue

        row = work.iloc[pos]
        try:
            cand = BarCandidate(
                source=source, symbol=sym, timeframe=tf,
                open_time=open_time.to_pydatetime(), close_time=ct,
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row["volume"]),
                quote_volume=_opt_float(row, "quote_asset_volume"),
                trade_count=_opt_int(row, "number_of_trades"),
                taker_buy_base_volume=_opt_float(row, "taker_buy_base_asset_volume"),
                taker_buy_quote_volume=_opt_float(row, "taker_buy_quote_asset_volume"),
            )
        except (KeyError, TypeError, ValueError):
            res.malformed_response += 1
            continue

        reason = validate_bar(cand)
        if reason is not None:
            res.note_invalid(reason)
            continue
        out.append(cand)

    res.eligible = len(out)
    return out, res


def _close_times(df: pd.DataFrame, *, timeframe: str) -> pd.DatetimeIndex:
    """Exchange close_time when present AND complete, derived otherwise."""
    if CLOSE_TIME_COLUMN in df.columns:
        raw = pd.to_datetime(df[CLOSE_TIME_COLUMN], utc=True, errors="coerce")
        ct = pd.DatetimeIndex(raw)
        if not ct.isna().any():
            return ct
    return pd.DatetimeIndex(df.index) + timeframe_duration(timeframe)


def _opt_float(row, key):
    try:
        v = row[key]
    except (KeyError, IndexError):
        return None
    if v is None or pd.isna(v):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _opt_int(row, key):
    v = _opt_float(row, key)
    return None if v is None else int(v)


# ── bounded network phase ────────────────────────────────────────────────────
async def fetch_bars_bounded(
    collector,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 500,
    end_time_ms: Optional[int] = None,
    timeout: float = DEFAULT_FETCH_TIMEOUT,
    retries: int = DEFAULT_FETCH_RETRIES,
    result: Optional[WriteResult] = None,
):
    """One bounded fetch. Returns (df|None, kind).

    kind: "fetch_success" | "fetch_timeout" | "fetch_error"

    `asyncio.wait_for` bounds the WHOLE coroutine — DNS, connect, TLS, a body
    that trickles under httpx's per-read ceiling, and the pandas parse. httpx's
    `timeout=10.0` bounds each I/O operation but has no total-request dimension,
    so without this a stalled fetch has no ceiling at all.
    """
    # RETRY CONTRACT: retries is the number of ADDITIONAL attempts and must be a
    # non-negative integer. A negative value made `range(1, retries + 2)` empty,
    # so the loop never ran and the function fell through to a `last` that was
    # never bound — an UnboundLocalError raised instead of a classified result.
    # Rejected here, loudly and BEFORE any network or database activity, rather
    # than coerced to 0: silently treating -1 as "no retries" would hide a
    # caller bug that the caller should fix.
    if isinstance(retries, bool) or not isinstance(retries, int):
        raise ValueError(f"retries must be an int, got {type(retries).__name__}")
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")

    res = result if result is not None else WriteResult()
    sym, tf = normalise_symbol(symbol), normalise_timeframe(timeframe)
    for attempt in range(1, retries + 2):
        res.fetch_attempts += 1
        try:
            df = await asyncio.wait_for(
                collector.fetch_ohlcv(sym, tf, limit=limit, end_time_ms=end_time_ms),
                timeout=timeout)
            res.fetch_success += 1
            if attempt > 1:
                res.retry_recovered += 1
            return df, "fetch_success"
        except (asyncio.TimeoutError, TimeoutError):
            # Caught BEFORE the generic handler on purpose: a stall that fell
            # through to `except Exception` would be indistinguishable from a
            # 429, and the whole point is that it stays visible.
            res.fetch_timeout += 1
            last = "fetch_timeout"
        except Exception:  # noqa: BLE001
            res.fetch_error += 1
            last = "fetch_error"
    res.retry_exhausted += 1
    return None, last


# ── persistence phase: ONE SAVEPOINT PER ROW ─────────────────────────────────
async def persist_bars(db, candidates: List[BarCandidate], *,
                       result: Optional[WriteResult] = None) -> WriteResult:
    """Persist validated candidates inside the CALLER's transaction.

    One SAVEPOINT per row. That is the whole point: the measured alternative —
    a single multi-row INSERT — loses every valid row in the page to one bad one
    and leaves the session unusable. Here a rejected row rolls back only its own
    savepoint and the next row still persists.

    This function NEVER commits and never rolls back the caller's transaction.
    """
    res = result if result is not None else WriteResult()
    for cand in candidates:
        stmt = (pg_insert(OhlcvBar.__table__)
                .values(**cand.as_row())
                .on_conflict_do_nothing(index_elements=list(CONFLICT_TARGET)))
        try:
            async with db.begin_nested():
                out = await db.execute(stmt)
            written = out.rowcount if out.rowcount is not None and out.rowcount >= 0 else 0
            if written:
                res.persisted += 1
            else:
                # ON CONFLICT DO NOTHING matched an existing row. An explicit
                # no-op, never an error, and never counted as an insert.
                res.duplicate += 1
        except Exception as exc:  # noqa: BLE001
            # A CHECK/NOT NULL violation lands here. The savepoint has already
            # been rolled back by the context manager, so the caller's
            # transaction is intact and the loop continues.
            name = type(exc).__name__
            if "Integrity" in name or "Check" in name or "DataError" in name:
                res.db_rejected += 1
            else:
                res.db_error += 1
                res.error = f"{name}: {exc}"
    return res


# ── orchestrator: network first, then the session ────────────────────────────
async def collect_and_persist(
    db,
    collector,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 500,
    end_time_ms: Optional[int] = None,
    now: Optional[datetime] = None,
    timeout: float = DEFAULT_FETCH_TIMEOUT,
    retries: int = DEFAULT_FETCH_RETRIES,
    margin: timedelta = DEFAULT_CLOSED_MARGIN,
) -> WriteResult:
    """Fetch, decide closure, validate — THEN touch the session.

    The ordering is the contract, not an implementation detail. Production sets
    `idle_in_transaction_session_timeout = 180000`; a transaction held open
    across a network fetch is exactly how a session gets terminated mid-batch.
    Every network and CPU step above completes before the first `db.` call.
    """
    # ONE result object for the whole call. It used to be discarded and replaced
    # on the failure path, which threw away everything `fetch_bars_bounded` had
    # counted — attempts, per-attempt timeouts, per-attempt errors, whether a
    # retry had recovered — and reported a single synthetic flag instead. A
    # caller could then see `fetch_timeout=1` for a run that had actually
    # timed out three times, and `fetch_attempts=0` for a run that made three.
    res = WriteResult()

    df, kind = await fetch_bars_bounded(
        collector, symbol, timeframe, limit=limit, end_time_ms=end_time_ms,
        timeout=timeout, retries=retries, result=res)
    if kind != "fetch_success":
        # `fetch_bars_bounded` has already recorded the real per-attempt counts
        # and set retry_exhausted. Nothing is synthesised here.
        return res

    # eligible_bars builds its own counters; fold them into the shared result so
    # the fetch phase's numbers survive into what the caller sees.
    candidates, elig = eligible_bars(df, symbol, timeframe, now=now, margin=margin)
    res.fetched += elig.fetched
    res.eligible += elig.eligible
    res.forming_or_not_closed += elig.forming_or_not_closed
    res.malformed_response += elig.malformed_response
    res.invalid += elig.invalid
    for reason, n in elig.invalid_reasons.items():
        res.invalid_reasons[reason] = res.invalid_reasons.get(reason, 0) + n

    # FIRST session contact happens only now.
    return await persist_bars(db, candidates, result=res)
