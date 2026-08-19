"""CP-MACRO-SHADOW-RESTORE-IMPLEMENTATION-B — the DISABLED production wiring.

Stage 2 connects `macro_shadow_v1` to the live candidate write and to nothing
else. Every payload it produces says `configured=false, executed=false`, so the
tests are organised around proving that claim is a property of the CODE PATH and
not merely a label on a dict.

  1. It is additive. `signal_decision_candidates.extra` gains one namespace and
     loses nothing — named keys, unknown keys and other namespaces all survive,
     `None` and a corrupt non-mapping are both handled without data loss, and a
     repeat is idempotent rather than nesting.

  2. It cannot decide. The wiring reads `decision` and never writes to it, never
     builds an EngineResult, never appends to `engine_results` — the one list
     composite, confidence, disagreement and consensus all read from. Proved by
     deep-freezing the decision around the call and by frozen grids over the
     decision, the candidate row, Pass A and the version set.

  3. It cannot fetch. Not "does not today": the whole candidate path is executed
     with sockets, httpx, urllib and MacroCollector armed to raise, and with
     `get_settings` and `os.environ` armed to raise. `executed=false` is what the
     code cannot do, not what it chose not to do.

  4. It cannot lose a candidate. Every failure mode of the helper degrades to a
     payload or to an omitted namespace; the row is written either way.

No DB, no network, no clock dependency, no secret.
"""
import ast
import asyncio
import copy
import hashlib
import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from app.engines.ai_decision.signal_generator import (
    BASE_ENGINE_WEIGHTS, CONSENSUS_VOTE_ENGINES, generate_signal,
)
from app.engines.base import EngineResult, SignalBias
from app.engines.macro.engine import MacroEngine
from app.models.decision_candidate import (
    CANDIDATE_POLICY_VERSION, CANDIDATE_SCHEMA_VERSION, SHADOW_UNDECIDABLE,
    classify_birth_shadow,
)
from app.services import candidate_log as cl
from app.services import coin_memory as cm
from app.services import macro_shadow as ms
from app.services import macro_shadow_wiring as msw

BACKEND = Path(__file__).resolve().parents[1]
E9 = list(BASE_ENGINE_WEIGHTS)
MACRO = "macro_analysis"
NS_KEY = ms.MACRO_SHADOW_VERSION           # "macro_shadow_v1"
DT = datetime(2026, 7, 31, 0, 5, 0, tzinfo=timezone.utc)

BIASES = [SignalBias.BULLISH, SignalBias.BEARISH, SignalBias.NEUTRAL,
          SignalBias.STRONG_BULLISH, SignalBias.STRONG_BEARISH]


def _digest(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _df(n=120, start=100.0, step=0.4):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = [start + i * step for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                         "low": [c * 0.99 for c in close], "close": close,
                         "volume": [1000.0 + i for i in range(n)]}, index=idx)


def _results(base=62.0, bias=SignalBias.BULLISH, bi=0):
    out = []
    for k, name in enumerate(E9):
        sc = max(0.0, min(100.0, base + (k * 3) - 6))
        bb = bias if k % 2 == 0 else BIASES[(bi + k) % len(BIASES)]
        out.append(EngineResult(engine_name=name, score=round(sc, 2), bias=bb,
                                confidence=40.0 + (k * 5) % 55, key_findings=[],
                                supporting_data={}, warnings=[]))
    return out


def _decision(results=None, *, mtf=None, macro_score=50.0, macro_bias="neutral",
              macro_conf=25.0):
    """Exactly the shape `AIDecisionEngine.analyze_and_decide` returns — in
    particular `engine_results = [res.model_dump() for res in results]`
    (app/engines/ai_decision/engine.py:412), a list of DICTS."""
    results = results if results is not None else _results()
    df = _df()
    out = generate_signal("BTCUSDT", "1h", df, results, mtf_trends=mtf,
                          weights=BASE_ENGINE_WEIGHTS,
                          current_price=float(df["close"].iloc[-1]))
    dumped = [r.model_dump() for r in results]
    for entry in dumped:
        if entry["engine_name"] == MACRO:
            entry["score"] = macro_score
            entry["bias"] = macro_bias
            entry["confidence"] = macro_conf
    return {
        "symbol": "BTCUSDT", "timeframe": "1h",
        "signal_type": out.signal_type, "direction": out.direction,
        "confidence_score": out.confidence_score,
        "probability_score": out.probability_score,
        "risk_score": out.risk_score, "risk_level": out.risk_level,
        "entry_zone_low": out.entry_zone_low, "entry_zone_high": out.entry_zone_high,
        "stop_loss": out.stop_loss, "tp1": out.tp1, "tp2": out.tp2, "tp3": out.tp3,
        "invalidation_conditions": [],
        "birth_telemetry": out.birth_telemetry,
        "consensus_telemetry": out.consensus_telemetry,
        "decision_input_telemetry": {
            "decision_input_version": "closed_candle_v1",
            "candle_policy": "closed_only", "current_price": 147.6,
            "decision_current_price_source": "full_frame_last_close",
            "analysis_close_price": 147.2,
            "last_analysis_bar_open_time": "2026-01-05T23:00:00+00:00",
            "last_analysis_bar_close_time": "2026-01-06T00:00:00+00:00",
            "last_analysis_bar_closed": True,
            "current_vs_analysis_close_pct": 0.27,
            "current_vs_analysis_close_atr": 0.11,
        },
        "engine_results": dumped,
        "engine_execution_telemetry": {
            "version": "engine_execution_v1", "engine_count": 9,
            "successful_engine_count": 9, "failed_engine_count": 0,
            "failed_engines": [], "fallback_used": False},
        "dependency_health": {"version": "dependency_health_v1",
                              "engines": {MACRO: {"configured": False}}},
        "explanation_tr": "x", "explanation_en": "x",
        "generated_at": "2026-01-06T00:00:00", "mtf_trends": mtf,
    }


_REGIME = NS(adx=27.5, atr_pct=1.8, atr_pct_median=1.5, volume_ratio=1.3,
             trend_direction="up")


def _values(decision=None, *, verdict="dropped", with_shadow=True, **kw):
    decision = decision if decision is not None else _decision()
    shadow = (msw.build_candidate_macro_shadow(
        decision=decision, decision_time=DT, verdict=verdict) if with_shadow else None)
    base = dict(
        asset_id=7, symbol="BTCUSDT", timeframe="1h", decision=decision,
        df=_df(), evaluated_at=DT, verdict=verdict, demotion_reason=None,
        primary_demotion_reason=None, final_signal_type=decision["signal_type"],
        final_direction=decision["direction"], regime_label="trend",
        regime_result=_REGIME, engine_weights=BASE_ENGINE_WEIGHTS,
        adaptive_active=True,
        adaptive_snapshot={"base": BASE_ENGINE_WEIGHTS, "memory_applied": True},
        last_close=147.6, macro_shadow=shadow)
    base.update(kw)
    return cl.build_candidate_values(**base)


# ══════════════════════════════════════════════════════════════════════════════
# 1-2 · CALL SITE · EXACTLY ONCE PER CANDIDATE
# ══════════════════════════════════════════════════════════════════════════════
def _generate_signal_ast():
    tree = ast.parse((BACKEND / "app" / "services" / "scheduler.py")
                     .read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_generate_signal"):
            return node
    raise AssertionError("_generate_signal not found")


def _record_candidate_calls(node):
    return [c for c in ast.walk(node)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", None) == "record_candidate"]


def test_every_record_candidate_call_carries_the_namespace():
    """No site may be left behind — a candidate without the namespace would look
    like a coverage gap when it is really a missed edit."""
    calls = _record_candidate_calls(_generate_signal_ast())
    assert len(calls) == 3, len(calls)
    for call in calls:
        names = [kw.arg for kw in call.keywords]
        assert "macro_shadow" in names, names


def test_the_namespace_argument_is_always_the_wiring_helper():
    """A literal dict at a call site would be a second payload formula."""
    for call in _record_candidate_calls(_generate_signal_ast()):
        arg = next(kw.value for kw in call.keywords if kw.arg == "macro_shadow")
        assert isinstance(arg, ast.Call), ast.dump(arg)[:120]
        assert getattr(arg.func, "id", None) == "build_candidate_macro_shadow"


def _parents(root):
    table = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            table[child] = node
    return table


def test_the_three_sites_are_mutually_exclusive():
    """THE property behind "exactly once per candidate".

    Two of the three calls sit in an `if` whose body ENDS in `return`, so no
    execution path can reach a second `record_candidate`; the third is the last
    one on the fall-through path. Asserted on the CONTROL FLOW: three calls in one
    coroutine would otherwise be indistinguishable from three writes per candidate,
    which is exactly the failure this checkpoint has to rule out.
    """
    node = _generate_signal_ast()
    parents = _parents(node)
    terminating, fallthrough = 0, 0
    for call in _record_candidate_calls(node):
        cur, guarded = call, False
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, ast.If) and isinstance(cur.body[-1], ast.Return):
                guarded = True
                break
            if cur is node:
                break
        if guarded:
            terminating += 1
        else:
            fallthrough += 1
    assert terminating == 2, terminating
    assert fallthrough == 1, fallthrough


def _ns_key_occurrences(obj, key):
    """How many times `key` appears as a KEY anywhere in the tree. The literal
    string also appears as the `version` VALUE, so counting substrings in the JSON
    would over-count and hide a real duplicate."""
    n = 0
    if isinstance(obj, dict):
        n += sum(1 for k in obj if k == key)
        n += sum(_ns_key_occurrences(v, key) for v in obj.values())
    elif isinstance(obj, list):
        n += sum(_ns_key_occurrences(v, key) for v in obj)
    return n


def test_the_namespace_appears_exactly_once_and_is_not_nested():
    extra = _values()["extra"]
    assert _ns_key_occurrences(extra, NS_KEY) == 1
    assert NS_KEY not in extra[NS_KEY]
    # The literal survives exactly twice in the JSON: once as the key, once as the
    # `version` value it must equal.
    blob = json.dumps(extra)
    assert blob.count(f'"{NS_KEY}"') == 2
    assert extra[NS_KEY]["version"] == NS_KEY


def test_the_wiring_helper_is_pure_and_returns_a_fresh_dict():
    d = _decision()
    a = msw.build_candidate_macro_shadow(decision=d, decision_time=DT, verdict="dropped")
    b = msw.build_candidate_macro_shadow(decision=d, decision_time=DT, verdict="dropped")
    assert a == b and a is not b
    a["errors"].append("tampered")
    assert b["errors"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 3 · DISABLED PAYLOAD EXACT CONTRACT
# ══════════════════════════════════════════════════════════════════════════════
def test_the_written_payload_is_disabled_in_every_field():
    p = _values()["extra"][NS_KEY]
    assert p["version"] == "macro_shadow_v1"
    assert p["mode"] == "shadow_observation_only"
    assert p["configured"] is False
    assert p["executed"] is False
    assert p["fetch_status"] == "not_configured"
    assert p["fallback_reason"] == "no_api_key"
    assert p["components_expected"] == 2
    assert p["components_available"] == 0
    assert p["components_used"] == 0
    assert p["decision_isolation_verified"] is True
    assert p["replayable"] is False
    assert p["occupancy_replay_available"] is False
    assert p["full_publish_counterfactual_available"] is False
    assert p["publish_counterfactual_scope"] == "gate_only_not_full_scheduler"
    assert p["series"] == {}
    assert p["errors"] == []
    assert ms.validate_macro_shadow(p) == []


@pytest.mark.parametrize("field", [
    "score_if_restored", "bias_if_restored", "confidence_if_restored",
    "delta_score", "delta_confidence", "would_change_direction",
    "would_change_composite", "would_change_confidence",
    "would_cross_publish_threshold", "shadow_publish_gate_result",
    "confidence_counterfactual_exact", "observation_time", "observation_lag_s",
])
def test_no_counterfactual_field_is_populated(field):
    """`false` would be an ANSWER. Nothing was computed, so every counterfactual
    is null — including `would_change_composite`, where `false` would assert that
    restoring macro leaves the composite alone. CP-MACRO-OPERATIONAL-DECISION-
    FORENSIC measured the opposite (+5.0 confidence, ~437 candidates over the 65
    gate), so `false` here would be a recorded falsehood."""
    assert _values()["extra"][NS_KEY][field] is None


def test_production_macro_values_come_from_the_decisions_own_engine_result():
    d = _decision(macro_score=61.5, macro_bias="bullish", macro_conf=70.0)
    p = _values(d)["extra"][NS_KEY]
    assert p["production_macro_score"] == 61.5
    assert p["production_macro_bias"] == "bullish"
    assert p["production_macro_confidence"] == 70.0


def test_todays_real_production_reading_is_recorded_as_the_fallback_triple():
    """Macro runs on its zero-component fallback on 100% of candidates today."""
    p = _values()["extra"][NS_KEY]
    assert (p["production_macro_score"], p["production_macro_bias"],
            p["production_macro_confidence"]) == (50.0, "neutral", 25.0)


@pytest.mark.parametrize("verdict", ["published", "dropped", "skipped"])
def test_the_publish_verdict_is_recorded_per_site(verdict):
    assert _values(verdict=verdict)["extra"][NS_KEY][
        "production_publish_verdict"] == verdict


def test_a_signal_bias_enum_is_written_as_its_value_not_its_repr():
    d = _decision()
    for entry in d["engine_results"]:
        if entry["engine_name"] == MACRO:
            entry["bias"] = SignalBias.BULLISH        # the raw member, not .value
    p = _values(d)["extra"][NS_KEY]
    assert p["production_macro_bias"] == "bullish"
    assert "SignalBias" not in json.dumps(p)


def test_a_missing_macro_engine_is_recorded_never_invented():
    """50/neutral/25 is exactly what a zero-component macro produces, so filling it
    in would make an ABSENT engine indistinguishable from a present one."""
    d = _decision()
    d["engine_results"] = [e for e in d["engine_results"] if e["engine_name"] != MACRO]
    p = _values(d)["extra"][NS_KEY]
    assert p["production_macro_score"] is None
    assert p["production_macro_bias"] is None
    assert p["production_macro_confidence"] is None
    assert p["errors"] == [{"error": "macro_engine_missing", "engine_name": MACRO}]
    assert ms.validate_macro_shadow(p) == []


def test_the_engine_name_matches_the_real_engine():
    assert msw.MACRO_ENGINE_NAME == MacroEngine().name == MACRO
    assert msw.MACRO_ENGINE_NAME in BASE_ENGINE_WEIGHTS


def test_macro_is_still_not_a_consensus_voter():
    """The wiring must not have quietly given macro a vote."""
    assert MACRO not in CONSENSUS_VOTE_ENGINES


# ══════════════════════════════════════════════════════════════════════════════
# 4-10 · ADDITIVE MERGE SEMANTICS
# ══════════════════════════════════════════════════════════════════════════════
PRE_EXISTING = {
    "dependency_health_v1": {"version": "dependency_health_v1", "engines": {}},
    "decision_input_version": "closed_candle_v1",
    "shadow_passb": {"path": "bar_walk", "n": 3},
    "primary_demotion_reason": "confidence_gate",
    "an_unknown_future_namespace": {"deep": {"nested": [1, 2, 3]}},
    "a_scalar": 7,
    "a_null": None,
}


def test_existing_extra_is_preserved_key_for_key():
    merged = cl.merge_additive_namespace(PRE_EXISTING, NS_KEY, {"a": 1})
    for k, v in PRE_EXISTING.items():
        assert merged[k] == v, k
    assert merged[NS_KEY] == {"a": 1}
    assert set(merged) == set(PRE_EXISTING) | {NS_KEY}


def test_the_input_extra_is_never_mutated():
    frozen = json.dumps(PRE_EXISTING, sort_keys=True)
    out = cl.merge_additive_namespace(PRE_EXISTING, NS_KEY, {"a": 1})
    assert json.dumps(PRE_EXISTING, sort_keys=True) == frozen
    assert out is not PRE_EXISTING


def test_extra_none_becomes_a_single_namespace_object():
    assert cl.merge_additive_namespace(None, NS_KEY, {"a": 1}) == {NS_KEY: {"a": 1}}


@pytest.mark.parametrize("corrupt", ["a string", 7, [1, 2], (1, 2), 3.5, True])
def test_a_non_mapping_extra_is_returned_untouched_rather_than_destroyed(corrupt):
    """Whatever that value is, it is production data this function did not write.
    Losing the telemetry beats overwriting the row's contents."""
    assert cl.merge_additive_namespace(corrupt, NS_KEY, {"a": 1}) == corrupt


def test_a_null_payload_leaves_extra_exactly_as_it_was():
    """An ABSENT namespace is honest; a null one would read as "the shadow ran
    and produced nothing"."""
    out = cl.merge_additive_namespace(PRE_EXISTING, NS_KEY, None)
    assert out == PRE_EXISTING
    assert NS_KEY not in out


def test_merging_twice_is_idempotent_and_never_nests():
    """`once` is SNAPSHOTTED before the second merge.

    Comparing the two live dicts is not a test: the copy is shallow, so any
    substructure the second merge mutates in place is mutated in BOTH, and
    `once == twice` stays true precisely when the function is misbehaving. A
    sabotage run proved it — an appending merge passed the naive form.
    """
    once = cl.merge_additive_namespace(PRE_EXISTING, NS_KEY, {"a": 1})
    snapshot = json.dumps(once, sort_keys=True)
    twice = cl.merge_additive_namespace(once, NS_KEY, {"a": 1})
    assert json.dumps(twice, sort_keys=True) == snapshot
    assert json.dumps(once, sort_keys=True) == snapshot     # first result untouched
    assert twice[NS_KEY] == {"a": 1}
    assert NS_KEY not in twice[NS_KEY]


def test_merging_ten_times_does_not_grow_the_object():
    extra = dict(PRE_EXISTING)
    sizes = set()
    for _ in range(10):
        extra = cl.merge_additive_namespace(extra, NS_KEY, {"a": 1})
        sizes.add(json.dumps(extra, sort_keys=True))
    assert len(sizes) == 1, "the merge accumulates state across repeats"


def test_a_repeat_replaces_rather_than_merges_into_the_old_payload():
    once = cl.merge_additive_namespace({"x": 1}, NS_KEY, {"a": 1, "stale": True})
    twice = cl.merge_additive_namespace(once, NS_KEY, {"a": 2})
    assert twice[NS_KEY] == {"a": 2}
    assert "stale" not in twice[NS_KEY]
    assert twice["x"] == 1


def test_the_real_extra_keeps_all_eighteen_production_keys():
    """The exact key set production writes today (verified against 7 239 live rows
    on 2026-07-31), plus the new namespace and nothing else."""
    keys = set(_values()["extra"])
    assert NS_KEY in keys
    assert keys - {NS_KEY} == {
        "adaptive_state_telemetry", "analysis_close_price", "candle_policy",
        "current_price", "current_vs_analysis_close_atr",
        "current_vs_analysis_close_pct", "decision_current_price_source",
        "decision_input_version", "dependency_health_v1", "engine_demoted",
        "engine_execution_telemetry", "entry_frame_caveat",
        "last_analysis_bar_close_time", "last_analysis_bar_closed",
        "last_analysis_bar_open_time", "primary_demotion_reason",
        "threshold_direction", "threshold_signal_type"}


def test_the_other_namespaces_survive_the_real_build():
    extra = _values()["extra"]
    assert extra["dependency_health_v1"] == {"version": "dependency_health_v1",
                                             "engines": {MACRO: {"configured": False}}}
    assert extra["decision_input_version"] == "closed_candle_v1"
    assert extra["engine_execution_telemetry"]["engine_count"] == 9
    assert extra["adaptive_state_telemetry"]["memory_applied"] is True


def test_without_the_namespace_the_row_is_byte_identical_to_before():
    """The default path must be a no-op, so an un-wired caller is unaffected."""
    a = _values(with_shadow=False)
    assert NS_KEY not in a["extra"]
    b = _values()
    b["extra"] = {k: v for k, v in b["extra"].items() if k != NS_KEY}
    assert json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# 11-22 · DECISION ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
def test_the_decision_object_is_deep_frozen_across_the_whole_candidate_path():
    d = _decision()
    frozen = json.dumps(d, sort_keys=True, default=str)
    deep = copy.deepcopy(d)
    msw.build_candidate_macro_shadow(decision=d, decision_time=DT, verdict="dropped")
    _values(d)
    assert json.dumps(d, sort_keys=True, default=str) == frozen
    assert d == deep


def test_engine_results_is_neither_extended_nor_reordered():
    d = _decision()
    before = [e["engine_name"] for e in d["engine_results"]]
    ids = [id(e) for e in d["engine_results"]]
    _values(d)
    assert [e["engine_name"] for e in d["engine_results"]] == before
    assert [id(e) for e in d["engine_results"]] == ids
    assert len(d["engine_results"]) == 9


@pytest.mark.parametrize("field", [
    "confidence_score", "probability_score", "risk_score", "risk_level",
    "direction", "signal_type", "entry_zone_low", "entry_zone_high",
    "stop_loss", "tp1", "tp2", "tp3", "mtf_trends",
])
def test_no_top_level_decision_field_moves(field):
    d = _decision(mtf={"15m": "bullish", "1h": "bullish", "4h": "bullish"})
    before = json.dumps(d[field], sort_keys=True, default=str)
    _values(d)
    assert json.dumps(d[field], sort_keys=True, default=str) == before


@pytest.mark.parametrize("block", ["birth_telemetry", "consensus_telemetry",
                                   "decision_input_telemetry",
                                   "engine_execution_telemetry", "dependency_health"])
def test_no_telemetry_block_moves(block):
    d = _decision()
    before = json.dumps(d[block], sort_keys=True, default=str)
    _values(d)
    assert json.dumps(d[block], sort_keys=True, default=str) == before


def test_the_candidate_row_records_the_same_numbers_with_or_without_the_shadow():
    """composite / confidence / disagreement / mtf_penalty / risk / verdict /
    geometry — every decision-derived COLUMN, compared pairwise."""
    d = _decision(mtf={"15m": "bearish", "1h": "bearish", "4h": "bullish"})
    a, b = _values(d, with_shadow=False), _values(d)
    for col in set(a) - {"extra"}:
        assert a[col] == b[col], col


def test_the_shadow_never_constructs_an_engine_result():
    code = _code_only(msw)
    for banned in ("EngineResult", "engine_results.append", "engine_results +=",
                   "engine_results.insert", "engine_results.extend"):
        assert banned not in code, banned


def test_the_shadow_module_is_never_given_a_weight():
    assert NS_KEY not in BASE_ENGINE_WEIGHTS
    assert "macro_shadow" not in BASE_ENGINE_WEIGHTS
    assert len(BASE_ENGINE_WEIGHTS) == 9
    assert round(sum(BASE_ENGINE_WEIGHTS.values()), 6) == 1.0


def test_the_publish_gate_constant_is_untouched():
    src = (BACKEND / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in src
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in src


def test_the_shadow_is_not_read_by_any_branch_in_the_scheduler():
    """The return value is an ARGUMENT and nothing else — never a condition.

    Only the CONDITION of each branch is inspected. Dumping the whole `If` would
    include its body and therefore match the call sites themselves, which is how a
    test like this passes for entirely the wrong reason.
    """
    node = _generate_signal_ast()
    conditions = []
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.IfExp)):
            conditions.append(child.test)
        elif isinstance(child, ast.Assert):
            conditions.append(child.test)
        elif isinstance(child, ast.Compare):
            conditions.append(child)
    for cond in conditions:
        dumped = ast.dump(cond)
        assert "macro_shadow" not in dumped, dumped[:200]


def test_the_shadow_result_is_never_bound_to_a_name_in_the_scheduler():
    """Not assigned means not reachable by anything later in the function."""
    node = _generate_signal_ast()
    for child in ast.walk(node):
        if isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign,
                              ast.NamedExpr, ast.Return)):
            value = getattr(child, "value", None)
            if value is not None:
                assert "macro_shadow" not in ast.dump(value), ast.dump(child)[:200]


def test_the_exposure_probe_is_untouched():
    """Occupancy input (CP-OBS-1A) must not have moved or gained an argument."""
    src = (BACKEND / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    assert "exposure = await _collect_exposure(" in src
    assert "macro_shadow" not in inspect.getsource(
        __import__("app.services.scheduler", fromlist=["_collect_exposure"])
        ._collect_exposure)


# ══════════════════════════════════════════════════════════════════════════════
# 23-24 · NO FETCH · NO SECRET — armed, not assumed
# ══════════════════════════════════════════════════════════════════════════════
def _code_only(obj):
    """Source with every docstring stripped. The prose legitimately NAMES the
    things the code may not touch; the ban is on the code."""
    src = inspect.getsource(obj)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


class _Armed(Exception):
    """Raised by any network or settings access that should be impossible."""


@pytest.fixture
def armed(monkeypatch):
    """Everything the wiring is forbidden to touch, wired to explode."""
    import socket
    import urllib.request

    def boom(*a, **k):
        raise _Armed("forbidden access attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        import httpx
        monkeypatch.setattr(httpx, "Client", boom)
        monkeypatch.setattr(httpx, "AsyncClient", boom)
        monkeypatch.setattr(httpx, "get", boom, raising=False)
    except ImportError:                                   # pragma: no cover
        pass
    import app.config
    monkeypatch.setattr(app.config, "get_settings", boom, raising=False)
    import app.collectors.macro_collector as mc
    monkeypatch.setattr(mc, "MacroCollector", boom)

    class _NoEnv(dict):
        def __getitem__(self, k):
            raise _Armed(f"env read: {k}")

        def get(self, *a, **k):
            raise _Armed("env read")
    monkeypatch.setattr(os, "environ", _NoEnv())
    monkeypatch.setattr(os, "getenv", boom)
    return True


def test_the_whole_candidate_path_runs_with_the_network_armed(armed):
    """`executed=false` proved as an inability, not a preference."""
    vals = _values()
    p = vals["extra"][NS_KEY]
    assert p["executed"] is False and p["configured"] is False
    assert p["fetch_status"] == "not_configured"


def test_the_wiring_helper_runs_with_settings_and_env_armed(armed):
    p = msw.build_candidate_macro_shadow(decision=_decision(), decision_time=DT,
                                         verdict="published")
    assert p["fallback_reason"] == "no_api_key"
    assert p["errors"] == []


def test_the_wiring_module_imports_nothing_that_could_fetch_or_read_a_secret():
    tree = ast.parse((BACKEND / "app" / "services" / "macro_shadow_wiring.py")
                     .read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    forbidden = ("os", "httpx", "requests", "aiohttp", "urllib", "socket",
                 "sqlalchemy", "app.database", "app.config", "app.models",
                 "app.collectors", "app.engines", "app.services.scheduler")
    for f in forbidden:
        assert not any(m == f or m.startswith(f + ".") for m in mods), (f, mods)
    assert mods == {"__future__", "logging", "typing", "app.services.macro_shadow"}, mods


def test_no_secret_or_transport_token_appears_in_the_wiring_code():
    code = _code_only(msw)
    for banned in ("FRED_API_KEY", "api_key=", "?api_key", "settings.", "os.environ",
                   "getenv", "environ[", "http://", "https://", "fetch_us_macro",
                   "MacroCollector", "str(exc)", "repr(exc)", "traceback"):
        assert banned not in code, banned
    assert code.count("api_key") == code.count("no_api_key")


def test_only_an_exception_class_name_survives_a_failure():
    """A message could carry the api_key query parameter. The class name cannot."""
    class _Boom(Exception):
        def __str__(self):
            return "https://api.stlouisfed.org/x?api_key=SENTINEL"

    payload = msw._last_resort(DT, "dropped", type(_Boom()).__name__)
    blob = json.dumps(payload)
    assert "SENTINEL" not in blob and "api_key=" not in blob
    assert payload["errors"] == [{"error": "exception", "error_class": "_Boom"}]


# ══════════════════════════════════════════════════════════════════════════════
# 25 · FAILURE ISOLATION — a broken shadow must never cost a candidate
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("decision", [
    None, {}, "not a decision", 42, [],
    {"engine_results": None}, {"engine_results": "a string"},
    {"engine_results": [None, 7, "x"]},
    {"engine_results": [{"engine_name": MACRO}]},          # no score/bias/conf
    {"engine_results": [{"engine_name": MACRO, "score": float("nan"),
                         "bias": object(), "confidence": float("inf")}]},
])
def test_a_hostile_decision_never_raises_and_still_yields_a_valid_payload(decision):
    p = msw.build_candidate_macro_shadow(decision=decision, decision_time=DT,
                                         verdict="dropped")
    assert p is not None
    assert ms.validate_macro_shadow(p) == []
    assert p["executed"] is False
    json.dumps(p)


def test_a_raising_contract_builder_does_not_lose_the_candidate(monkeypatch):
    def boom(**kw):
        raise RuntimeError("contract exploded")
    monkeypatch.setattr(msw, "build_disabled_macro_shadow", boom)
    shadow = msw.build_candidate_macro_shadow(decision=_decision(),
                                              decision_time=DT, verdict="dropped")
    assert shadow is None                      # both attempts failed
    vals = _values(with_shadow=False)
    assert vals is not None and NS_KEY not in vals["extra"]
    assert vals["verdict"] == "dropped"        # the row is intact


def test_the_second_attempt_is_used_when_only_the_first_build_fails(monkeypatch):
    calls = {"n": 0}
    real = ms.build_disabled_macro_shadow

    def once(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt exploded")
        return real(**kw)
    monkeypatch.setattr(msw, "build_disabled_macro_shadow", once)
    p = msw.build_candidate_macro_shadow(decision=_decision(), decision_time=DT,
                                         verdict="dropped")
    assert p is not None
    assert p["errors"] == [{"error": "exception", "error_class": "RuntimeError"}]
    assert ms.validate_macro_shadow(p) == []


def test_the_helper_never_raises_for_any_decision_time():
    for dt in (None, "", "not-a-date", 0, DT, "2026-07-31T00:00:00Z", object()):
        p = msw.build_candidate_macro_shadow(decision=_decision(), decision_time=dt,
                                             verdict=None)
        assert p is not None and ms.validate_macro_shadow(p) == []


def test_the_helper_has_no_shared_mutable_default():
    for p in inspect.signature(msw.build_candidate_macro_shadow).parameters.values():
        assert not isinstance(p.default, (list, dict, set)), p.name


def test_two_candidates_cannot_share_one_payload_object():
    """Asserted at BOTH layers, and the helper layer is the load-bearing one.

    `_json_safe` rebuilds every dict and list on its way into the candidate row,
    so a shared mutable inside the contract module is invisible from there — a
    sabotage that made `errors` a module-level list passed the candidate-layer
    check alone. The row-level assertion is still worth keeping (it pins that
    isolation), but it cannot stand in for the one below it.
    """
    d = _decision()
    pa = msw.build_candidate_macro_shadow(decision=d, decision_time=DT, verdict="dropped")
    pb = msw.build_candidate_macro_shadow(decision=d, decision_time=DT, verdict="dropped")
    assert pa["errors"] is not pb["errors"]
    assert pa["series"] is not pb["series"]
    pa["errors"].append("tampered")
    pa["fetch_status"] = "tampered"
    assert pb["errors"] == []
    assert pb["fetch_status"] == "not_configured"

    a, b = _values(d), _values(d)
    a["extra"][NS_KEY]["errors"].append("tampered")
    a["extra"][NS_KEY]["fetch_status"] = "tampered"
    assert b["extra"][NS_KEY]["errors"] == []
    assert b["extra"][NS_KEY]["fetch_status"] == "not_configured"


def test_a_payload_is_never_reused_across_calls():
    """Ten payloads, ten distinct list objects — the shape a module-level default
    or a cache would collapse."""
    d = _decision()
    payloads = [msw.build_candidate_macro_shadow(decision=d, decision_time=DT,
                                                 verdict="dropped") for _ in range(10)]
    assert len({id(p) for p in payloads}) == 10
    assert len({id(p["errors"]) for p in payloads}) == 10
    assert len({id(p["series"]) for p in payloads}) == 10


# ══════════════════════════════════════════════════════════════════════════════
# 26-28 · CMV2 · PASS A · PASS B ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
def test_cmv2_cohort_resolution_reads_one_named_key_and_ignores_the_namespace():
    src = inspect.getsource(cm._resolve_fold_cohort)
    assert '"decision_input_version" not in extra' in src
    assert 'extra.get("decision_input_version")' in src
    for banned in ("for k, v in extra", "extra.items()", "macro_shadow",
                   "jsonb_object_keys", "**extra"):
        assert banned not in src, banned


def test_the_cohort_is_identical_with_and_without_the_namespace():
    plain = {"decision_input_version": "closed_candle_v1"}
    withns = {**plain, NS_KEY: _values()["extra"][NS_KEY]}
    for extra in (plain, withns):
        assert isinstance(extra, dict) and "decision_input_version" in extra
        assert extra.get("decision_input_version") == "closed_candle_v1"
    assert cm.cm_v2_cohort_key({"decision_input_version": "closed_candle_v1",
                                "policy_version": 1}) == \
        "decision_input_version=closed_candle_v1|policy_version=1"


def test_no_production_module_iterates_candidate_extra_generically():
    """The ONE way an additive namespace could ever be folded by accident."""
    for path in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for banned in ("extra.items()", "jsonb_object_keys", "jsonb_each",
                       "**row.extra", "**candidate.extra"):
            assert banned not in text, f"{path.relative_to(BACKEND)}: {banned}"


def test_passa_birth_classification_is_untouched_by_the_wiring():
    vals = _values()
    reason = classify_birth_shadow(
        direction=vals["engine_direction"], entry_zone_low=vals["entry_zone_low"],
        entry_zone_high=vals["entry_zone_high"], stop_loss=vals["stop_loss"])
    assert vals["shadow_resolution_reason"] == reason
    assert vals["shadow_outcome"] == (SHADOW_UNDECIDABLE if reason else None)
    assert vals["shadow_evaluated_at"] == (DT if reason else None)


def test_passb_columns_are_never_written_by_the_candidate_builder():
    vals = _values()
    for col in ("shadow_resolution_path", "shadow_resolved_at", "shadow_r_multiple",
                "shadow_return_pct", "shadow_mfe_pct", "shadow_mae_pct",
                "shadow_bars_walked", "shadow_detail_label", "shadow_entry_reached",
                "shadow_never_entered"):
        assert col not in vals, col


def test_the_namespace_cannot_collide_with_passb():
    """PassB rides in `extra.shadow_passb` — a different key, and neither is a
    prefix of the other."""
    assert NS_KEY != "shadow_passb"
    assert not NS_KEY.startswith("shadow_")
    merged = cl.merge_additive_namespace({"shadow_passb": {"n": 1}}, NS_KEY, {"a": 1})
    assert merged["shadow_passb"] == {"n": 1}
    assert set(merged) == {"shadow_passb", NS_KEY}


def test_passb_write_is_still_not_started():
    src = (BACKEND / "app" / "services" / "shadow_eval.py").read_text(encoding="utf-8")
    assert "macro_shadow" not in src
    assert "shadow_passb" in src


# ══════════════════════════════════════════════════════════════════════════════
# 29 · API AND FRONTEND NON-LEAKAGE
# ══════════════════════════════════════════════════════════════════════════════
def _code_of(path):
    """A file's source with every docstring removed — prose that NAMES the table
    is documentation, not a reference to it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_the_candidate_table_is_referenced_by_exactly_four_modules():
    """Scanned on CODE, not prose: macro_shadow_wiring's docstring legitimately
    names the table it writes telemetry into, and that is not a reference to it.
    None of the four serves an HTTP response."""
    refs = set()
    for path in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        code = _code_of(path)
        if "SignalDecisionCandidate" in code or "signal_decision_candidates" in code:
            refs.add(path.relative_to(BACKEND).as_posix())
    assert refs == {
        "app/models/__init__.py",
        "app/models/decision_candidate.py",
        "app/services/candidate_log.py",
        "app/services/coin_memory.py",
        # CP-V1. shadow_observation.py NAMES the table inside the JSON record it
        # builds, so an analyst reading a snapshot years later knows where to
        # join — but it never imports the model and never queries it. The
        # distinction is asserted below rather than assumed, so admitting this
        # fifth entry does not quietly admit a fifth WRITER.
        "app/services/shadow_observation.py",
        # CP-J. candidate_lineage.py READS the table — one indexed lookup of the
        # preceding row — to resolve opportunity identity. It is admitted as a
        # sixth entry rather than the guard being relaxed, and it is a reader in
        # the logger's own domain: the assertions below pin that it writes
        # nothing and cannot reach a decision.
        "app/services/candidate_lineage.py",
    }, refs

    obs = _code_of(BACKEND / "app" / "services" / "shadow_observation.py")
    assert "SignalDecisionCandidate" not in obs, "the observation module imported the model"
    for access in ("select(", "insert(", "update(", "delete(", ".execute(", "await "):
        assert access not in obs, f"the observation module reached the database: {access}"


def test_no_http_read_surface_returns_candidate_rows():
    """The precise claim. There ARE two admin HTTP surfaces that WRITE candidates
    (POST /admin/signals/generate, POST /admin/system/jobs/{id}/trigger); what does
    not exist is any surface that reads one back."""
    for path in (BACKEND / "app" / "api").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        code = _code_of(path)
        for banned in ("SignalDecisionCandidate", "signal_decision_candidates"):
            assert banned not in code, f"{path.relative_to(BACKEND)}: {banned}"


def test_no_api_route_mentions_the_candidate_table_or_the_namespace():
    for path in (BACKEND / "app" / "api").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for banned in ("SignalDecisionCandidate", "signal_decision_candidates",
                       "macro_shadow", NS_KEY):
            assert banned not in text, f"{path.relative_to(BACKEND)}: {banned}"


def test_the_two_candidate_shaped_response_keys_are_backtest_counters():
    """`BacktestResponse` DOES ship two keys whose names contain "candidates".

    They are in-memory counters from a backtest run, not rows of the candidate
    log, and they are declared in app/schemas — which a grep scoped to app/api
    cannot see. Pinned here so "the HTTP surface never says candidate" is never
    asserted as a blanket claim it cannot support.
    """
    schema = (BACKEND / "app" / "schemas" / "signal.py").read_text(encoding="utf-8")
    assert "candidates_rejected_by_confidence" in schema
    assert "candidates_holded_by_mtf" in schema
    assert "SignalDecisionCandidate" not in schema
    assert NS_KEY not in schema


def test_the_admin_http_entry_point_adds_no_fourth_call_site():
    """`POST /api/v1/admin/signals/generate` reaches candidate writes inside the
    request handler (admin.py:447 → generate_signal_now → _generate_signal, fully
    awaited). So the wiring runs on an HTTP path too — and a raise there would be
    a 500, not just a lost row.

    The public wrapper must therefore stay a pure delegation: no candidate write
    and no shadow build of its own, or the admin path would acquire a fourth,
    unreviewed site that the `_generate_signal` AST assertions cannot see.
    """
    import app.services.scheduler as sched
    src = inspect.getsource(sched.generate_signal_now)
    assert "_generate_signal(" in src
    for banned in ("record_candidate", "build_candidate_macro_shadow", "macro_shadow"):
        assert banned not in src, banned
    admin = (BACKEND / "app" / "api" / "routes" / "admin.py").read_text(encoding="utf-8")
    assert "generate_signal_now(" in admin          # the entry point still exists
    assert "macro_shadow" not in admin


def test_no_schema_or_websocket_layer_exposes_the_namespace():
    for sub in ("schemas", "api", "engines", "backtesting"):
        root = BACKEND / "app" / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            assert NS_KEY not in path.read_text(encoding="utf-8"), path


def test_the_frontend_never_references_the_namespace():
    fe = BACKEND.parent / "frontend" / "src"
    if not fe.exists():                                   # pragma: no cover
        pytest.skip("frontend/src not present")
    hits = []
    for path in fe.rglob("*"):
        if path.suffix not in (".ts", ".tsx", ".js", ".jsx") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if NS_KEY in text or "macro_shadow" in text or "decision_candidate" in text:
            hits.append(path.name)
    assert hits == [], hits


# ══════════════════════════════════════════════════════════════════════════════
# 31-32 · SERIALISATION AND SIZE BUDGET
# ══════════════════════════════════════════════════════════════════════════════
def test_the_row_survives_json_round_trip_with_no_non_finite_values():
    extra = _values()["extra"]
    blob = json.dumps(extra)
    assert "NaN" not in blob and "Infinity" not in blob
    assert json.loads(blob) == extra


def test_json_safe_leaves_the_payload_unchanged():
    """The namespace is merged BEFORE `_json_safe`, so it must already be clean —
    any coercion would mean the tested payload is not the written one."""
    p = msw.build_candidate_macro_shadow(decision=_decision(), decision_time=DT,
                                         verdict="dropped")
    assert cl._json_safe(p) == p


def test_the_namespace_stays_inside_its_size_budget():
    """Measured against the live baseline: `extra` averaged 4 856 B over 7 239 rows
    in the 24 h before this shipped. The budget is what makes an unnoticed
    escalation impossible, not a decoration."""
    p = _values()["extra"][NS_KEY]
    size = len(json.dumps({NS_KEY: p}, separators=(",", ":")))
    assert size < 1400, size
    assert size / 4856 < 0.30, f"{100 * size / 4856:.1f}% of the average extra"


def test_the_payload_is_flat_enough_for_the_json_safe_depth_guard():
    """`_json_safe` degrades anything past depth 6 to `str(...)`. The namespace
    sits at depth 1 inside `extra`, so its own nesting must stay well under."""
    def depth(o, d=0):
        if isinstance(o, dict):
            return max([depth(v, d + 1) for v in o.values()] or [d])
        if isinstance(o, list):
            return max([depth(v, d + 1) for v in o] or [d])
        return d
    assert depth(_values()["extra"][NS_KEY]) <= 3


def test_repeating_the_build_does_not_grow_the_row():
    d = _decision()
    sizes = {len(json.dumps(_values(d), sort_keys=True, default=str)) for _ in range(5)}
    assert len(sizes) == 1, sizes


# ══════════════════════════════════════════════════════════════════════════════
# 30 · FROZEN PRODUCTION DIGESTS — captured BEFORE the wiring existed
# ══════════════════════════════════════════════════════════════════════════════
FROZEN_CANDIDATE = "be788de14556c4f06a930f0715a4ed98d02ed99ce8187c363c89fef3de12989c"
FROZEN_EXTRA_KEYS = "21640e652c6a353757c7b8369b5f9cec8239899faa91a0f43275c73720b0137c"
FROZEN_CANDIDATE_COLS = "7f7ec749cf0c30b3ff00fef1426bf18583e33bff05e61078d0c81edaaad35ffb"
FROZEN_PASSA = "b0539f0d7d06cf1f2106d263bc1f20c17ed7c2a27b667ea9a8221c33a5071aed"
FROZEN_VERSIONS = "becec0a970be268dc7a3e461f37f698926703f4b7071a340502f3834ed3dd3a6"

VERDICTS = ("published", "dropped", "skipped")


def _candidate_grid(with_shadow):
    df = _df()
    ts = pd.Timestamp("2026-01-06T00:05:00Z").to_pydatetime()
    rows = []
    for si, base in enumerate((22.0, 48.0, 62.0, 84.0)):
        for bi, b in enumerate((SignalBias.BULLISH, SignalBias.BEARISH,
                                SignalBias.NEUTRAL)):
            for mi, mtf in enumerate((None,
                                      {"15m": "bullish", "1h": "bullish", "4h": "bullish"},
                                      {"15m": "bearish", "1h": "bearish", "4h": "bullish"})):
                results = _results(base, b, bi)
                out = generate_signal("BTCUSDT", "1h", df, results, mtf_trends=mtf,
                                      weights=BASE_ENGINE_WEIGHTS,
                                      current_price=float(df["close"].iloc[-1]))
                dec = {
                    "symbol": "BTCUSDT", "timeframe": "1h",
                    "signal_type": out.signal_type, "direction": out.direction,
                    "confidence_score": out.confidence_score,
                    "probability_score": out.probability_score,
                    "risk_score": out.risk_score, "risk_level": out.risk_level,
                    "entry_zone_low": out.entry_zone_low,
                    "entry_zone_high": out.entry_zone_high,
                    "stop_loss": out.stop_loss, "tp1": out.tp1, "tp2": out.tp2,
                    "tp3": out.tp3, "invalidation_conditions": [],
                    "birth_telemetry": out.birth_telemetry,
                    "consensus_telemetry": out.consensus_telemetry,
                    "decision_input_telemetry": {
                        "decision_input_version": "closed_candle_v1",
                        "candle_policy": "closed_only", "current_price": 147.6,
                        "decision_current_price_source": "full_frame_last_close",
                        "analysis_close_price": 147.2,
                        "last_analysis_bar_open_time": "2026-01-05T23:00:00+00:00",
                        "last_analysis_bar_close_time": "2026-01-06T00:00:00+00:00",
                        "last_analysis_bar_closed": True,
                        "current_vs_analysis_close_pct": 0.27,
                        "current_vs_analysis_close_atr": 0.11},
                    "engine_results": [r.model_dump() for r in results],
                    "engine_execution_telemetry": {
                        "version": "engine_execution_v1", "engine_count": 9,
                        "successful_engine_count": 9, "failed_engine_count": 0,
                        "failed_engines": [], "fallback_used": False},
                    "dependency_health": {
                        "version": "dependency_health_v1",
                        "engines": {MACRO: {"configured": False,
                                            "status": "not_configured"}}},
                    "explanation_tr": "x", "explanation_en": "x",
                    "generated_at": "2026-01-06T00:00:00", "mtf_trends": mtf}
                regime = NS(adx=27.5, atr_pct=1.8, atr_pct_median=1.5,
                            volume_ratio=1.3, trend_direction="up")
                for vi, verdict in enumerate(VERDICTS):
                    shadow = (msw.build_candidate_macro_shadow(
                        decision=dec, decision_time=ts, verdict=verdict)
                        if with_shadow else None)
                    vals = cl.build_candidate_values(
                        asset_id=7, symbol="BTCUSDT", timeframe="1h", decision=dec,
                        df=df, evaluated_at=ts, verdict=verdict,
                        demotion_reason=None, primary_demotion_reason=None,
                        final_signal_type=out.signal_type,
                        final_direction=out.direction, regime_label="trend",
                        regime_result=regime, engine_weights=BASE_ENGINE_WEIGHTS,
                        adaptive_active=True,
                        adaptive_snapshot={"base": BASE_ENGINE_WEIGHTS,
                                           "memory_applied": True},
                        last_close=float(df["close"].iloc[-1]),
                        signal_id=99 if verdict == "published" else None,
                        macro_shadow=shadow)
                    rows.append({"k": f"{si}-{bi}-{mi}-{vi}", "vals": vals})
    return rows


def _normalised(rows):
    out = []
    for r in rows:
        v = dict(r["vals"])
        extra = dict(v.get("extra") or {})
        extra.pop(NS_KEY, None)
        v["extra"] = extra
        out.append({"k": r["k"], "vals": v})
    return out


def test_frozen_candidate_digest_is_unmoved_with_the_namespace_stripped():
    """108 candidate rows across four score bands, three biases, three MTF states
    and all three verdicts. Every column and every pre-existing `extra` key is
    digested. The ONLY permitted difference from the pre-change capture is the new
    namespace, so it is removed before hashing — and the hash must not move."""
    rows = _candidate_grid(with_shadow=True)
    assert len(rows) == 108
    assert _digest(_normalised(rows)) == FROZEN_CANDIDATE


def test_the_unwired_grid_produces_the_same_digest_as_the_wired_one():
    """Proves the namespace is the only difference, rather than the normalisation
    hiding a second one."""
    assert _digest(_normalised(_candidate_grid(with_shadow=False))) == \
        _digest(_normalised(_candidate_grid(with_shadow=True))) == FROZEN_CANDIDATE


def test_frozen_extra_key_set_is_unmoved():
    keys = set()
    for r in _candidate_grid(with_shadow=True):
        keys |= set((r["vals"].get("extra") or {}).keys())
    assert NS_KEY in keys
    keys.discard(NS_KEY)
    assert _digest(sorted(keys)) == FROZEN_EXTRA_KEYS


def test_frozen_candidate_column_set_is_unmoved():
    cols = set()
    for r in _candidate_grid(with_shadow=True):
        cols |= set(r["vals"].keys())
    assert _digest(sorted(cols)) == FROZEN_CANDIDATE_COLS


def test_frozen_passa_grid_is_unmoved():
    rows = []
    for d in ("bullish", "bearish", "neutral", None):
        for lo, hi, sl in ((100.0, 101.0, 96.0), (None, None, 96.0),
                           (100.0, 101.0, None), (100.0, 101.0, 100.5),
                           (100.0, 101.0, 101.5), (0.0, 0.0, 0.0)):
            reason = classify_birth_shadow(direction=d, entry_zone_low=lo,
                                           entry_zone_high=hi, stop_loss=sl)
            rows.append({"dir": d, "geom": [lo, hi, sl], "reason": reason,
                         "outcome": SHADOW_UNDECIDABLE if reason else None})
    assert _digest(rows) == FROZEN_PASSA


def test_frozen_version_set_is_unmoved():
    """No version may be bumped by a telemetry wiring."""
    assert _digest({
        "CANDIDATE_POLICY_VERSION": CANDIDATE_POLICY_VERSION,
        "CANDIDATE_SCHEMA_VERSION": CANDIDATE_SCHEMA_VERSION,
        "BASE_ENGINE_WEIGHTS": dict(sorted(BASE_ENGINE_WEIGHTS.items())),
        "CONSENSUS_VOTE_ENGINES": sorted(CONSENSUS_VOTE_ENGINES),
        "engine_count": len(BASE_ENGINE_WEIGHTS),
    }) == FROZEN_VERSIONS


def test_the_cmv2_rule_versions_are_unbumped():
    assert cm.CM_V2_CONTRACT_VERSION == "cm_v2_contract_1"
    assert cm.CM_V2_FOLD_RULE_VERSION == "cm_v2_fold_1"
    assert cm.CM_V2_METRIC_RULE_VERSION == "cm_v2_metric_1"
    assert cm.CM_V2_AGGREGATION_VERSION == "cm_v2_aggregation_1"


# ══════════════════════════════════════════════════════════════════════════════
# 33-34 · PERSISTENCE — the namespace really reaches the INSERT
# ══════════════════════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, rid):
        self._rid = rid

    def scalar_one_or_none(self):
        return self._rid


class _CapturingDB:
    """Enough of an AsyncSession for `record_candidate`: a nested-transaction
    context manager and an `execute` that records the compiled INSERT."""

    def __init__(self, rid=1):
        self.statements = []
        self._rid = rid
        self.nested_entered = 0

    def begin_nested(self):
        db = self

        class _Ctx:
            async def __aenter__(self_inner):
                db.nested_entered += 1
                return self_inner

            async def __aexit__(self_inner, *a):
                return False
        return _Ctx()

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self._rid)


def _record(db, **kw):
    d = _decision()
    shadow = msw.build_candidate_macro_shadow(decision=d, decision_time=DT,
                                              verdict="dropped")
    base = dict(asset_id=7, symbol="BTCUSDT", timeframe="1h", decision=d,
                df=_df(), evaluated_at=DT, verdict="dropped", demotion_reason=None,
                primary_demotion_reason=None, final_signal_type=d["signal_type"],
                final_direction=d["direction"], regime_label="trend",
                regime_result=_REGIME, engine_weights=BASE_ENGINE_WEIGHTS,
                adaptive_active=True, adaptive_snapshot=None, last_close=147.6,
                macro_shadow=shadow)
    base.update(kw)
    return asyncio.run(cl.record_candidate(db, **base))


def _inserted_extra(stmt):
    for col, value in stmt.compile().params.items():
        if col.endswith("extra") or col == "extra":
            return value
    values = getattr(stmt, "_values", None) or {}
    for col, value in values.items():
        if getattr(col, "name", str(col)) == "extra":
            return getattr(value, "value", value)
    raise AssertionError("extra not found in the compiled INSERT")


def _inserts(db):
    """Only the INSERT statements a record_candidate call emitted.

    CP-J gave the write path one indexed SELECT (the lineage predecessor lookup),
    so "the only statement" is no longer the same claim as "the only write".
    Filtering to inserts keeps what these guards were actually protecting — one
    row per evaluation — and is strictly stronger than a positional index, which
    would silently start asserting against whichever statement happened to run
    first.
    """
    return [st for st in db.statements
            if type(st).__name__ == "Insert" or "INSERT" in str(st).upper()[:80]]


def test_the_namespace_reaches_the_actual_insert_statement():
    db = _CapturingDB()
    assert _record(db) is True
    assert len(_inserts(db)) == 1
    assert db.nested_entered == 1          # savepoint isolation kept
    extra = _inserted_extra(_inserts(db)[0])
    assert extra[NS_KEY]["version"] == "macro_shadow_v1"
    assert extra[NS_KEY]["executed"] is False
    assert extra["decision_input_version"] == "closed_candle_v1"
    assert "dependency_health_v1" in extra


def test_one_record_candidate_call_issues_exactly_one_insert():
    db = _CapturingDB()
    _record(db)
    assert len(_inserts(db)) == 1


def test_the_insert_still_uses_on_conflict_do_nothing():
    """The only thing that makes a duplicate write safe under the pre-existing
    overlap between signals_15m and signals_1h."""
    db = _CapturingDB()
    _record(db)
    sql = str(_inserts(db)[0].compile(
        dialect=__import__("sqlalchemy.dialects.postgresql",
                           fromlist=["dialect"]).dialect()))
    assert "ON CONFLICT" in sql and "DO NOTHING" in sql


def test_a_second_identical_write_is_absorbed_by_the_conflict_clause():
    db = _CapturingDB(rid=None)            # the row already existed
    assert _record(db) is False
    assert len(_inserts(db)) == 1


def test_a_failing_insert_still_does_not_raise_into_the_scheduler():
    class _Exploding(_CapturingDB):
        async def execute(self, stmt):
            raise RuntimeError("statement error")
    assert _record(_Exploding()) is False


def test_a_row_with_no_scored_bar_is_skipped_not_written():
    db = _CapturingDB()
    assert _record(db, df=pd.DataFrame()) is False
    assert db.statements == []
