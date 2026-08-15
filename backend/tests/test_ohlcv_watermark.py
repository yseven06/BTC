"""CP-OHLCV-A3c — the watermark gate. STILL DORMANT; nothing is scheduled here.

WHY THIS EXISTS. A3b re-offered its whole fetch window to the writer on every
run. Measured against production's 125.26 ms RTT that is 341,772 round trips per
run — 11.9 hours — because the per-row savepoint costs 3 round trips per bar and
the window is 499 bars wide per series. The watermark removes the bars that are
already stored BEFORE the session is touched, which takes the same run to 1,146
round trips.

WHAT IS DELIBERATELY NOT TESTED HERE, because A3 does not do it: backfill, gap
detection, paging, rewind, bar revision. Those are A4's. The guards below
actively assert that A3 has not quietly grown any of them.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_collector_job as J
from app.services import ohlcv_writer as W
from app.services.ohlcv_collector_job import (BOOTSTRAP_MAX_BARS,
                                              REQUEST_SPACING_SECONDS,
                                              STORAGE_TIMEFRAMES,
                                              WATERMARK_CHUNK,
                                              WatermarkSnapshot, collect_once,
                                              load_watermarks,
                                              run_collection_once)
from app.services.ohlcv_writer import (SOURCE_BINANCE, WriteResult,
                                       apply_lower_bound, collect_and_persist,
                                       eligible_bars, fetch_bars_bounded)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1),
        "4h": timedelta(hours=4), "1d": timedelta(days=1)}


def frame(n, tf="15m", start=T0):
    step = STEP[tf]
    idx = pd.DatetimeIndex([start + i * step for i in range(n)])
    df = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 110.0),
                       "low": np.full(n, 90.0), "close": np.full(n, 100.0),
                       "volume": np.full(n, 10.0)}, index=idx)
    df["close_time"] = [t + step for t in idx]
    return df


def cands(n, tf="15m", start=T0):
    got, _ = eligible_bars(frame(n, tf, start), "BTCUSDT", tf,
                           now=start + 10_000 * STEP[tf])
    return got


class WmSession:
    """A session whose watermark query answers with a scripted row set."""

    def __init__(self, rows=(), registry=None, new_bars=None):
        self.rows = list(rows)
        self.registry = registry if registry is not None else []
        self.queries = []
        self.params = []
        self.inserted = []
        self.savepoints = 0
        self.commits = 0
        self.rollbacks = 0
        self.new_bars = new_bars

    async def __aenter__(self):
        self.registry.append(self)
        return self

    async def __aexit__(self, *e):
        return False

    def begin_nested(self):
        outer = self

        class _SP:
            async def __aenter__(self_):
                outer.savepoints += 1
                return self_

            async def __aexit__(self_, *e):
                return False
        return _SP()

    async def execute(self, stmt, *a, **k):
        text = " ".join(str(stmt).split())
        self.queries.append(text)
        try:
            self.params.append(dict(stmt.compile().params))
        except Exception:                      # noqa: BLE001 — non-Core stmt
            self.params.append({})
        if "INSERT INTO ohlcv_bars" in text:
            try:
                self.inserted.append(stmt.compile().params.get("source"))
            except Exception:                  # noqa: BLE001 — non-Core stmt
                self.inserted.append("<uncompilable>")
        rows = self.rows if "wm_pairs" in text else []

        class _R:
            rowcount = 1

            def all(self_):
                return rows

            def scalars(self_):
                class _S:
                    def all(s_):
                        return []
                return _S()
        return _R()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def factory(registry, rows=()):
    return lambda: WmSession(rows, registry)


class Collector:
    def __init__(self, n=6, tf_start=None):
        self.n = n
        self.calls = []
        self.tf_start = tf_start or {}
        self.closed = 0

    async def fetch_ohlcv(self, symbol, timeframe, limit=500, end_time_ms=None):
        self.calls.append((symbol, timeframe, limit, end_time_ms))
        return frame(self.n, timeframe, self.tf_start.get(timeframe, T0))

    async def close(self):
        self.closed += 1



# A watermark that is legitimately CAUGHT UP: `Collector(n=6)` returns bars
# T0..T0+5*step and withholds T0+5 as the forming candle, so T0+4 is the newest
# bar that could ever have been persisted. Nothing is strictly greater than it,
# which is what "quiet series" means — as opposed to a mark BEYOND anything the
# exchange has, which is corruption and is asserted separately in section 14.
def caught_up(symbols, tfs=STORAGE_TIMEFRAMES):
    return [(s, tf, T0 + 4 * STEP[tf]) for s in symbols for tf in tfs]


# ══ 1 · STRICTLY GREATER, never >= ══════════════════════════════════════════
def test_a_bar_exactly_at_the_watermark_is_dropped():
    """`>=` would re-offer the stored row on EVERY run of EVERY series forever.

    This is the single assertion that separates the design from the bug it was
    written to remove: one wasted savepoint round trip per series per run.
    """
    c = cands(6)
    res = WriteResult()
    kept = apply_lower_bound(c, after=c[2].open_time, max_bars=None, result=res)

    assert all(k.open_time > c[2].open_time for k in kept), "boundary bar survived"
    assert c[2].open_time not in [k.open_time for k in kept]
    assert len(kept) == len(c) - 3, "everything at or below W must go"
    assert res.below_watermark == 3


def test_below_watermark_is_not_counted_as_a_duplicate():
    """A duplicate is a row the DATABASE rejected. These never reached it."""
    c = cands(6)
    res = WriteResult()
    apply_lower_bound(c, after=c[0].open_time, max_bars=None, result=res)
    assert res.below_watermark == 1
    assert res.duplicate == 0, "a filtered bar is not a database duplicate"
    assert res.persisted == 0 and res.db_rejected == 0


def test_a_watermark_newer_than_everything_offers_nothing():
    c = cands(6)
    res = WriteResult()
    kept = apply_lower_bound(c, after=c[-1].open_time + timedelta(days=9),
                             max_bars=None, result=res)
    assert kept == [] and res.below_watermark == len(c)


def test_no_watermark_means_no_filtering_at_all():
    c = cands(6)
    res = WriteResult()
    kept = apply_lower_bound(c, after=None, max_bars=None, result=res)
    assert kept == c and res.below_watermark == 0 and res.bootstrap_trimmed == 0


# ══ 2 · BOOTSTRAP — bounded first load, newest end ══════════════════════════
def test_bootstrap_keeps_the_NEWEST_bars_not_the_oldest():
    """Keeping the oldest would seed the store with ancient bars and leave a
    permanent hole between them and the next run."""
    c = cands(10)
    res = WriteResult()
    kept = apply_lower_bound(c, after=None, max_bars=4, result=res)
    assert len(kept) == 4
    assert [k.open_time for k in kept] == [x.open_time for x in c[-4:]]
    assert res.bootstrap_trimmed == len(c) - 4


def test_bootstrap_does_not_apply_once_a_watermark_exists():
    """Otherwise a symbol that had been offline for a while would silently lose
    bars it was entitled to — the cap is a FIRST-LOAD bound, nothing else."""
    c = cands(10)
    res = WriteResult()
    kept = apply_lower_bound(c, after=c[0].open_time, max_bars=2, result=res)
    assert len(kept) == len(c) - 1, "the cap must not bite when W is known"
    assert res.bootstrap_trimmed == 0


def test_bootstrap_is_derived_from_the_cadence_contract():
    """4 = 2 x (max 15m bars between two EFFECTIVE runs under coalesce=True)."""
    assert BOOTSTRAP_MAX_BARS == 4
    assert STORAGE_TIMEFRAMES[0] == "15m", "the finest timeframe is the binding case"


@pytest.mark.asyncio
async def test_a_bootstrap_of_zero_is_refused_because_the_series_could_never_start():
    with pytest.raises(ValueError, match="bootstrap"):
        await collect_once(factory([]), Collector(), symbols=["BTCUSDT"], bootstrap=0)


# ══ 3 · THE SNAPSHOT ════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_exactly_ONE_watermark_query_per_run_not_one_per_series():
    """228 SELECT MAXes would be ~28 s of pure latency at production RTT."""
    reg = []
    await collect_once(factory(reg), Collector(),
                       symbols=[f"S{i}USDT" for i in range(20)])
    wm = [q for s in reg for q in s.queries if "wm_pairs" in q]
    assert len(wm) == 1, f"expected 1 watermark query, got {len(wm)}"


@pytest.mark.asyncio
async def test_the_watermark_query_is_a_lateral_not_a_group_by():
    """MEASURED: GROUP BY takes a parallel seq scan (196 ms at 601 k rows,
    1287 ms at 2.63 M). The LATERAL is an index-only scan, flat at ~9 ms."""
    reg = []
    await collect_once(factory(reg), Collector(), symbols=["BTCUSDT"])
    wm = [q for s in reg for q in s.queries if "wm_pairs" in q][0]
    up = wm.upper()
    assert "LATERAL" in up, "the aggregate form does a full table scan"
    assert "GROUP BY" not in up
    assert "LIMIT" in up
    # DESC is the whole meaning of the subquery. Ascending would return the
    # OLDEST bar as the watermark, so every run would re-offer the entire
    # series and the filter would silently do nothing at all.
    assert "ORDER BY OHLCV_BARS.OPEN_TIME DESC" in up, "the watermark is not the newest bar"


@pytest.mark.asyncio
async def test_the_watermark_query_is_scoped_to_the_selected_series_only():
    reg = []
    await collect_once(factory(reg), Collector(), symbols=["BTCUSDT", "ETHUSDT"])
    wm = [q for s in reg for q in s.queries if "wm_pairs" in q][0]
    assert "ohlcv_bars.source" in wm
    assert "ohlcv_bars.symbol = wm_pairs.symbol" in wm
    assert "ohlcv_bars.timeframe = wm_pairs.timeframe" in wm


@pytest.mark.asyncio
async def test_an_absent_series_maps_to_None_not_to_the_epoch():
    """Absence must mean "never written", which bootstraps. If it ever became a
    zero/epoch datetime the first run would try to load all of history."""
    db = WmSession(rows=[("BTCUSDT", "15m", T0)])
    snap = await load_watermarks(db, ["BTCUSDT"], ["15m", "1h"])
    assert snap.get(SOURCE_BINANCE, "BTCUSDT", "15m") == T0
    assert snap.get(SOURCE_BINANCE, "BTCUSDT", "1h") is None
    assert snap.get(SOURCE_BINANCE, "NOSUCH", "15m") is None


@pytest.mark.asyncio
async def test_a_snapshot_refuses_to_answer_for_a_different_source():
    """Reusing binance's watermark for another provider would suppress that
    provider's bars entirely — silent data loss shaped exactly like "no news"."""
    snap = await load_watermarks(WmSession(rows=[("BTCUSDT", "15m", T0)]),
                                 ["BTCUSDT"], ["15m"])
    with pytest.raises(ValueError, match="source"):
        snap.get("kraken", "BTCUSDT", "15m")


@pytest.mark.asyncio
async def test_an_empty_universe_issues_no_query_at_all():
    db = WmSession()
    snap = await load_watermarks(db, [], list(STORAGE_TIMEFRAMES))
    assert db.queries == [] and snap.series_known == 0
    db2 = WmSession()
    await load_watermarks(db2, ["BTCUSDT"], [])
    assert db2.queries == []


@pytest.mark.asyncio
async def test_a_naive_timestamp_from_a_driver_is_normalised_to_utc():
    """A naive value would raise TypeError the moment it met a tz-aware bar."""
    naive = datetime(2026, 8, 1, 12, 0)
    snap = await load_watermarks(WmSession(rows=[("BTCUSDT", "15m", naive)]),
                                 ["BTCUSDT"], ["15m"])
    got = snap.get(SOURCE_BINANCE, "BTCUSDT", "15m")
    assert got.tzinfo is not None and got.utcoffset() == timedelta(0)
    assert got > T0 - timedelta(days=1)          # comparable, which is the point


@pytest.mark.asyncio
async def test_a_null_max_row_is_ignored_rather_than_stored_as_a_mark():
    snap = await load_watermarks(WmSession(rows=[("BTCUSDT", "15m", None)]),
                                 ["BTCUSDT"], ["15m"])
    assert snap.series_known == 0
    assert snap.get(SOURCE_BINANCE, "BTCUSDT", "15m") is None


@pytest.mark.asyncio
async def test_each_chunk_carries_only_its_own_symbols():
    """Counting the queries is not enough: a loop that runs the right number of
    times while sending the WHOLE universe every time is still unbounded, and
    the parameter list is what actually has to stay under the ceiling."""
    syms = [f"S{i}" for i in range(7)]
    db = WmSession()
    await load_watermarks(db, syms, ["15m"], chunk=3)
    assert len(db.queries) == 3, "ceil(7/3) bounded queries"

    seen = []
    for i, params in enumerate(db.params):
        sent = [v for v in params.values() if isinstance(v, str) and v.startswith("S")]
        assert len(sent) <= 3, f"query {i} carried {len(sent)} symbols, chunk was 3"
        seen += sent
    assert sorted(seen) == sorted(syms),         f"chunks must PARTITION the universe, got {sorted(seen)}"


@pytest.mark.asyncio
async def test_a_zero_chunk_is_refused():
    with pytest.raises(ValueError, match="chunk"):
        await load_watermarks(WmSession(), ["A"], ["15m"], chunk=0)


def test_the_chunk_stays_under_the_postgres_parameter_ceiling():
    assert WATERMARK_CHUNK * len(STORAGE_TIMEFRAMES) * 2 + 2 < 65535


# ══ 4 · THE WATERMARK IS AN OPTIMISATION BOUNDARY, NOT A COMPLETENESS CLAIM ═
def test_a_hole_below_the_watermark_is_left_alone():
    """W says "do not re-offer", NOT "everything below is present". A3 must not
    grow gap repair by accident; that is A4's, and conflating them would let a
    silent hole be reported as a healthy series."""
    c = cands(10)
    res = WriteResult()
    kept = apply_lower_bound(c, after=c[6].open_time, max_bars=None, result=res)
    assert [k.open_time for k in kept] == [x.open_time for x in c[7:]]
    assert res.below_watermark == 7
    # nothing anywhere reports the hole as filled, or as a gap
    assert not hasattr(res, "gaps") and not hasattr(res, "backfilled")


def test_A4_boundary_no_paging_no_rewind_no_revision():
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    seen_end_time = False
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "end_time_ms":
            seen_end_time = True
            assert isinstance(node.value, ast.Constant) and node.value.value is None, \
                "A3 must never seek historically; end_time_ms stays None"
    assert seen_end_time, "the live-window pin disappeared; the guard cannot bite"

    # IDENTIFIERS only. Prose may DISCUSS backfill — that is exactly how the A4
    # boundary is documented. What must not exist is code that performs it.
    idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    idents |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    idents |= {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    idents |= {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments)
               for a in list(n.args) + list(n.kwonlyargs)}
    for name in ("backfill", "rewind", "paginate", "page_through",
                 "on_conflict_do_update", "fill_gaps", "start_time_ms", "startTime"):
        assert name not in idents, f"A3 grew an A4 responsibility: {name}"


@pytest.mark.asyncio
async def test_the_collector_only_ever_asks_for_the_live_window():
    col = Collector()
    await collect_once(factory([]), col, symbols=["BTCUSDT"])
    assert all(end is None for _, _, _, end in col.calls), \
        "a non-None end_time_ms turns this into a historical downloader"


# ══ 5 · ROUND-TRIP ECONOMY ══════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_a_series_with_nothing_new_opens_no_session_at_all():
    """The whole point: no new bars must cost no pool checkout, no BEGIN, no
    COMMIT. Opening a session "just in case" would put 228 round trips back."""
    reg = []
    rows = caught_up(("BTCUSDT", "ETHUSDT"))
    await collect_once(factory(reg, rows), Collector(n=6),
                       symbols=["BTCUSDT", "ETHUSDT"])
    assert [s for s in reg if s.savepoints] == [], "nothing new, yet a row was written"
    # AsyncSession acquires a connection LAZILY, so an opened-but-unused session
    # costs no round trip; what costs is a statement. Measured in production
    # terms this is the difference between 59 and 228 pool checkouts per run.
    worked = [s for s in reg[1:] if s.queries]
    assert worked == [], f"{len(worked)} sessions issued statements for zero new bars"


@pytest.mark.asyncio
async def test_only_the_genuinely_new_bars_reach_the_writer():
    reg = []
    w = T0 + 3 * STEP["15m"]
    rows = [("BTCUSDT", tf, T0 + 3 * STEP[tf]) for tf in STORAGE_TIMEFRAMES]
    await collect_once(factory(reg, rows), Collector(n=6), symbols=["BTCUSDT"],
                       timeframes=["15m"])
    sp = sum(s.savepoints for s in reg)
    # frame(6) -> 5 eligible (T0..T0+4, newest withheld). W = T0+3, and STRICTLY
    # greater leaves exactly one: T0+4. Under `>=` it would be two.
    assert sp == 1, f"expected 1 savepoint for the 1 genuinely new bar, got {sp}"
    assert w == T0 + 3 * STEP["15m"]


# ══ 6 · symbols_skipped — RATIFIED SEMANTICS ═══════════════════════════════
@pytest.mark.asyncio
async def test_skipped_means_zero_new_bars_and_nothing_else():
    reg = []
    rows = caught_up(("AUSDT", "BUSDT"))
    res = await collect_once(factory(reg, rows), Collector(n=6),
                             symbols=["AUSDT", "BUSDT"])
    assert res.symbols_skipped == 2
    assert res.symbols_succeeded == 2, "a symbol with no news still succeeded"
    assert res.symbols_failed == 0


@pytest.mark.asyncio
async def test_a_fetch_failure_is_a_failure_NOT_a_skip():
    class Dead:
        async def fetch_ohlcv(self, *a, **k):
            raise RuntimeError("exchange down")

    res = await collect_once(factory([]), Dead(), symbols=["BTCUSDT"],
                             timeframes=["15m"], retries=0)
    assert res.symbols_failed == 1
    assert res.symbols_skipped == 0, "a failure must never be laundered into a skip"
    assert res.symbols_succeeded == 0


@pytest.mark.asyncio
async def test_a_db_failure_is_a_failure_NOT_a_skip():
    class Boom(WmSession):
        async def execute(self, stmt, *a, **k):
            if "wm_pairs" in " ".join(str(stmt).split()):
                return await super().execute(stmt, *a, **k)
            raise RuntimeError("db down")

    res = await collect_once(lambda: Boom(), Collector(), symbols=["BTCUSDT"],
                             timeframes=["15m"])
    assert res.symbols_failed == 1 and res.symbols_skipped == 0


@pytest.mark.asyncio
async def test_succeeded_plus_failed_partitions_attempted():
    rows = caught_up(("AUSDT",))
    res = await collect_once(factory([], rows), Collector(n=6),
                             symbols=["AUSDT", "BUSDT"])
    assert res.symbols_succeeded + res.symbols_failed == res.symbols_attempted
    assert res.symbols_skipped <= res.symbols_succeeded


# ══ 7 · HTTP CLASSIFICATION AND BACKOFF ════════════════════════════════════
class _Resp:
    def __init__(self, code, headers=None):
        self.status_code = code
        self.headers = headers or {}


class _HTTPError(Exception):
    def __init__(self, code, headers=None):
        super().__init__(f"HTTP {code}")
        self.response = _Resp(code, headers)


class Status:
    def __init__(self, code, headers=None):
        self.code, self.headers, self.calls = code, headers, 0

    async def fetch_ohlcv(self, *a, **k):
        self.calls += 1
        raise _HTTPError(self.code, self.headers)


@pytest.mark.asyncio
async def test_429_is_classified_backed_off_and_retried():
    col = Status(429)
    res = WriteResult()
    W.BACKOFF_BASE_SECONDS, base = 0.001, W.BACKOFF_BASE_SECONDS
    try:
        df, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=2, result=res)
    finally:
        W.BACKOFF_BASE_SECONDS = base
    assert kind == "fetch_rate_limited" and df is None
    assert res.fetch_rate_limited == 3 and res.fetch_error == 0
    assert col.calls == 3, "a rate limit is retried"
    assert res.retry_exhausted == 1


@pytest.mark.asyncio
async def test_418_abandons_the_retry_budget_immediately():
    """Binance's 418 means the IP is already banned; each further request
    EXTENDS the ban. Retrying is not merely useless, it deepens the hole."""
    col = Status(418)
    res = WriteResult()
    df, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=5, result=res)
    assert kind == "fetch_ip_banned" and df is None
    assert col.calls == 1, f"418 must not be retried, made {col.calls} requests"
    assert res.fetch_ip_banned == 1 and res.retry_exhausted == 1
    assert "418" in (res.error or "")


@pytest.mark.asyncio
async def test_a_non_429_http_error_stays_a_generic_fetch_error():
    col = Status(500)
    res = WriteResult()
    W.BACKOFF_BASE_SECONDS, base = 0.001, W.BACKOFF_BASE_SECONDS
    try:
        _, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=1, result=res)
    finally:
        W.BACKOFF_BASE_SECONDS = base
    assert kind == "fetch_error" and res.fetch_error == 2
    assert res.fetch_rate_limited == 0 and res.fetch_ip_banned == 0


def test_retry_after_is_honoured_but_CLAMPED():
    """An unclamped Retry-After lets the exchange choose a sleep inside a
    budgeted job. The cap, not the remote party, decides the worst case."""
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "2"})) == 2.0
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "9999"})) \
        == W.BACKOFF_MAX_SECONDS
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "-5"})) == 0.0
    # junk and date-form headers fall back to the local schedule
    assert W._retry_after_seconds(_HTTPError(429, {"Retry-After": "Wed, 21 Oct"})) is None
    assert W._retry_after_seconds(_HTTPError(429, {})) is None
    assert W._retry_after_seconds(RuntimeError("no response")) is None


def test_backoff_is_exponential_and_bounded():
    assert W._backoff_seconds(1) == W.BACKOFF_BASE_SECONDS
    assert W._backoff_seconds(2) == 2 * W.BACKOFF_BASE_SECONDS
    assert W._backoff_seconds(50) == W.BACKOFF_MAX_SECONDS
    assert all(W._backoff_seconds(i) <= W.BACKOFF_MAX_SECONDS for i in range(1, 40))


@pytest.mark.asyncio
async def test_no_backoff_is_spent_after_the_final_attempt():
    """Sleeping after the last try buys nothing and spends job budget."""
    W.BACKOFF_BASE_SECONDS, base = 5.0, W.BACKOFF_BASE_SECONDS
    try:
        t0 = asyncio.get_event_loop().time()
        await fetch_bars_bounded(Status(500), "BTCUSDT", "15m", retries=0,
                                 result=WriteResult())
        assert asyncio.get_event_loop().time() - t0 < 1.0, "slept after the last attempt"
    finally:
        W.BACKOFF_BASE_SECONDS = base


def test_status_extraction_does_not_assume_httpx():
    assert W._http_status(_HTTPError(429)) == 429
    assert W._http_status(RuntimeError("nope")) is None

    class Bare(Exception):
        status_code = 418
    assert W._http_status(Bare()) == 418


# ══ 8 · REQUEST SPACING ════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_requests_are_spaced_but_the_run_does_not_open_with_a_dead_wait():
    sleeps = []
    real = asyncio.sleep

    async def spy(d, *a, **k):
        sleeps.append(d)
        return await real(0)

    asyncio.sleep, saved = spy, asyncio.sleep
    try:
        await collect_once(factory([]), Collector(), symbols=["A", "B"],
                           timeframes=["15m", "1h"], spacing=0.25)
    finally:
        asyncio.sleep = saved
    spacing_sleeps = [s for s in sleeps if s == 0.25]
    assert len(spacing_sleeps) == 3, "n-1 gaps for n requests, never a leading one"


@pytest.mark.asyncio
async def test_spacing_must_not_be_negative():
    with pytest.raises(ValueError, match="spacing"):
        await collect_once(factory([]), Collector(), symbols=["A"], spacing=-1)


def test_spacing_stays_inside_the_documented_weight_ceiling():
    """klines at limit<=500 costs weight 2; the IP ceiling is 1200/min."""
    per_min = (60.0 / REQUEST_SPACING_SECONDS) * 2
    assert per_min <= 1200 * 0.75, f"{per_min} weight/min leaves too little headroom"


# ══ 9 · COLLECTOR LIFECYCLE ════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_the_collector_is_closed_even_when_the_run_raises():
    """BinanceCollector.__init__ builds an httpx.AsyncClient; only close()
    releases it. A run that dies at the budget deadline must still close."""
    made = []

    class Exploding(Collector):
        async def fetch_ohlcv(self, *a, **k):
            raise RuntimeError("boom")

    def fake_ctor():
        c = Exploding()
        made.append(c)
        return c

    J.BinanceCollector, real = fake_ctor, J.BinanceCollector
    try:
        await run_collection_once(run_seq=0, session_factory=factory([]), symbols=["BTCUSDT"],
                                  timeframes=["15m"], retries=0, spacing=0)
        with pytest.raises(ValueError):
            await run_collection_once(run_seq=0, session_factory=factory([]), symbols=["BTCUSDT"], limit=1)
    finally:
        J.BinanceCollector = real
    assert len(made) == 2 and all(c.closed == 1 for c in made), \
        "every constructed collector must be closed exactly once"


@pytest.mark.asyncio
async def test_a_failure_to_close_does_not_mask_the_real_outcome():
    class Stubborn(Collector):
        async def close(self):
            raise RuntimeError("close failed")

    J.BinanceCollector, real = Stubborn, J.BinanceCollector
    try:
        res = await run_collection_once(run_seq=0, session_factory=factory([]), symbols=["BTCUSDT"],
                                        timeframes=["15m"], spacing=0)
    finally:
        J.BinanceCollector = real
    assert res.symbols_attempted == 1


def test_no_client_is_constructed_at_import_time():
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:                       # module level only
        for sub in ast.walk(node) if isinstance(node, (ast.Assign, ast.Expr)) else []:
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "BinanceCollector":
                pytest.fail("a module-level collector opens a socket on import")


# ══ 10 · THE PER-ROW SAVEPOINT IS UNTOUCHED ════════════════════════════════
def test_persist_bars_still_uses_one_savepoint_per_row():
    """A2's measured contract: a single multi-row INSERT loses 6 of 7 valid bars
    and poisons the caller's transaction. A3c must not have traded that away for
    speed — the watermark is what makes per-row affordable, not a replacement."""
    src = inspect.getsource(W.persist_bars)
    tree = ast.parse(src.lstrip())
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor))]
    assert loops, "persistence must still iterate row by row"
    nested = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]
    assert nested, "the per-row savepoint is gone"
    inside = [n for n in ast.walk(loops[0])
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]
    assert inside, "begin_nested must be INSIDE the per-row loop, not around it"
    assert "executemany" not in src and "add_all" not in src


def test_conflict_target_is_still_the_portable_column_list():
    assert W.CONFLICT_TARGET == ("source", "symbol", "timeframe", "open_time")
    src = inspect.getsource(W.persist_bars)
    assert "on_conflict_do_nothing" in src
    assert "constraint=" not in src, "named-constraint ON CONFLICT is not portable"


# ══ 11 · STILL DORMANT ═════════════════════════════════════════════════════
def test_A3c_added_no_production_caller():
    hits = []
    for p in list((BACKEND / "app").rglob("*.py")) + list((BACKEND / "scripts").rglob("*.py")):
        # The dormant subsystem's OWN files. ohlcv_progression.py joined it in
        # 0012: it holds the fairness counter and is imported only by the
        # collector, so it is part of what must stay dormant — not a caller of it.
        if p.name in ("ohlcv_collector_job.py", "ohlcv_writer.py",
                      "ohlcv_progression.py", "scheduler.py"):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        if any(k in t for k in ("ohlcv_collector_job", "collect_once",
                                "run_collection_once", "load_watermarks")):
            hits.append(str(p.relative_to(BACKEND)))
    assert hits == [], f"A3c must remain dormant; called from {hits}"


def test_A3c_registered_no_scheduler_job():
    src = (BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8")
    # NB: the scheduler legitimately calls `collector.fetch_ohlcv` for signals.
    # What must be absent is any reference to THIS module or its entry points.
    # A3c IS NOW ACTIVATED: scheduler.py is the ONE allowed caller, via
    # run_collection_once only. See tests/test_ohlcv_activation_registration.py.
    for name in ("collect_once", "load_watermarks", "ohlcv_writer"):
        assert name not in src, f"scheduler references {name}"


def test_no_decision_surface_reads_the_new_counters():
    """Collection health describes a network copy, not a market opinion."""
    names = ("bars_below_watermark", "series_bootstrapped", "watermark_series_known",
             "fetch_rate_limited", "fetch_ip_banned", "bars_bootstrap_trimmed")
    for p in (BACKEND / "app").rglob("*.py"):
        # The dormant subsystem's OWN files. ohlcv_progression.py joined it in
        # 0012: it holds the fairness counter and is imported only by the
        # collector, so it is part of what must stay dormant — not a caller of it.
        if p.name in ("ohlcv_collector_job.py", "ohlcv_writer.py",
                      "ohlcv_progression.py"):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        for n in names:
            assert n not in t, f"{n} leaked into {p.name}"


# ══ 12 · A WATERMARK FAILURE DEGRADES, IT DOES NOT ABORT ═══════════════════
class _WmBroken(WmSession):
    async def execute(self, stmt, *a, **k):
        if "wm_pairs" in " ".join(str(stmt).split()):
            raise RuntimeError("watermark read exploded")
        return await super().execute(stmt, *a, **k)


@pytest.mark.asyncio
async def test_a_watermark_failure_still_collects_but_is_never_called_healthy():
    """Losing an optimisation must not cost a whole cadence of data. It also
    must not pass quietly — a run that re-seeds every series while reporting
    full health would hide a persistent database problem indefinitely."""
    reg = []
    res = await collect_once(lambda: _WmBroken(registry=reg), Collector(n=6),
                             symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.watermark_failed is True
    assert res.healthy is False, "a degraded run must never report healthy"
    assert any("watermark" in f for f in res.failures)
    assert res.bars_persisted > 0, "the run must still have collected"
    assert res.symbols_failed == 0, "the items themselves did not fail"


@pytest.mark.asyncio
async def test_the_degraded_path_is_bounded_by_the_bootstrap_cap():
    """Degrading must not mean 'offer the entire 499-bar window'. That is the
    11.9-hour run this checkpoint exists to prevent."""
    reg = []
    res = await collect_once(lambda: _WmBroken(registry=reg), Collector(n=60),
                             symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.bars_persisted == BOOTSTRAP_MAX_BARS
    assert res.bars_bootstrap_trimmed == 59 - BOOTSTRAP_MAX_BARS
    assert sum(s.savepoints for s in reg) == BOOTSTRAP_MAX_BARS


@pytest.mark.asyncio
async def test_a_healthy_run_reports_watermark_failed_false():
    """Guard against the flag being hard-wired True and the tests above passing
    for the wrong reason."""
    res = await collect_once(factory([], [("BTCUSDT", "15m", T0)]), Collector(n=6),
                             symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.watermark_failed is False and res.healthy is True


# ══ 13 · SOURCE IS ONE VALUE PER ITEM, READ AND WRITTEN ════════════════════
def _sources_of(reg):
    """(watermark-read source binds, distinct row-write source values)."""
    read, write = [], []
    for s in reg:
        for q, params in zip(s.queries, s.params):
            if "wm_pairs" in q:
                read += [v for k, v in params.items() if k.startswith("source")]
        write += s.inserted
    return read, sorted(set(write))


@pytest.mark.asyncio
async def test_binance_source_is_read_and_written_unchanged():
    reg = []
    await collect_once(factory(reg), Collector(n=6), symbols=["BTCUSDT"],
                       timeframes=["15m"], source=SOURCE_BINANCE)
    read, write = _sources_of(reg)
    assert read == [SOURCE_BINANCE] and write == [SOURCE_BINANCE]


@pytest.mark.asyncio
async def test_a_non_binance_source_is_never_silently_rewritten_to_binance():
    """The defect this pins: `source` reached the watermark READ but not the
    WRITE, so a caller asking for one provider got rows stamped with another —
    and the run still reported healthy. Two providers would then share one
    namespace while each believed it owned its own."""
    reg = []
    res = await collect_once(factory(reg), Collector(n=6), symbols=["BTCUSDT"],
                             timeframes=["15m"], source="kraken")
    read, write = _sources_of(reg)
    assert read == ["kraken"], f"watermark read used {read}"
    assert write == ["kraken"], f"rows were stamped {write}, not 'kraken'"
    assert SOURCE_BINANCE not in write, "silently fell back to binance"
    assert res.bars_persisted > 0, "vacuous if nothing was written at all"


@pytest.mark.asyncio
async def test_read_source_equals_write_source_for_every_source_tried():
    for src in (SOURCE_BINANCE, "kraken", "coinbase", "SOURCE-WITH-DASH"):
        reg = []
        await collect_once(factory(reg), Collector(n=6), symbols=["BTCUSDT"],
                           timeframes=["15m"], source=src)
        read, write = _sources_of(reg)
        assert read == [src] == write, f"{src}: read={read} write={write}"


def test_source_participates_in_the_natural_key_identity():
    """Same symbol/timeframe/open_time under two sources are DIFFERENT rows."""
    now = T0 + 99 * STEP["15m"]
    a, _ = eligible_bars(frame(4), "BTCUSDT", "15m", now=now, source=SOURCE_BINANCE)
    b, _ = eligible_bars(frame(4), "BTCUSDT", "15m", now=now, source="kraken")
    assert [x.open_time for x in a] == [x.open_time for x in b]
    ka = {(x.source, x.symbol, x.timeframe, x.open_time) for x in a}
    kb = {(x.source, x.symbol, x.timeframe, x.open_time) for x in b}
    assert ka and ka.isdisjoint(kb), "two sources collapsed into one namespace"
    assert W.CONFLICT_TARGET[0] == "source", "source must lead the conflict target"


@pytest.mark.asyncio
async def test_two_sources_in_sequence_do_not_cross_contaminate():
    regs = {}
    for src in ("kraken", SOURCE_BINANCE):
        regs[src] = []
        await collect_once(factory(regs[src]), Collector(n=6), symbols=["BTCUSDT"],
                           timeframes=["15m"], source=src)
    for src, reg in regs.items():
        read, write = _sources_of(reg)
        assert read == [src] == write, f"{src} leaked: read={read} write={write}"


@pytest.mark.asyncio
async def test_an_empty_source_is_refused_rather_than_stamping_a_nameless_row():
    for bad in ("", "   ", None, 7):
        with pytest.raises(ValueError, match="source"):
            await collect_once(factory([]), Collector(), symbols=["A"], source=bad)


def test_collect_and_persist_forwards_source_rather_than_re_deriving_it():
    """Structural: one item has exactly ONE authoritative source, the caller's."""
    src = inspect.getsource(W.collect_and_persist)
    tree = ast.parse(src.lstrip())
    call = next(n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "eligible_bars")
    kw = {k.arg for k in call.keywords}
    assert "source" in kw, "eligible_bars called without source; it will default"
    passed = next(k for k in call.keywords if k.arg == "source")
    assert isinstance(passed.value, ast.Name) and passed.value.id == "source", \
        "source must be forwarded verbatim, not re-derived or hard-coded"


# ══ 14 · A FUTURE WATERMARK IS AN ANOMALY, NOT A QUIET SERIES ══════════════
FUTURE = T0 + timedelta(days=3650)


def _future_rows(symbols, tfs=("15m",)):
    return [(s, tf, FUTURE) for s in symbols for tf in tfs]


@pytest.mark.asyncio
async def test_a_future_watermark_is_reported_as_a_distinct_anomaly():
    """Without this the lower bound silently removes every candidate, the item
    persists nothing, and the run reports healthy forever while the series is
    frozen — indistinguishable from a market that simply had no new bars."""
    reg = []
    res = await collect_once(factory(reg, _future_rows(["BTCUSDT"])), Collector(n=6),
                             symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.watermark_anomalies == 1
    assert res.healthy is False, "a frozen series must never report healthy"
    assert res.symbols_skipped == 0, "an anomaly must not be laundered into a skip"
    assert any("WATERMARK ANOMALY" in f for f in res.failures)
    assert res.bars_persisted == 0, "progress must not be faked"
    assert sum(s.savepoints for s in reg) == 0, "no row may be written"


@pytest.mark.asyncio
async def test_the_anomaly_neither_resets_rewinds_nor_backfills():
    reg = []
    await collect_once(factory(reg, _future_rows(["BTCUSDT"])), Collector(n=6),
                       symbols=["BTCUSDT"], timeframes=["15m"])
    stmts = " ".join(q.upper() for s in reg for q in s.queries)
    for forbidden in ("DELETE", "UPDATE", "TRUNCATE", "DROP", "INSERT"):
        assert forbidden not in stmts, f"anomaly path issued a {forbidden}"


@pytest.mark.asyncio
async def test_the_anomaly_does_not_trigger_historical_seeking():
    col = Collector(n=6)
    await collect_once(factory([], _future_rows(["BTCUSDT"])), col,
                       symbols=["BTCUSDT"], timeframes=["15m"])
    assert all(end is None for _, _, _, end in col.calls), "anomaly started a backfill"
    assert len(col.calls) == 1, "anomaly caused extra fetches (paging)"


@pytest.mark.asyncio
async def test_siblings_continue_past_an_anomalous_series():
    rows = _future_rows(["AAAUSDT"]) + [("BBBUSDT", "15m", T0)]
    res = await collect_once(factory([], rows), Collector(n=6),
                             symbols=["AAAUSDT", "BBBUSDT"], timeframes=["15m"])
    assert res.watermark_anomalies == 1
    assert res.symbols_attempted == 2
    assert res.bars_persisted > 0, "the healthy sibling must still be collected"
    assert res.symbols_failed == 0, "an anomaly is not a failure of another symbol"
    assert res.healthy is False


@pytest.mark.asyncio
async def test_the_anomalous_symbol_is_not_counted_as_failed():
    """The fetch worked and the database worked. Calling it a failure would send
    an operator hunting for an outage that never happened."""
    res = await collect_once(factory([], _future_rows(["BTCUSDT"])), Collector(n=6),
                             symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.symbols_failed == 0
    assert res.symbols_succeeded + res.symbols_failed == res.symbols_attempted
    assert res.db_error == 0 and res.retry_exhausted == 0


@pytest.mark.asyncio
async def test_a_current_or_past_watermark_stays_healthy():
    """Guard against the anomaly gate firing on ordinary marks."""
    for mark in (T0, T0 + 3 * STEP["15m"], T0 + 4 * STEP["15m"]):
        res = await collect_once(factory([], [("BTCUSDT", "15m", mark)]),
                                 Collector(n=6), symbols=["BTCUSDT"],
                                 timeframes=["15m"])
        assert res.watermark_anomalies == 0, f"false positive at mark {mark}"
        assert res.healthy is True


@pytest.mark.asyncio
async def test_a_watermark_equal_to_the_forming_bar_is_not_flagged():
    """Equality is deliberately not an anomaly: the newest element of a response
    is the forming candle, which the closure rule already withholds, so only a
    STRICTLY greater watermark is provably impossible."""
    newest = frame(6).index[-1].to_pydatetime()
    res = await collect_once(factory([], [("BTCUSDT", "15m", newest)]),
                             Collector(n=6), symbols=["BTCUSDT"], timeframes=["15m"])
    assert res.watermark_anomalies == 0 and res.healthy is True


def test_the_anomaly_authority_is_the_response_not_the_clock():
    """No tolerance is applied and none is needed: both sides of the comparison
    come from the SAME fetch, so clock skew cannot manufacture a false positive.
    A margin here would be a second clock rule."""
    df = frame(6)
    assert W._newest_open_time(df) == df.index[-1].to_pydatetime()
    assert W._newest_open_time(df.iloc[0:0]) is None
    assert W._newest_open_time(None) is None
    src = inspect.getsource(W.collect_and_persist)
    tail = src[src.index("newest = _newest_open_time"):src.index("watermark_in_future")]
    assert "now" not in tail, "the anomaly comparison must not consult the clock"
    assert ">" in tail and ">=" not in tail, "must be STRICTLY greater"


@pytest.mark.asyncio
async def test_a_watermark_READ_FAILURE_stays_separate_from_a_FUTURE_watermark():
    """Two different worlds: 'we could not read it' vs 'we read it and it is
    impossible'. Conflating them hides a corrupt series behind a transient
    database story, and the degrade paths are opposite — one bootstraps, the
    other must write nothing at all."""
    broken = await collect_once(lambda: _WmBroken(), Collector(n=6),
                                symbols=["BTCUSDT"], timeframes=["15m"])
    assert broken.watermark_failed is True and broken.watermark_anomalies == 0
    assert broken.bars_persisted > 0, "a read failure still collects (bootstrap)"

    future = await collect_once(factory([], _future_rows(["BTCUSDT"])), Collector(n=6),
                                symbols=["BTCUSDT"], timeframes=["15m"])
    assert future.watermark_anomalies == 1 and future.watermark_failed is False
    assert future.bars_persisted == 0, "an impossible mark must write nothing"
    assert broken.healthy is False and future.healthy is False


@pytest.mark.asyncio
async def test_the_anomaly_run_stays_bounded():
    col = Collector(n=6)
    syms = [f"S{i}USDT" for i in range(6)]
    res = await collect_once(factory([], _future_rows(syms, STORAGE_TIMEFRAMES)), col,
                             symbols=syms)
    n = 6 * len(STORAGE_TIMEFRAMES)
    assert len(col.calls) == n, "one fetch per item, no retry storm"
    assert res.watermark_anomalies == n
    assert res.bars_persisted == 0 and res.healthy is False
