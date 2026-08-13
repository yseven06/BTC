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

    # HTTP classification. These were previously indistinguishable inside
    # `fetch_error`, which meant a rate limit and a malformed URL produced the
    # same number and the same immediate retry.
    fetch_rate_limited: int = 0      # HTTP 429 — backed off, then retried
    fetch_ip_banned: int = 0         # HTTP 418 — retries ABANDONED, see below

    # WATERMARK ACCOUNTING. Bars the caller's lower bound removed before the
    # session was touched. These are NOT duplicates: a duplicate is a row the
    # database rejected, these never reached it.
    below_watermark: int = 0
    bootstrap_trimmed: int = 0

    # The stored watermark is newer than anything the exchange returned, i.e.
    # the store claims a bar that does not exist. Counted SEPARATELY from a
    # watermark-read failure: that is "we could not read it", this is "we read
    # it and it is impossible". Conflating them would hide a corrupt series
    # behind a transient-database story.
    watermark_in_future: int = 0

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


def _newest_open_time(df) -> Optional[datetime]:
    """The newest open_time the exchange actually returned, normalised to UTC.

    Includes the still-forming candle on purpose: the question this answers is
    "what is the furthest bar the exchange admits exists", which is the widest
    possible upper bound a stored watermark could legitimately hold. Using the
    newest CLOSED bar instead would flag a store that is merely one candle ahead
    of the closure rule, which is not corruption.

    Same tz normalisation as `eligible_bars`, so the two cannot disagree about
    what a timestamp means.
    """
    if df is None or len(df) == 0:
        return None
    try:
        idx = pd.DatetimeIndex(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    except (TypeError, ValueError):
        # A malformed index is eligible_bars' problem to classify, not ours; a
        # sanity check must never be the thing that raises.
        return None
    return max(idx).to_pydatetime()


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
# ── HTTP CLASSIFICATION HELPERS ──────────────────────────────────────────────
# Deliberately duck-typed rather than `except httpx.HTTPStatusError`. The writer
# takes ANY object with `fetch_ohlcv`, so it must not assume the collector is
# built on httpx; a fake, a ccxt client or a future replacement raising its own
# exception type still classifies correctly if it carries a status code.
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 5.0


def _http_status(exc: Exception) -> Optional[int]:
    """Best-effort HTTP status for an arbitrary exception. None if not HTTP."""
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    if code is None:
        code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Honour a Retry-After header, CLAMPED.

    An unclamped Retry-After is a remote party handing us an arbitrary sleep
    inside a budgeted job. Binance may legitimately answer with minutes; obeying
    that literally would blow the job budget, so it is capped and the cap — not
    the exchange — decides the worst case.
    """
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return None
        return max(0.0, min(float(raw), BACKOFF_MAX_SECONDS))
    except (TypeError, ValueError):
        # A date-form Retry-After, or junk. Fall back to the local schedule.
        return None


def _backoff_seconds(attempt: int) -> float:
    """Bounded exponential: 1s, 2s, 4s … capped at BACKOFF_MAX_SECONDS."""
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)


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
            backoff = _backoff_seconds(attempt)
        except Exception as exc:  # noqa: BLE001
            status = _http_status(exc)
            if status == 418:
                # Binance returns 418 when an IP has been BANNED for ignoring
                # 429s. Every further request extends the ban, so retrying is
                # not merely useless, it is the thing that deepens the hole.
                # Abandon the retry budget immediately.
                res.fetch_ip_banned += 1
                res.retry_exhausted += 1
                res.error = "HTTP 418: IP banned by exchange; retries abandoned"
                return None, "fetch_ip_banned"
            if status == 429:
                res.fetch_rate_limited += 1
                last = "fetch_rate_limited"
                backoff = _retry_after_seconds(exc) or _backoff_seconds(attempt)
            else:
                res.fetch_error += 1
                last = "fetch_error"
                backoff = _backoff_seconds(attempt)

        # Wait only if another attempt is actually coming. Sleeping after the
        # final attempt buys nothing and spends job budget.
        if attempt <= retries and backoff > 0:
            await asyncio.sleep(backoff)

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
    after: Optional[datetime] = None,
    max_bars: Optional[int] = None,
    source: str = SOURCE_BINANCE,
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
    #
    # `source` is FORWARDED, never re-derived. It used to be omitted here, so
    # eligible_bars fell back to its SOURCE_BINANCE default: a caller that asked
    # for one provider's watermark got rows stamped with another provider's
    # name, and the run still reported healthy. One item has exactly one
    # authoritative source, and it is the caller's.
    candidates, elig = eligible_bars(df, symbol, timeframe, now=now,
                                     margin=margin, source=source)
    res.fetched += elig.fetched
    res.eligible += elig.eligible
    res.forming_or_not_closed += elig.forming_or_not_closed
    res.malformed_response += elig.malformed_response
    res.invalid += elig.invalid
    for reason, n in elig.invalid_reasons.items():
        res.invalid_reasons[reason] = res.invalid_reasons.get(reason, 0) + n

    # WATERMARK SANITY — the exchange refutes its own watermark.
    #
    # A stored watermark can only ever be a bar the exchange has already
    # published. If it is STRICTLY NEWER than the newest bar in the response we
    # just received, the store is claiming a candle the exchange does not have.
    # That is corruption, not quiet market: without this gate the lower bound
    # silently removes every candidate, the item persists nothing, and the run
    # reports healthy forever while the series is frozen.
    #
    # AUTHORITY: the response itself, NOT the local clock. This is the same
    # authority the closure rule's second gate already uses — "never the newest
    # bar of a response" — chosen there precisely because it needs no trusted
    # clock. NO TOLERANCE IS APPLIED, AND NONE IS NEEDED: both sides of the
    # comparison come from the same fetch, so clock skew cannot manufacture a
    # false positive, and inventing a margin here would be inventing a second
    # clock rule. Equality is deliberately NOT flagged — the newest element of a
    # response is the forming candle, which the closure rule already withholds,
    # so only a strictly greater watermark is provably impossible.
    #
    # This detects; it never repairs. No reset, no rewind, no backfill — those
    # are A4's, and silently "fixing" a watermark would destroy the evidence.
    newest = _newest_open_time(df)
    if after is not None and newest is not None and after > newest:
        res.watermark_in_future += 1
        res.error = (f"watermark {after.isoformat()} is newer than the newest bar "
                     f"{newest.isoformat()} returned by the exchange for "
                     f"{normalise_symbol(symbol)}/{normalise_timeframe(timeframe)}")
        return res              # persist NOTHING; progress must not be faked

    candidates = apply_lower_bound(
        candidates, after=after, max_bars=max_bars, result=res)

    # FIRST session contact happens only now.
    return await persist_bars(db, candidates, result=res)


def apply_lower_bound(
    candidates: List[BarCandidate],
    *,
    after: Optional[datetime],
    max_bars: Optional[int],
    result: WriteResult,
) -> List[BarCandidate]:
    """Drop bars at or below `after`, then cap an unbounded first load.

    THE WRITER NEVER READS A WATERMARK. `after` is supplied by the caller, which
    is what keeps the watermark a caller-owned optimisation instead of a claim
    this module makes about the store. Passing None is always safe and always
    correct — it simply offers everything, exactly as before.

    STRICTLY GREATER, NEVER >=. `after` is a persisted `open_time`, and
    (source, symbol, timeframe, open_time) is the natural key, so a bar whose
    open_time EQUALS the watermark is by definition the row already stored.
    `>=` would re-offer that one row on every single run of every series
    forever — one guaranteed wasted savepoint round trip per series per run,
    which is precisely the cost this gate exists to remove.

    WHAT THIS IS NOT: `after` is an optimisation boundary, not an assertion that
    the series is complete below it. Gaps before `after` are entirely possible
    and detecting or repairing them is A4's job. Nothing here may be read as
    "there is no hole before W".
    """
    if after is not None:
        kept = [c for c in candidates if c.open_time > after]
        result.below_watermark += len(candidates) - len(kept)
        candidates = kept
    elif max_bars is not None and len(candidates) > max_bars:
        # NO WATERMARK — this series has never been written. Without a cap the
        # first run would offer the entire fetch window for every series at
        # once, which is the one-off stampede that made activation unaffordable.
        # `eligible_bars` returns ascending, so the tail is the newest.
        result.bootstrap_trimmed += len(candidates) - max_bars
        candidates = candidates[-max_bars:]
    return candidates
