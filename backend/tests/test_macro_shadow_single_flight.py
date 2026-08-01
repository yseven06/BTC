"""CP-MACRO-SHADOW-FETCH-SINGLE-FLIGHT — one cycle per key, however many callers.

WHAT WAS WRONG
    The cache is written AFTER a cycle completes, so concurrent callers meeting a
    cold cache all missed and all fetched. Measured in production on 2026-08-01:
    the 15m and 4h sweeps started 1.0 s apart on a fresh container and produced
    FOUR requests in 64 ms — two cycles, not one. The TTL bounded the steady
    state and never bounded the cold start.

WHY THE OLD TESTS DID NOT SEE IT
    `test_a_hundred_candidates_cost_one_request_cycle` drives a hundred
    SEQUENTIAL `asyncio.run` calls. Every one of them finds a warm cache because
    the previous one finished. Concurrency was never exercised, so the guarantee
    the module documents — "shared by every candidate and every overlapping job"
    — was only ever tested in the half where it already held.

    Every concurrency test here therefore uses `asyncio.gather` on ONE loop, and
    the transport BLOCKS until every caller has arrived. A test that lets the
    first caller finish before the second starts measures the sequential path
    again and proves nothing.

No test here can reach the network.
"""
import asyncio

import httpx
import pytest

from app.services import macro_shadow as ms
from app.services import macro_shadow_fetch as msf

SYNTHETIC_KEY = "synthetic-not-a-real-fred-key"
SERIES_COUNT = len(ms.SCORED_SERIES)          # 2 — one request per scored series


class _Settings:
    MACRO_SHADOW_FETCH_ENABLED = True
    FRED_API_KEY = SYNTHETIC_KEY
    MACRO_FRED_FETCH_ENABLED = False


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    msf.reset_cache_for_tests()
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    yield
    msf.reset_cache_for_tests()


class _Barrier:
    """Counts requests and holds every one open until released.

    Holding is the whole point: it guarantees the callers really are in flight
    together. Without it the first caller could complete, warm the cache, and
    turn the test back into the sequential one that already passed.
    """

    def __init__(self, *, fail=False, date="2026-06-01"):
        self.calls = []
        self.fail = fail
        self.date = date
        self.gate = None                      # created on the running loop
        self.arrived = None

    def handler(self):
        async def _h(request: httpx.Request) -> httpx.Response:
            if self.gate is None:
                self.gate = asyncio.Event()
                self.arrived = asyncio.Event()
            self.calls.append(request.url.params.get("series_id"))
            if len(self.calls) >= SERIES_COUNT:
                self.arrived.set()
            await self.gate.wait()
            if self.fail:
                raise httpx.ConnectError("upstream down")
            return httpx.Response(200, json={
                "observations": [{"date": self.date, "value": "4.33"}]})
        return _h

    def release(self):
        if self.gate is not None:
            self.gate.set()


async def _swarm(n, transport, *, job_id=None):
    """`n` callers in flight together, released only once the first cycle's
    requests have all arrived."""
    async def _release_when_ready():
        # Wait for the leader's requests to land, then let them answer. If no
        # request ever arrives (a bug that skips the fetch), the timeout below
        # fails the test rather than hanging it.
        for _ in range(200):
            if transport.arrived is not None and transport.arrived.is_set():
                break
            await asyncio.sleep(0.005)
        transport.release()

    tasks = [asyncio.create_task(msf.get_shadow_macro_snapshot(job_id=job_id))
             for _ in range(n)]
    releaser = asyncio.create_task(_release_when_ready())
    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    finally:
        releaser.cancel()
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE DEFECT — concurrent callers, one cycle
# ══════════════════════════════════════════════════════════════════════════════
def test_a_hundred_concurrent_callers_cost_one_cycle():
    """THE regression. Before single-flight this was one cycle per caller that
    arrived cold — measured as four requests in production with just two."""
    t = _Barrier()

    async def _run():
        _monkey(t)
        return await _swarm(100, t)

    results = asyncio.run(_with_settings(_run, t))
    assert len(results) == 100
    assert all(r is not None for r in results)
    assert len(t.calls) == SERIES_COUNT, \
        f"expected one cycle ({SERIES_COUNT} requests), got {len(t.calls)}: {t.calls}"
    assert sorted(t.calls) == sorted(ms.SCORED_SERIES)


def test_two_overlapping_scans_make_one_cycle():
    """The production shape exactly: the 15m and 4h sweeps arriving together on
    a cold container."""
    t = _Barrier()

    async def _run():
        _monkey(t)
        return await _swarm(2, t)

    results = asyncio.run(_with_settings(_run, t))
    assert len(t.calls) == SERIES_COUNT, t.calls
    assert results[0]["fetch_status"] == "ok"
    assert results[1]["fetch_status"] == "ok"


def test_exactly_one_caller_reports_the_miss():
    """One leader, ninety-nine followers. A second `miss` would mean a second
    cycle wearing a cached coat."""
    t = _Barrier()

    async def _run():
        _monkey(t)
        return await _swarm(100, t)

    results = asyncio.run(_with_settings(_run, t))
    misses = [r for r in results if r["cache_status"] == "miss"]
    assert len(misses) == 1, f"{len(misses)} callers ran their own cycle"
    assert len(t.calls) == SERIES_COUNT


# ══════════════════════════════════════════════════════════════════════════════
# 2 · THE LOCK IS PER KEY, NOT GLOBAL
# ══════════════════════════════════════════════════════════════════════════════
def test_different_cache_keys_do_not_block_each_other():
    """A future stage fetching a different series set must not queue behind this
    one. Driven by holding key A's lock and timing key B's acquisition."""
    async def _run():
        a = msf._lock_for("macro_shadow_v1|A")
        b = msf._lock_for("macro_shadow_v1|B")
        assert a is not b, "one lock is serving two keys"
        await a.acquire()
        try:
            # B must be free WHILE A is held. `wait_for` turns a global lock
            # into a failure instead of a hang.
            await asyncio.wait_for(b.acquire(), timeout=1.0)
            b.release()
        finally:
            a.release()
        return True

    assert asyncio.run(_run()) is True


def test_the_same_key_yields_the_same_lock():
    async def _run():
        return (msf._lock_for("k") is msf._lock_for("k"))
    assert asyncio.run(_run()) is True


def test_a_new_event_loop_gets_a_new_lock():
    """`asyncio.Lock` binds to the loop it first contends on. Reusing one across
    loops raises "bound to a different event loop" — which would work in
    production, where there is one loop forever, and break anywhere else."""
    async def _grab():
        lock = msf._lock_for("k")
        async with lock:
            pass
        return lock

    first = asyncio.run(_grab())
    second = asyncio.run(_grab())
    assert first is not second


# ══════════════════════════════════════════════════════════════════════════════
# 3 · FAILURE — no deadlock, no stampede, no poison
# ══════════════════════════════════════════════════════════════════════════════
def test_a_failed_leader_does_not_deadlock_the_waiters():
    t = _Barrier(fail=True)

    async def _run():
        _monkey(t)
        return await _swarm(20, t)

    results = asyncio.run(_with_settings(_run, t))
    assert len(results) == 20
    assert all(r is not None for r in results), "a waiter was left with nothing"
    assert all(r["fetch_status"] != "ok" for r in results)


def test_a_failed_leader_does_not_become_a_stampede():
    """The reason a bare lock is not enough. Serialised retries would turn one
    timeout into twenty, end to end, and burn the job budget the fetch is
    supposed to stay inside."""
    t = _Barrier(fail=True)

    async def _run():
        _monkey(t)
        return await _swarm(20, t)

    asyncio.run(_with_settings(_run, t))
    assert len(t.calls) == SERIES_COUNT, \
        f"{len(t.calls) // SERIES_COUNT} cycles ran for one failure: {t.calls}"


def test_a_failure_is_never_cached():
    """It may be shared across the one in-flight window and never served again:
    the next caller must fetch for itself, because the next scan IS the retry."""
    t = _Barrier(fail=True)

    async def _run():
        _monkey(t)
        await _swarm(5, t)
        assert msf.cache_key() not in msf._SHADOW_CACHE, "a failure was cached"
        # A caller arriving AFTER that window fetches again.
        t.release()
        return await msf.get_shadow_macro_snapshot()

    later = asyncio.run(_with_settings(_run, t))
    assert later is not None
    assert len(t.calls) == 2 * SERIES_COUNT, \
        f"the later caller did not run its own cycle: {t.calls}"


def test_the_shared_cycle_is_not_readable_by_a_later_caller():
    """`_share_completed_cycle` is the difference between sharing a result and
    caching one, so the boundary is asserted directly."""
    async def _run():
        key = "k"
        msf._record_cycle(key, {"fetch_status": "timeout"})
        seq = msf._cycle_seq(key)
        # A caller that queued BEFORE that cycle sees it.
        assert msf._share_completed_cycle(key, seq - 1) is not None
        # A caller arriving after it does NOT.
        assert msf._share_completed_cycle(key, seq) is None
    asyncio.run(_run())


def test_the_recorded_cycle_is_a_copy_of_the_leaders_snapshot():
    """The record must not alias the object the leader returned. If it did, a
    caller mutating its own payload would rewrite what the waiters behind it
    receive — a leak in the opposite direction from the one the deep copy on
    the way OUT prevents, and invisible to a test that only checks the way out.
    """
    async def _run():
        snapshot = {"fetch_status": "timeout", "series": {"a": {}}}
        msf._record_cycle("k", snapshot)
        snapshot["series"]["a"]["poisoned"] = True
        shared = msf._share_completed_cycle("k", msf._cycle_seq("k") - 1)
        assert "poisoned" not in shared["series"]["a"], \
            "the record aliases the caller's snapshot"
    asyncio.run(_run())


def test_the_shared_result_is_a_copy_not_the_stored_object():
    async def _run():
        key = "k"
        msf._record_cycle(key, {"fetch_status": "timeout", "series": {"a": {}}})
        seq = msf._cycle_seq(key)
        one = msf._share_completed_cycle(key, seq - 1)
        two = msf._share_completed_cycle(key, seq - 1)
        assert one is not two
        assert one["series"] is not two["series"]
        one["series"]["a"]["poisoned"] = True
        assert "poisoned" not in two["series"]["a"]
    asyncio.run(_run())


# ══════════════════════════════════════════════════════════════════════════════
# 4 · CANCELLATION LEAVES NOTHING HELD
# ══════════════════════════════════════════════════════════════════════════════
def test_the_lock_propagates_cancellation_and_stays_free():
    """The single-flight mechanism itself, in isolation.

    A caller cancelled while queueing must stay cancelled and must leave the
    lock free for the next one. Driven against the real lock rather than through
    `get_shadow_macro_snapshot`, whose pre-existing outer boundary converts
    every BaseException — cancellation included — into None; that conversion is
    pinned separately below and is not this checkpoint's to change.
    """
    async def _run():
        lock = msf._lock_for("k")
        await lock.acquire()                  # held, so the next caller queues

        async def _queue():
            async with msf._lock_for("k"):
                return "entered"

        queued = asyncio.create_task(_queue())
        await asyncio.sleep(0.02)
        assert not queued.done(), "precondition: it really is waiting"
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert queued.cancelled(), "cancellation was converted into a result"

        lock.release()
        assert not lock.locked(), "the cancelled waiter left the lock held"
        # And it is genuinely reusable, not merely reporting itself free.
        await asyncio.wait_for(lock.acquire(), timeout=1.0)
        lock.release()

    asyncio.run(_run())


def test_cancelling_a_waiter_leaves_the_lock_usable():
    t = _Barrier()

    async def _run():
        _monkey(t)
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        for _ in range(200):
            if t.arrived is not None and t.arrived.is_set():
                break
            await asyncio.sleep(0.005)
        waiter = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await asyncio.sleep(0.02)             # let it reach the lock
        waiter.cancel()
        # NOTE: this does NOT raise. `get_shadow_macro_snapshot`'s outer
        # `except BaseException` predates this checkpoint and turns cancellation
        # into None — see `test_the_outer_boundary_still_swallows_cancellation`.
        # What this test owns is the state left behind.
        result = await waiter
        assert result is None, "a cancelled caller must not receive a snapshot"

        t.release()
        assert await asyncio.wait_for(leader, timeout=5) is not None
        lock = msf._lock_for(msf.cache_key())
        assert not lock.locked(), "the cancelled waiter left the lock held"
        await asyncio.wait_for(lock.acquire(), timeout=1.0)
        lock.release()

    asyncio.run(_with_settings(_run, t))
    assert len(t.calls) == SERIES_COUNT, t.calls


def test_cancelling_the_leader_leaves_the_lock_usable():
    """Whatever the leader's own error handling makes of the cancellation, the
    lock must not stay held — `async with` is what guarantees that."""
    t = _Barrier()

    async def _run():
        _monkey(t)
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        for _ in range(200):
            if t.arrived is not None and t.arrived.is_set():
                break
            await asyncio.sleep(0.005)
        leader.cancel()
        try:
            await leader
        except asyncio.CancelledError:
            pass
        t.release()
        await asyncio.sleep(0)
        lock = msf._lock_for(msf.cache_key())
        assert not lock.locked(), "a cancelled leader left the lock held"

    asyncio.run(_with_settings(_run, t))


def test_the_outer_boundary_still_swallows_cancellation():
    """PINS A PRE-EXISTING BEHAVIOUR THIS CHECKPOINT DID NOT CHANGE.

    `get_shadow_macro_snapshot` wraps everything in `except BaseException` and
    returns None, so a cancelled caller receives None instead of staying
    cancelled. That predates single-flight and contradicts the module's own
    stated principle — `_fetch_one` re-raises `CancelledError` precisely because
    "a handler that catches this would fight its own bound".

    It is pinned rather than fixed because changing it alters what every caller
    of this function sees when a scan is torn down, which is a scheduler-visible
    change and outside a single-flight checkpoint. If the pin fails, someone
    changed the boundary — decide deliberately, do not just update the test.
    """
    t = _Barrier()

    async def _run():
        _monkey(t)
        leader = asyncio.create_task(msf.get_shadow_macro_snapshot())
        for _ in range(200):
            if t.arrived is not None and t.arrived.is_set():
                break
            await asyncio.sleep(0.005)
        waiter = asyncio.create_task(msf.get_shadow_macro_snapshot())
        await asyncio.sleep(0.02)
        waiter.cancel()
        result = await waiter
        assert result is None
        assert not waiter.cancelled(), (
            "the outer boundary no longer swallows cancellation — this is a "
            "deliberate decision to make, not a test to update")
        t.release()
        await asyncio.wait_for(leader, timeout=5)

    asyncio.run(_with_settings(_run, t))


# ══════════════════════════════════════════════════════════════════════════════
# 5 · THE CACHE PATH IS UNCHANGED
# ══════════════════════════════════════════════════════════════════════════════
def test_a_warm_cache_costs_no_request_and_no_queueing():
    t = _Barrier()

    async def _run():
        _monkey(t)
        await _swarm(3, t)
        before = len(t.calls)
        again = await asyncio.gather(*(msf.get_shadow_macro_snapshot()
                                       for _ in range(50)))
        assert len(t.calls) == before, "the warm path issued a request"
        assert all(r["cache_status"] == "hit" for r in again)
        return again

    asyncio.run(_with_settings(_run, t))


def test_every_caller_gets_its_own_object():
    """No mutable sharing, on any of the three return paths."""
    t = _Barrier()

    async def _run():
        _monkey(t)
        swarm = await _swarm(10, t)
        warm = await asyncio.gather(*(msf.get_shadow_macro_snapshot()
                                      for _ in range(5)))
        return swarm + list(warm)

    payloads = asyncio.run(_with_settings(_run, t))
    ids = [id(p) for p in payloads]
    assert len(set(ids)) == len(ids), "two callers share one object"
    series_ids = [id(p["series"]) for p in payloads]
    assert len(set(series_ids)) == len(series_ids), "two callers share one series map"
    payloads[0]["series"][ms.SERIES_FEDFUNDS]["poisoned"] = True
    assert all("poisoned" not in p["series"][ms.SERIES_FEDFUNDS]
               for p in payloads[1:]), "a mutation reached another caller"


def test_the_ttl_expiry_starts_exactly_one_new_cycle():
    t = _Barrier()

    async def _run():
        _monkey(t)
        await _swarm(5, t)
        assert len(t.calls) == SERIES_COUNT
        msf._SHADOW_CACHE[msf.cache_key()]["stored_at"] -= (
            msf.SHADOW_CACHE_TTL_SECONDS + 1)
        t.gate = None                          # a fresh gate for the second cycle
        t.arrived = None
        await _swarm(20, t)
        return True

    asyncio.run(_with_settings(_run, t))
    assert len(t.calls) == 2 * SERIES_COUNT, \
        f"the expiry started {len(t.calls) // SERIES_COUNT} cycles: {t.calls}"


# ══════════════════════════════════════════════════════════════════════════════
# 6 · NOTHING ELSE MOVED
# ══════════════════════════════════════════════════════════════════════════════
def test_the_bounded_fetch_constants_are_unchanged():
    assert msf.SHADOW_CACHE_TTL_SECONDS == 900.0
    assert msf.SHADOW_FETCH_TIMEOUT_SECONDS == 6.0
    assert msf.SHADOW_STALE_MAX_AGE_SECONDS == 3600.0
    assert msf.SHADOW_BUDGET_MARGIN_SECONDS == 4.0


def test_the_production_fetch_flag_is_still_off():
    from app.config import Settings
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False


def test_the_budget_guard_still_declines_before_queueing(monkeypatch):
    """A caller near its deadline must not spend what is left waiting in line."""
    t = _Barrier()
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: 1.0)

    async def _run():
        _monkey(t)
        snap = await msf.get_shadow_macro_snapshot(job_id="signals_15m")
        assert snap["fetch_status"] == "budget_guard"
        assert snap["fallback_reason"] == "budget_guard"
        return snap

    asyncio.run(_with_settings(_run, t))
    assert t.calls == [], "the budget guard queued instead of declining"


def test_the_observation_time_telemetry_still_works():
    t = _Barrier(date="2026-06-01")

    async def _run():
        _monkey(t)
        return await _swarm(5, t)

    results = asyncio.run(_with_settings(_run, t))
    assert all(r["observation_time"] == "2026-06-01" for r in results)


def test_no_payload_carries_the_key():
    import json
    t = _Barrier()

    async def _run():
        _monkey(t)
        return await _swarm(10, t)

    results = asyncio.run(_with_settings(_run, t))
    blob = json.dumps(results, default=str)
    assert SYNTHETIC_KEY not in blob
    assert "api_key" not in blob


# ── harness plumbing ─────────────────────────────────────────────────────────
# `monkeypatch` cannot be used inside `asyncio.run`, so settings and the client
# are swapped by hand and restored afterwards.
_SAVED = {}


def _monkey(transport):
    _SAVED["settings"] = msf.get_settings
    _SAVED["client"] = msf.httpx.AsyncClient
    real = msf.httpx.AsyncClient
    msf.get_settings = lambda: _Settings()

    def _client(*a, **kw):
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(transport.handler()), **kw)
    msf.httpx.AsyncClient = _client


async def _with_settings(fn, transport):
    try:
        return await fn()
    finally:
        if "settings" in _SAVED:
            msf.get_settings = _SAVED.pop("settings")
        if "client" in _SAVED:
            msf.httpx.AsyncClient = _SAVED.pop("client")
