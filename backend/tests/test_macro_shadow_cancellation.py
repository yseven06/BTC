"""CP-MACRO-SHADOW-CANCELLATION-PROPAGATION — a cancel is control flow, not telemetry.

WHAT WAS WRONG
    Two `except BaseException` handlers on the shadow fetch path absorbed
    `asyncio.CancelledError`. A forensic pass drove the real code and measured
    what each one produced:

      * `_fetch_fresh`  — an external cancel came out as a SNAPSHOT with
        `fetch_status=internal_error` and `error_class=CancelledError` on BOTH
        series. An internal failure that never happened, written to a candidate.
        This was the frame that mattered: the outer handler was never reached.
      * `get_shadow_macro_snapshot` — a cancel while queueing on the
        single-flight lock came out as `None`.

    `_fetch_one` re-raises `CancelledError` and always did, with a comment
    explaining why. That re-raise was then caught one frame up, so its stated
    purpose held only for the INTERNAL `asyncio.timeout` and never for an
    external cancel.

WHY IT MATTERS
    `get_shadow_macro_snapshot` is awaited from exactly one production site —
    `scheduler.py:345`, inside `_generate_signal`, before its database block.
    Returning instead of raising let a scan the guard had already given up on
    walk on and write a candidate, which is the opposite of what
    `run_asset_with_deadline` documents: "no candidate is written and nothing is
    fabricated".

WHAT MUST NOT MOVE
    The 6 s bound. `asyncio.timeout` converts its OWN expiry to `TimeoutError`
    before it leaves the block, so that path still classifies as `timeout` and
    never reaches the new clause. That is asserted here, because "we did not
    break the timeout" is exactly the claim that quietly stops being true.

No test here can reach the network.
"""
import asyncio

import httpx
import pytest

from app.services import macro_shadow as ms
from app.services import macro_shadow_fetch as msf

SYNTHETIC_KEY = "synthetic-not-a-real-fred-key"
SERIES_COUNT = len(ms.SCORED_SERIES)


class _Settings:
    MACRO_SHADOW_FETCH_ENABLED = True
    FRED_API_KEY = SYNTHETIC_KEY
    MACRO_FRED_FETCH_ENABLED = False


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    msf.reset_cache_for_tests()
    monkeypatch.setattr(msf, "get_settings", lambda: _Settings())
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    yield
    msf.reset_cache_for_tests()


def _transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def _client(*a, **kw):
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(msf.httpx, "AsyncClient", _client)


def _hanging(started=None, calls=None):
    async def _h(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.params.get("series_id"))
        if started is not None:
            started.set()
        await asyncio.sleep(3600)             # the cancel lands here
        return httpx.Response(200, json={"observations": []})
    return _h


def _ok(date="2026-06-01"):
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "observations": [{"date": date, "value": "4.33"}]})
    return _h


async def _await_started(event, limit=200):
    for _ in range(limit):
        if event.is_set():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the fetch never started — the test measured nothing")


# ══════════════════════════════════════════════════════════════════════════════
# 1 · BOTH BOUNDARIES PROPAGATE
# ══════════════════════════════════════════════════════════════════════════════
def test_a_cancel_during_the_fetch_propagates(monkeypatch):
    """`_fetch_fresh`'s boundary. This is the one that used to produce
    `internal_error` / `CancelledError` on both series."""
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))

    async def _run():
        task = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled(), "the cancel was converted into a result"

    asyncio.run(_run())


def test_a_cancel_during_the_fetch_writes_no_snapshot(monkeypatch):
    """The old behaviour is asserted ABSENT by its fingerprint, so a partial
    revert that keeps raising but still records something is caught too."""
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))

    async def _run():
        task = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Nothing cached, and no completed cycle for a waiter to inherit.
        assert msf.cache_key() not in msf._SHADOW_CACHE
        assert msf._cycle_seq(msf.cache_key()) == 0, \
            "a cancelled fetch was recorded as a completed cycle"

    asyncio.run(_run())


def test_a_cancel_while_queueing_on_the_lock_propagates(monkeypatch):
    """`get_shadow_macro_snapshot`'s boundary — the caller never reached the
    fetch at all, so this exercises the outer handler specifically."""
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))

    async def _run():
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        await asyncio.sleep(0.02)
        assert msf._lock_for(msf.cache_key()).locked(), \
            "precondition: the leader holds the lock"

        waiter = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await asyncio.sleep(0.03)
        assert not waiter.done(), "precondition: the waiter is queueing"

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert waiter.cancelled()

        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader

    asyncio.run(_run())


def test_the_cancelled_caller_never_reaches_its_next_statement(monkeypatch):
    """Why this checkpoint exists, in the caller's shape.

    `_generate_signal` awaits the snapshot and then opens a database session and
    writes a candidate. While the cancel was absorbed, that next statement RAN
    for a scan the guard had already abandoned. Modelled here with a flag rather
    than a database, so the assertion is about control flow and nothing else.
    """
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))
    wrote = []

    async def _caller():
        await msf.get_shadow_macro_snapshot(job_id="signals_15m")
        wrote.append("candidate")             # the DB block in the real caller

    async def _run():
        task = asyncio.create_task(_caller())
        await _await_started(started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())
    assert wrote == [], "a cancelled scan still wrote its candidate"


# ══════════════════════════════════════════════════════════════════════════════
# 2 · THE 6 s BOUND IS UNTOUCHED
# ══════════════════════════════════════════════════════════════════════════════
def test_the_internal_timeout_still_classifies_as_timeout(monkeypatch):
    """THE regression this change could plausibly cause.

    `asyncio.timeout` cancels its body to enforce the bound, so a naive reading
    says the new clause would swallow the deadline and let it escape as a
    cancellation. It does not: `asyncio.timeout` converts its OWN expiry to
    `TimeoutError` on the way out, and only a cancel from OUTSIDE arrives as
    `CancelledError`. Driven against a real hang and a shortened bound.
    """
    monkeypatch.setattr(msf, "SHADOW_FETCH_TIMEOUT_SECONDS", 0.2)
    _transport(monkeypatch, _hanging())

    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap is not None, "the internal timeout escaped as a cancellation"
    assert snap["fetch_status"] == "timeout"
    for sid in ms.SCORED_SERIES:
        assert snap["series"][sid]["fetch_status"] == "timeout"
        assert snap["series"][sid]["error_class"] is not None


def test_the_timeout_constant_is_unchanged():
    assert msf.SHADOW_FETCH_TIMEOUT_SECONDS == 6.0


# ══════════════════════════════════════════════════════════════════════════════
# 3 · THE LOCK, AND THE CALLERS BEHIND IT
# ══════════════════════════════════════════════════════════════════════════════
def test_the_lock_is_free_after_a_cancelled_leader(monkeypatch):
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))

    async def _run():
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        lock = msf._lock_for(msf.cache_key())
        assert lock.locked()
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        assert not lock.locked(), "a cancelled leader left the lock held"
        await asyncio.wait_for(lock.acquire(), timeout=1.0)
        lock.release()

    asyncio.run(_run())


def test_waiters_do_not_deadlock_when_the_leader_is_cancelled(monkeypatch):
    """The leader dies mid-flight and records no cycle. The waiters must wake,
    find the lock free, and complete — not hang behind a lock nobody holds."""
    started = asyncio.Event()
    calls = []

    def _handler(request):
        return _slow(request)

    async def _slow(request):
        calls.append(request.url.params.get("series_id"))
        started.set()
        await asyncio.sleep(0.4)
        return httpx.Response(200, json={
            "observations": [{"date": "2026-06-01", "value": "4.33"}]})

    _transport(monkeypatch, _slow)

    async def _run():
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        waiters = [asyncio.create_task(msf.get_shadow_macro_snapshot())
                   for _ in range(5)]
        await asyncio.sleep(0.02)
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        results = await asyncio.wait_for(asyncio.gather(*waiters), timeout=5)
        assert all(r is not None for r in results), "a waiter was left with nothing"
        assert all(r["fetch_status"] == "ok" for r in results)

    asyncio.run(_run())


# ══════════════════════════════════════════════════════════════════════════════
# 4 · EVERY OTHER PATH IS UNCHANGED
# ══════════════════════════════════════════════════════════════════════════════
def test_the_normal_fetch_is_unchanged(monkeypatch):
    _transport(monkeypatch, _ok())
    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap["fetch_status"] == "ok"
    assert snap["cache_status"] == "miss"
    assert snap["observation_time"] == "2026-06-01"
    assert set(snap["series"]) == set(ms.SCORED_SERIES)


def test_the_cache_hit_is_unchanged(monkeypatch):
    _transport(monkeypatch, _ok())

    async def _run():
        first = await msf.get_shadow_macro_snapshot()
        second = await msf.get_shadow_macro_snapshot()
        return first, second

    first, second = asyncio.run(_run())
    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert second["cache_age_s"] is not None
    assert second is not first


def test_a_transport_failure_is_still_fail_silent(monkeypatch):
    """Everything that is NOT a cancellation still becomes a snapshot rather
    than an exception — the fail-silent contract is untouched."""
    def _boom(request):
        raise httpx.ConnectError("down")
    _transport(monkeypatch, _boom)

    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap is not None, "a transport failure must not raise"
    assert snap["fetch_status"] != "ok"
    for sid in ms.SCORED_SERIES:
        assert snap["series"][sid]["error_class"] == "ConnectError"


def test_the_stale_path_is_still_served_on_a_non_cancel_failure(monkeypatch):
    """Stale serving lives inside the same handler the new clause sits in front
    of, so it is asserted explicitly: a FAILURE still reaches it."""
    _transport(monkeypatch, _ok())
    asyncio.run(msf.get_shadow_macro_snapshot())          # warm the cache

    entry = msf._SHADOW_CACHE[msf.cache_key()]
    entry["stored_at"] -= msf.SHADOW_CACHE_TTL_SECONDS + 1

    def _boom(request):
        raise httpx.ConnectError("down")
    _transport(monkeypatch, _boom)

    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap is not None
    assert snap["cache_status"] == "stale", snap["cache_status"]


def test_an_unexpected_error_still_returns_none(monkeypatch):
    """The outer boundary keeps absorbing everything that is not a cancel."""
    def _explode():
        raise RuntimeError("settings blew up")
    monkeypatch.setattr(msf, "get_settings", _explode)

    assert asyncio.run(msf.get_shadow_macro_snapshot()) is None


def test_the_disabled_path_is_unchanged(monkeypatch):
    class _Off:
        MACRO_SHADOW_FETCH_ENABLED = False
        FRED_API_KEY = SYNTHETIC_KEY
        MACRO_FRED_FETCH_ENABLED = False
    monkeypatch.setattr(msf, "get_settings", lambda: _Off())
    assert asyncio.run(msf.get_shadow_macro_snapshot()) is None


# ══════════════════════════════════════════════════════════════════════════════
# 5 · INVARIANTS
# ══════════════════════════════════════════════════════════════════════════════
def test_no_cancelled_fetch_status_was_invented():
    """Cancellation is control flow. Giving it a status would put it back into
    the telemetry it must stay out of."""
    for status in ms.FETCH_STATUSES:
        assert "cancel" not in status.lower(), status


def test_the_production_fetch_flag_is_still_off():
    from app.config import Settings
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False


def test_no_cancellation_path_carries_the_key(monkeypatch):
    """A cancelled fetch produces no payload, but the exception travels — and
    httpx puts request URLs in exception messages."""
    started = asyncio.Event()
    _transport(monkeypatch, _hanging(started))

    async def _run():
        task = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await _await_started(started)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError as exc:
            text = f"{exc!r}{exc.args}"
            assert SYNTHETIC_KEY not in text
            assert "api_key" not in text
            return
        raise AssertionError("the cancel did not propagate")

    asyncio.run(_run())
