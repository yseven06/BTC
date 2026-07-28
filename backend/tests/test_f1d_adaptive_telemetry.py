"""F1-D — the decision-time adaptive weight snapshot.

Backtest adaptive parity is not_applied because coin_memory has no version,
valid_from or as_of column and every fold overwrites the row: the state that
produced a past decision is simply gone by the time anyone asks. Applying
today's memory to a past bar would be look-ahead wearing a parity label, so the
only honest way to get the state is to record it at the moment the decision uses
it. That is what this captures, forward-only — nothing is backfilled.

The tests below assert two separate things and must not be confused:
  1. the snapshot faithfully records the chain the decision resolved, and
  2. recording it changes nothing about the decision.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
from app.services import coin_memory as cm
from app.services.candidate_log import _adaptive_state_entry
from app.services.coin_memory import (
    ADAPTIVE_TELEMETRY_VERSION,
    FALLBACK_BELOW_MIN_SAMPLES,
    FALLBACK_NO_ENGINE_READY,
    FALLBACK_NO_MEMORY,
    MIN_ENGINE_SAMPLES,
    MIN_SAMPLES_FOR_ADAPTIVE,
    get_effective_weights,
    resolve_weight_chain,
    weight_chain_snapshot,
)

ENGINES = list(BASE_ENGINE_WEIGHTS)
REGIMES = [None, "trending_bull", "trending_bear", "ranging",
           "volatile_high", "low_volume", "breakout", "unknown_regime"]


def _stats(**per_engine):
    return {e: {"correct": c, "total": t} for e, (c, t) in per_engine.items()}


def _learned_memory(total_signals=40, correct=10, total=MIN_ENGINE_SAMPLES + 5):
    return NS(
        total_signals=total_signals,
        engine_stats={e: {"correct": correct, "total": total} for e in ENGINES},
        adaptive_weights=None,
        last_updated_at=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )


def _snapshot(regime="ranging", memory=None, symbol="BTCUSDT", timeframe="1h"):
    chain = resolve_weight_chain(regime, memory)
    return chain, weight_chain_snapshot(chain, symbol=symbol, timeframe=timeframe,
                                        regime=regime, memory=memory)


# --------------------------------------------------------------------------- #
# 1. the chain is recorded faithfully
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("regime", REGIMES)
def test_all_nine_engines_are_present_in_every_layer(regime):
    _, snap = _snapshot(regime, _learned_memory())
    for layer in ("base_weights", "regime_multipliers", "regime_adjusted_weights",
                  "coin_memory_multipliers", "coin_memory_adjusted_weights",
                  "effective_weights"):
        assert sorted(snap[layer]) == sorted(ENGINES), f"{layer} motor kumesi eksik/fazla"


def test_engine_order_is_canonical_and_deterministic():
    _, snap = _snapshot(memory=_learned_memory())
    assert snap["engine_order"] == ENGINES
    _, again = _snapshot(memory=_learned_memory())
    assert again["engine_order"] == snap["engine_order"]


def test_base_layer_is_the_base_mix():
    _, snap = _snapshot("ranging", _learned_memory())
    assert snap["base_weights"] == dict(BASE_ENGINE_WEIGHTS)


@pytest.mark.parametrize("regime", REGIMES)
def test_regime_layer_matches_the_function_the_decision_uses(regime):
    _, snap = _snapshot(regime, None)
    assert snap["regime_adjusted_weights"] == cm.regime_weights(regime)


def test_regime_multipliers_are_spelled_out_for_every_engine():
    """An omitted engine means 1.0; recording it explicitly means a reader never
    has to know that."""
    _, snap = _snapshot("ranging", None)
    tilt = cm._REGIME_TILTS["ranging"]
    for e in ENGINES:
        assert snap["regime_multipliers"][e] == pytest.approx(tilt.get(e, 1.0))


def test_memory_multipliers_match_the_decisions_recompute():
    mem = _learned_memory()
    _, snap = _snapshot("ranging", mem)
    assert snap["coin_memory_multipliers"] == cm._decision_adaptive_weights(mem)


@pytest.mark.parametrize("regime", REGIMES)
def test_effective_layer_is_what_the_decision_actually_uses(regime):
    for mem in (None, _learned_memory(), _learned_memory(total_signals=3)):
        _, snap = _snapshot(regime, mem)
        assert snap["effective_weights"] == get_effective_weights(regime, mem)


def test_effective_weight_sum_is_recorded_and_correct():
    _, snap = _snapshot("volatile_high", _learned_memory())
    assert snap["effective_weight_sum"] == pytest.approx(1.0, abs=1e-9)
    assert snap["effective_weight_sum"] == pytest.approx(
        sum(snap["effective_weights"].values()), abs=1e-12)


def test_memory_layer_and_effective_agree_while_memory_is_last():
    _, snap = _snapshot("ranging", _learned_memory())
    assert snap["coin_memory_adjusted_weights"] == snap["effective_weights"]


# --------------------------------------------------------------------------- #
# 2. adaptive on / off / fallback
# --------------------------------------------------------------------------- #

def test_adaptive_applied_path_is_recorded():
    _, snap = _snapshot("ranging", _learned_memory())
    assert snap["adaptive_active"] is True
    assert snap["memory_applied"] is True
    assert snap["memory_available"] is True
    assert snap["fallback_reason"] is None
    assert snap["coin_memory_multipliers"] is not None


def test_no_memory_row_reports_that_reason():
    _, snap = _snapshot("ranging", None)
    assert snap["adaptive_active"] is False
    assert snap["memory_available"] is False
    assert snap["fallback_reason"] == FALLBACK_NO_MEMORY
    assert snap["coin_memory_multipliers"] is None
    assert snap["memory_sample_count"] is None


def test_below_min_samples_reports_that_reason():
    mem = _learned_memory(total_signals=MIN_SAMPLES_FOR_ADAPTIVE - 1)
    _, snap = _snapshot("ranging", mem)
    assert snap["fallback_reason"] == FALLBACK_BELOW_MIN_SAMPLES
    assert snap["memory_sample_count"] == MIN_SAMPLES_FOR_ADAPTIVE - 1
    assert snap["adaptive_active"] is False


def test_no_engine_above_min_samples_reports_that_reason():
    mem = NS(total_signals=50, adaptive_weights=None, last_updated_at=None,
             engine_stats={e: {"correct": 1, "total": MIN_ENGINE_SAMPLES - 1} for e in ENGINES})
    _, snap = _snapshot("ranging", mem)
    assert snap["fallback_reason"] == FALLBACK_NO_ENGINE_READY
    assert snap["adaptive_active"] is False
    # The gate is what fell back, not the sample count — that one is fine.
    assert snap["memory_sample_count"] == 50


def test_the_three_fallback_reasons_are_distinct():
    assert len({FALLBACK_NO_MEMORY, FALLBACK_BELOW_MIN_SAMPLES,
                FALLBACK_NO_ENGINE_READY}) == 3


@pytest.mark.parametrize("regime", ["trending_bull", "trending_bear", "ranging", None])
def test_every_regime_records_its_own_label(regime):
    _, snap = _snapshot(regime, _learned_memory())
    assert snap["regime"] == regime


# --------------------------------------------------------------------------- #
# 3. immutability — the snapshot must not move afterwards
# --------------------------------------------------------------------------- #

def test_building_the_snapshot_does_not_mutate_the_base_weights():
    before = dict(BASE_ENGINE_WEIGHTS)
    _snapshot("ranging", _learned_memory())
    assert BASE_ENGINE_WEIGHTS == before


def test_building_the_snapshot_does_not_mutate_the_regime_tilts():
    before = json.dumps(cm._REGIME_TILTS, sort_keys=True)
    _snapshot("volatile_high", _learned_memory())
    assert json.dumps(cm._REGIME_TILTS, sort_keys=True) == before


def test_the_snapshot_survives_later_mutation_of_the_chain():
    """A stored reference would let a later sweep rewrite an earlier row's
    record. The snapshot has to be a copy, not a view."""
    chain, snap = _snapshot("ranging", _learned_memory())
    frozen = json.dumps(snap["effective_weights"], sort_keys=True)
    chain.effective["technical_analysis"] = 999.0
    assert json.dumps(snap["effective_weights"], sort_keys=True) == frozen


def test_mutating_the_snapshot_does_not_reach_the_next_one():
    _, a = _snapshot("ranging", _learned_memory())
    a["effective_weights"]["technical_analysis"] = 42.0
    _, b = _snapshot("ranging", _learned_memory())
    assert b["effective_weights"]["technical_analysis"] != 42.0


def test_no_two_layers_share_one_dict():
    """Aliasing is the quiet version of the mutation bug: two fields pointing at
    one dict means editing either rewrites both, and nothing looks wrong until
    something downstream edits one."""
    chain, snap = _snapshot("ranging", _learned_memory())
    layers = ["base_weights", "regime_multipliers", "regime_adjusted_weights",
              "coin_memory_multipliers", "coin_memory_adjusted_weights",
              "effective_weights"]
    seen = {}
    for name in layers:
        obj = snap[name]
        if obj is None:
            continue
        for other, prev in seen.items():
            assert obj is not prev, f"{name} ile {other} ayni dict nesnesi"
        seen[name] = obj
    for name in layers:
        if snap[name] is not None:
            assert snap[name] is not getattr(chain, {
                "base_weights": "base", "regime_multipliers": "regime_multipliers",
                "regime_adjusted_weights": "regime_adjusted",
                "coin_memory_multipliers": "memory_multipliers",
                "coin_memory_adjusted_weights": "effective",
                "effective_weights": "effective"}[name]), f"{name} zinciri isaret ediyor"


def test_effective_weight_sum_is_computed_not_assumed():
    """Every normalised chain sums to 1.0, so a hard-coded 1.0 looks right on
    every real input. This feeds a chain that deliberately does not."""
    chain = resolve_weight_chain("ranging", None)
    skewed = {k: v * 2.0 for k, v in chain.effective.items()}
    lopsided = cm.WeightChain(
        base=chain.base, regime_adjusted=chain.regime_adjusted,
        regime_multipliers=chain.regime_multipliers,
        memory_multipliers=None, effective=skewed,
        memory_applied=False, fallback_reason=chain.fallback_reason)
    snap = weight_chain_snapshot(lopsided, symbol="X", timeframe="1h",
                                 regime="ranging", memory=None)
    assert snap["effective_weight_sum"] == pytest.approx(2.0, abs=1e-9)
    assert snap["effective_weight_sum"] != 1.0


def test_the_coin_memory_policy_constants_are_pinned():
    """These shape which decisions get the learned layer at all. A silent edit
    would change the meaning of every snapshot taken after it, and the band in
    particular is currently unreachable (the multiplier tops out at 1.3), so
    nothing else would notice."""
    assert cm.MIN_SAMPLES_FOR_ADAPTIVE == 20
    assert cm.MIN_ENGINE_SAMPLES == 12
    assert cm.ADAPTIVE_BAND_LOW == 0.55
    assert cm.ADAPTIVE_BAND_HIGH == 1.75
    assert set(cm._REGIME_TILTS) == {
        "trending_bull", "trending_bear", "ranging",
        "volatile_high", "low_volume", "breakout"}


def test_candidate_entry_copies_rather_than_sharing():
    """One sweep passes the same snapshot to three record_candidate sites; a
    shared dict would let the last row rewrite the first."""
    _, snap = _snapshot("ranging", _learned_memory())
    e1 = _adaptive_state_entry(snap, {"direction": "bullish"}, datetime.now(timezone.utc))
    e2 = _adaptive_state_entry(snap, {"direction": "bearish"}, datetime.now(timezone.utc))
    assert e1["direction"] == "bullish" and e2["direction"] == "bearish"
    assert "direction" not in snap, "orijinal snapshot kirletildi"


# --------------------------------------------------------------------------- #
# 4. value hygiene
# --------------------------------------------------------------------------- #

def test_non_finite_weights_are_rejected_not_written():
    chain = resolve_weight_chain("ranging", None)
    chain.effective["technical_analysis"] = float("nan")
    with pytest.raises(ValueError):
        weight_chain_snapshot(chain, symbol="X", timeframe="1h", regime="ranging", memory=None)


def test_infinity_is_rejected_too():
    chain = resolve_weight_chain("ranging", None)
    chain.effective["macro_analysis"] = float("inf")
    with pytest.raises(ValueError):
        weight_chain_snapshot(chain, symbol="X", timeframe="1h", regime="ranging", memory=None)


def test_a_missing_engine_is_not_silently_zero_filled():
    chain = resolve_weight_chain("ranging", None)
    chain.effective.pop("macro_analysis")
    with pytest.raises(ValueError) as ei:
        weight_chain_snapshot(chain, symbol="X", timeframe="1h", regime="ranging", memory=None)
    assert "macro_analysis" in str(ei.value)


def test_the_snapshot_is_json_serializable():
    _, snap = _snapshot("ranging", _learned_memory())
    text = json.dumps(snap)
    assert json.loads(text) == snap


def test_timestamps_are_utc_aware():
    _, snap = _snapshot("ranging", _learned_memory())
    captured = datetime.fromisoformat(snap["captured_at"])
    assert captured.tzinfo is not None and captured.utcoffset() == timedelta(0)
    updated = datetime.fromisoformat(snap["memory_last_updated_at"])
    assert updated.tzinfo is not None


def test_a_naive_memory_timestamp_is_promoted_to_utc():
    mem = _learned_memory()
    mem.last_updated_at = datetime(2026, 7, 28, 12, 0)      # naive
    _, snap = _snapshot("ranging", mem)
    assert datetime.fromisoformat(snap["memory_last_updated_at"]).tzinfo is not None


def test_the_same_inputs_produce_the_same_snapshot_apart_from_capture_time():
    _, a = _snapshot("ranging", _learned_memory())
    _, b = _snapshot("ranging", _learned_memory())
    a.pop("captured_at"), b.pop("captured_at")
    assert a == b


def test_the_snapshot_carries_no_unbounded_blob():
    """Only the fields that decided the multipliers — not the whole memory row."""
    _, snap = _snapshot("ranging", _learned_memory())
    size = len(json.dumps(snap))
    assert size < 8000, f"snapshot {size} bayt — sinirsiz blob riski"
    for banned in ("engine_stats", "regime_stats", "tm_stats", "outcome_label_stats"):
        assert banned not in snap, f"tum memory satiri kopyalanmis: {banned}"


def test_the_memory_fingerprint_tracks_the_inputs_that_matter():
    a = _learned_memory()
    b = _learned_memory()
    assert cm._memory_state_fingerprint(a) == cm._memory_state_fingerprint(b)
    b.engine_stats["technical_analysis"] = {"correct": 99, "total": 120}
    assert cm._memory_state_fingerprint(a) != cm._memory_state_fingerprint(b)
    assert cm._memory_state_fingerprint(None) is None


def test_sample_count_is_recorded_verbatim():
    for n in (0, 1, MIN_SAMPLES_FOR_ADAPTIVE, 137):
        _, snap = _snapshot("ranging", _learned_memory(total_signals=n))
        assert snap["memory_sample_count"] == n


# --------------------------------------------------------------------------- #
# 5. version / policy
# --------------------------------------------------------------------------- #

def test_version_and_policy_are_recorded():
    _, snap = _snapshot("ranging", _learned_memory())
    assert snap["telemetry_version"] == ADAPTIVE_TELEMETRY_VERSION == "adaptive_state_v1"
    assert snap["capture_policy"] == "decision_time_snapshot"
    assert snap["history_policy"] == "forward_only"
    assert snap["historical_backfill"] is False


def test_the_gates_that_shaped_the_decision_are_recorded():
    """Without these a later replay cannot tell a fallback caused by the gate
    from one caused by the data."""
    _, snap = _snapshot("ranging", _learned_memory())
    assert snap["min_samples_for_adaptive"] == MIN_SAMPLES_FOR_ADAPTIVE
    assert snap["min_engine_samples"] == MIN_ENGINE_SAMPLES
    assert snap["adaptive_band"] == [cm.ADAPTIVE_BAND_LOW, cm.ADAPTIVE_BAND_HIGH]


# --------------------------------------------------------------------------- #
# 6. the candidate-log entry
# --------------------------------------------------------------------------- #

def test_direction_and_decision_time_come_from_the_candidate_layer():
    _, snap = _snapshot("ranging", _learned_memory())
    when = datetime(2026, 7, 28, 18, 30, tzinfo=timezone.utc)
    entry = _adaptive_state_entry(snap, {"direction": "bearish"}, when)
    assert entry["direction"] == "bearish"
    assert entry["decision_evaluated_at"] == when.isoformat()
    assert datetime.fromisoformat(entry["decision_evaluated_at"]).tzinfo is not None


def test_an_absent_snapshot_yields_no_entry_rather_than_a_guess():
    assert _adaptive_state_entry(None, {"direction": "bullish"}, datetime.now(timezone.utc)) is None


def test_the_entry_keeps_every_snapshot_field():
    _, snap = _snapshot("ranging", _learned_memory())
    entry = _adaptive_state_entry(snap, {"direction": "bullish"}, datetime.now(timezone.utc))
    for k, v in snap.items():
        assert entry[k] == v


# --------------------------------------------------------------------------- #
# 7. the decision must not move
# --------------------------------------------------------------------------- #

def _legacy_get_effective_weights(regime, memory):
    """The pre-F1-D body, verbatim. resolve_weight_chain must match it exactly."""
    weights = cm.regime_weights(regime)
    learned = cm._decision_adaptive_weights(memory)
    if learned:
        combined = {k: weights[k] * float(learned.get(k, 1.0)) for k in weights}
        weights = cm._normalize(combined)
    return weights


@pytest.mark.parametrize("regime", REGIMES)
def test_effective_weights_are_byte_identical_to_the_pre_refactor_logic(regime):
    memories = [
        None,
        _learned_memory(),
        _learned_memory(total_signals=MIN_SAMPLES_FOR_ADAPTIVE - 1),
        _learned_memory(correct=0),
        _learned_memory(correct=MIN_ENGINE_SAMPLES + 5),
        NS(total_signals=99, adaptive_weights=None, last_updated_at=None,
           engine_stats={e: {"correct": 3, "total": MIN_ENGINE_SAMPLES - 1} for e in ENGINES}),
    ]
    for mem in memories:
        assert get_effective_weights(regime, mem) == _legacy_get_effective_weights(regime, mem)


def test_the_flag_still_agrees_with_the_applied_layer():
    for mem in (None, _learned_memory(), _learned_memory(total_signals=2)):
        chain = resolve_weight_chain("ranging", mem)
        assert chain.memory_applied is cm.adaptive_is_active(mem)


def test_telemetry_never_reaches_the_decision_even_when_it_fails():
    """load_effective_weights_meta must return usable weights even if the
    snapshot blows up — an exception there would leave the caller's
    engine_weights at None and the signal would be scored on the base mix."""
    class _Res:
        def scalar_one_or_none(self):
            return _learned_memory()

    class _DB:
        async def execute(self, *_a, **_kw):
            return _Res()

    def _boom(*_a, **_kw):
        raise RuntimeError("telemetry patladi")

    original = cm.weight_chain_snapshot
    cm.weight_chain_snapshot = _boom
    try:
        weights, active, snap = asyncio.run(
            cm.load_effective_weights_meta(_DB(), "BTCUSDT", "1h", "ranging"))
    finally:
        cm.weight_chain_snapshot = original

    assert snap is None
    assert active is True
    assert weights == get_effective_weights("ranging", _learned_memory())
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)


def test_every_candidate_verdict_carries_the_snapshot():
    """Adaptive weights help decide which candidates get DROPPED, not only which
    get published, so a published-only record would be a biased sample of exactly
    the thing a later replay wants to measure. Checked on the AST: all three
    record_candidate sites must pass it."""
    import ast
    import inspect
    import textwrap
    from app.services import scheduler as sched

    tree = ast.parse(textwrap.dedent(inspect.getsource(sched._generate_signal)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "record_candidate"]
    assert len(calls) == 3, f"beklenen 3 record_candidate cagrisi, bulunan {len(calls)}"

    verdicts, without = [], []
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        v = kw.get("verdict")
        verdicts.append(getattr(v, "id", None) or getattr(v, "attr", None))
        arg = kw.get("adaptive_snapshot")
        if not (isinstance(arg, ast.Name) and arg.id == "adaptive_snapshot"):
            without.append(verdicts[-1])
    assert not without, f"su verdict'lerde telemetri yok: {without}"
    assert set(verdicts) == {"VERDICT_SKIPPED", "VERDICT_DROPPED", "VERDICT_PUBLISHED"}


def test_the_candidate_logger_does_not_gate_telemetry_on_verdict():
    """The entry builder must not decide for itself which rows deserve a record."""
    import inspect
    from app.services import candidate_log

    src = inspect.getsource(candidate_log.build_candidate_values)
    line = [l for l in src.splitlines() if "_adaptive_state_entry(" in l]
    assert line, "entry hic olusturulmuyor"
    joined = " ".join(line)
    for banned in ("VERDICT_PUBLISHED", "verdict ==", "if verdict"):
        assert banned not in joined, f"telemetri verdict'e gore kapiliyor: {banned}"


def test_the_snapshot_is_not_rebuilt_from_the_database_later():
    """Re-resolving at log time could read a coin_memory row a later fold has
    already overwritten, recording weights the decision never used."""
    import inspect
    from app.services import candidate_log

    src = inspect.getsource(candidate_log._adaptive_state_entry)
    for banned in ("get_effective_weights", "resolve_weight_chain", "CoinMemory",
                   "select(", "execute("):
        assert banned not in src, f"candidate_log agirligi yeniden cozuyor: {banned}"
