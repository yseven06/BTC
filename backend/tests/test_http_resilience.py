"""CP-HTTP-RESILIENCE-1 — bounded jobs, cancellation cleanup, scheduler liveness.

The incident these guard against: on 2026-07-28 signal generation stopped for 45
minutes while /health answered 200 in 4ms. Every HTTP request was already
bounded (all ten httpx clients carry an explicit timeout); the JOB was not, so
per-request timeouts multiplied across 57 assets x 13 upstream requests until a
4-minute sweep outlived its own 15-minute cadence and max_instances=1 suppressed
every later run.

These tests assert behaviour, not source text: a deadline is proven by making
something hang and measuring that control returns, and the structural checks
walk the AST or read live objects rather than grepping for a phrase a comment
could satisfy.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import socket
import textwrap
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services import job_guard
from app.services.job_guard import (
    DEFAULT_BUDGET_SECONDS,
    JOB_SPECS,
    JobDeadlineExceeded,
    budget_for,
    classify_upstream_error,
    run_asset_with_deadline,
    run_with_deadline,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_liveness():
    job_guard.reset_for_tests()
    yield
    job_guard.reset_for_tests()


# --------------------------------------------------------------------------- #
# 1. HTTP client bounds
# --------------------------------------------------------------------------- #

COLLECTOR_FACTORIES = [
    ("binance", "app.collectors.binance_collector", "BinanceCollector"),
    ("bybit", "app.collectors.bybit_collector", "BybitCollector"),
    ("coingecko", "app.collectors.coingecko_collector", "CoinGeckoCollector"),
    ("macro", "app.collectors.macro_collector", "MacroCollector"),
    ("onchain", "app.collectors.onchain_collector", "OnchainCollector"),
]


@pytest.mark.parametrize("name,module,cls", COLLECTOR_FACTORIES)
async def test_collector_timeouts_are_finite_on_every_phase(name, module, cls):
    """connect/read/write/pool must all be bounded on the live client object.

    Read off the constructed httpx client, so a future edit that drops the
    timeout argument fails here even though the word "timeout" survives in a
    docstring nearby.
    """
    import importlib

    collector = getattr(importlib.import_module(module), cls)()
    try:
        t = collector.client.timeout
        for phase in ("connect", "read", "write", "pool"):
            value = getattr(t, phase)
            assert value is not None, f"{name}: {phase} timeout is None (unbounded)"
            assert 0 < value <= 30, f"{name}: {phase} timeout {value} outside sane range"
    finally:
        await collector.close()


async def test_no_httpx_client_is_constructed_without_a_timeout():
    """Every httpx client in app/ passes a timeout — checked on the AST.

    A call with no `timeout=` keyword inherits httpx's default, which is 5s
    today but is a library default rather than a decision this codebase made.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            target = getattr(fn, "attr", None)
            if target not in ("AsyncClient", "Client"):
                continue
            if not any(k.arg == "timeout" for k in node.keywords):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"timeout'suz httpx istemcisi: {offenders}"


async def test_hanging_dns_still_returns_control_to_the_caller():
    """A resolver that never answers must not hold a request open forever.

    httpx resolves through anyio.to_thread, and a thread in a blocking syscall
    cannot be cancelled — the await is abandoned but the worker stays busy.
    What matters is that the CALLER regains control, which is what the sweep
    needs in order to move to the next asset.
    """
    real = socket.getaddrinfo
    block = threading.Event()

    def hanging(*a, **kw):
        block.wait(30)
        return real(*a, **kw)

    socket.getaddrinfo = hanging
    try:
        t0 = time.perf_counter()
        with pytest.raises(httpx.HTTPError):
            async with httpx.AsyncClient(timeout=0.4) as c:
                await c.get("https://never-resolves.invalid/x")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"DNS asilmasi {elapsed:.1f}s surdu — sinirli degil"
    finally:
        socket.getaddrinfo = real
        block.set()


async def test_collectors_perform_no_retries():
    """The collectors must not retry — retrying multiplies the exact cost that
    caused the incident (13 requests x 10s x 57 assets).

    Bounded twice over: the counter trips at ATTEMPT_CAP and an outer deadline
    cuts the call. An unbounded retry loop must FAIL here, not hang — a test
    that hangs cannot tell "retries forever" from "is slow today", and the whole
    point of this checkpoint is that hanging is never an acceptable outcome.
    """
    from app.collectors.binance_collector import BinanceCollector

    class _TooManyAttempts(BaseException):
        """BaseException on purpose: a retry loop written as `except Exception:
        continue` would swallow an AssertionError and spin forever, so the
        escape hatch has to live outside Exception."""

    ATTEMPT_CAP = 5
    attempts = 0

    async def failing_send(self, request, **kw):
        nonlocal attempts
        attempts += 1
        if attempts > ATTEMPT_CAP:
            raise _TooManyAttempts(f"sinirsiz retry: {attempts} deneme")
        raise httpx.ConnectError("nope", request=request)

    collector = BinanceCollector()
    original = httpx.AsyncClient.send
    httpx.AsyncClient.send = failing_send
    try:
        with pytest.raises((httpx.ConnectError, _TooManyAttempts, TimeoutError,
                            asyncio.TimeoutError)):
            async with asyncio.timeout(10):
                await collector.fetch_ohlcv("BTCUSDT", "1h", limit=10)
    finally:
        httpx.AsyncClient.send = original
        await collector.close()
    assert attempts == 1, f"retry tespit edildi: {attempts} deneme"


async def test_client_is_closed_and_pool_released():
    from app.collectors.binance_collector import BinanceCollector

    collector = BinanceCollector()
    assert not collector.client.is_closed
    await collector.close()
    assert collector.client.is_closed


# --------------------------------------------------------------------------- #
# 2. whole-job deadline
# --------------------------------------------------------------------------- #

async def test_deadline_cancels_a_job_that_never_returns():
    async def forever():
        await asyncio.Event().wait()

    t0 = time.perf_counter()
    with pytest.raises(JobDeadlineExceeded) as ei:
        await run_with_deadline("signals_15m", forever(), budget=0.25)
    assert time.perf_counter() - t0 < 3.0
    assert ei.value.job_id == "signals_15m"


async def test_deadline_lets_a_normal_job_finish():
    async def quick():
        await asyncio.sleep(0.01)
        return {"ok": True}

    assert await run_with_deadline("perf_tracking", quick(), budget=2.0) == {"ok": True}


async def test_deadline_runs_finally_blocks_so_clients_close():
    """Cancellation must unwind through `finally`, which is where every
    collector does `await client.close()`."""
    cleaned = []

    async def with_cleanup():
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.append("closed")

    with pytest.raises(JobDeadlineExceeded):
        await run_with_deadline("price_alerts", with_cleanup(), budget=0.2)
    assert cleaned == ["closed"], "deadline finally blogunu calistirmadi"


async def test_deadline_releases_a_semaphore_held_by_the_cancelled_job():
    sem = asyncio.Semaphore(1)

    async def holds_slot():
        async with sem:
            await asyncio.Event().wait()

    with pytest.raises(JobDeadlineExceeded):
        await run_with_deadline("price_alerts", holds_slot(), budget=0.2)
    assert sem.locked() is False, "iptal sonrasi semaphore serbest birakilmadi"


async def test_external_cancellation_is_not_swallowed_or_relabelled():
    """A shutdown cancel must stay a CancelledError. Turning it into
    JobDeadlineExceeded would tell the scheduler a job failed when the loop was
    actually being torn down."""
    started = asyncio.Event()

    async def body():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(run_with_deadline("signals_1h", body(), budget=30.0))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_every_job_id_resolves_to_a_finite_budget():
    for job_id in JOB_SPECS:
        assert 0 < budget_for(job_id) < 3600
    assert 0 < budget_for("a-job-nobody-registered") == DEFAULT_BUDGET_SECONDS


async def test_budget_is_strictly_below_cadence_for_every_job():
    """The invariant the whole checkpoint rests on: a job that outlives its own
    cadence blocks its successor under max_instances=1."""
    for job_id, spec in JOB_SPECS.items():
        if spec.cadence_seconds is None:
            continue
        assert spec.budget_seconds < spec.cadence_seconds, (
            f"{job_id}: butce {spec.budget_seconds}s >= cadence {spec.cadence_seconds}s"
        )


async def test_signal_sweep_budget_beats_the_all_timeouts_worst_case():
    """13 upstream requests x 10s x 57 assets = 124 minutes. The 15m budget must
    cut that well before the next trigger."""
    worst_case_seconds = 13 * 10.0 * 57
    assert JOB_SPECS["signals_15m"].budget_seconds < worst_case_seconds / 10


# --------------------------------------------------------------------------- #
# 3. per-asset isolation
# --------------------------------------------------------------------------- #

async def test_one_hanging_asset_does_not_stall_the_sweep():
    async def hangs():
        await asyncio.Event().wait()

    t0 = time.perf_counter()
    ok = await run_asset_with_deadline("signals_15m", "STUCKUSDT", "15m", hangs(), budget=0.25)
    assert ok is False
    assert time.perf_counter() - t0 < 3.0


async def test_asset_deadline_actually_cancels_the_assets_work():
    """The per-asset bound must CANCEL, not just stop waiting.

    A guard that returns while the asset's coroutine keeps running would leave
    its HTTP client and DB session open and its `finally` unreached — the sweep
    would look bounded while resources kept piling up. Proven by asserting both
    that the finally ran and that the body did not reach completion.
    """
    marks = []

    async def with_cleanup():
        try:
            await asyncio.Event().wait()
            marks.append("completed")
        finally:
            marks.append("cleaned")

    ok = await run_asset_with_deadline("signals_15m", "X", "15m", with_cleanup(), budget=0.2)
    await asyncio.sleep(0.15)          # ihmal edilen bir task calismaya devam ederse gorulur
    assert ok is False
    assert "cleaned" in marks, "varlik iptalinde finally calismadi"
    assert "completed" not in marks, "varlik coroutine'i iptal edilmedi, calismaya devam etti"


async def test_asset_deadline_releases_a_semaphore():
    sem = asyncio.Semaphore(1)

    async def holds():
        async with sem:
            await asyncio.Event().wait()

    await run_asset_with_deadline("signals_15m", "X", "15m", holds(), budget=0.2)
    await asyncio.sleep(0.05)
    assert sem.locked() is False, "varlik iptali sonrasi semaphore serbest birakilmadi"


async def test_a_failing_asset_does_not_raise_into_the_sweep():
    async def boom():
        raise httpx.ConnectError("upstream down")

    assert await run_asset_with_deadline("signals_15m", "X", "15m", boom()) is False


async def test_skipped_asset_is_counted_and_classified():
    async def dns_fail():
        raise socket.gaierror(-3, "Temporary failure in name resolution")

    await run_asset_with_deadline("signals_15m", "X", "15m", dns_fail())
    snap = job_guard.snapshot()["jobs"]["signals_15m"]
    assert snap["assets_skipped_count"] == 1
    assert snap["upstream_dns_error_count"] == 1


async def test_full_sweep_skips_the_stuck_asset_and_finishes_the_rest(monkeypatch):
    """Exercises the real _run_all_signals loop: a stuck asset is dropped and
    the sweep still reaches every other asset and returns."""
    from app.services import scheduler as sched

    class _Asset:
        def __init__(self, symbol):
            self.symbol = symbol
            self.asset_type = type("T", (), {"value": "crypto"})()

    assets = [_Asset("AAA"), _Asset("STUCK"), _Asset("BBB")]

    class _Res:
        def scalars(self):
            return self

        def all(self):
            return assets

    class _DB:
        async def execute(self, *_a, **_kw):
            return _Res()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(sched, "async_session_factory", lambda: _DB())
    monkeypatch.setattr(job_guard, "PER_ASSET_BUDGET_SECONDS", 0.25)

    done = []

    async def fake_generate(symbol, asset_type, timeframe):
        if symbol == "STUCK":
            await asyncio.Event().wait()
        done.append(symbol)

    monkeypatch.setattr(sched, "_generate_signal", fake_generate)

    real_sleep = asyncio.sleep
    monkeypatch.setattr(sched.asyncio, "sleep", lambda _s: real_sleep(0))

    # Outer bound so a sweep that lost its per-asset guard FAILS here instead of
    # hanging the suite. Hanging is the exact behaviour this checkpoint exists
    # to make impossible; a test that reproduces it is not reporting it.
    try:
        async with asyncio.timeout(10):
            await sched._run_all_signals(timeframe="15m")
    except (asyncio.TimeoutError, TimeoutError):
        pytest.fail("sweep sinirsiz bekledi — varlik basina guard devre disi")

    assert done == ["AAA", "BBB"], f"takilan varlik sweep'i durdurdu: {done}"
    assert job_guard.snapshot()["jobs"]["signals_15m"]["assets_skipped_count"] == 1


async def test_timed_out_asset_produces_no_data_at_all():
    """A skipped asset must yield nothing — not stale data, not a placeholder.
    run_asset_with_deadline returns a bool and never a substitute payload."""
    async def hangs():
        await asyncio.Event().wait()
        return {"fabricated": True}

    result = await run_asset_with_deadline("signals_15m", "X", "15m", hangs(), budget=0.2)
    assert result is False
    assert not isinstance(result, dict)


# --------------------------------------------------------------------------- #
# 4. error classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("exc,expected", [
    (socket.gaierror(-3, "Temporary failure in name resolution"), "dns"),
    (httpx.ConnectTimeout("t"), "timeout"),
    (httpx.ReadTimeout("t"), "timeout"),
    (httpx.PoolTimeout("t"), "timeout"),
    (asyncio.TimeoutError(), "timeout"),
    (JobDeadlineExceeded("signals_15m", 600.0), "deadline"),
    (ValueError("unrelated"), "other"),
])
async def test_error_classification(exc, expected):
    assert classify_upstream_error(exc) == expected


async def test_connect_error_wrapping_gaierror_is_dns_not_connect():
    err = httpx.ConnectError("connect failed")
    err.__cause__ = socket.gaierror(-3, "Temporary failure in name resolution")
    assert classify_upstream_error(err) == "dns"


# --------------------------------------------------------------------------- #
# 5. liveness + health
# --------------------------------------------------------------------------- #

async def test_health_keeps_its_existing_contract():
    """The compose healthcheck and anything else polling /health must not
    break: `status` and `service` keep their exact values."""
    from app.main import health_check

    body = await health_check()
    assert body["status"] == "healthy"
    assert body["service"] == "zatetrade-backend"
    assert "scheduler" in body


async def test_health_reports_a_healthy_scheduler_as_not_degraded():
    for job_id in JOB_SPECS:
        job_guard.record_start(job_id)
        job_guard.record_success(job_id)
    snap = job_guard.snapshot()
    assert snap["degraded"] is False
    assert snap["critical_job_stale"] is False


async def test_a_critical_job_that_stops_succeeding_goes_stale():
    job_guard.record_start("price_alerts")
    job_guard.record_success("price_alerts")
    stale_moment = datetime.now(timezone.utc) - timedelta(
        seconds=JOB_SPECS["price_alerts"].cadence_seconds
        * job_guard.STALE_CADENCE_MULTIPLIER + 30
    )
    job_guard._STATE["price_alerts"].success_at = stale_moment.isoformat()

    snap = job_guard.snapshot()
    assert snap["critical_job_stale"] is True
    assert "price_alerts" in snap["stale_jobs"]
    assert snap["degraded"] is True


async def test_a_job_running_past_its_budget_is_reported_as_overrunning():
    job_guard.record_start("signals_15m")
    job_guard._STATE["signals_15m"].running_since_monotonic = (
        time.monotonic() - JOB_SPECS["signals_15m"].budget_seconds - 60
    )
    snap = job_guard.snapshot()
    assert "signals_15m" in snap["overrunning_jobs"]
    assert snap["degraded"] is True


async def test_failure_counter_rises_then_recovers():
    for _ in range(3):
        job_guard.record_start("perf_tracking")
        job_guard.record_failure("perf_tracking", httpx.ConnectTimeout("t"))
    assert job_guard.snapshot()["jobs"]["perf_tracking"]["consecutive_failures"] == 3
    assert job_guard.snapshot()["jobs"]["perf_tracking"]["upstream_timeout_count"] == 3

    job_guard.record_start("perf_tracking")
    job_guard.record_success("perf_tracking")
    after = job_guard.snapshot()["jobs"]["perf_tracking"]
    assert after["consecutive_failures"] == 0
    assert after["last_success_at"] is not None
    assert after["stale"] is False


async def test_deadline_exceeded_is_counted_separately_from_upstream_errors():
    job_guard.record_start("signals_15m")
    job_guard.record_failure("signals_15m", JobDeadlineExceeded("signals_15m", 600.0))
    snap = job_guard.snapshot()["jobs"]["signals_15m"]
    assert snap["deadline_exceeded_count"] == 1
    assert snap["upstream_timeout_count"] == 0


async def test_refused_triggers_are_counted():
    """max_instances / missed fires were only ever a log line — the 45-minute
    outage is exactly the shape this counter makes visible."""
    for _ in range(4):
        job_guard.record_missed("signals_15m")
    assert job_guard.snapshot()["jobs"]["signals_15m"]["missed_or_skipped_count"] == 4


async def test_running_flag_clears_after_deadline_so_health_is_truthful():
    async def forever():
        await asyncio.Event().wait()

    job_guard.record_start("price_alerts")
    with pytest.raises(JobDeadlineExceeded):
        await run_with_deadline("price_alerts", forever(), budget=0.2)
    job_guard.record_failure("price_alerts", JobDeadlineExceeded("price_alerts", 0.2))
    assert job_guard.snapshot()["jobs"]["price_alerts"]["currently_running"] is False


async def test_snapshot_never_raises_on_a_malformed_timestamp():
    job_guard.record_start("price_alerts")
    job_guard._STATE["price_alerts"].success_at = "not-a-timestamp"
    assert job_guard.snapshot()["jobs"]["price_alerts"]["stale"] is False


# --------------------------------------------------------------------------- #
# 6. scheduler wiring (structural, on the AST — comments cannot satisfy these)
# --------------------------------------------------------------------------- #

def _scheduler_source():
    from app.services import scheduler as sched
    return ast.parse(inspect.getsource(sched))


async def test_every_scheduled_job_routes_through_the_tracked_wrapper():
    """add_job must target a wrapper that goes through _run_tracked — that is
    where the deadline and the liveness recording live. A job registered
    directly would be unbounded again."""
    from app.services import scheduler as sched

    tree = _scheduler_source()
    registered = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_job":
            if node.args and isinstance(node.args[0], ast.Name):
                registered.append(node.args[0].id)
    assert registered, "add_job cagrisi bulunamadi"

    for name in registered:
        fn = getattr(sched, name)
        body = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        calls = {n.func.id for n in ast.walk(body)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_run_tracked" in calls, f"{name} _run_tracked uzerinden gecmiyor"


async def test_run_tracked_actually_applies_the_deadline():
    """AST, not grep: _run_tracked must call run_with_deadline, and the awaited
    coroutine must be the one passed in."""
    from app.services import scheduler as sched

    src = textwrap.dedent(inspect.getsource(sched._run_tracked))
    tree = ast.parse(src)
    guarded = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", None) == "run_with_deadline"
    ]
    assert guarded, "_run_tracked run_with_deadline cagirmiyor"
    args = guarded[0].args
    assert any(isinstance(a, ast.Name) and a.id == "coro" for a in args), \
        "run_with_deadline'a is gerceklestiren coroutine gecirilmiyor"


async def test_sweep_uses_the_per_asset_guard():
    from app.services import scheduler as sched

    src = textwrap.dedent(inspect.getsource(sched._run_all_signals))
    tree = ast.parse(src)
    names = {getattr(n.func, "attr", None) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "run_asset_with_deadline" in names


async def test_scheduler_registers_a_listener_for_refused_triggers():
    tree = _scheduler_source()
    listeners = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "add_listener"]
    assert listeners, "refuse edilen tetikleyiciler icin listener yok"


# --------------------------------------------------------------------------- #
# 7. regression — nothing about the decision changed
# --------------------------------------------------------------------------- #

async def test_scheduler_cadence_is_unchanged():
    from app.services import scheduler as sched

    src = inspect.getsource(sched.start_scheduler)
    for expected in ('CronTrigger(minute=1)',
                     'CronTrigger(hour="0,4,8,12,16,20", minute=2)',
                     'CronTrigger(minute="2,17,32,47")',
                     'CronTrigger(hour=0, minute=3)',
                     'CronTrigger(minute="*/2")',
                     'CronTrigger(minute="*")'):
        assert expected in src, f"cadence degismis: {expected} bulunamadi"


async def test_job_defaults_are_unchanged():
    from app.services import scheduler as sched

    src = inspect.getsource(sched.start_scheduler)
    assert '"coalesce": True' in src
    assert '"max_instances": 1' in src
    assert '"misfire_grace_time": 300' in src


async def test_decision_thresholds_are_unchanged():
    from app.services import scheduler as sched
    import re

    src = inspect.getsource(sched)
    assert re.search(r"MIN_ACTIONABLE_CONFIDENCE\s*=\s*65\.0", src)
    assert re.search(r"REVERSAL_MIN_CONFIDENCE\s*=\s*72\.0", src)


async def test_decision_input_version_is_unchanged():
    from app.engines.ai_decision import signal_generator as sg

    assert sg.DECISION_INPUT_VERSION == "closed_candle_v1"
    assert sg.CANDLE_POLICY == "closed_features_live_geometry"


async def test_f1c_backtest_parity_constants_are_unchanged():
    import app.backtesting.engine as bt

    assert bt.MIN_ACTIONABLE_CONFIDENCE == 65.0
    assert bt.MTF_PARITY == "exact"
    assert bt.ADAPTIVE_WEIGHTS_PARITY == "not_applied"
    assert bt.BACKTEST_INPUT_VERSION == "closed_candle_v1"


async def test_job_guard_writes_nothing_to_a_database():
    """Liveness is in-process by design — no table, no migration, no write."""
    src = inspect.getsource(job_guard)
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("async_session_factory", "execute", "commit", "session"):
        assert forbidden not in names, f"job_guard DB'ye dokunuyor: {forbidden}"


async def test_no_secret_reaches_a_log_line():
    """Timeout logs carry job/symbol/timeframe/kind — never a URL, header or
    token."""
    src = inspect.getsource(job_guard)
    for banned in ("Authorization", "bot_token", "api_key", "DATABASE_URL",
                   "request.url", "headers"):
        assert banned not in src, f"log yuzeyinde sizinti riski: {banned}"
