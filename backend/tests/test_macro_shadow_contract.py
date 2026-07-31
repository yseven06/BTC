"""CP-MACRO-SHADOW-RESTORE-IMPLEMENTATION-A — `macro_shadow_v1`, Stage 1.

What Stage 1 ships: a pure contract and its arithmetic. What it deliberately does
NOT ship: a call site. So the tests are organised around proving two things.

  1. The shadow computes what the real macro engine WOULD have computed. Not
     "something similar" — the score, confidence and bias rules are restated in the
     shadow module (they are inline in engine.py and cannot be imported without
     editing production), so every boundary is pinned against the REAL
     MacroEngine.analyze() running with a stubbed collector. Drift is a red test,
     not a second truth.

  2. It cannot reach a decision. The shadow never builds an EngineResult and never
     enters `engine_results` — which is the single list composite, confidence,
     disagreement and consensus all read from, so that one property closes every
     leak path at once. Reinforced here by a repo scan proving no production module
     imports the shadow at all, and by frozen digests over the whole decision grid.

No DB, no network, no clock dependency, no secret.
"""
import ast
import asyncio
import hashlib
import inspect
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from app.engines.ai_decision.signal_generator import (
    BASE_ENGINE_WEIGHTS, generate_signal,
)
from app.engines.base import EngineResult, SignalBias
from app.engines.macro import engine as macro_engine_module
from app.engines.macro.engine import MacroEngine
from app.services import coin_memory as cm
from app.services import macro_shadow as ms

BACKEND = Path(__file__).resolve().parents[1]
E9 = list(BASE_ENGINE_WEIGHTS)
DT = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)

PROD = dict(production_macro_score=50.0, production_macro_bias="neutral",
            production_macro_confidence=25.0)


def _snap(ff=4.33, y10=4.10, *, ff_date="2026-06-01", y10_date="2026-07-29",
          configured=True, drop=(), **kw):
    """Immutable-ish FRED snapshot fixture. `drop` removes a series entirely."""
    series = {}
    if ms.SERIES_FEDFUNDS not in drop:
        series[ms.SERIES_FEDFUNDS] = {
            "value": ff, "observation_date": ff_date, "fetch_status": "ok",
            "retrieved_at": "2026-07-30T11:59:00+00:00", "cache_status": "miss",
            "cache_age_s": None, "latency_ms": 210.5, "error_class": None}
    if ms.SERIES_DGS10 not in drop:
        series[ms.SERIES_DGS10] = {
            "value": y10, "observation_date": y10_date, "fetch_status": "ok",
            "retrieved_at": "2026-07-30T11:59:00+00:00", "cache_status": "miss",
            "cache_age_s": None, "latency_ms": 198.0, "error_class": None}
    out = {"configured": configured, "cache_status": "miss", "cache_age_s": None,
           "request_latency_ms": 412.0,
           "observation_time": "2026-07-30T11:59:00+00:00", "series": series}
    out.update(kw)
    return out


def _build(**kw):
    base = dict(decision_time=DT, snapshot=_snap(), engine_count=9,
                production_total_confidence=62.0, publish_threshold=65.0,
                production_publish_verdict="dropped", **PROD)
    base.update(kw)
    return ms.build_macro_shadow_from_snapshot(**base)


# ══════════════════════════════════════════════════════════════════════════════
# 1-3 · CONTRACT SHAPE · VERSION · JSON
# ══════════════════════════════════════════════════════════════════════════════
def test_contract_shape_is_complete():
    for payload in (ms.build_disabled_macro_shadow(decision_time=DT, **PROD), _build()):
        assert set(payload) == set(ms.REQUIRED_TOP_LEVEL), (
            set(payload) ^ set(ms.REQUIRED_TOP_LEVEL))
        assert ms.validate_macro_shadow(payload) == []


def test_series_contract_shape_is_complete():
    payload = _build()
    assert set(payload["series"]) == set(ms.ALL_SERIES)
    for sid, entry in payload["series"].items():
        assert set(entry) == set(ms.REQUIRED_SERIES_FIELDS), sid


def test_contract_version_and_mode_are_fixed():
    p = _build()
    assert p["version"] == ms.MACRO_SHADOW_VERSION == "macro_shadow_v1"
    assert p["mode"] == ms.MACRO_SHADOW_MODE == "shadow_observation_only"
    assert p["score_rule_version"] == "macro_score_rule_1"
    assert p["confidence_rule_version"] == "macro_conf_rule_1"


def test_versions_come_from_one_source():
    src = inspect.getsource(ms)
    for literal in ('"macro_shadow_v1"', '"shadow_observation_only"',
                    '"macro_score_rule_1"', '"macro_conf_rule_1"'):
        assert src.count(literal) == 1, literal


def test_payload_is_json_serialisable_and_finite():
    for payload in (ms.build_disabled_macro_shadow(decision_time=DT, **PROD),
                    _build(), _build(snapshot=_snap(ff=None, y10=None)),
                    _build(snapshot=None)):
        blob = json.dumps(payload)
        assert "NaN" not in blob and "Infinity" not in blob
        assert json.loads(blob) == payload


# ══════════════════════════════════════════════════════════════════════════════
# 4 · DISABLED PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════
def test_disabled_payload_semantics():
    p = ms.build_disabled_macro_shadow(decision_time=DT, **PROD)
    assert p["configured"] is False and p["executed"] is False
    assert p["fetch_status"] == "not_configured"
    assert p["fallback_reason"] == "no_api_key"
    for k in ("score_if_restored", "bias_if_restored", "confidence_if_restored",
              "delta_score", "delta_confidence", "would_change_confidence",
              "would_cross_publish_threshold"):
        assert p[k] is None, k
    assert p["decision_isolation_verified"] is True
    assert p["errors"] == []


def test_disabled_payload_reflects_todays_production_state():
    """The values are ARGUMENTS, not constants — but today they are exactly these."""
    p = ms.build_disabled_macro_shadow(decision_time=DT, **PROD)
    assert p["production_macro_score"] == 50.0
    assert p["production_macro_bias"] == "neutral"
    assert p["production_macro_confidence"] == 25.0


def test_disabled_payload_does_not_hard_code_production_values():
    p = ms.build_disabled_macro_shadow(
        decision_time=DT, production_macro_score=61.0,
        production_macro_bias="bullish", production_macro_confidence=70.0)
    assert (p["production_macro_score"], p["production_macro_bias"],
            p["production_macro_confidence"]) == (61.0, "bullish", 70.0)
    src = inspect.getsource(ms.build_disabled_macro_shadow)
    assert "50.0" not in src and "25.0" not in src


def test_disabled_payload_series_map_is_complete_but_unrequested():
    p = ms.build_disabled_macro_shadow(decision_time=DT, **PROD)
    assert set(p["series"]) == set(ms.ALL_SERIES)
    assert all(e["requested"] is False for e in p["series"].values())


# ══════════════════════════════════════════════════════════════════════════════
# 5-7 · COMPLETE / PARTIAL / MISSING SERIES
# ══════════════════════════════════════════════════════════════════════════════
def test_complete_two_series():
    p = _build()
    assert p["executed"] is True
    assert p["components_expected"] == 2 and p["components_used"] == 2
    assert p["confidence_if_restored"] == 70.0
    assert p["fetch_status"] == "ok" and p["fallback_reason"] is None


def test_partial_one_series():
    p = _build(snapshot=_snap(y10=None))
    assert p["components_used"] == 1
    assert p["confidence_if_restored"] == 55.0
    assert p["fallback_reason"] == "partial_data"


def test_missing_series_entirely():
    p = _build(snapshot=_snap(drop=(ms.SERIES_FEDFUNDS, ms.SERIES_DGS10)))
    assert p["components_used"] == 0 and p["components_available"] == 0
    assert p["confidence_if_restored"] == 25.0          # NOT min(40,85)=40
    assert p["fallback_reason"] == "no_data"


@pytest.mark.parametrize("snap,components,confidence", [
    (_snap(ff=None), 1, 55.0),
    (_snap(y10=None), 1, 55.0),
    (_snap(drop=(ms.SERIES_DGS10,)), 1, 55.0),
    (_snap(ff=None, y10=None), 0, 25.0),
    (_snap(drop=(ms.SERIES_FEDFUNDS, ms.SERIES_DGS10)), 0, 25.0),
])
def test_incomplete_series_produce_the_exact_expected_confidence(snap, components,
                                                                 confidence):
    """Asserts the EXACT value, not merely `!= 70`. A sabotage run showed the
    loose form let `components <= 0` degrade to `components < 0` — which turns the
    zero-component case from 25.0 into 40.0 — pass unnoticed."""
    p = _build(snapshot=snap)
    assert p["components_used"] == components
    assert p["confidence_if_restored"] == confidence
    assert p["confidence_if_restored"] != 70.0


def test_unscored_series_are_declared_but_never_requested():
    p = _build()
    for sid in ms.UNSCORED_SERIES:
        e = p["series"][sid]
        assert e["requested"] is False
        assert e["used_by_macro_score"] is False
        assert e["excluded_from_score_reason"] == "not_read_by_engine"
    for sid in ms.SCORED_SERIES:
        assert p["series"][sid]["used_by_macro_score"] is True


# ══════════════════════════════════════════════════════════════════════════════
# EQUIVALENCE WITH THE REAL ENGINE — the anti-drift gate
# ══════════════════════════════════════════════════════════════════════════════
def _df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = [100.0 + i * 0.3 for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                         "low": [c * 0.99 for c in close], "close": close,
                         "volume": [1000.0] * n}, index=idx)


class _FakeCollector:
    """Stands in for MacroCollector. NO network: returns a fixed snapshot."""
    _snapshot = None

    def __init__(self):
        self.last_status = {}

    async def fetch_us_macro_snapshot(self):
        return dict(_FakeCollector._snapshot)

    async def fetch_tcmb_usd_try(self):
        return None

    async def close(self):
        return None


def _run_real_engine(monkeypatch, *, ff, y10, configured=True):
    _FakeCollector._snapshot = {"fed_funds_rate": ff, "ten_year_yield": y10,
                                "cpi": None, "usd_broad_index": None,
                                "configured": configured}
    monkeypatch.setattr(macro_engine_module, "MacroCollector", _FakeCollector)
    return asyncio.run(MacroEngine().analyze("BTCUSDT", "1h", _df()))


@pytest.mark.parametrize("ff,y10", [
    (None, None), (4.33, None), (None, 4.10), (4.33, 4.10),
    (5.0, 5.0), (5.5, 6.0), (2.0, 3.0), (1.0, 2.0), (2.01, 3.01),
    (4.99, 4.99), (0.0, 0.0), (10.0, 10.0), (5.0, 3.0), (2.0, 5.0),
])
def test_score_and_confidence_match_the_real_macro_engine(monkeypatch, ff, y10):
    """The load-bearing test: the restated rules must equal the engine EXACTLY at
    every threshold boundary, including the ones that decide a bias flip."""
    real = _run_real_engine(monkeypatch, ff=ff, y10=y10)
    score, components = ms.macro_score_from_components(ff, y10)
    assert score == real.score, (ff, y10)
    assert ms.macro_confidence_from_components(components) == real.confidence
    assert ms.macro_bias_from_score(score) == real.bias.value


@pytest.mark.parametrize("score", [0, 29.9, 30, 30.1, 45, 45.1, 50, 54.9, 55,
                                   69.9, 70, 70.1, 100])
def test_bias_rule_matches_the_real_engine_at_every_boundary(score):
    assert ms.macro_bias_from_score(float(score)) == \
        MacroEngine._score_to_bias(float(score)).value


def test_unconfigured_engine_matches_the_disabled_payload(monkeypatch):
    real = _run_real_engine(monkeypatch, ff=None, y10=None, configured=False)
    p = ms.build_disabled_macro_shadow(
        decision_time=DT, production_macro_score=real.score,
        production_macro_bias=real.bias.value,
        production_macro_confidence=real.confidence)
    assert (real.score, real.bias.value, real.confidence) == (50.0, "neutral", 25.0)
    assert p["production_macro_confidence"] == 25.0


def test_confidence_rule_table_matches_the_engine_formula():
    assert [ms.macro_confidence_from_components(c) for c in range(0, 6)] == \
        [25.0, 55.0, 70.0, 85.0, 85.0, 85.0]


# ══════════════════════════════════════════════════════════════════════════════
# 8-12 · CONFIDENCE DELTA · THRESHOLD · GATE-ONLY SCOPE
# ══════════════════════════════════════════════════════════════════════════════
def test_confidence_delta_uses_the_supplied_engine_count():
    p = _build(engine_count=9)
    assert p["delta_confidence"] == pytest.approx((70.0 - 25.0) / 9)
    assert _build(engine_count=8)["delta_confidence"] == pytest.approx(45.0 / 8)
    assert _build(engine_count=10)["delta_confidence"] == pytest.approx(45.0 / 10)


def test_engine_count_is_not_hard_coded():
    src = inspect.getsource(ms.build_macro_shadow_from_snapshot)
    assert "/ 9" not in src and "engine_count" in src


def test_threshold_crossing():
    p = _build(production_total_confidence=62.0, publish_threshold=65.0)
    assert p["would_cross_publish_threshold"] is True     # 62 + 5 = 67 >= 65
    assert p["shadow_publish_gate_result"] == "pass"


def test_no_threshold_crossing():
    p = _build(production_total_confidence=55.0, publish_threshold=65.0)
    assert p["would_cross_publish_threshold"] is False    # 55 + 5 = 60 < 65
    assert p["shadow_publish_gate_result"] == "fail"


def test_already_above_threshold_is_not_a_crossing():
    p = _build(production_total_confidence=71.0, publish_threshold=65.0)
    assert p["would_cross_publish_threshold"] is False    # already passed
    assert p["shadow_publish_gate_result"] == "pass"


def test_gate_only_scope_is_declared_on_every_payload():
    for p in (ms.build_disabled_macro_shadow(decision_time=DT, **PROD), _build(),
              _build(snapshot=None)):
        assert p["publish_counterfactual_scope"] == "gate_only_not_full_scheduler"
        assert p["occupancy_replay_available"] is False
        assert p["full_publish_counterfactual_available"] is False


def test_crossing_is_never_described_as_a_publish():
    """`would_cross_publish_threshold` is a confidence-gate fact. Occupancy sends
    ~80% of gate-passers to duplicate_or_existing, so no field may imply a publish."""
    blob = json.dumps(_build())
    for banned in ("would_publish", "will_publish", "published_if", "signal_created"):
        assert banned not in blob
    assert _build()["production_publish_verdict"] == "dropped"


def test_confidence_counterfactual_is_flagged_inexact_at_the_clamp():
    assert _build(production_total_confidence=62.0)["confidence_counterfactual_exact"] is True
    for edge in (20.0, 98.0):
        assert _build(production_total_confidence=edge)["confidence_counterfactual_exact"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 13-14 · DIRECTION AND COMPOSITE ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
def _code_only(obj) -> str:
    """Source with docstrings and comments stripped — prose that MENTIONS a banned
    name must not fail a test that is about what the code DOES."""
    tree = ast.parse(inspect.getsource(obj))
    return "\n".join(ast.unparse(n) for n in ast.walk(tree)
                     if isinstance(n, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Call,
                                       ast.Return, ast.If, ast.For, ast.Attribute))
                     and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                              and isinstance(n.value.value, str)))


def test_no_score_move_means_no_composite_or_direction_change():
    """Today's reality: FRED at 4.33/4.10 leaves the score at 50.0, exactly as it
    did for all 3244 historical signals where FRED worked."""
    p = _build()
    assert p["score_if_restored"] == 50.0
    assert p["delta_score"] == 0.0
    assert p["would_change_composite"] is False
    # Certain: an identical macro contribution cannot move the composite, and macro
    # has no other route to direction (it is not a consensus voter).
    assert p["would_change_direction"] is False


def test_a_moved_score_leaves_direction_unknown_rather_than_guessed():
    """If the score DID move, the resulting direction depends on the other eight
    engines and the disagreement penalty — which this module does not recompute.
    `None` is the honest answer; `True`/`False` would be a fabrication."""
    p = _build(snapshot=_snap(ff=5.5, y10=5.5))          # −10 −5 → 35.0
    assert p["score_if_restored"] == 35.0
    assert p["delta_score"] == -15.0
    assert p["would_change_composite"] is True
    assert p["would_change_direction"] is None
    assert p["bias_if_restored"] == "bearish"


def test_shadow_never_constructs_an_engine_result():
    code = _code_only(ms)
    for banned in ("EngineResult(", "engine_results", "generate_signal(",
                   "SignalBias.", "composite_score"):
        assert banned not in code, banned


def test_shadow_does_not_recompute_production_composite_or_direction():
    code = _code_only(ms.build_macro_shadow_from_snapshot)
    for banned in ("generate_signal", "BASE_ENGINE_WEIGHTS", "resolve_weight_chain"):
        assert banned not in code


# ══════════════════════════════════════════════════════════════════════════════
# 15-16 · IMMUTABILITY AND OUTPUT INDEPENDENCE
# ══════════════════════════════════════════════════════════════════════════════
def test_input_snapshot_is_never_mutated():
    snap = _snap()
    frozen = json.dumps(snap, sort_keys=True)
    ms.build_macro_shadow_from_snapshot(
        decision_time=DT, snapshot=snap, engine_count=9,
        production_total_confidence=62.0, publish_threshold=65.0,
        production_publish_verdict="dropped", **PROD)
    assert json.dumps(snap, sort_keys=True) == frozen


def test_production_macro_fixture_is_never_mutated():
    prod = dict(PROD)
    frozen = json.dumps(prod, sort_keys=True)
    _build()
    ms.build_disabled_macro_shadow(decision_time=DT, **prod)
    assert json.dumps(prod, sort_keys=True) == frozen


def test_two_calls_produce_identical_json():
    assert json.dumps(_build(), sort_keys=True) == json.dumps(_build(), sort_keys=True)
    a = ms.build_disabled_macro_shadow(decision_time=DT, **PROD)
    b = ms.build_disabled_macro_shadow(decision_time=DT, **PROD)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_mutating_one_output_cannot_affect_another():
    a, b = _build(), _build()
    a["errors"].append("tampered")
    a["series"][ms.SERIES_FEDFUNDS]["fetch_status"] = "tampered"
    assert b["errors"] == []
    assert b["series"][ms.SERIES_FEDFUNDS]["fetch_status"] == "ok"


def test_no_shared_mutable_default():
    """A default `errors=[]` shared across calls would bleed between candidates."""
    for fn in (ms.build_disabled_macro_shadow, ms.build_macro_shadow_from_snapshot):
        for p in inspect.signature(fn).parameters.values():
            assert not isinstance(p.default, (list, dict, set)), (fn.__name__, p.name)


def test_output_contains_no_non_json_types():
    def walk(o, path="root"):
        assert not isinstance(o, (set, frozenset, datetime, tuple)), path
        if isinstance(o, float):
            assert math.isfinite(o), path
        if isinstance(o, dict):
            for k, v in o.items():
                assert isinstance(k, str), path
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
    walk(_build())
    walk(ms.build_disabled_macro_shadow(decision_time=DT, **PROD))


# ══════════════════════════════════════════════════════════════════════════════
# 17-19 · OBSERVATION DATE · LOOK-AHEAD · VINTAGE
# ══════════════════════════════════════════════════════════════════════════════
def test_observation_date_is_recorded_not_replaced_by_retrieval_time():
    p = _build()
    e = p["series"][ms.SERIES_FEDFUNDS]
    assert e["observation_date"] == "2026-06-01"
    assert e["retrieved_at"] == "2026-07-30T11:59:00+00:00"
    assert e["observation_date"] != e["retrieved_at"]


def test_past_observation_is_lookahead_safe():
    p = _build()
    for sid in ms.SCORED_SERIES:
        assert p["series"][sid]["available_at_decision_time"] is True
        assert p["series"][sid]["lookahead_safe"] is True
    assert p["errors"] == []


def test_future_observation_is_rejected_and_recorded():
    future = (DT + timedelta(days=3)).date().isoformat()
    p = _build(snapshot=_snap(ff_date=future))
    e = p["series"][ms.SERIES_FEDFUNDS]
    assert e["available_at_decision_time"] is False and e["lookahead_safe"] is False
    assert any(x["error"] == "lookahead_violation" for x in p["errors"])
    assert p["fallback_reason"] == "lookahead_violation"
    # the future value must NOT have been folded into the counterfactual
    assert p["components_used"] == 1


def test_future_observation_in_both_series_yields_no_components():
    future = (DT + timedelta(days=3)).date().isoformat()
    p = _build(snapshot=_snap(ff_date=future, y10_date=future))
    assert p["components_used"] == 0
    assert p["confidence_if_restored"] == 25.0
    assert len(p["errors"]) == 2


def test_malformed_observation_date_is_not_treated_as_safe():
    p = _build(snapshot=_snap(ff_date="not-a-date"))
    e = p["series"][ms.SERIES_FEDFUNDS]
    assert e["lookahead_safe"] is False
    assert p["components_used"] == 1


def test_vintage_and_replayable_semantics():
    p = _build()
    assert p["replayable"] is False
    for sid in ms.ALL_SERIES:
        e = p["series"][sid]
        assert e["source_vintage"] == "realtime_latest"
        assert e["replayable"] is False
        assert e["revision_possible"] is True
    assert p["series"][ms.SERIES_FEDFUNDS]["release_date"] is None


def test_observation_lag_is_computed_from_decision_time():
    p = _build()
    assert p["observation_lag_s"] == pytest.approx(60.0)   # 12:00:00 − 11:59:00


# ══════════════════════════════════════════════════════════════════════════════
# 20-22 · FAILURE CLASSIFICATION · SECRET REDACTION
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("status,reason", [
    ("http_4xx", "auth_failed"), ("http_429", "rate_limited"),
    ("timeout", "fetch_failed"), ("network_error", "fetch_failed"),
    ("parse_error", "fetch_failed"), ("stale_cache", None),
    ("internal_error", "exception"), ("budget_guard", "budget_guard"),
])
def test_failure_vocabularies_are_closed_sets(status, reason):
    assert status in ms.FETCH_STATUSES
    assert reason is None or reason in ms.FALLBACK_REASONS


def test_caller_supplied_fetch_status_is_honoured():
    p = _build(snapshot=_snap(fetch_status="http_429"))
    assert p["fetch_status"] == "http_429"


def test_unknown_fetch_status_falls_back_to_a_known_one():
    p = ms.build_disabled_macro_shadow(decision_time=DT, fetch_status="made_up",
                                       fallback_reason="also_made_up", **PROD)
    assert p["fetch_status"] in ms.FETCH_STATUSES
    assert p["fallback_reason"] in ms.FALLBACK_REASONS


def test_no_snapshot_is_disabled_not_executed():
    p = _build(snapshot=None)
    assert p["executed"] is False
    assert p["fetch_status"] == "disabled" and p["fallback_reason"] == "fetch_disabled"


def test_unconfigured_snapshot_reports_no_api_key():
    p = _build(snapshot=_snap(configured=False))
    assert p["configured"] is False and p["executed"] is False
    assert p["fetch_status"] == "not_configured"
    assert p["fallback_reason"] == "no_api_key"


def test_only_an_error_class_is_carried_never_a_message():
    snap = _snap()
    snap["series"][ms.SERIES_FEDFUNDS]["error_class"] = "ConnectTimeout"
    p = _build(snapshot=snap)
    assert p["series"][ms.SERIES_FEDFUNDS]["error_class"] == "ConnectTimeout"
    # Scanned on CODE, not prose: the module docstring legitimately NAMES
    # FRED_API_KEY when explaining the regression it exists for. The ban is on the
    # code reading or transporting the key, and on any raw exception text.
    code = _code_only(ms)
    for banned in ("str(exc)", "repr(exc)", "traceback", "response.text",
                   "FRED_API_KEY", "api_key=", "?api_key", "settings.",
                   "os.environ", "getenv", "environ["):
        assert banned not in code, banned
    # The only `api_key` substring anywhere in the code is the `no_api_key` constant.
    assert code.count("api_key") == code.count("no_api_key")


def test_hostile_strings_in_ignored_fields_cannot_reach_the_payload():
    snap = _snap()
    snap["series"][ms.SERIES_FEDFUNDS]["url"] = "https://example.invalid?api_key=SENTINEL"
    snap["secret_note"] = "SENTINEL-TOKEN-DO-NOT-USE"
    blob = json.dumps(_build(snapshot=snap))
    for banned in ("SENTINEL", "api_key", "https://"):
        assert banned not in blob, banned


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_inf_are_rejected_at_the_boundary(bad):
    p = _build(snapshot=_snap(ff=bad), production_total_confidence=bad)
    json.dumps(p)                                    # must not raise
    assert p["components_used"] == 1                 # bad value not counted


# ══════════════════════════════════════════════════════════════════════════════
# 23-25 · CMV2 · PassA · PassB ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
def test_cmv2_reads_only_a_specific_extra_key():
    """CMV2's ONLY candidate-extra read is `decision_input_version`
    (coin_memory.py:_resolve_fold_cohort). A new namespace is invisible to it."""
    src = inspect.getsource(cm._resolve_fold_cohort)
    assert '"decision_input_version" not in extra' in src
    assert 'extra.get("decision_input_version")' in src
    for banned in ("for k, v in extra", "extra.items()", "macro_shadow"):
        assert banned not in src


def test_cmv2_cohort_is_unchanged_by_the_shadow_namespace():
    plain = {"decision_input_version": "closed_candle_v1"}
    withns = {**plain, "macro_shadow_v1": _build()}
    for extra in (plain, withns):
        assert extra.get("decision_input_version") == "closed_candle_v1"
    assert cm.cm_v2_cohort_key({
        "decision_input_version": "closed_candle_v1", "policy_version": 1}) == \
        "decision_input_version=closed_candle_v1|policy_version=1"


def test_cmv2_fold_and_exclusions_ignore_the_shadow_namespace():
    path = NS(signal_id="s1", symbol="BTC", timeframe="4h", schema_version=2,
              outcome="win", detail_label="tp1_hit", resolved_at=None,
              direction="bullish", regime="trending_bull", volatility_bucket="normal",
              still_forming_resolution=False, intrabar_ambiguous=False,
              sl_dist_pct=4.0, cur_realized_return=6.0, mfe_r=1.2, mae_r=0.5,
              mfe_pct=4.8, mae_pct=2.0, mfe_atr=2.0, mae_atr=0.8, bars_total=10,
              cur_bars_to_tp1=3, cur_reached_tp1=True, cur_reached_tp2=False,
              cur_reached_tp3=False, cur_gave_back_after_tp1=False,
              entry_price=100.0, sl_price=96.0, tp1_price=103.0)
    cohort = {"decision_input_version": "closed_candle_v1",
              "policy_version": 1, "decision_input_version_source": "candidate_extra",
              "policy_version_source": "candidate_policy_version_column"}
    a = cm.observe_cm_v2_fold(None, path, cohort, "t0")
    b = cm.observe_cm_v2_fold(None, path, {**cohort, "ignored": _build()}, "t0")
    assert a["counts"] == b["counts"] and a["cohort"] == b["cohort"]
    assert cm.cm_v2_exclusions(path, cohort) == cm.cm_v2_exclusions(path, cohort)


def test_shadow_namespace_does_not_collide_with_passb():
    """PassB rides in `extra.shadow_passb` (shadow_eval.py:310). Different key."""
    assert ms.MACRO_SHADOW_VERSION != "shadow_passb"
    assert not ms.MACRO_SHADOW_VERSION.startswith("shadow_")
    src = (BACKEND / "app" / "services" / "shadow_eval.py").read_text(encoding="utf-8")
    assert "macro_shadow" not in src
    assert "shadow_passb" in src


def test_passa_passb_sources_do_not_reference_the_shadow_module():
    for rel in ("app/services/shadow_eval.py", "app/services/scheduler.py"):
        text = (BACKEND / rel).read_text(encoding="utf-8")
        for banned in ("macro_shadow", "macro_shadow_v1", "build_macro_shadow"):
            assert banned not in text, f"{rel}: {banned}"


# ══════════════════════════════════════════════════════════════════════════════
# 26 · API NON-LEAKAGE + PRODUCTION CALL-SITE BAN
# ══════════════════════════════════════════════════════════════════════════════
def _py_files(root: Path):
    for p in root.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def test_no_production_module_imports_the_shadow():
    """Stage 1 ships no call site. Deployed as-is, it cannot produce behaviour."""
    importers = []
    for p in _py_files(BACKEND / "app"):
        if p.name == "macro_shadow.py":
            continue
        text = p.read_text(encoding="utf-8")
        if "macro_shadow" in text:
            importers.append(str(p.relative_to(BACKEND)))
    assert importers == [], importers


def test_api_layer_never_mentions_the_shadow_or_candidate_extra():
    for p in _py_files(BACKEND / "app" / "api"):
        text = p.read_text(encoding="utf-8")
        for banned in ("macro_shadow", "SignalDecisionCandidate",
                       "signal_decision_candidates"):
            assert banned not in text, f"{p.relative_to(BACKEND)}: {banned}"


def test_shadow_module_imports_nothing_forbidden():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    forbidden = ("httpx", "requests", "aiohttp", "sqlalchemy", "app.database",
                 "app.config", "app.models", "os", "app.services.scheduler",
                 "app.collectors", "app.engines")
    for f in forbidden:
        assert not any(m == f or m.startswith(f + ".") for m in mods), (f, mods)
    assert mods == {"__future__", "math", "datetime", "typing",
                    "app.services.dependency_health"}, mods


def test_shadow_module_has_no_module_level_mutable_state():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow.py")
                     .read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            val = node.value
            if isinstance(val, (ast.List, ast.Set)):
                raise AssertionError("module-level mutable literal")
            if isinstance(val, ast.Dict):
                targets = getattr(node, "targets", [getattr(node, "target", None)])
                name = getattr(targets[0], "id", "")
                assert name.isupper(), f"non-constant module dict: {name}"


# ══════════════════════════════════════════════════════════════════════════════
# 27 · FROZEN PRODUCTION DIGEST — captured BEFORE this module existed
# ══════════════════════════════════════════════════════════════════════════════
FROZEN_DECISION = "b808118aad519f0461d91a28bd113f145a7bcdcfb9941449911aa9e285bfc102"
FROZEN_WEIGHT_CHAIN = "ccd851349f050125bb140447d8f4dfc78ca9a2518b8758883def559706493555"
FROZEN_MACRO_ENGINE = "63348ef98017ce5585af3fef7cae9730a891b38fd07837d39b4d6f50a9700f22"
FROZEN_V1_BUCKET = "e93f6fbad25758c3e76ea48444cbd6a5015ae777a0099401f1d4f6de897f5df7"

BIASES = [SignalBias.BULLISH, SignalBias.BEARISH, SignalBias.NEUTRAL,
          SignalBias.STRONG_BULLISH, SignalBias.STRONG_BEARISH]


def _digest(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _grid_df(n=120, start=100.0, step=0.4):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = [start + i * step for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                         "low": [c * 0.99 for c in close], "close": close,
                         "volume": [1000.0 + i for i in range(n)]}, index=idx)


def test_frozen_decision_digest_is_unmoved():
    """280 generate_signal cases covering signal_type, direction, composite,
    confidence, probability, risk, levels, disagreement, mtf_penalty and the
    consensus/threshold telemetry. Stage 1 adds a file and no call site, so this
    must be identical to the pre-change capture."""
    df = _grid_df()
    rows = []
    for si, base in enumerate((22.0, 35.0, 48.0, 55.0, 62.0, 71.0, 84.0)):
        for bi, b in enumerate(BIASES):
            for mi, mtf in enumerate((None,
                                      {"15m": "bullish", "1h": "bullish", "4h": "bullish"},
                                      {"15m": "bearish", "1h": "bearish", "4h": "bullish"},
                                      {"15m": "bearish", "1h": "bearish", "4h": "bearish"})):
                results = []
                for k, name in enumerate(E9):
                    sc = max(0.0, min(100.0, base + (k * 3) - 6))
                    bb = b if k % 2 == 0 else BIASES[(bi + k) % len(BIASES)]
                    results.append(EngineResult(
                        engine_name=name, score=round(sc, 2), bias=bb,
                        confidence=40.0 + (k * 5) % 55, key_findings=[],
                        supporting_data={}, warnings=[]))
                for wi, w in enumerate((None, BASE_ENGINE_WEIGHTS)):
                    out = generate_signal("BTCUSDT", "1h", df, results,
                                          mtf_trends=mtf, weights=w,
                                          current_price=float(df["close"].iloc[-1]))
                    rows.append({
                        "k": f"{si}-{bi}-{mi}-{wi}",
                        "signal_type": out.signal_type, "direction": out.direction,
                        "confidence_score": round(float(out.confidence_score), 10),
                        "probability_score": round(float(out.probability_score), 10),
                        "risk_score": out.risk_score, "risk_level": out.risk_level,
                        "entry_zone_low": out.entry_zone_low,
                        "entry_zone_high": out.entry_zone_high,
                        "stop_loss": out.stop_loss, "tp1": out.tp1, "tp2": out.tp2,
                        "tp3": out.tp3, "consensus": out.consensus_telemetry,
                        "birth": out.birth_telemetry,
                    })
    assert len(rows) == 280
    assert _digest(rows) == FROZEN_DECISION


def test_frozen_weight_chain_digest_is_unmoved():
    def mem(total, per, ratio):
        es = {}
        for i, e in enumerate(E9):
            t = per + i
            c = int(round(t * ratio))
            es[e] = {"total": t, "correct": c, "win_rate": round(c / t, 4) if t else 0.0}
        return NS(total_signals=total, engine_stats=es, adaptive_weights=None,
                  wins=0, losses=0, regime_stats={}, tm_stats=None, tm_sample_count=0)
    rows = []
    for regime in [None, "unknown"] + sorted(cm._REGIME_TILTS):
        for m in [None, mem(0, 0, .5), mem(19, 11, .5), mem(20, 12, .0),
                  mem(20, 12, .5), mem(20, 12, 1.), mem(200, 150, .62)]:
            ch = cm.resolve_weight_chain(regime, m)
            rows.append({"regime": regime,
                         "effective": {k: round(float(v), 10)
                                       for k, v in sorted(ch.effective.items())},
                         "memory_applied": bool(ch.memory_applied),
                         "adaptive_is_active": bool(cm.adaptive_is_active(m))})
    assert len(rows) == 56
    assert _digest(rows) == FROZEN_WEIGHT_CHAIN


def test_frozen_macro_engine_digest_is_unmoved():
    e = MacroEngine()
    payload = {
        "name": e.name, "weight": e.weight,
        "score_to_bias": {str(s): MacroEngine._score_to_bias(float(s)).value
                          for s in (0, 29.9, 30, 30.1, 45, 45.1, 50, 54.9, 55,
                                    69.9, 70, 70.1, 100)},
        "confidence_rule": {str(c): (25.0 if c == 0 else min(40 + c * 15, 85))
                            for c in range(0, 6)},
    }
    assert _digest(payload) == FROZEN_MACRO_ENGINE


def test_frozen_v1_bucket_digest_is_unmoved():
    def p(**kw):
        b = dict(symbol="BTC", timeframe="4h", schema_version=2, regime="trend",
                 still_forming_resolution=False, mfe_r=1.2, mae_r=0.5, mfe_atr=2.0,
                 mae_atr=0.8, bars_total=10, cur_bars_to_tp1=3,
                 cur_realized_return=1.5, cur_reached_tp1=True,
                 cur_reached_tp2=False, cur_reached_tp3=False,
                 cur_gave_back_after_tp1=None, entry_price=100.0, sl_price=96.0,
                 tp1_price=103.0, detail_label=None)
        b.update(kw)
        return NS(**b)
    bucket = cm._empty_bucket()
    for i in range(24):
        cm._fold_into_bucket(bucket, p(mfe_r=0.3 + i * .17, mae_r=.1 + i * .09,
                                       cur_realized_return=-1.0 + i * .3,
                                       bars_total=4 + i))
    assert _digest(bucket) == FROZEN_V1_BUCKET


# ══════════════════════════════════════════════════════════════════════════════
# 28 · IDEMPOTENCY / VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
def test_validation_accepts_every_builder_output():
    for p in (ms.build_disabled_macro_shadow(decision_time=DT, **PROD), _build(),
              _build(snapshot=None), _build(snapshot=_snap(configured=False)),
              _build(snapshot=_snap(ff=None, y10=None))):
        assert ms.validate_macro_shadow(p) == []


@pytest.mark.parametrize("mutation,expect", [
    ({"version": "macro_shadow_v2"}, "bad version"),
    ({"mode": "live"}, "bad mode"),
    ({"fetch_status": "made_up"}, "bad fetch_status"),
    ({"fallback_reason": "made_up"}, "bad fallback_reason"),
    ({"occupancy_replay_available": True}, "occupancy_replay_available"),
    ({"full_publish_counterfactual_available": True}, "full_publish"),
    ({"publish_counterfactual_scope": "full"}, "publish_counterfactual_scope"),
    ({"replayable": True}, "replayable"),
    ({"series": "nope"}, "series is not a mapping"),
])
def test_validation_rejects_tampered_payloads(mutation, expect):
    p = {**_build(), **mutation}
    problems = ms.validate_macro_shadow(p)
    assert any(expect in x for x in problems), problems


def test_validation_never_raises_on_junk():
    for junk in (None, 42, "text", [], {}, {"version": None}):
        assert isinstance(ms.validate_macro_shadow(junk), (list, tuple))


def test_validation_catches_a_missing_required_key():
    p = _build()
    del p["delta_confidence"]
    assert any("delta_confidence" in x for x in ms.validate_macro_shadow(p))
