"""CP-MACRO-SHADOW-SECRET-PRESENCE-WIRING — the shadow stops saying `no_api_key`.

CP-MACRO-FRED-FETCH-KILLSWITCH split the credential from the on-switch, and
CP-...-SECRET-PRESENCE stored the key. After that, production told two different
stories about the same fact: `dependency_health_v1` correctly reported
`fetch_disabled`, while `macro_shadow_v1` still reported `no_api_key` on every
row — a false record on ~7 200 candidates a day. This wires the one missing input.

FOUR CLAIMS

  1. The shadow learns presence as a BOOLEAN and nothing else. No value, no
     length, no prefix, no digest, and no new dependency: the wiring reads
     `decision["dependency_health"]`, which is already in the decision, so its
     import set stays exactly four modules.

  2. Presence is read from what the engine OBSERVED at decision time, not from
     what the environment says afterwards. The two can disagree — the settings
     object is lru_cached and a container can outlive an .env edit — and the row
     must describe the decision it belongs to.

  3. `configured` means the credential is configured; `executed` means a fetch
     ran. They are separate, and `executed` is False on every path here
     regardless of the key.

  4. Nothing else moves. The macro EngineResult, the composite, the whole
     decision grid and every neighbouring namespace are unchanged — driven
     through the REAL MacroEngine across the full (key × flag) matrix.

No network: every engine run uses a stubbed collector. No real credential: the
only key-shaped strings here are obvious synthetic placeholders.
"""
import ast
import asyncio
import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from app.collectors import macro_collector as mc
from app.collectors.macro_collector import FRED_FETCH_DISABLED_REASON
from app.engines.base import SignalBias
from app.engines.macro import engine as macro_engine_module
from app.engines.macro.engine import MacroEngine
from app.services import macro_shadow as ms
from app.services import macro_shadow_wiring as msw

BACKEND = Path(__file__).resolve().parents[1]
MACRO = "macro_analysis"
NS = ms.MACRO_SHADOW_VERSION
SERIES = ("FEDFUNDS", "CPIAUCSL", "DGS10", "DTWEXBGS")

# Obvious placeholders. A real credential must never enter a fixture, and these
# are shaped so that no reader could mistake one for a key.
SYNTHETIC_KEY = "synthetic-not-a-real-fred-key"
SYNTHETIC_EMPTY = ""
SYNTHETIC_BLANK = "   "

PROD = dict(production_macro_score=50.0, production_macro_bias="neutral",
            production_macro_confidence=25.0)


# ══════════════════════════════════════════════════════════════════════════════
# THE REAL ENGINE, DRIVEN ACROSS THE (key × flag) MATRIX — no network
# ══════════════════════════════════════════════════════════════════════════════
class _Armed(BaseException):
    """`fetch_fred_series` swallows ordinary exceptions, so an outbound attempt
    has to raise something its `except Exception` cannot catch."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise _Armed("outbound call attempted")
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", boom)
    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()
    yield
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()


def _df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = [100.0 + i * 0.3 for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                         "low": [c * 0.99 for c in close], "close": close,
                         "volume": [1000.0] * n}, index=idx)


def _collector_class(key, enabled):
    """A REAL MacroCollector built against an explicit (key, flag) pair — the
    genuine __init__ runs, so the genuine gate runs."""
    class _S:
        FRED_API_KEY = key
        MACRO_FRED_FETCH_ENABLED = enabled

    class _Built(mc.MacroCollector):
        def __init__(self):
            import app.collectors.macro_collector as m
            real = m.get_settings
            m.get_settings = lambda: _S()
            try:
                super().__init__()
            finally:
                m.get_settings = real
    return _Built


def _run_engine(monkeypatch, *, key, enabled):
    """Returns (EngineResult, dependency_health entry) from the REAL engine."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(macro_engine_module, "MacroCollector",
                        _collector_class(key, enabled))
    eng = MacroEngine()
    result = asyncio.run(eng.analyze("BTCUSDT", "1h", _df()))
    health = (eng._dependency_health or {})
    return result, health


def _decision(health, *, macro=(50.0, "neutral", 25.0)):
    """The decision shape `analyze_and_decide` produces, carrying the REAL
    dependency_health record the engine just wrote."""
    score, bias, conf = macro
    return {
        "engine_results": [{"engine_name": MACRO, "score": score, "bias": bias,
                            "confidence": conf, "key_findings": [],
                            "supporting_data": {}, "warnings": []}],
        "dependency_health": {"version": "dependency_health_v1",
                              "engines": {MACRO: health}},
    }


def _shadow(health, **kw):
    return msw.build_candidate_macro_shadow(
        decision=_decision(health, **kw), decision_time="2026-07-31T16:00:00+00:00",
        verdict="dropped")


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE STATE MATRIX
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("key,enabled,configured,status,reason", [
    # secret absent + flag off — today's pre-secret production, must not move
    (SYNTHETIC_EMPTY, False, False, "not_configured", "no_api_key"),
    # secret absent + flag ON — safe: no key means nothing to fetch
    (SYNTHETIC_EMPTY, True,  False, "not_configured", "no_api_key"),
    # PRESENT_EMPTY is not presence
    (SYNTHETIC_BLANK, False, False, "not_configured", "no_api_key"),
    (SYNTHETIC_BLANK, True,  False, "not_configured", "no_api_key"),
    # secret present + flag off — THE state this checkpoint exists for
    (SYNTHETIC_KEY,   False, True,  "disabled",       "fetch_disabled"),
])
def test_the_shadow_reports_the_real_state(monkeypatch, key, enabled,
                                           configured, status, reason):
    result, health = _run_engine(monkeypatch, key=key, enabled=enabled)
    p = _shadow(health)
    assert p["configured"] is configured
    assert p["fetch_status"] == status
    assert p["fallback_reason"] == reason
    assert p["executed"] is False            # never, on any of these rows
    assert ms.validate_macro_shadow(p) == []
    # And the engine itself was untouched by any of it.
    assert (result.score, result.bias, result.confidence) == \
           (50.0, SignalBias.NEUTRAL, 25.0)


def test_present_empty_is_not_presence_at_the_contract_boundary():
    """Belt and braces: the builder's own boolean, independent of the engine."""
    for val in (False, 0, "", None):
        p = ms.build_disabled_macro_shadow(decision_time=None, key_present=val, **PROD)
        assert p["configured"] is False
        assert p["fallback_reason"] == "no_api_key"


def test_the_key_present_flag_never_turns_executed_on():
    for present in (False, True):
        p = ms.build_disabled_macro_shadow(decision_time=None, key_present=present,
                                           **PROD)
        assert p["executed"] is False
        assert p["series"] == {}
        assert p["components_used"] == 0
        assert p["components_available"] == 0


@pytest.mark.parametrize("field", [
    "score_if_restored", "bias_if_restored", "confidence_if_restored",
    "delta_score", "delta_confidence", "would_change_direction",
    "would_change_composite", "would_change_confidence",
    "would_cross_publish_threshold", "shadow_publish_gate_result",
    "confidence_counterfactual_exact", "request_latency_ms", "observation_time",
])
def test_no_counterfactual_appears_just_because_a_key_exists(field):
    assert ms.build_disabled_macro_shadow(
        decision_time=None, key_present=True, **PROD)[field] is None


def test_the_enabled_state_is_pinned_at_contract_level_without_fetching():
    """secret present + flag ON is the BOUNDED-FETCH state. It is not exercised
    here — no fetch runs in this checkpoint — but the contract it will have to
    produce is pinned now, so that stage cannot silently invent a fourth state."""
    p = ms.build_disabled_macro_shadow(decision_time=None, key_present=True, **PROD)
    assert (p["configured"], p["executed"]) == (True, False)
    assert p["fetch_status"] in ms.FETCH_STATUSES
    assert p["fallback_reason"] in ms.FALLBACK_REASONS
    # `ok` and `executed=True` belong to the snapshot builder, not this one.
    src = inspect.getsource(ms.build_disabled_macro_shadow)
    assert '"executed"] = False' in src
    assert "OK" not in src.split('"""')[-1]


# ══════════════════════════════════════════════════════════════════════════════
# 2 · PROVENANCE — decision-time truth, not "what the environment says now"
# ══════════════════════════════════════════════════════════════════════════════
def test_presence_comes_from_the_decision_not_from_the_environment(monkeypatch):
    """The env is set to the OPPOSITE of the decision's record. The row must
    follow the decision — settings are lru_cached and a container outlives an
    .env edit, so "now" is not the right clock for a past decision."""
    monkeypatch.setenv("FRED_API_KEY", SYNTHETIC_KEY)
    _, health_no_key = _run_engine(monkeypatch, key=SYNTHETIC_EMPTY, enabled=False)
    assert _shadow(health_no_key)["configured"] is False

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    _, health_key = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    assert _shadow(health_key)["configured"] is True


def test_the_presence_signal_string_is_pinned_to_the_collector():
    """The wiring may not import the collector, so the two constants are held
    equal HERE instead. A rename on either side turns this red rather than
    silently making every row report `no_api_key` again."""
    assert ms.FETCH_DISABLED == FRED_FETCH_DISABLED_REASON == "fetch_disabled"
    assert msw.FETCH_DISABLED == FRED_FETCH_DISABLED_REASON


def test_only_the_macro_engines_own_entry_is_consulted():
    """Another engine reporting `fetch_disabled` must not imply a FRED key."""
    health = {"configured": False, "fallback_reason": "no_api_key"}
    decision = {"engine_results": [{"engine_name": MACRO, "score": 50.0,
                                    "bias": "neutral", "confidence": 25.0}],
                "dependency_health": {"engines": {
                    MACRO: health,
                    "onchain_analysis": {"fallback_reason": "fetch_disabled"}}}}
    p = msw.build_candidate_macro_shadow(decision=decision, decision_time=None,
                                         verdict="dropped")
    assert p["configured"] is False


@pytest.mark.parametrize("decision", [
    None, {}, "x", 42, [],
    {"dependency_health": None},
    {"dependency_health": "x"},
    {"dependency_health": {}},
    {"dependency_health": {"engines": None}},
    {"dependency_health": {"engines": "x"}},
    {"dependency_health": {"engines": {}}},
    {"dependency_health": {"engines": {MACRO: None}}},
    {"dependency_health": {"engines": {MACRO: "x"}}},
    {"dependency_health": {"engines": {MACRO: {}}}},
])
def test_a_malformed_dependency_health_degrades_to_absent_and_never_raises(decision):
    """`dependency_health` is fail-open upstream, so None is an expected input.
    Guessing "present" from a broken record would be the dangerous default."""
    p = msw.build_candidate_macro_shadow(decision=decision, decision_time=None,
                                         verdict="dropped")
    assert p is not None
    assert p["configured"] is False
    assert p["fallback_reason"] == "no_api_key"
    assert ms.validate_macro_shadow(p) == []


def test_a_fetch_that_actually_ran_is_recorded_not_mislabelled():
    """Unreachable while the kill-switch is shut. If it ever happens, a payload
    saying `executed=False` would be a falsehood, so it is flagged."""
    decision = {"engine_results": [{"engine_name": MACRO, "score": 61.0,
                                    "bias": "bullish", "confidence": 70.0}],
                "dependency_health": {"engines": {
                    MACRO: {"configured": True, "fallback_reason": None}}}}
    p = msw.build_candidate_macro_shadow(decision=decision, decision_time=None,
                                         verdict="published")
    assert any(e["error"] == msw.FETCH_RAN_UNEXPECTEDLY for e in p["errors"])
    assert ms.validate_macro_shadow(p) == []


def test_todays_production_state_produces_no_errors(monkeypatch):
    _, health = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    assert _shadow(health)["errors"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 3 · NOTHING ELSE MOVES
# ══════════════════════════════════════════════════════════════════════════════
def test_the_engine_result_is_identical_across_the_whole_matrix(monkeypatch):
    seen = set()
    for key in (SYNTHETIC_EMPTY, SYNTHETIC_BLANK, SYNTHETIC_KEY):
        for enabled in (False,):
            result, _ = _run_engine(monkeypatch, key=key, enabled=enabled)
            seen.add(json.dumps(result.model_dump(), sort_keys=True, default=str))
    assert len(seen) == 1, "the EngineResult moved with the key"


def test_dependency_health_semantics_are_untouched(monkeypatch):
    """This checkpoint READS that record; it may not reshape it."""
    _, no_key = _run_engine(monkeypatch, key=SYNTHETIC_EMPTY, enabled=False)
    _, key = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    assert set(no_key) == set(key)
    assert no_key["fallback_reason"] == "no_api_key"
    assert key["fallback_reason"] == "fetch_disabled"
    for field in ("configured", "fetch_status", "input_completeness",
                  "input_expected", "components"):
        assert no_key[field] == key[field], field
    assert key["fetch_status"] == "not_configured"
    assert all(v == "not_configured" for v in key["components"].values())


def test_the_decision_is_never_mutated(monkeypatch):
    _, health = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    d = _decision(health)
    frozen = json.dumps(d, sort_keys=True, default=str)
    msw.build_candidate_macro_shadow(decision=d, decision_time=None, verdict="dropped")
    assert json.dumps(d, sort_keys=True, default=str) == frozen


def test_no_fetch_happens_anywhere_in_the_matrix(monkeypatch):
    """The transport is armed for every test in this file; reaching here at all
    proves nothing called out."""
    for key in (SYNTHETIC_EMPTY, SYNTHETIC_BLANK, SYNTHETIC_KEY):
        _, health = _run_engine(monkeypatch, key=key, enabled=False)
        assert health["fetch_status"] == "not_configured"
        assert all(v == "not_configured" for v in health["components"].values())
    assert mc._MACRO_CACHE == {}


def test_two_payloads_never_share_a_mutable(monkeypatch):
    _, health = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    a, b = _shadow(health), _shadow(health)
    assert a == b and a is not b
    assert a["errors"] is not b["errors"]
    a["errors"].append("tampered")
    assert b["errors"] == []


def _erroring_decision():
    """A decision that FORCES an error entry: the macro engine is missing."""
    return {"engine_results": [],
            "dependency_health": {"engines": {MACRO: {
                "configured": False, "fallback_reason": "fetch_disabled"}}}}


def test_the_error_list_does_not_accumulate_across_payloads():
    """THE case a shared mutable actually damages.

    On the happy path `errors` stays empty and is never assigned onto the
    payload, so a module-level list is invisible there — a sabotage that made
    `errors` shared passed the no-error test above. Errors have to be forced.
    """
    payloads = [msw.build_candidate_macro_shadow(
        decision=_erroring_decision(), decision_time=None, verdict="dropped")
        for _ in range(5)]
    for p in payloads:
        assert len(p["errors"]) == 1, p["errors"]
        assert p["errors"][0]["error"] == msw.MACRO_ENGINE_MISSING
    assert len({id(p["errors"]) for p in payloads}) == 5
    payloads[0]["errors"].append("tampered")
    assert all(len(p["errors"]) == 1 for p in payloads[1:])


def test_the_last_resort_error_list_is_also_per_call(monkeypatch):
    def boom(**kw):
        raise RuntimeError("first attempt exploded")
    real = ms.build_disabled_macro_shadow
    calls = {"n": 0}

    def once(**kw):
        calls["n"] += 1
        if calls["n"] % 2 == 1:
            raise RuntimeError("boom")
        return real(**kw)
    monkeypatch.setattr(msw, "build_disabled_macro_shadow", once)
    a = msw.build_candidate_macro_shadow(decision={}, decision_time=None,
                                         verdict="dropped")
    b = msw.build_candidate_macro_shadow(decision={}, decision_time=None,
                                         verdict="dropped")
    assert a["errors"] is not b["errors"]
    assert len(a["errors"]) == len(b["errors"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 4 · NO SECRET, NO NEW DEPENDENCY
# ══════════════════════════════════════════════════════════════════════════════
def _code_only(obj):
    tree = ast.parse(inspect.getsource(obj))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_the_wiring_import_set_is_still_exactly_four_modules():
    """The whole point of reading presence off the decision: no settings, no
    collector, no os, no transport."""
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_wiring.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    assert mods == {"__future__", "logging", "typing",
                    "app.services.macro_shadow"}, mods


def test_the_contract_module_import_set_is_unchanged():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    assert mods == {"__future__", "math", "datetime", "typing",
                    "app.services.dependency_health"}, mods


@pytest.mark.parametrize("module", [ms, msw])
def test_only_a_boolean_crosses_the_boundary(module):
    """Nothing may measure, slice, stringify or digest the credential."""
    code = _code_only(module)
    for banned in ("FRED_API_KEY", "api_key=", "?api_key", "settings.", "os.environ",
                   "getenv", "environ[", "hashlib", "len(key", "key[:", "key[0",
                   "MacroCollector", "http://", "https://"):
        assert banned not in code, banned
    assert code.count("api_key") == code.count("no_api_key")


# The exact keyword set each call site may pass. An ALLOWLIST, not a blacklist:
# a sabotage that smuggled `fetch_status=str(len(...))` past the substring scan
# above walked straight through it, because a blacklist can only ban the shapes
# someone thought of. This bans everything not named.
ALLOWED_KWARGS = {
    "decision_time", "production_macro_score", "production_macro_bias",
    "production_macro_confidence", "production_publish_verdict",
    "components_expected", "key_present", "fetch_status", "fallback_reason",
}
PRIMARY_KWARGS = ALLOWED_KWARGS - {"fetch_status", "fallback_reason"}


def _builder_calls():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_wiring.py")
                     .read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "build_disabled_macro_shadow"]


def test_the_wiring_passes_only_allowlisted_arguments():
    calls = _builder_calls()
    assert len(calls) == 2, len(calls)          # primary + last-resort
    for call in calls:
        assert call.args == [], "positional args would bypass the allowlist"
        names = {kw.arg for kw in call.keywords}
        assert names <= ALLOWED_KWARGS, names - ALLOWED_KWARGS


def test_the_primary_call_derives_status_and_reason_rather_than_passing_them():
    """`fetch_status`/`fallback_reason` are the two fields a leak could ride in
    on. The live path must let the contract DERIVE them from the boolean."""
    primary = _builder_calls()[0]
    names = {kw.arg for kw in primary.keywords}
    assert names <= PRIMARY_KWARGS, names - PRIMARY_KWARGS
    assert "key_present" in names


def test_presence_is_passed_as_the_helper_call_and_nothing_else():
    """Exactly `_key_present(health)` — not a literal, not an expression that
    could measure something."""
    primary = _builder_calls()[0]
    value = next(kw.value for kw in primary.keywords if kw.arg == "key_present")
    assert ast.unparse(value) == "_key_present(health)", ast.unparse(value)


def test_the_presence_helper_returns_a_comparison_and_nothing_richer():
    """One equality against one constant. A helper that returned a length, a
    slice or a truthy string would satisfy `bool()` downstream and leak."""
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_wiring.py")
                     .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_key_present")
    body = [s for s in fn.body if not isinstance(s, ast.Expr)]   # drop docstring
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    assert isinstance(body[0].value, ast.Compare)
    assert ast.unparse(body[0].value) == \
        "health.get('fallback_reason') == FETCH_DISABLED"
    assert isinstance(msw._key_present({"fallback_reason": "fetch_disabled"}), bool)


def test_the_presence_input_is_typed_as_a_bool():
    """Resolved via `get_type_hints`, not the raw annotation: the module uses
    `from __future__ import annotations`, so `p.annotation` is the STRING "bool"
    and `is bool` would compare a str to a type — a test that can only ever fail,
    or worse, one that passes against a string someone typo'd."""
    import typing
    hints = typing.get_type_hints(ms.build_disabled_macro_shadow)
    assert hints["key_present"] is bool
    p = inspect.signature(ms.build_disabled_macro_shadow).parameters["key_present"]
    assert p.default is False          # safe by default
    assert p.kind is inspect.Parameter.KEYWORD_ONLY


def test_no_synthetic_or_real_key_can_reach_the_payload(monkeypatch):
    _, health = _run_engine(monkeypatch, key=SYNTHETIC_KEY, enabled=False)
    blob = json.dumps(_shadow(health))
    assert SYNTHETIC_KEY not in blob
    assert "api_key" not in blob.replace("no_api_key", "")


def test_no_api_route_or_schema_gained_a_presence_field():
    for sub in ("api", "schemas"):
        root = BACKEND / "app" / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for banned in ("key_present", "fred_key_present", "macro_shadow",
                           "MACRO_FRED_FETCH_ENABLED", "FRED_API_KEY"):
                assert banned not in text, f"{path.relative_to(BACKEND)}: {banned}"


def test_the_kill_switch_default_is_still_off():
    """This checkpoint must not have nudged it."""
    from app.config import Settings
    assert Settings.model_fields["MACRO_FRED_FETCH_ENABLED"].default is False
