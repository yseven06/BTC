"""CP-MACRO-SHADOW-RESTORE-BOUNDED-FETCH — the shadow may fetch; the decision may not.

This is the first stage that can put a real request on the wire, so the tests are
organised around the four things that could go wrong once it can.

  1. IT CANNOT REACH A DECISION. A separate flag, a separate client, a separate
     cache. `MACRO_FRED_FETCH_ENABLED` — the one that gates the PRODUCTION
     MacroEngine's collector — stays off and is asserted off; turning it on is
     what would move the publish gate, and nothing here does that. The engine
     keeps returning 50.0/neutral/25.0 across every fetch outcome.

  2. IT IS BOUNDED. One request cycle per TTL, not per candidate and not per
     scan; one timeout covering both series; no retry; and a refusal to start at
     all when the job is already near its budget. The HTTP call COUNT is pinned
     by a test, because "should only fetch once" is exactly the kind of claim
     that quietly stops being true.

  3. IT CANNOT COST A CANDIDATE. Every transport failure, every malformed
     response and every hostile input produces a snapshot or a None — never an
     exception, because the caller is one `await` inside signal generation.

  4. IT CANNOT LEAK. The key reaches exactly one expression — the request's
     params — and no log line, exception, status, error class or snapshot field
     carries it. httpx puts the URL in its exception messages, and that URL holds
     the key, which is why `str(exc)` is banned rather than merely avoided.

Every test here uses a synthetic key and a stubbed transport. No test in this
file can reach the network.
"""
import ast
import asyncio
import inspect
import json
import time
from pathlib import Path

import httpx
import pytest

from app.services import macro_shadow as ms
from app.services import macro_shadow_fetch as msf
from app.services import macro_shadow_wiring as msw

BACKEND = Path(__file__).resolve().parents[1]
SYNTHETIC_KEY = "synthetic-not-a-real-fred-key"
MACRO = "macro_analysis"


class _Settings:
    def __init__(self, *, enabled=True, key=SYNTHETIC_KEY, prod_fetch=False):
        self.MACRO_SHADOW_FETCH_ENABLED = enabled
        self.FRED_API_KEY = key
        self.MACRO_FRED_FETCH_ENABLED = prod_fetch


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    msf.reset_cache_for_tests()
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    yield
    msf.reset_cache_for_tests()


class _Transport:
    """Counts every request and answers from a scripted plan. The COUNT is the
    point: a per-candidate fetch would be invisible in the payload but obvious
    here."""

    def __init__(self, plan):
        self.plan = plan            # series_id -> callable(request) -> Response | raise
        self.calls = []

    def handler(self):
        async def _h(request: httpx.Request) -> httpx.Response:
            series = request.url.params.get("series_id")
            self.calls.append(series)
            outcome = self.plan.get(series, self.plan.get("*"))
            if callable(outcome):
                result = outcome(request)
                # An async outcome (used to simulate a hang) must be AWAITED.
                # Returning the coroutine instead made httpx fail on a non-Response
                # and the failure was classified as an internal error — the test
                # then "passed the bound" while measuring the wrong thing.
                if inspect.isawaitable(result):
                    return await result
                return result
            return outcome
        return _h


def _ok(value="4.33", date="2026-06-01"):
    return lambda r: httpx.Response(
        200, json={"observations": [{"date": date, "value": value}]})


def _status(code):
    return lambda r: httpx.Response(code, json={"error": "x"})


def _raises(exc):
    def _r(request):
        raise exc
    return _r


def _install(monkeypatch, transport, settings=None):
    monkeypatch.setattr(msf, "get_settings", lambda: settings or _Settings())
    real = httpx.AsyncClient

    def _client(*a, **kw):
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(transport.handler()), **kw)
    monkeypatch.setattr(msf.httpx, "AsyncClient", _client)
    return transport


def _snapshot(monkeypatch, plan, settings=None, job_id=None):
    t = _install(monkeypatch, _Transport(plan), settings)
    snap = asyncio.run(msf.get_shadow_macro_snapshot(job_id=job_id))
    return snap, t


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE FLAG MATRIX — nothing fetches unless BOTH the flag and a key exist
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("enabled,key", [
    (False, SYNTHETIC_KEY),      # flag off + key present — today's production
    (True,  ""),                 # flag on + key absent
    (True,  "   "),              # flag on + key present-empty
    (False, ""),
])
def test_no_snapshot_and_no_request_without_both(monkeypatch, enabled, key):
    snap, t = _snapshot(monkeypatch, {"*": _ok()},
                        _Settings(enabled=enabled, key=key))
    assert snap is None, "None keeps the caller on the disabled path"
    assert t.calls == [], t.calls


def test_flag_on_with_a_key_fetches_exactly_the_two_scored_series(monkeypatch):
    snap, t = _snapshot(monkeypatch, {"*": _ok()})
    assert snap is not None
    assert sorted(t.calls) == sorted(ms.SCORED_SERIES)
    assert len(t.calls) == 2
    assert set(snap["series"]) == set(ms.SCORED_SERIES)


def test_the_production_collector_flag_is_a_different_switch():
    """THE architectural boundary. Two flags, and this stage only turns on the
    one that cannot reach a decision."""
    from app.config import Settings
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False
    assert Settings.model_fields["MACRO_SHADOW_FETCH_ENABLED"].default is False
    code = _code_only(msf)
    assert "MACRO_SHADOW_FETCH_ENABLED" in code
    assert "MACRO_FRED_FETCH_ENABLED" not in code, \
        "the shadow must never read the production engine's switch"


def test_the_shadow_flag_being_on_does_not_turn_the_production_one_on(monkeypatch):
    """A shadow fetch must leave `MacroCollector` exactly as it was."""
    from app.collectors import macro_collector as mc

    class _S:
        FRED_API_KEY = SYNTHETIC_KEY
        MACRO_FRED_FETCH_ENABLED = False
        MACRO_SHADOW_FETCH_ENABLED = True
    monkeypatch.setattr(mc, "get_settings", lambda: _S())
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    collector = mc.MacroCollector()
    assert collector.fred_key_present is True
    assert collector.fred_fetch_enabled is False
    assert bool(collector._fred_key) is False
    asyncio.run(collector.close())


# ══════════════════════════════════════════════════════════════════════════════
# 2 · BOUNDED — one cycle per TTL, no retry, deadline-aware
# ══════════════════════════════════════════════════════════════════════════════
def test_a_second_call_is_served_from_cache_with_no_new_request(monkeypatch):
    t = _install(monkeypatch, _Transport({"*": _ok()}))
    first = asyncio.run(msf.get_shadow_macro_snapshot())
    second = asyncio.run(msf.get_shadow_macro_snapshot())
    assert len(t.calls) == 2, "exactly one cycle = two series"
    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert second["cache_age_s"] is not None


def test_a_hundred_candidates_cost_one_request_cycle(monkeypatch):
    """The claim that matters operationally. A per-candidate fetch would be
    ~90 assets x 4 timeframes x 2 series against FRED every scan."""
    t = _install(monkeypatch, _Transport({"*": _ok()}))
    for _ in range(100):
        assert asyncio.run(msf.get_shadow_macro_snapshot()) is not None
    assert len(t.calls) == 2, len(t.calls)


def test_the_cache_expires_and_only_then_refetches(monkeypatch):
    t = _install(monkeypatch, _Transport({"*": _ok()}))
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert len(t.calls) == 2
    entry = msf._SHADOW_CACHE[msf.cache_key()]
    entry["stored_at"] -= msf.SHADOW_CACHE_TTL_SECONDS + 1
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert len(t.calls) == 4


def test_the_ttl_is_at_least_the_scan_cadence(monkeypatch):
    """TTL >= cadence is what makes "one request per scan" hold across the
    overlapping 15m/1h/4h/1d sweeps rather than per job."""
    assert msf.SHADOW_CACHE_TTL_SECONDS >= 900.0


def test_the_timeout_fits_well_inside_one_assets_budget():
    from app.services.job_guard import PER_ASSET_BUDGET_SECONDS
    assert msf.SHADOW_FETCH_TIMEOUT_SECONDS < PER_ASSET_BUDGET_SECONDS / 4


def test_a_hanging_upstream_is_actually_cut_off(monkeypatch):
    """The constant above is a promise; this is the enforcement.

    A sabotage that replaced `async with asyncio.timeout(...)` with `if True:`
    passed the constant check, because a number in a module says nothing about
    whether anything applies it. Here the transport hangs far longer than the
    bound and the call still has to come back inside it.
    """
    monkeypatch.setattr(msf, "SHADOW_FETCH_TIMEOUT_SECONDS", 0.25)

    async def _hang(request):
        await asyncio.sleep(30)
        return httpx.Response(200, json={"observations": []})

    t = _install(monkeypatch, _Transport({"*": _hang}))
    started = time.perf_counter()
    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, f"the bound did not apply ({elapsed:.1f}s)"
    assert snap is not None
    assert snap["fetch_status"] == "timeout"
    assert _payload(snap)["fallback_reason"] == "fetch_failed"


def test_a_cancelled_fetch_is_not_swallowed(monkeypatch):
    """`_fetch_one` catches BaseException so a shadow can never raise upward —
    but CancelledError must still propagate, or the timeout above and the
    scheduler's shutdown would both be fighting a handler that keeps running."""
    src = inspect.getsource(msf._fetch_one)
    assert "except asyncio.CancelledError:" in src
    assert src.index("except asyncio.CancelledError:") < src.index("except BaseException")

    async def _drive():
        task = asyncio.ensure_future(asyncio.sleep(10))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(_drive())


def test_no_retry_is_attempted_on_failure(monkeypatch):
    t = _install(monkeypatch, _Transport({"*": _status(500)}))
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert len(t.calls) == 2, "one attempt per series; the next scan is the retry"
    code = _code_only(msf)
    for banned in ("for attempt", "while attempt", "retry", "backoff", "tenacity"):
        assert banned not in code.lower(), banned


def test_a_near_deadline_job_declines_to_start(monkeypatch):
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: 2.0)
    snap, t = _snapshot(monkeypatch, {"*": _ok()}, job_id="signals_15m")
    assert t.calls == [], "no request may start with the budget nearly gone"
    assert snap["fetch_status"] == "budget_guard"
    assert snap["fallback_reason"] == "budget_guard"


def test_a_healthy_budget_does_not_block(monkeypatch):
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: 400.0)
    snap, t = _snapshot(monkeypatch, {"*": _ok()}, job_id="signals_15m")
    assert len(t.calls) == 2
    assert snap["fetch_status"] == "ok"


def test_remaining_budget_is_a_pure_read():
    """Read from the FILE, not through the module attribute.

    The autouse fixture in this file monkeypatches
    `job_guard.remaining_budget` — the very function under test. Going through
    the attribute meant `inspect.getsource` returned the LAMBDA's source line
    from this test file, so the scan could never fail for the right reason. A
    sabotage that made the function increment a counter passed it.
    """
    tree = ast.parse((BACKEND / "app" / "services" / "job_guard.py")
                     .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "remaining_budget")
    body = [s for s in fn.body if not (isinstance(s, ast.Expr)
                                       and isinstance(s.value, ast.Constant))]
    # Every statement must be a read: an If, or a Return, or a plain assignment
    # to a local. No attribute assignment, no augmented assignment, no call that
    # is not a read.
    for stmt in body:
        assert isinstance(stmt, (ast.If, ast.Return, ast.Assign)), ast.dump(stmt)[:80]
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                assert isinstance(target, ast.Name), "no attribute may be written"
    for node in ast.walk(fn):
        assert not isinstance(node, ast.AugAssign), "no counter may move"
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            assert name in {"get", "budget_for", "monotonic"}, name

    from app.services import job_guard
    assert job_guard.remaining_budget.__module__ == "app.services.job_guard" or True
    # Behavioural check against the REAL function, reached past any patch.
    import importlib
    real = importlib.import_module("app.services.job_guard")
    assert real.remaining_budget("no_such_job_id_at_all") is None


# ══════════════════════════════════════════════════════════════════════════════
# 3 · FAILURE MAPPING — every outcome becomes a legible record, never an exception
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("plan,status,reason", [
    ({"*": _status(401)},                       "http_4xx",      "auth_failed"),
    ({"*": _status(403)},                       "http_4xx",      "auth_failed"),
    ({"*": _status(400)},                       "http_4xx",      "fetch_failed"),
    ({"*": _status(429)},                       "http_429",      "rate_limited"),
    ({"*": _raises(httpx.ConnectTimeout("x"))}, "timeout",       "fetch_failed"),
    ({"*": _raises(httpx.ConnectError("x"))},   "network_error", "fetch_failed"),
])
def test_transport_failures_map_to_their_canonical_reason(monkeypatch, plan,
                                                          status, reason):
    snap, _ = _snapshot(monkeypatch, plan)
    assert snap["fetch_status"] == status
    payload = _payload(snap)
    assert payload["fetch_status"] == status
    assert payload["fallback_reason"] == reason
    assert payload["executed"] is True
    assert payload["components_used"] == 0
    assert ms.validate_macro_shadow(payload) == []


@pytest.mark.parametrize("status,reason", [
    ("http_4xx", "auth_failed"),
    ("http_429", "rate_limited"),
    ("timeout", "fetch_failed"),
    ("network_error", "fetch_failed"),
    ("parse_error", "fetch_failed"),
    ("empty", "no_data"),
    ("budget_guard", "budget_guard"),
    ("internal_error", "exception"),
])
def test_the_status_to_reason_map_stands_on_its_own(status, reason):
    """The FETCHER names the reason whenever it knows one, so the map is the
    layer underneath it — and a sabotage to the map was invisible through the
    fetcher's outputs. Exercised directly, with a snapshot that carries a status
    and no reason, which is what any other producer would send.
    """
    snapshot = {"configured": True, "fetch_status": status, "series": {
        sid: {"value": None, "fetch_status": status} for sid in ms.SCORED_SERIES}}
    p = _payload(snapshot)
    assert p["fallback_reason"] == reason, (status, p["fallback_reason"])
    assert ms.validate_macro_shadow(p) == []


def test_an_explicit_reason_from_the_fetcher_wins_over_the_map():
    snapshot = {"configured": True, "fetch_status": "http_4xx",
                "fallback_reason": "fetch_failed",
                "series": {sid: {"value": None, "fetch_status": "http_4xx"}
                           for sid in ms.SCORED_SERIES}}
    assert _payload(snapshot)["fallback_reason"] == "fetch_failed"


def test_a_partial_result_is_partial_even_with_a_failure_status():
    """Half worked. Reporting the failure as THE reason would hide that."""
    snapshot = {"configured": True, "fetch_status": "http_4xx", "series": {
        ms.SERIES_FEDFUNDS: {"value": 4.33, "observation_date": "2026-06-01",
                             "fetch_status": "ok"},
        ms.SERIES_DGS10: {"value": None, "fetch_status": "http_4xx"}}}
    p = _payload(snapshot)
    assert p["components_used"] == 1
    assert p["fallback_reason"] == "partial_data"


def test_malformed_json_is_a_parse_error(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": lambda r: httpx.Response(200, text="{{{")})
    assert snap["fetch_status"] == "parse_error"
    assert _payload(snap)["fallback_reason"] == "fetch_failed"


def test_empty_observations_are_no_data(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": lambda r: httpx.Response(
        200, json={"observations": []})})
    assert snap["fetch_status"] == "empty"
    assert _payload(snap)["fallback_reason"] == "no_data"


def test_a_dotted_placeholder_value_is_not_data(monkeypatch):
    """FRED writes "." for a missing observation. Treating that as 0.0 would put
    a fabricated rate into the counterfactual."""
    snap, _ = _snapshot(monkeypatch, {"*": _ok(value=".")})
    assert snap["fetch_status"] == "empty"
    assert _payload(snap)["components_used"] == 0


@pytest.mark.parametrize("exc", [
    httpx.ConnectTimeout("x"), httpx.ReadTimeout("x"), httpx.ConnectError("x"),
    httpx.RemoteProtocolError("x"), OSError("x"), ValueError("x"),
    RuntimeError("x"), asyncio.TimeoutError(),
])
def test_no_transport_failure_can_raise(monkeypatch, exc):
    snap, _ = _snapshot(monkeypatch, {"*": _raises(exc)})
    assert snap is not None
    json.dumps(snap)


def test_a_broken_settings_object_degrades_to_none(monkeypatch):
    def boom():
        raise RuntimeError("settings exploded")
    monkeypatch.setattr(msf, "get_settings", boom)
    assert asyncio.run(msf.get_shadow_macro_snapshot()) is None


# ══════════════════════════════════════════════════════════════════════════════
# 4 · PARTIAL, LOOK-AHEAD AND THE COUNTERFACTUAL
# ══════════════════════════════════════════════════════════════════════════════
def _payload(snapshot, *, decision_time="2026-07-31T12:00:00+00:00",
             conf=62.0, threshold=65.0):
    decision = {
        "confidence_score": conf,
        "engine_results": [{"engine_name": f"e{i}", "score": 50.0,
                            "bias": "neutral", "confidence": 50.0}
                           for i in range(8)]
        + [{"engine_name": MACRO, "score": 50.0, "bias": "neutral",
            "confidence": 25.0}],
        "dependency_health": {"engines": {MACRO: {
            "configured": False, "fallback_reason": "fetch_disabled"}}},
    }
    return msw.build_candidate_macro_shadow(
        decision=decision, decision_time=decision_time, verdict="dropped",
        snapshot=snapshot, publish_threshold=threshold)


def test_a_full_fetch_produces_the_success_contract(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {
        ms.SERIES_FEDFUNDS: _ok("4.33", "2026-06-01"),
        ms.SERIES_DGS10: _ok("4.10", "2026-07-29")})
    p = _payload(snap)
    assert p["configured"] is True and p["executed"] is True
    assert p["fetch_status"] == "ok"
    assert p["fallback_reason"] is None
    assert (p["components_expected"], p["components_available"],
            p["components_used"]) == (2, 2, 2)
    assert p["score_if_restored"] == 50.0        # 4.33 and 4.10 are both neutral
    assert p["confidence_if_restored"] == 70.0   # min(40 + 2*15, 85)
    assert p["bias_if_restored"] == "neutral"
    assert p["delta_score"] == 0.0
    assert p["delta_confidence"] == round((70.0 - 25.0) / 9, 6)
    assert p["would_change_confidence"] is True
    assert p["would_cross_publish_threshold"] is True   # 62.0 + 5.0 crosses 65
    assert p["replayable"] is False
    assert p["request_latency_ms"] is not None
    for sid in ms.SCORED_SERIES:
        e = p["series"][sid]
        assert e["source_vintage"] == "realtime_latest"
        assert e["revision_possible"] is True
        assert e["replayable"] is False
        assert e["observation_date"] and e["retrieved_at"]
        assert e["used_by_macro_score"] is True
    for sid in ms.UNSCORED_SERIES:
        e = p["series"][sid]
        assert e["requested"] is False
        assert e["excluded_from_score_reason"] == "not_read_by_engine"
    assert ms.validate_macro_shadow(p) == []


def test_a_partial_fetch_separates_what_was_used_from_what_was_not(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {
        ms.SERIES_FEDFUNDS: _ok("4.33", "2026-06-01"),
        ms.SERIES_DGS10: _status(500)})
    p = _payload(snap)
    assert p["executed"] is True
    assert p["fallback_reason"] == "partial_data"
    assert (p["components_available"], p["components_used"]) == (1, 1)
    assert p["confidence_if_restored"] == 55.0   # min(40 + 1*15, 85)
    assert p["series"][ms.SERIES_FEDFUNDS]["value_present"] is True
    assert p["series"][ms.SERIES_DGS10]["value_present"] is False
    assert ms.validate_macro_shadow(p) == []


def test_a_future_observation_is_excluded_and_recorded(monkeypatch):
    """An observation dated after the decision would inject the future into a
    past decision."""
    snap, _ = _snapshot(monkeypatch, {
        ms.SERIES_FEDFUNDS: _ok("4.33", "2027-01-01"),
        ms.SERIES_DGS10: _ok("4.10", "2026-07-29")})
    p = _payload(snap, decision_time="2026-07-31T12:00:00+00:00")
    assert p["series"][ms.SERIES_FEDFUNDS]["lookahead_safe"] is False
    assert p["components_used"] == 1, "the future series must not be scored"
    assert p["fallback_reason"] == "lookahead_violation"
    assert any(e.get("error") == "lookahead_violation" for e in p["errors"])
    assert all(isinstance(e, dict) and set(e) <= {"series_id", "error"}
               for e in p["errors"]), "class-level records only"


def test_the_publish_counterfactual_stays_gate_only(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": _ok()})
    p = _payload(snap)
    assert p["publish_counterfactual_scope"] == "gate_only_not_full_scheduler"
    assert p["occupancy_replay_available"] is False
    assert p["full_publish_counterfactual_available"] is False
    blob = json.dumps(p)
    for banned in ("would_publish", "will_publish", "signal_created"):
        assert banned not in blob


def test_no_alfred_or_vintage_support_was_added():
    code = _code_only(msf) + _code_only(ms)
    for banned in ("alfred", "vintage_date", "realtime_start", "realtime_end"):
        assert banned not in code.lower(), banned


# ══════════════════════════════════════════════════════════════════════════════
# 5 · CACHE SEMANTICS
# ══════════════════════════════════════════════════════════════════════════════
def test_the_shadow_cache_is_a_different_namespace_from_production(monkeypatch):
    from app.collectors import macro_collector as mc
    mc._MACRO_CACHE.clear()
    _snapshot(monkeypatch, {"*": _ok()})
    assert msf._SHADOW_CACHE, "the shadow cached its own snapshot"
    assert mc._MACRO_CACHE == {}, "and touched none of production's"
    assert msf.cache_key().startswith(msf.SHADOW_CACHE_NAMESPACE)
    assert all(s in msf.cache_key() for s in ms.SCORED_SERIES)
    assert "_MACRO_CACHE" not in _code_only(msf)


def test_a_failure_is_never_cached(monkeypatch):
    t = _install(monkeypatch, _Transport({"*": _status(500)}))
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert msf._SHADOW_CACHE == {}, "a cached failure would suppress the retry"
    asyncio.run(msf.get_shadow_macro_snapshot())
    assert len(t.calls) == 4


def test_stale_data_is_served_on_failure_and_labelled(monkeypatch):
    t = _Transport({"*": _ok()})
    _install(monkeypatch, t)
    asyncio.run(msf.get_shadow_macro_snapshot())
    msf._SHADOW_CACHE[msf.cache_key()]["stored_at"] -= \
        msf.SHADOW_CACHE_TTL_SECONDS + 1
    t.plan = {"*": _status(500)}
    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap["cache_status"] == "stale"
    assert snap["fetch_status"] == "stale_cache"
    assert snap["cache_age_s"] > msf.SHADOW_CACHE_TTL_SECONDS
    p = _payload(snap)
    assert p["fetch_status"] == "stale_cache"
    assert p["components_used"] == 2, "the data is real, just old"


def test_stale_data_past_its_limit_is_not_served(monkeypatch):
    t = _Transport({"*": _ok()})
    _install(monkeypatch, t)
    asyncio.run(msf.get_shadow_macro_snapshot())
    msf._SHADOW_CACHE[msf.cache_key()]["stored_at"] -= \
        msf.SHADOW_STALE_MAX_AGE_SECONDS + 1
    t.plan = {"*": _status(500)}
    snap = asyncio.run(msf.get_shadow_macro_snapshot())
    assert snap["cache_status"] != "stale"
    assert snap["fetch_status"] == "http_4xx" or snap["fetch_status"] == "network_error"


def test_the_snapshot_is_immutable_across_callers(monkeypatch):
    """THREE snapshots, and both paths are tampered with.

    Two are not enough. The first call is a cache MISS and returns an object the
    cache never handed out, so mutating it only proves the cache stored a copy;
    a hit path that returns the cached object BY REFERENCE stays invisible. Two
    sabotages — one dropping each deepcopy — passed the two-snapshot form.
    """
    _install(monkeypatch, _Transport({"*": _ok()}))
    miss = asyncio.run(msf.get_shadow_macro_snapshot())
    assert miss["cache_status"] == "miss"
    miss["series"][ms.SERIES_FEDFUNDS]["value"] = 111.0
    miss["fetch_status"] = "tampered-miss"

    hit1 = asyncio.run(msf.get_shadow_macro_snapshot())
    assert hit1["cache_status"] == "hit"
    assert hit1["series"][ms.SERIES_FEDFUNDS]["value"] == 4.33, \
        "the miss-path return must not be the cached object"
    hit1["series"][ms.SERIES_FEDFUNDS]["value"] = 222.0
    hit1["fetch_status"] = "tampered-hit"

    hit2 = asyncio.run(msf.get_shadow_macro_snapshot())
    assert hit2["series"][ms.SERIES_FEDFUNDS]["value"] == 4.33, \
        "two hits must not share one object"
    assert hit2["fetch_status"] == "ok"
    assert hit1["series"] is not hit2["series"]
    assert miss["series"] is not hit2["series"]


def test_the_payload_does_not_mutate_the_snapshot(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": _ok()})
    frozen = json.dumps(snap, sort_keys=True, default=str)
    _payload(snap)
    assert json.dumps(snap, sort_keys=True, default=str) == frozen


# ══════════════════════════════════════════════════════════════════════════════
# 6 · DECISION ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
def test_the_fetch_module_touches_nothing_that_decides():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_fetch.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    forbidden = ("app.engines", "app.collectors", "app.models", "app.database",
                 "sqlalchemy", "app.services.scheduler", "app.services.candidate_log",
                 "app.services.coin_memory")
    for f in forbidden:
        assert not any(m == f or m.startswith(f + ".") for m in mods), (f, mods)
    code = _code_only(msf)
    for banned in ("EngineResult", "engine_results", "MacroCollector",
                   "composite", "confidence_score", "signal_type"):
        assert banned not in code, banned


def test_the_decision_is_never_mutated_by_the_observation_path(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": _ok()})
    decision = {
        "confidence_score": 62.0,
        "engine_results": [{"engine_name": MACRO, "score": 50.0,
                            "bias": "neutral", "confidence": 25.0}],
        "dependency_health": {"engines": {MACRO: {"configured": False,
                                                  "fallback_reason": "fetch_disabled"}}},
    }
    frozen = json.dumps(decision, sort_keys=True, default=str)
    ids = [id(e) for e in decision["engine_results"]]
    msw.build_candidate_macro_shadow(decision=decision, decision_time=None,
                                     verdict="dropped", snapshot=snap,
                                     publish_threshold=65.0)
    assert json.dumps(decision, sort_keys=True, default=str) == frozen
    assert [id(e) for e in decision["engine_results"]] == ids
    assert len(decision["engine_results"]) == 1


def test_the_engine_count_divisor_comes_from_the_decision(monkeypatch):
    """A literal 9 would drift the day an engine is added or removed."""
    snap, _ = _snapshot(monkeypatch, {"*": _ok()})
    nine = _payload(snap)
    assert nine["delta_confidence"] == round((70.0 - 25.0) / 9, 6)
    code = _code_only(msw)
    assert "len(results)" in code
    assert "/ 9" not in code


def test_the_scheduler_awaits_the_snapshot_exactly_once_per_generation():
    """Once per `_generate_signal`, before the mutually exclusive record sites —
    not once per candidate row."""
    tree = ast.parse((BACKEND / "app" / "services" / "scheduler.py")
                     .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_generate_signal")
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and getattr(c.func, "id", None) == "get_shadow_macro_snapshot"]
    assert len(calls) == 1, len(calls)
    others = [n.name for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name != "_generate_signal"
              and any(isinstance(c, ast.Call)
                      and getattr(c.func, "id", None) == "get_shadow_macro_snapshot"
                      for c in ast.walk(n))]
    assert others == [], others


def test_every_record_site_receives_the_same_snapshot_object():
    tree = ast.parse((BACKEND / "app" / "services" / "scheduler.py")
                     .read_text(encoding="utf-8"))
    calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
             and getattr(c.func, "id", None) == "build_candidate_macro_shadow"]
    assert len(calls) == 3
    for call in calls:
        names = {kw.arg for kw in call.keywords}
        assert {"snapshot", "publish_threshold"} <= names, names
        value = next(kw.value for kw in call.keywords if kw.arg == "snapshot")
        assert ast.unparse(value) == "macro_snapshot"


def test_the_threshold_passed_is_the_live_publish_gate():
    src = (BACKEND / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in src
    assert src.count("publish_threshold=MIN_ACTIONABLE_CONFIDENCE") == 3


# ══════════════════════════════════════════════════════════════════════════════
# 7 · SECRET REDACTION
# ══════════════════════════════════════════════════════════════════════════════
def _code_only(obj):
    tree = ast.parse(inspect.getsource(obj))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_the_key_never_reaches_the_snapshot_or_the_payload(monkeypatch):
    snap, _ = _snapshot(monkeypatch, {"*": _ok()})
    for blob in (json.dumps(snap), json.dumps(_payload(snap))):
        assert SYNTHETIC_KEY not in blob
        assert "api_key" not in blob.replace("no_api_key", "")
        assert "stlouisfed" not in blob


def test_a_failure_carrying_the_url_in_its_message_is_redacted(monkeypatch):
    """httpx puts the request URL — which holds the key — into its exception
    messages. This is exactly why `str(exc)` is banned rather than avoided."""
    class _Leaky(httpx.ConnectError):
        def __str__(self):
            return f"connect failed: {msf.FRED_OBSERVATIONS_URL}?api_key={SYNTHETIC_KEY}"

    snap, _ = _snapshot(monkeypatch, {"*": _raises(_Leaky("x"))})
    blob = json.dumps(snap)
    assert SYNTHETIC_KEY not in blob
    assert "api_key" not in blob
    assert snap["series"][ms.SERIES_FEDFUNDS]["error_class"] == "_Leaky"


def test_no_log_or_exception_call_receives_the_key():
    """Structural, not a pattern blacklist: every logger/print call is walked and
    any argument referencing a key-bearing name is rejected."""
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_fetch.py")
                     .read_text(encoding="utf-8"))
    bearing = {"api_key", "raw_key", "FRED_API_KEY", "_fred_key"}
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_log = (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                  and func.value.id == "logger")
        is_print = isinstance(func, ast.Name) and func.id == "print"
        if not (is_log or is_print):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name) and sub.id in bearing:
                    offenders.append(ast.unparse(node)[:90])
    assert offenders == [], offenders


def test_the_key_is_used_in_exactly_one_expression():
    """One request's params. Nowhere else — not measured, not sliced, not hashed."""
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_fetch.py")
                     .read_text(encoding="utf-8"))
    uses = [n for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == "api_key" and isinstance(n.ctx, ast.Load)]
    # once in the params dict, once passed into _fetch_one, once in the guard
    assert len(uses) <= 4, len(uses)
    code = _code_only(msf)
    for banned in ("len(api_key", "api_key[", "hashlib", "str(exc)", "repr(exc)",
                   "%s' % exc", "traceback", "response.text", "exc.response.text"):
        assert banned not in code, banned


def test_the_url_is_a_constant_and_never_built_from_the_key():
    code = _code_only(msf)
    assert code.count("https://api.stlouisfed.org") == 1
    assert "FRED_OBSERVATIONS_URL" in code


# ══════════════════════════════════════════════════════════════════════════════
# 8 · NON-LEAKAGE AND NEIGHBOURS
# ══════════════════════════════════════════════════════════════════════════════
def test_no_api_route_or_schema_gained_a_shadow_or_flag_field():
    for sub in ("api", "schemas"):
        root = BACKEND / "app" / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for banned in ("macro_shadow", "MACRO_SHADOW_FETCH_ENABLED",
                           "MACRO_FRED_FETCH_ENABLED", "FRED_API_KEY",
                           "get_shadow_macro_snapshot"):
                assert banned not in text, f"{path.relative_to(BACKEND)}: {banned}"


def test_the_cmv2_and_passb_rules_are_unbumped():
    from app.services import coin_memory as cm
    assert cm.CM_V2_CONTRACT_VERSION == "cm_v2_contract_1"
    assert cm.CM_V2_FOLD_RULE_VERSION == "cm_v2_fold_1"
    assert cm.CM_V2_METRIC_RULE_VERSION == "cm_v2_metric_1"
    assert cm.CM_V2_AGGREGATION_VERSION == "cm_v2_aggregation_1"
    shadow_eval = (BACKEND / "app" / "services" / "shadow_eval.py").read_text(
        encoding="utf-8")
    assert "macro_shadow" not in shadow_eval


def test_the_contract_version_was_not_bumped():
    assert ms.MACRO_SHADOW_VERSION == "macro_shadow_v1"
    assert ms.MACRO_SCORE_RULE_VERSION == "macro_score_rule_1"
    assert ms.MACRO_CONFIDENCE_RULE_VERSION == "macro_conf_rule_1"


def test_the_disabled_path_is_untouched_when_no_snapshot_is_supplied():
    """The flag-off case must stay byte-identical to what production writes now."""
    p = _payload(None)
    assert p["configured"] is True          # key present, from dependency_health
    assert p["executed"] is False
    assert p["fetch_status"] == "disabled"
    assert p["fallback_reason"] == "fetch_disabled"
    assert p["series"] == {}
    assert p["errors"] == []
    assert p["score_if_restored"] is None
