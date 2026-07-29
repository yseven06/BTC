"""CP-DEP-HEALTH-1 — the dependency-health telemetry contract.

Every test here runs the REAL collectors, the REAL engines and the REAL
orchestrator assembly. Nothing greps for a literal to prove behaviour; the two
places that read source do so to prove a NEGATIVE (no decision branch reads the
telemetry, no message text is persisted) and say so.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import time
from typing import Any, Dict, Optional

import httpx
import numpy as np
import pandas as pd
import pytest

from app.collectors import macro_collector as mc
from app.collectors import onchain_collector as oc
from app.collectors.macro_collector import MacroCollector
from app.collectors.onchain_collector import OnchainCollector
from app.engines.macro.engine import MacroEngine
from app.engines.onchain.engine import OnchainEngine
from app.services import candidate_log, dependency_health as dh

REQ = httpx.Request("GET", "https://example.invalid/x?api_key=SUPERSECRETVALUE")


@pytest.fixture(autouse=True)
def _clean():
    """Caches and their parallel status memory are process-global."""
    for mod, mem in ((mc, mc._MACRO_STATUS), (oc, oc._ONCHAIN_STATUS)):
        pass
    mc._MACRO_CACHE.clear(); mc._MACRO_CACHE_EXPIRY.clear(); mc._MACRO_STATUS.clear()
    oc._ONCHAIN_CACHE.clear(); oc._ONCHAIN_CACHE_EXPIRY.clear(); oc._ONCHAIN_STATUS.clear()
    yield
    mc._MACRO_CACHE.clear(); mc._MACRO_CACHE_EXPIRY.clear(); mc._MACRO_STATUS.clear()
    oc._ONCHAIN_CACHE.clear(); oc._ONCHAIN_CACHE_EXPIRY.clear(); oc._ONCHAIN_STATUS.clear()


def frame(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-07-01", periods=n, freq="15min", tz="UTC")
    c = np.linspace(100.0, 104.0, n)
    return pd.DataFrame({"open": c, "high": c * 1.004, "low": c * 0.996,
                         "close": c, "volume": np.full(n, 1000.0)}, index=idx)


class FakeClient:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    async def get(self, url, **kw):
        self.calls += 1
        return self.behaviour(url)

    async def aclose(self):
        pass


def raises(exc):
    def _(url):
        raise exc
    return _


def json_resp(payload, status=200):
    return httpx.Response(status, json=payload, request=REQ)


# ── 1 · every error class maps to an exact, honest status ──────────────────
@pytest.mark.parametrize("exc,expected", [
    (httpx.ConnectTimeout("t", request=REQ), dh.TIMEOUT),
    (httpx.ReadTimeout("t", request=REQ), dh.TIMEOUT),
    (httpx.PoolTimeout("t", request=REQ), dh.TIMEOUT),
    (httpx.ConnectError("c", request=REQ), dh.NETWORK_ERROR),
    (httpx.ReadError("r", request=REQ), dh.NETWORK_ERROR),
    (httpx.RemoteProtocolError("p", request=REQ), dh.NETWORK_ERROR),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(429, request=REQ)), dh.HTTP_429),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(500, request=REQ)), dh.HTTP_5XX),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(503, request=REQ)), dh.HTTP_5XX),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(404, request=REQ)), dh.HTTP_4XX),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(401, request=REQ)), dh.HTTP_4XX),
    (json.JSONDecodeError("bad", "{}", 0), dh.PARSE_ERROR),
    (ValueError("v"), dh.PARSE_ERROR),
    (KeyError("k"), dh.PARSE_ERROR),
    (TypeError("t"), dh.PARSE_ERROR),
    (RuntimeError("?"), dh.INTERNAL_ERROR),
])
def test_classify_exception_is_exact(exc, expected):
    assert dh.classify_exception(exc) == expected


def test_timeout_is_tested_before_network_error():
    """TimeoutException subclasses TransportError; wrong order makes every
    timeout read as a generic network error."""
    assert issubclass(httpx.TimeoutException, httpx.TransportError)
    assert dh.classify_exception(httpx.ConnectTimeout("t", request=REQ)) == dh.TIMEOUT


# ── 2 · macro: configured / not-configured / each failure ──────────────────
def test_macro_not_configured_is_recorded_for_all_four_series():
    c = MacroCollector()
    c._fred_key = ""
    snap = asyncio.run(c.fetch_us_macro_snapshot())
    assert snap["configured"] is False
    assert set(c.last_status) == {"fred_FEDFUNDS", "fred_CPIAUCSL",
                                  "fred_DGS10", "fred_DTWEXBGS"}
    assert all(v["fetch_status"] == dh.NOT_CONFIGURED for v in c.last_status.values())


@pytest.mark.parametrize("exc,expected", [
    (httpx.ConnectTimeout("t", request=REQ), dh.TIMEOUT),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(429, request=REQ)), dh.HTTP_429),
    (httpx.HTTPStatusError("e", request=REQ, response=httpx.Response(500, request=REQ)), dh.HTTP_5XX),
    (httpx.ConnectError("c", request=REQ), dh.NETWORK_ERROR),
    (ValueError("bad json"), dh.PARSE_ERROR),
])
def test_macro_fetch_failures_are_classified_and_the_return_is_unchanged(exc, expected):
    c = MacroCollector()
    c._fred_key = "placeholder"
    c.client = FakeClient(raises(exc))
    assert asyncio.run(c.fetch_fred_series("DGS10")) is None, "return contract unchanged"
    assert c.last_status["fred_DGS10"]["fetch_status"] == expected


def test_macro_empty_observation_is_empty_not_an_error():
    c = MacroCollector()
    c._fred_key = "placeholder"
    c.client = FakeClient(lambda url: json_resp({"observations": []}))
    assert asyncio.run(c.fetch_fred_series("DGS10")) is None
    assert c.last_status["fred_DGS10"]["fetch_status"] == dh.EMPTY


def test_macro_success_then_cache_hit_reports_ok_and_an_age():
    c = MacroCollector()
    c._fred_key = "placeholder"
    c.client = FakeClient(lambda url: json_resp({"observations": [{"value": "4.71"}]}))
    assert asyncio.run(c.fetch_fred_series("DGS10")) == 4.71
    assert c.last_status["fred_DGS10"]["fetch_status"] == dh.OK
    assert c.last_status["fred_DGS10"]["served_from_cache"] is False

    c2 = MacroCollector()
    c2._fred_key = "placeholder"
    c2.client = FakeClient(raises(AssertionError("must not be called")))
    assert asyncio.run(c2.fetch_fred_series("DGS10")) == 4.71
    entry = c2.last_status["fred_DGS10"]
    assert entry["served_from_cache"] is True
    assert entry["fetch_status"] == dh.OK
    assert entry["data_freshness_s"] is not None and entry["data_freshness_s"] >= 0


# ── 3 · stale cache: a cached FAILURE must not read as data ────────────────
def test_a_cached_failure_is_reported_as_stale_cache():
    c1 = OnchainCollector()
    c1.client = FakeClient(raises(httpx.ConnectTimeout("t", request=REQ)))
    asyncio.run(c1.fetch_fear_greed())
    assert c1.last_status["fear_greed"]["fetch_status"] == dh.TIMEOUT

    c2 = OnchainCollector()
    c2.client = FakeClient(lambda url: json_resp({"data": [{"value": "55"}]}))
    out = asyncio.run(c2.fetch_fear_greed())
    assert out["value"] is None, "cache behaviour unchanged — the failure still wins"
    assert c2.client.calls == 0
    assert c2.last_status["fear_greed"]["fetch_status"] == dh.STALE_CACHE
    assert c2.last_status["fear_greed"]["served_from_cache"] is True


def test_cache_ttls_and_keys_are_untouched():
    """The status memory must not have changed a single cache rule."""
    assert oc.FNG_CACHE_TTL == 300
    assert oc.BTC_NET_CACHE_TTL == 300
    assert oc.GECKO_CACHE_TTL == 1800
    assert mc.MACRO_CACHE_TTL == 900
    src = inspect.getsource(oc.OnchainCollector.fetch_fear_greed)
    assert "now + 60" in src, "the 60s failure cache is deliberately preserved"


# ── 4 · fan-out: a partial BTC-network result must not report as ok ────────
def test_btc_network_partial_failure_reports_the_worst_and_names_each_endpoint():
    c = OnchainCollector()

    def behaviour(url):
        if "blockchain.info" in url:
            return httpx.Response(200, json={"hash_rate": 6e8},
                                  headers={"content-type": "application/json"}, request=REQ)
        raise httpx.HTTPStatusError("e", request=REQ,
                                    response=httpx.Response(429, request=REQ))

    c.client = FakeClient(behaviour)
    out = asyncio.run(c.fetch_btc_network())
    assert out["hash_rate_ths"] == 6e8, "return contract unchanged"
    entry = c.last_status["btc_network"]
    assert entry["fetch_status"] == dh.HTTP_429, "worst-of, not ok"
    assert entry["components"] == {"stats": dh.OK, "mempool": dh.HTTP_429, "fees": dh.HTTP_429}


def test_worst_status_precedence():
    assert dh.worst_status([dh.OK, dh.EMPTY]) == dh.EMPTY
    assert dh.worst_status([dh.OK, dh.TIMEOUT, dh.EMPTY]) == dh.TIMEOUT
    assert dh.worst_status([dh.TIMEOUT, dh.HTTP_5XX]) == dh.HTTP_5XX
    assert dh.worst_status([]) == dh.OK


# ── 5 · engines record completeness, not just success ─────────────────────
def _stub_macro(monkeypatch, *, configured, ff=None, y10=None, statuses=None):
    class Stub:
        def __init__(self):
            self.last_status = statuses or {}

        async def fetch_us_macro_snapshot(self):
            return {"fed_funds_rate": ff, "cpi": None, "ten_year_yield": y10,
                    "usd_broad_index": None, "configured": configured}

        async def fetch_tcmb_usd_try(self):
            return None

        async def close(self):
            pass

    import app.engines.macro.engine as me
    monkeypatch.setattr(me, "MacroCollector", Stub)


def test_macro_engine_records_zero_completeness_when_unconfigured(monkeypatch):
    _stub_macro(monkeypatch, configured=False,
                statuses={"fred_DGS10": {"fetch_status": dh.NOT_CONFIGURED,
                                         "served_from_cache": False,
                                         "data_freshness_s": None}})
    eng = MacroEngine()
    res = asyncio.run(eng.analyze("BTCUSDT", "15m", frame()))
    assert (res.score, res.confidence) == (50.0, 25.0), "engine output unchanged"
    h = eng._dependency_health
    assert h["configured"] is False
    assert h["fetch_status"] == dh.NOT_CONFIGURED
    assert h["fallback_used"] is True and h["fallback_reason"] == "no_api_key"
    assert h["input_completeness"] == 0 and h["input_expected"] == 2
    assert h["confidence_semantic_type"] == dh.DATA_AVAILABILITY


def test_macro_engine_separates_configured_but_unreachable(monkeypatch):
    """The exact case that was indistinguishable before this checkpoint."""
    _stub_macro(monkeypatch, configured=True,
                statuses={"fred_DGS10": {"fetch_status": dh.HTTP_5XX,
                                         "served_from_cache": False,
                                         "data_freshness_s": None}})
    eng = MacroEngine()
    res = asyncio.run(eng.analyze("BTCUSDT", "15m", frame()))
    assert (res.score, res.confidence) == (50.0, 25.0), "identical output to no-key"
    h = eng._dependency_health
    assert h["configured"] is True, "the key WAS present"
    assert h["fetch_status"] == dh.HTTP_5XX, "and the reason it still failed"
    assert h["fallback_reason"] == "no_data"


def test_macro_engine_records_full_data(monkeypatch):
    _stub_macro(monkeypatch, configured=True, ff=3.63, y10=4.71,
                statuses={"fred_FEDFUNDS": {"fetch_status": dh.OK,
                                            "served_from_cache": False,
                                            "data_freshness_s": None},
                          "fred_DGS10": {"fetch_status": dh.OK,
                                         "served_from_cache": False,
                                         "data_freshness_s": None}})
    eng = MacroEngine()
    res = asyncio.run(eng.analyze("BTCUSDT", "15m", frame()))
    assert res.confidence == 70.0
    h = eng._dependency_health
    assert h["input_completeness"] == 2 and h["input_expected"] == 2
    assert h["fallback_used"] is False and h["fetch_status"] == dh.OK


def _stub_onchain(monkeypatch, fng, meta, statuses=None):
    class Stub:
        def __init__(self):
            self.last_status = statuses or {}

        async def fetch_fear_greed(self):
            return fng

        async def fetch_btc_network(self):
            return {}

        async def fetch_coin_metadata(self, cid):
            return meta

        async def close(self):
            pass

    import app.engines.onchain.engine as oe
    monkeypatch.setattr(oe, "OnchainCollector", Stub)


def test_onchain_engine_reports_partial_data(monkeypatch):
    _stub_onchain(monkeypatch, {"value": 30, "classification": "Fear", "delta_24h": 0}, {},
                  statuses={"fear_greed": {"fetch_status": dh.OK, "served_from_cache": False,
                                           "data_freshness_s": None},
                            "gecko_meta_ethereum": {"fetch_status": dh.HTTP_429,
                                                    "served_from_cache": False,
                                                    "data_freshness_s": None}})
    eng = OnchainEngine()
    res = asyncio.run(eng.analyze("ETHUSDT", "15m", frame()))
    assert res.confidence == 52.0, "engine output unchanged"
    h = eng._dependency_health
    assert h["input_completeness"] == 1 and h["input_expected"] == 3
    assert h["fetch_status"] == dh.HTTP_429
    assert h["components"]["gecko_meta_ethereum"] == dh.HTTP_429
    assert h["configured"] is None, "keyless public endpoints have no key question"


def test_onchain_stock_is_not_applicable_not_a_failure(monkeypatch):
    eng = OnchainEngine()
    res = asyncio.run(eng.analyze("THYAO.IS", "15m", frame(), asset_type="stock"))
    assert res.confidence == 20.0, "engine output unchanged"
    h = eng._dependency_health
    assert h["fetch_status"] == dh.NOT_APPLICABLE
    assert h["fallback_reason"] == "not_applicable_asset_type"


def test_backtest_is_not_applicable_for_both_engines(monkeypatch):
    for eng in (MacroEngine(), OnchainEngine()):
        asyncio.run(eng.analyze("BTCUSDT", "15m", frame(), is_backtest=True))
        assert eng._dependency_health["fetch_status"] == dh.NOT_APPLICABLE
        assert eng._dependency_health["fallback_reason"] == "backtest_simulated"


# ── 6 · the assembled record ──────────────────────────────────────────────
def test_build_marks_degraded_and_derives_execution_status():
    rec = dh.build_dependency_health(
        engines={
            "macro_analysis": dh.engine_entry(
                configured=False, fetch_status=dh.NOT_CONFIGURED, fallback_used=True,
                fallback_reason="no_api_key", input_completeness=0, input_expected=2,
                served_from_cache=False, data_freshness_s=None,
                confidence_semantic_type=dh.DATA_AVAILABILITY),
            "onchain_analysis": dh.engine_entry(
                configured=None, fetch_status=dh.OK, fallback_used=False,
                fallback_reason=None, input_completeness=3, input_expected=3,
                served_from_cache=False, data_freshness_s=1.0,
                confidence_semantic_type=dh.DATA_AVAILABILITY),
        },
        mtf={"15m": dh.OK, "1h": dh.OK, "4h": dh.TIMEOUT},
        engine_execution_telemetry={"failed_engine_count": 0},
    )
    assert rec["version"] == "dependency_health_v1"
    assert rec["degraded_input"] is True
    assert rec["degraded_engines"] == ["macro_analysis"]
    assert rec["mtf"]["4h"] == dh.TIMEOUT
    assert rec["engine_execution_status"] == "all_ok"


def test_a_crashed_engine_makes_execution_status_degraded():
    rec = dh.build_dependency_health(
        engines={}, mtf={}, engine_execution_telemetry={"failed_engine_count": 1})
    assert rec["engine_execution_status"] == "degraded"
    assert rec["degraded_input"] is True


def test_partial_completeness_alone_marks_degraded():
    rec = dh.build_dependency_health(
        engines={"onchain_analysis": dh.engine_entry(
            configured=None, fetch_status=dh.OK, fallback_used=False,
            fallback_reason=None, input_completeness=1, input_expected=3,
            served_from_cache=False, data_freshness_s=None,
            confidence_semantic_type=dh.DATA_AVAILABILITY)},
        mtf={}, engine_execution_telemetry={"failed_engine_count": 0})
    assert rec["degraded_engines"] == ["onchain_analysis"]


# ── 6b · end to end through the REAL orchestrator ─────────────────────────
def test_the_whole_chain_assembles_through_analyze_and_decide(monkeypatch):
    """Collectors stubbed at the network boundary; everything else is production
    code — nine real engines, the real generator, the real assembly."""
    from app.engines.ai_decision import engine as orch

    class StubBinance:
        async def fetch_ohlcv(self, symbol, tf, limit=100, **kw):
            if tf == "4h":
                raise httpx.ConnectTimeout("t", request=REQ)
            return frame()

        async def close(self):
            pass

    monkeypatch.setattr(orch, "BinanceCollector", StubBinance)
    _stub_macro(monkeypatch, configured=False)
    _stub_onchain(monkeypatch, {"value": 30, "classification": "Fear", "delta_24h": 0}, {})

    engine = orch.AIDecisionEngine()
    decision = asyncio.run(engine.analyze_and_decide("BTCUSDT", "15m", frame()))

    rec = decision["dependency_health"]
    assert rec["version"] == "dependency_health_v1"
    assert rec["degraded_input"] is True
    assert "macro_analysis" in rec["degraded_engines"]
    assert rec["engines"]["macro_analysis"]["fallback_reason"] == "no_api_key"
    assert rec["engines"]["macro_analysis"]["confidence_semantic_type"] == dh.DATA_AVAILABILITY
    # The fail-open MTF path: 4h timed out, and the record says so even though
    # the decision itself saw a harmless "neutral".
    assert rec["mtf"]["4h"] == dh.TIMEOUT
    assert rec["mtf"]["15m"] == dh.OK and rec["mtf"]["1h"] == dh.OK
    assert decision["mtf_trends"]["4h"] == "neutral", "decision value unchanged"
    assert rec["engine_execution_status"] == "all_ok"


def test_the_new_key_never_reaches_the_public_engines_data_payload(monkeypatch):
    """`decision["engine_results"]` is written to `signals.engines_data` and
    served verbatim by /api/reports. The telemetry must not be in it."""
    from app.engines.ai_decision import engine as orch

    class StubBinance:
        async def fetch_ohlcv(self, symbol, tf, limit=100, **kw):
            return frame()

        async def close(self):
            pass

    monkeypatch.setattr(orch, "BinanceCollector", StubBinance)
    _stub_macro(monkeypatch, configured=False)
    _stub_onchain(monkeypatch, {"value": 30, "classification": "Fear", "delta_24h": 0}, {})
    decision = asyncio.run(
        orch.AIDecisionEngine().analyze_and_decide("BTCUSDT", "15m", frame()))
    blob = json.dumps(decision["engine_results"], default=str)
    assert "dependency_health" not in blob
    assert "fetch_status" not in blob
    for res in decision["engine_results"]:
        assert set(res) == {"engine_name", "score", "bias", "confidence",
                            "key_findings", "supporting_data", "warnings"}


# ── 7 · no secret and no raw error text may be persisted ──────────────────
def test_no_exception_message_url_or_secret_reaches_the_record():
    """REQ's URL carries a fake api_key. Nothing derived from it may appear."""
    c = MacroCollector()
    c._fred_key = "placeholder"
    c.client = FakeClient(raises(httpx.HTTPStatusError(
        "boom https://example.invalid/x?api_key=SUPERSECRETVALUE",
        request=REQ, response=httpx.Response(500, request=REQ))))
    asyncio.run(c.fetch_fred_series("DGS10"))
    blob = json.dumps(c.last_status)
    # NB: "http" alone is not a forbidden token — `http_5xx` is a legitimate
    # status name. What must never appear is the secret, the query parameter,
    # the host, the message text or a URL scheme.
    for forbidden in ("SUPERSECRETVALUE", "api_key", "example.invalid",
                      "boom", "https://", "http://"):
        assert forbidden not in blob, f"{forbidden!r} leaked into the telemetry"
    assert c.last_status["fred_DGS10"]["fetch_status"] == dh.HTTP_5XX


def test_the_status_vocabulary_is_closed():
    """Only the fixed vocabulary may ever be written — never free text."""
    allowed = {dh.OK, dh.NOT_CONFIGURED, dh.TIMEOUT, dh.HTTP_429, dh.HTTP_5XX,
               dh.HTTP_4XX, dh.NETWORK_ERROR, dh.PARSE_ERROR, dh.EMPTY,
               dh.STALE_CACHE, dh.INTERNAL_ERROR, dh.NOT_APPLICABLE, dh.UNKNOWN}
    for exc in (RuntimeError("x"), ValueError("y"), httpx.ConnectError("z", request=REQ)):
        assert dh.classify_exception(exc) in allowed


def test_classify_never_reads_the_message():
    # getsource on a module-level function is already at column 0; cleandoc
    # would re-indent the docstring away from its body and break the parse.
    tree = ast.parse(inspect.getsource(dh.classify_exception))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "str", "str(exc) must never be an input"
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("args", "message"), "message text is off limits"


# ── 8 · fail-open: telemetry can never take the decision down ─────────────
def test_orchestrator_wrapper_returns_none_when_assembly_explodes(monkeypatch):
    from app.engines.ai_decision import engine as orch

    def boom(**kw):
        raise RuntimeError("telemetry exploded")

    monkeypatch.setattr(orch.dh, "build_dependency_health", boom)
    assert orch._dependency_health_or_none([], {}, None) is None


def test_engine_records_none_rather_than_raising_when_health_fails(monkeypatch):
    import app.engines.macro.engine as me
    monkeypatch.setattr(me, "engine_entry",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    _stub_macro(monkeypatch, configured=False)
    eng = MacroEngine()
    res = asyncio.run(eng.analyze("BTCUSDT", "15m", frame()))
    assert (res.score, res.confidence) == (50.0, 25.0), "decision survived intact"
    assert eng._dependency_health is None


def test_collector_note_never_raises():
    c = MacroCollector()
    c.last_status = None            # force an internal failure
    c._note("k", dh.OK)             # must swallow
    assert True


# ── 9 · candidate_log: namespaced, additive, and never read by a decision ──
def test_candidate_log_writes_the_namespace_and_keeps_everything_else():
    from tests.test_dep_health_parity import FROZEN_EXTRA_KEYS, _values
    record = {"version": "dependency_health_v1", "degraded_input": True,
              "degraded_engines": ["macro_analysis"], "engines": {},
              "mtf": {}, "engine_execution_status": "all_ok"}
    extra = _values(decision={"dependency_health": record})["extra"]
    assert extra["dependency_health_v1"] == record
    assert FROZEN_EXTRA_KEYS <= set(extra), "no pre-existing key was dropped"
    assert extra["primary_demotion_reason"] == "not_actionable"


def test_a_missing_record_is_none_and_breaks_nothing():
    from tests.test_dep_health_parity import _values
    extra = _values()["extra"]
    assert extra["dependency_health_v1"] is None


def test_nothing_in_the_decision_path_reads_the_telemetry():
    """The hard rule: observability that a branch can read is not observability."""
    import app.engines.ai_decision.signal_generator as sg
    import app.services.scheduler as sched
    for mod in (sg, sched):
        src = inspect.getsource(mod)
        assert "dependency_health" not in src, (
            f"{mod.__name__} references the telemetry — no decision code may")


def test_the_record_survives_the_json_safe_depth_cap():
    """`_json_safe` stringifies anything deeper than 6 levels FROM `extra`.

    The record nests extra(0) → dependency_health_v1(1) → engines(2) →
    macro_analysis(3) → components(4) → status(5). One more level and the
    component map would silently become a string, which is exactly the kind of
    quiet loss this telemetry exists to prevent.
    """
    from tests.test_dep_health_parity import _values
    record = dh.build_dependency_health(
        engines={"macro_analysis": dh.engine_entry(
            configured=False, fetch_status=dh.NOT_CONFIGURED, fallback_used=True,
            fallback_reason="no_api_key", input_completeness=0, input_expected=2,
            served_from_cache=False, data_freshness_s=None,
            confidence_semantic_type=dh.DATA_AVAILABILITY,
            components={"fred_DGS10": dh.NOT_CONFIGURED})},
        mtf={"15m": dh.OK}, engine_execution_telemetry={"failed_engine_count": 0})
    stored = _values(decision={"dependency_health": record})["extra"]["dependency_health_v1"]
    comps = stored["engines"]["macro_analysis"]["components"]
    assert isinstance(comps, dict), "the deepest level must survive as a dict"
    assert comps["fred_DGS10"] == dh.NOT_CONFIGURED


def test_the_record_is_json_serialisable():
    """`extra` is a json column; a non-serialisable value would fail at write."""
    rec = dh.build_dependency_health(
        engines={"macro_analysis": dh.engine_entry(
            configured=False, fetch_status=dh.NOT_CONFIGURED, fallback_used=True,
            fallback_reason="no_api_key", input_completeness=0, input_expected=2,
            served_from_cache=False, data_freshness_s=None,
            confidence_semantic_type=dh.DATA_AVAILABILITY)},
        mtf={"15m": dh.OK}, engine_execution_telemetry={"failed_engine_count": 0})
    assert json.loads(json.dumps(candidate_log._json_safe(rec))) == rec
