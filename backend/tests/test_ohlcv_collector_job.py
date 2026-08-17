"""CP-OHLCV-A3a/A3b — writer corrections and the dormant collector.

A3b exists so A3c has something safe to schedule. It is NOT scheduled here, and
these tests fail if anything wires it.

The two A3a corrections both come from measured defects, not review taste:
  * `collect_and_persist` used to discard the fetch phase's counters on failure
    and synthesise a single flag, so three timeouts reported as one and
    `fetch_attempts` came back 0.
  * a negative `retries` made `range(1, retries + 2)` empty, so the loop never
    ran and the function raised UnboundLocalError instead of returning a
    classified failure.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ohlcv_collector_job as J
from app.services.ohlcv_collector_job import (DEFAULT_FETCH_LIMIT,
                                              MIN_FETCH_LIMIT,
                                              STORAGE_TIMEFRAMES, UNIVERSE_CAP,
                                              CollectionResult, collect_once,
                                              load_universe)
from app.services.ohlcv_writer import WriteResult, fetch_bars_bounded

BACKEND = pathlib.Path(__file__).resolve().parent.parent
UTC = timezone.utc
T0 = datetime(2026, 8, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)


def frame(n=5, tf="15m", forming=True):
    step = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1),
            "4h": timedelta(hours=4), "1d": timedelta(days=1)}[tf]
    idx = pd.DatetimeIndex([T0 + i * step for i in range(n)], tz=UTC)
    df = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 110.0),
                       "low": np.full(n, 90.0), "close": np.full(n, 100.0),
                       "volume": np.full(n, 10.0)}, index=idx)
    df["close_time"] = [t + step for t in idx]
    return df


class Collector:
    """behaviour: 'ok' | 'hang' | 'err' | 'empty' | 'malformed' | callable(symbol, tf)"""

    def __init__(self, behaviour="ok"):
        self.behaviour = behaviour
        self.calls = []
        self.concurrent = 0
        self.max_concurrent = 0

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
        self.calls.append((symbol, timeframe, limit, end_time_ms))
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            b = self.behaviour(symbol, timeframe) if callable(self.behaviour) else self.behaviour
            if b == "ok":
                await asyncio.sleep(0)
                return frame(5, timeframe)
            if b == "empty":
                return frame(0, timeframe)
            if b == "malformed":
                return frame(5, timeframe).drop(columns=["high"])
            if b == "reversed":
                return frame(5, timeframe).iloc[::-1]
            if b == "hang":
                await asyncio.sleep(3600)
            raise ConnectionError("boom")
        finally:
            self.concurrent -= 1


def insert_row_count(stmt):
    """How many rows an INSERT carries — 0 for anything that is not one.

    The writer emits two shapes: `.values([row, ...])` for the batched healthy
    path, which compiles one bind per row (`source_m0`, `source_m1`, ...), and
    `.values(**row)` in the per-row fallback, which compiles the bare column
    name. A fake must read both or its rowcount stops meaning anything.
    """
    try:
        params = stmt.compile().params
    except Exception:                          # noqa: BLE001 — non-Core stmt
        return 0
    if "source" in params:
        return 1
    return sum(1 for k in params if k.startswith("source_m"))


class FakeSession:
    """Records lifecycle. Never claims to reproduce PostgreSQL semantics."""

    def __init__(self, registry, fail_on=None):
        self.registry = registry
        self.fail_on = fail_on or (lambda stmt: False)
        self.in_tx = False
        self.commits = 0
        self.closed = False
        self.savepoints = 0

    async def __aenter__(self):
        self.registry.append(self)
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False

    def begin_nested(self):
        outer = self

        class _SP:
            async def __aenter__(self_):
                outer.savepoints += 1
                outer.in_tx = True
                return self_

            async def __aexit__(self_, *e):
                return False
        return _SP()

    async def execute(self, stmt, *a, **k):
        self.in_tx = True
        if self.fail_on(stmt):
            raise RuntimeError("db down")
        written = insert_row_count(stmt)

        class _R:
            # DERIVED from the statement, not a hardcoded 1. The writer sends a
            # whole page as one multi-row INSERT on its healthy path, so a fixed
            # 1 would report `bars_persisted=1` for a page of six and every
            # counter assertion below would be measuring the fake, not the code.
            rowcount = written

            def all(self_):
                # An EMPTY store: no watermark for any series. Every series
                # therefore bootstraps, which is the state these A3a/A3b tests
                # were written against and must keep exercising.
                return []
        return _R()

    async def commit(self):
        self.commits += 1
        self.in_tx = False

    async def rollback(self):
        self.in_tx = False


def factory(registry, fail_on=None):
    return lambda: FakeSession(registry, fail_on)


# ══ A3a · counter preservation ══════════════════════════════════════════════
@pytest.mark.asyncio
async def test_A3a_fetch_counters_survive_a_failed_fetch():
    """The regression: three real timeouts used to be reported as one synthetic
    flag with fetch_attempts=0."""
    from app.services.ohlcv_writer import collect_and_persist
    reg = []
    res = await collect_and_persist(FakeSession(reg), Collector("hang"),
                                    "BTCUSDT", "15m", timeout=0.02, retries=2)
    assert res.fetch_attempts == 3, "every attempt must be counted, not synthesised"
    assert res.fetch_timeout == 3
    assert res.retry_exhausted == 1
    assert res.fetch_error == 0, "a stall is never a generic error"
    assert res.fetch_success == 0 and res.persisted == 0


@pytest.mark.asyncio
async def test_A3a_a_recovered_retry_keeps_both_the_failure_and_the_recovery():
    from app.services.ohlcv_writer import collect_and_persist
    n = {"i": 0}

    class Flaky:
        async def fetch_ohlcv(self, *a, **k):
            n["i"] += 1
            if n["i"] == 1:
                raise ConnectionError("x")
            return frame(5)

    res = await collect_and_persist(FakeSession([]), Flaky(), "BTCUSDT", "15m",
                                    now=T0 + 100 * STEP, retries=2)
    assert res.fetch_attempts == 2 and res.fetch_error == 1
    assert res.retry_recovered == 1 and res.fetch_success == 1
    assert res.retry_exhausted == 0
    assert res.eligible == 4 and res.persisted == 4, "the bar phase still ran"


@pytest.mark.asyncio
async def test_A3a_fetch_and_bar_counters_coexist_in_one_result():
    from app.services.ohlcv_writer import collect_and_persist
    res = await collect_and_persist(FakeSession([]), Collector("ok"), "BTCUSDT",
                                    "15m", now=T0 + 100 * STEP)
    assert res.fetch_attempts == 1 and res.fetch_success == 1
    assert res.fetched == 5 and res.eligible == 4
    assert res.forming_or_not_closed == 1
    assert res.persisted == 4


def test_A3a_the_shared_result_is_threaded_into_the_fetch_not_created_after_it():
    """The MECHANISM behind the fix, guarded structurally.

    A behavioural test cannot catch every way of losing the counters — within a
    single call, folding with `=` and `+=` are indistinguishable. What must hold
    is that ONE result object is created before the fetch and handed to
    `fetch_bars_bounded` via `result=`, so the fetch phase writes into the same
    object the caller finally sees.
    """
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "collect_and_persist")

    call = next(n for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "fetch_bars_bounded")
    kw = {k.arg for k in call.keywords}
    assert "result" in kw, "the fetch must write into the caller's result object"

    # and that object must be created BEFORE the fetch, not after it
    made = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "WriteResult"]
    assert made and min(made) < call.lineno, "result must pre-date the fetch"
    # ...and there must be exactly ONE, so no failure path can substitute a fresh
    # blank result and drop what the fetch already counted.
    assert len(made) == 1, f"exactly one WriteResult per call, found {len(made)}"


def test_A3a_distinct_failure_classes_are_never_merged():
    r = WriteResult()
    for f in ("fetch_timeout", "fetch_error", "malformed_response",
              "db_rejected", "db_error", "duplicate", "persisted", "fetch_success"):
        assert hasattr(r, f), f


# ══ A3a · retry contract ════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("retries", [-2, -1])
async def test_A3a_negative_retries_are_rejected_before_any_io(retries):
    """Rejected, NOT coerced to 0 — a caller passing -1 has a bug worth seeing."""
    col = Collector("ok")
    with pytest.raises(ValueError, match=">= 0"):
        await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=retries)
    assert col.calls == [], "rejection must precede the network call"


@pytest.mark.asyncio
@pytest.mark.parametrize("retries,expected_attempts", [(0, 1), (1, 2), (2, 3)])
async def test_A3a_attempt_count_is_exactly_retries_plus_one(retries, expected_attempts):
    col = Collector("err")
    res = WriteResult()
    df, kind = await fetch_bars_bounded(col, "BTCUSDT", "15m", retries=retries, result=res)
    assert df is None and kind == "fetch_error"
    assert len(col.calls) == expected_attempts
    assert res.fetch_attempts == expected_attempts
    assert res.retry_exhausted == 1


@pytest.mark.asyncio
async def test_A3a_a_bool_is_not_an_int_here():
    with pytest.raises(ValueError):
        await fetch_bars_bounded(Collector("ok"), "BTCUSDT", "15m", retries=True)


# ══ A3b · timeframe contract ════════════════════════════════════════════════
def test_A3b_storage_timeframes_are_exactly_four_in_order():
    assert STORAGE_TIMEFRAMES == ("15m", "1h", "4h", "1d")
    assert list(STORAGE_TIMEFRAMES) == sorted(
        STORAGE_TIMEFRAMES, key=lambda t: ("mhd".index(t[-1]), int(t[:-1])))


def test_A3b_1m_is_not_selected_even_though_the_writer_accepts_it():
    from app.services.candle_window import TIMEFRAME_DURATIONS
    from app.services.ohlcv_writer import normalise_timeframe
    assert "1m" in TIMEFRAME_DURATIONS
    assert normalise_timeframe("1m") == "1m", "the writer still accepts it"
    assert "1m" not in STORAGE_TIMEFRAMES, "but A3 must not select it"
    assert "1w" not in STORAGE_TIMEFRAMES and "5m" not in STORAGE_TIMEFRAMES


@pytest.mark.asyncio
async def test_A3b_an_unknown_timeframe_is_rejected_before_any_work():
    col = Collector("ok")
    with pytest.raises(ValueError):
        await collect_once(factory([]), col, symbols=["BTCUSDT"], timeframes=["30m"])
    assert col.calls == []


# ══ A3b · universe contract ═════════════════════════════════════════════════
class _UniverseSession:
    def __init__(self, symbols):
        self._symbols = symbols
        self.stmts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    async def execute(self, stmt, *a, **k):
        self.stmts.append(str(stmt))
        rows = sorted(self._symbols)          # the DB would apply ORDER BY

        class _R:
            def scalars(self_):
                class _S:
                    def all(s_):
                        return rows
                return _S()
        return _R()


@pytest.mark.asyncio
async def test_A3b_universe_is_active_crypto_ordered_by_symbol():
    db = _UniverseSession(["ETHUSDT", "BTCUSDT", "ADAUSDT"])
    syms, eligible, overflow = await load_universe(db)
    assert syms == ["ADAUSDT", "BTCUSDT", "ETHUSDT"], "deterministic total order"
    assert eligible == 3 and overflow is False
    sql = db.stmts[0].lower()
    assert "is_active" in sql and "asset_type" in sql
    assert "order by" in sql and "symbol" in sql.split("order by")[1]


@pytest.mark.asyncio
async def test_A3b_overflow_is_explicit_and_never_silent():
    db = _UniverseSession([f"S{i:03d}" for i in range(10)])
    syms, eligible, overflow = await load_universe(db, cap=4)
    assert len(syms) == 4 and eligible == 10 and overflow is True
    assert syms == ["S000", "S001", "S002", "S003"], "the capped slice is deterministic"


@pytest.mark.asyncio
async def test_A3b_an_overflowing_run_is_UNHEALTHY():
    """The core anti-silent-truncation guard: a run that could not cover the
    universe must not report success."""
    res = CollectionResult(universe_overflow=True)
    assert res.healthy is False
    assert CollectionResult().healthy is True


def test_A3b_the_cap_is_explicit_finite_and_above_current_population():
    assert isinstance(UNIVERSE_CAP, int) and UNIVERSE_CAP > 0
    assert UNIVERSE_CAP >= 100, "must sit comfortably above the measured 57"


@pytest.mark.asyncio
async def test_A3b_universe_query_is_not_the_signal_sweep():
    src = (BACKEND / "app" / "services" / "ohlcv_collector_job.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", " ", src)
    code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
    assert "_run_all_signals" not in code
    assert "scheduler" not in code, "the collector must not import the scheduler"
    assert "generate_batch" not in code


# ══ A3b · serial architecture, session/network boundary ═════════════════════
@pytest.mark.asyncio
async def test_A3b_is_strictly_serial_one_request_at_a_time():
    reg = []
    col = Collector("ok")
    res = await collect_once(factory(reg), col, symbols=["AAA", "BBB", "CCC"])
    assert col.max_concurrent == 1, "no fan-out"
    assert len(col.calls) == 3 * len(STORAGE_TIMEFRAMES)
    assert res.symbols_succeeded == 3 and res.symbols_failed == 0


@pytest.mark.asyncio
async def test_A3b_live_window_only_no_end_time_and_limit_at_least_two():
    col = Collector("ok")
    await collect_once(factory([]), col, symbols=["AAA"])
    for _sym, _tf, limit, end_time_ms in col.calls:
        assert end_time_ms is None, "A3 is live collection; no historical seeking"
        assert limit >= MIN_FETCH_LIMIT


@pytest.mark.asyncio
async def test_A3b_limit_one_is_refused_because_it_could_never_persist():
    with pytest.raises(ValueError, match=">= 2"):
        await collect_once(factory([]), Collector("ok"), symbols=["AAA"], limit=1)


@pytest.mark.asyncio
async def test_A3b_no_db_transaction_is_open_while_the_network_is_in_flight():
    seen = {}
    reg = []

    class Watching:
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
            # the session for THIS item is the most recently created one
            seen.setdefault("in_tx", []).append(reg[-1].in_tx if reg else None)
            await asyncio.sleep(0.001)
            return frame(5, timeframe)

    await collect_once(factory(reg), Watching(), symbols=["AAA", "BBB"])
    assert seen["in_tx"] and all(v is False for v in seen["in_tx"]), (
        f"a transaction was open during network I/O: {seen['in_tx']}")


@pytest.mark.asyncio
async def test_A3b_each_item_gets_its_own_session_and_commit():
    reg = []
    await collect_once(factory(reg), Collector("ok"), symbols=["AAA", "BBB"])
    per_item = 2 * len(STORAGE_TIMEFRAMES)
    # reg[0] is A3c's watermark session, which is read-only and rolls back.
    wm, items = reg[0], reg[1:]
    assert wm.commits == 0, "the watermark read must never commit"
    assert len(items) == per_item, "one session per (symbol, timeframe)"
    assert all(s.closed for s in reg), "every session closed"
    assert all(s.commits == 1 for s in items), "the CALLER commits, once per item"


# ══ A3b · failure isolation ═════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_A3b_one_symbol_timeout_does_not_stop_the_others():
    col = Collector(lambda s, tf: "hang" if s == "BBB" else "ok")
    res = await collect_once(factory([]), col, symbols=["AAA", "BBB", "CCC"],
                             timeout=0.02, retries=0)
    assert res.symbols_succeeded == 2 and res.symbols_failed == 1
    # A3c-repair-v4: a terminal item failure no longer ABANDONS the rest of that
    # symbol's timeframes — v2 did that, and a review proved it let timeframe
    # ORDER decide REACHABILITY. All four are attempted now (hence four
    # timeouts, not one); what bounds the cost is the REDUCED per-item budget the
    # siblings run under. The isolation contract that matters — other symbols
    # continue — is unchanged and asserted below.
    n_tf = len(STORAGE_TIMEFRAMES)
    assert res.fetch_timeout == n_tf, \
        "a timeframe of the sick symbol was never attempted — starvation is back"
    assert res.timeframes_degraded_after_failure == n_tf - 1
    assert res.timeframes_attempted == 3 * n_tf, "one timeframe went unattempted"
    assert res.bars_persisted > 0, "healthy symbols still stored"
    assert any("BBB" in f for f in res.failures)


@pytest.mark.asyncio
async def test_A3b_one_symbol_db_outage_does_not_stop_the_others():
    reg = []
    fail = lambda stmt: "AAA" in str(stmt) if False else False   # noqa: E731

    class F:
        def __init__(self):
            self.n = 0

        def __call__(self):
            self.n += 1
            # n == 1 is A3c's watermark session; it must stay healthy so this
            # test keeps measuring isolation and not watermark fallback.
            # A3c-repair-v2: only the FIRST item of the first symbol may fail —
            # the symbol is then abandoned, so session 3 already belongs to the
            # second symbol.
            bad = self.n == 2
            return FakeSession(reg, fail_on=(lambda s: bad))

    res = await collect_once(F(), Collector("ok"), symbols=["AAA", "BBB"])
    assert res.symbols_failed == 1 and res.symbols_succeeded == 1
    assert res.db_error > 0
    assert not res.watermark_failed, "the watermark read was not the failure here"


@pytest.mark.asyncio
async def test_A3b_an_exception_escaping_the_writer_isolates_to_that_item():
    """The outer handler, exercised for real.

    `collect_and_persist` swallows its own errors, so the collector's
    `except Exception` is only reachable when something OUTSIDE it fails —
    e.g. the session cannot be created at all (pool exhausted, DB unreachable).
    Without this, that handler is untested and could be narrowed to a type that
    never fires while every test still passed.
    """
    calls = {"n": 0}

    def exploding_factory():
        calls["n"] += 1
        # A3c-repair-v2: the first symbol is ABANDONED after one terminal
        # failure, so only its first item may raise — targeting call 3 as well
        # would land on the SECOND symbol and destroy what this test measures.
        if calls["n"] == 2:             # the first item of the first symbol
            raise RuntimeError("pool exhausted")
        return FakeSession([])

    res = await collect_once(exploding_factory, Collector("ok"),
                             symbols=["AAA", "BBB"])
    assert res.symbols_attempted == 2
    assert res.symbols_failed == 1 and res.symbols_succeeded == 1
    # one raise, because the symbol is abandoned after it. The isolation
    # contract is the two assertions above and the two below, not this count.
    assert res.db_error == 1
    assert any("pool exhausted" in f for f in res.failures)
    assert res.bars_persisted > 0, "the healthy symbol still stored bars"
    assert res.healthy is False


@pytest.mark.asyncio
@pytest.mark.parametrize("behaviour,expect", [
    ("empty", "empty"), ("malformed", "malformed"), ("reversed", "ordered"),
])
async def test_A3b_degenerate_responses_are_classified_not_crashes(behaviour, expect):
    res = await collect_once(factory([]), Collector(behaviour), symbols=["AAA"])
    assert res.symbols_attempted == 1
    if expect == "malformed":
        assert res.malformed_response > 0 and res.bars_persisted == 0
    elif expect == "empty":
        assert res.bars_persisted == 0 and res.db_error == 0
    else:
        assert res.bars_persisted > 0


@pytest.mark.asyncio
async def test_A3b_retries_are_bounded_and_exhaustion_is_reported():
    col = Collector("err")
    res = await collect_once(factory([]), col, symbols=["AAA"], retries=2)
    per_tf = 3
    n_tf = len(STORAGE_TIMEFRAMES)
    # A3c-repair-v4: retries stay bounded PER ITEM (3 attempts). The symbol is no
    # longer abandoned after the first exhaustion — every timeframe is attempted,
    # so the call count is per_tf on each of the four. This fixture fails
    # instantly; a sibling that actually STALLED would instead be cut by the
    # reduced budget long before its third 20 s attempt, which is what keeps the
    # cost bounded without dropping coverage.
    assert len(col.calls) == per_tf * n_tf, \
        "a timeframe was never attempted — starvation is back"
    assert res.retry_exhausted == n_tf
    assert res.timeframes_degraded_after_failure == n_tf - 1
    assert res.timeframes_attempted == n_tf
    assert res.symbols_failed == 1 and res.healthy is False


# ══ A3b · closure / idempotency ═════════════════════════════════════════════
@pytest.mark.asyncio
async def test_A3b_forming_newest_bar_is_excluded_without_extra_loss():
    """The writer already owns closure. The collector adds no second rule, so a
    live response loses exactly the forming bar and no closed one."""
    from app.services.ohlcv_writer import eligible_bars
    df = frame(5, "15m")
    live_now = T0 + 4 * STEP + timedelta(minutes=1)       # last bar still forming
    got, r = eligible_bars(df, "AAA", "15m", now=live_now)
    assert len(got) == 4 and r.forming_or_not_closed == 1
    closed_bars = 4
    assert len(got) == closed_bars, "no extra closed-bar penalty on a live window"


def test_A3b_conflict_target_is_the_column_list_never_a_constraint_name():
    src = (BACKEND / "app" / "services" / "ohlcv_writer.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", " ", src)
    code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
    assert "index_elements" in code
    assert "uq_ohlcv_bars_natural" not in code and "constraint=" not in code


@pytest.mark.asyncio
async def test_A3b_a_repeated_run_is_idempotent_at_the_call_level():
    col = Collector("ok")
    r1 = await collect_once(factory([]), col, symbols=["AAA"])
    r2 = await collect_once(factory([]), col, symbols=["AAA"])
    assert r1.bars_eligible == r2.bars_eligible, "same window, same decision"


# ══ A3b · DORMANCY ══════════════════════════════════════════════════════════
def test_A3b_module_level_is_inert():
    tree = ast.parse((BACKEND / "app" / "services" / "ohlcv_collector_job.py")
                     .read_text(encoding="utf-8"))
    for node in tree.body:
        assert isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign,
                                 ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)), type(node).__name__
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant), "only a docstring may execute"
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                assert n.func.attr not in ("create_task", "add_job", "run", "ensure_future"), \
                    f"module level must not schedule: {n.func.attr}"


def test_A3b_nothing_in_production_calls_the_collector():
    hits = []
    for root in ("app", "scripts"):
        for p in (BACKEND / root).rglob("*.py"):
            # ohlcv_progression.py joined the dormant subsystem in 0012: it holds
            # the fairness counter and is imported only by the collector, so it is
            # part of what must stay dormant — not something that wires it up.
            if p.name in ("ohlcv_collector_job.py",
                          "ohlcv_progression.py") or "__pycache__" in str(p):
                continue
            if re.search(r"ohlcv_collector_job|collect_once", p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(p.relative_to(BACKEND).as_posix())
    # A3c IS NOW ACTIVATED, so "nothing wires it" is obsolete. The invariant that
    # survives is stronger than the old empty-list check: EXACTLY ONE file may
    # reach the collector, it must be the scheduler, and it must do so only
    # through the ratified entry point.
    assert hits == ["app/services/scheduler.py"], \
        f"expected exactly one OHLCV caller (the scheduler), found {hits}"
    sched = (BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8")
    assert "collect_once" not in sched, "scheduler bypasses run_collection_once"
    assert "collect_and_persist" not in sched and "ohlcv_writer" not in sched, \
        "scheduler reaches into the writer directly"
    # Structural, not a raw count: the docstring legitimately names the entry
    # point, so counting text would make this guard depend on prose.
    tree = ast.parse(sched)
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
               and n.module == "app.services.ohlcv_collector_job"]
    assert len(imports) == 1, f"expected exactly one lazy import, got {len(imports)}"
    # AN EXACT ALLOW-LIST, deliberately not "run_collection_once is among them":
    # the entry point, plus the canonical K the job must bind explicitly. A
    # CONSTANT is not an execution path — the execution-path invariant is carried
    # by the three assertions above and by the single-call check below — but
    # anything else appearing here still fails, which is the point. K is imported
    # rather than repeated as a literal so there is exactly one K in the runtime;
    # see test_ohlcv_activation_registration.py for the binding guards.
    assert sorted(a.name for a in imports[0].names) == \
        ["SYMBOLS_PER_RUN", "run_collection_once"], \
        [a.name for a in imports[0].names]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "run_collection_once"]
    assert len(calls) == 1, f"expected exactly one call, got {len(calls)}"


def test_A3b_scheduler_and_main_do_not_reference_it():
    # A3c IS NOW ACTIVATED: scheduler.py is the ONE allowed caller, via
    # run_collection_once only. See tests/test_ohlcv_activation_registration.py.
    for rel in ("app/main.py",
                "app/api/routes/signals.py"):
        code = (BACKEND / rel).read_text(encoding="utf-8")
        code = re.sub(r"#[^\n]*", " ", code)
        code = re.sub(r'"""(?:.|\n)*?"""', " ", code)
        for token in ("ohlcv_collector_job", "collect_once", "ohlcv_writer",
                      "collect_and_persist"):
            assert token not in code, f"{rel} references {token}"


def test_A3b_no_ohlcv_job_is_registered():
    src = (BACKEND / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    ids = re.findall(r'id="([^"]+)"', src)
    # A3c was activated and then DISABLED in the same session: the first genuine
    # run was cancelled at 148.196 s against the frozen 78.947 s gate. The
    # registration is gone; scheduler.py still contains _job_ohlcv_collect and
    # the JobSpec, which is why this guard checks the REGISTRATION and not the
    # mere presence of the string. See tests/test_ohlcv_activation_registration.py.
    assert [i for i in ids if "ohlcv" in i.lower()] == [], ids
    assert sorted(ids) == ["perf_tracking", "price_alerts",
                           "signals_15m", "signals_1d", "signals_1h",
                           "signals_4h", "startup_check"], ids


def test_A3b_the_collector_imports_no_decision_module():
    tree = ast.parse((BACKEND / "app" / "services" / "ohlcv_collector_job.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    for forbidden in ("scheduler", "tracker", "lifecycle", "resolution",
                      "entry_activation", "entry_flags", "publication",
                      "coin_memory", "signal_generator", "shadow_eval"):
        assert not any(forbidden in m for m in mods), f"{forbidden} in {mods}"


def test_A3b_adds_no_migration():
    """A3b shipped no migration of its own, and nothing added later may reshape
    the table it depends on.

    This used to assert `names[-1] == "0011_ohlcv_shadow.sql"` — a LOCAL claim
    ("this checkpoint added no migration") proved by a GLOBAL fact ("nothing has
    been added to the repo since"). The first legitimate later migration breaks
    that, which is precisely what 0012 did. The repair is the one already applied
    to six sibling guards: pin the set A3b was written against BY NAME, and assert
    separately that no later migration touches `ohlcv_bars`."""
    names = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    assert "0011_ohlcv_shadow.sql" in names
    assert [n for n in names if n <= "0011_ohlcv_shadow.sql"][-1] == "0011_ohlcv_shadow.sql"
    for later in [n for n in names if n > "0011_ohlcv_shadow.sql"]:
        body = (BACKEND / "migrations" / later).read_text(encoding="utf-8").lower()
        body = " ".join(l for l in body.splitlines()
                        if not l.strip().startswith("--"))
        assert "ohlcv_bars" not in body, f"{later} reshapes ohlcv_bars"


# ══ telemetry must not become a trading input ═══════════════════════════════
def test_no_decision_surface_reads_collection_health():
    for rel in ("app/backtesting/tracker.py", "app/backtesting/resolution_core.py",
                "app/services/entry_activation.py", "app/services/publication.py",
                "app/services/coin_memory.py",
                "app/engines/ai_decision/signal_generator.py"):
        text = (BACKEND / rel).read_text(encoding="utf-8")
        for token in ("CollectionResult", "collect_once", "bars_persisted",
                      "universe_overflow"):
            assert token not in text, f"{rel} reads collection telemetry"
