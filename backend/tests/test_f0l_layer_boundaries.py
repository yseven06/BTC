"""CP-F0-L1: pin today's Log / Feature / Model / Actuator boundary.

The F0 structural debt is "the model is embedded in the store". The chain today:

    resolution (LOG)
      -> fold_signal_into            -> engine_stats           (FEATURE)
      -> _recompute_adaptive_weights -> adaptive_weights       (MODEL, same row)
      -> get_effective_weights       -> weights                (ACTUATOR)
      -> generate_signal(symbol, timeframe, df, engine_results, weights)

F0-K already drew the log->feature line: features are rebuildable from the SoT. The
line still missing is feature->model — the model runs INSIDE the fold and its output
is stored beside the facts, so swapping it would mean re-folding history and running
two models side by side is impossible.

These tests change nothing. They pin the boundary as it stands so that a future
CP-F0-L2 (lifting the model out of the fold) has a diff that is legible and a safety
net that fails loudly. Measured on the live DB before writing them: 52 of 52 cells
with stored weights match a fresh recomputation exactly, 0 mismatches — so the model
IS a pure function of the feature today, and the tests below lock that.

Test-only: no production code, no DB, no migration.
"""
import ast
import inspect
import pathlib
from types import SimpleNamespace as NS

import pytest

from app.models.intelligence import CoinMemory
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome
from app.services import coin_memory as cm
from app.services.coin_memory import (
    MIN_ENGINE_SAMPLES, MIN_SAMPLES_FOR_ADAPTIVE, _recompute_adaptive_weights,
    adaptive_is_active, fold_signal_into, get_effective_weights, regime_weights,
)

APP = pathlib.Path(cm.__file__).parents[1]
DECISION = APP / "engines" / "ai_decision" / "signal_generator.py"


# ── Doubles ─────────────────────────────────────────────────────────────────
def _cell(**kw):
    base = dict(symbol="BTCUSDT", timeframe="4h", total_signals=0, wins=0, losses=0,
                engine_stats={}, regime_stats={}, outcome_label_stats={})
    base.update(kw)
    return CoinMemory(**base)


def _sig(direction="bullish"):
    return NS(id="s1", timeframe=Timeframe.H4, direction=NS(value=direction))


def _perf(outcome=SignalOutcome.WIN, bars=5):
    return NS(outcome=outcome, detail_label="tp1_hit", bars_to_outcome=bars)


def _snap(bias="bullish", regime="trend"):
    return NS(regime=regime, engine_scores={
        "technical_analysis": {"bias": bias},
        "market_structure": {"bias": bias},
        "smart_money_concepts": {"bias": bias},
    })


def _book(n):
    """Enough folds to cross MIN_ENGINE_SAMPLES so a model actually gets built."""
    return [(_sig("bullish" if i % 4 else "bearish"),
             _perf(SignalOutcome.WIN if i % 3 else SignalOutcome.LOSS, bars=3 + i % 5),
             _snap()) for i in range(n)]


# ── 1 · THE invariant: the model is a pure function of the feature ──────────
def test_stored_model_always_equals_a_fresh_recomputation_from_the_feature():
    """The lock that makes lifting the model out of the fold safe.

    If adaptive_weights can always be re-derived from engine_stats, then computing
    it at read time is byte-identical to reading the stored column — which is
    exactly what CP-F0-L2 would rely on. Verified on live data first: 52/52 cells
    matched, 0 mismatches.
    """
    mem = _cell()
    for i, (sig, perf, snap) in enumerate(_book(30), start=1):
        fold_signal_into(mem, sig, perf, snap)
        # after EVERY fold, not just at the end
        assert mem.adaptive_weights == _recompute_adaptive_weights(mem.engine_stats), (
            f"fold #{i}: stored model drifted from its feature")
    assert mem.adaptive_weights is not None, "the book never crossed MIN_ENGINE_SAMPLES"


def test_the_invariant_has_teeth():
    """Perturb the feature without re-running the model -> the invariant must break.
    Otherwise the test above would pass on a broken boundary too."""
    mem = _cell()
    for sig, perf, snap in _book(20):
        fold_signal_into(mem, sig, perf, snap)
    assert mem.adaptive_weights == _recompute_adaptive_weights(mem.engine_stats)

    stats = {k: dict(v) for k, v in mem.engine_stats.items()}
    stats["technical_analysis"]["correct"] = 0          # feature moved, model stale
    mem.engine_stats = stats
    assert mem.adaptive_weights != _recompute_adaptive_weights(mem.engine_stats)


def test_the_model_is_deterministic_and_reads_nothing_but_the_feature():
    stats = {"technical_analysis": {"correct": 9, "total": 12},
             "market_structure": {"correct": 6, "total": 12}}
    a = _recompute_adaptive_weights(stats)
    b = _recompute_adaptive_weights(dict(stats))
    assert a == b and a is not None
    # a feature below the engine-sample floor contributes a neutral multiplier
    thin = _recompute_adaptive_weights({"technical_analysis": {"correct": 5, "total": 5}})
    assert thin is None, "no engine crossed MIN_ENGINE_SAMPLES -> no model at all"


# ── 2/3 · The decision path is DB-free by construction ─────────────────────
def test_the_decision_module_imports_no_database_no_orm_no_memory():
    """generate_signal cannot read a stored field it cannot import.

    This is the strongest form of the boundary: not "it doesn't read telemetry",
    but "it has no way to". Locks that signal_generator stays pure.
    """
    tree = ast.parse(DECISION.read_text(encoding="utf-8"))
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module)

    forbidden = ("sqlalchemy", "app.models", "app.database", "app.services.coin_memory")
    hits = [m for m in imported for f in forbidden if m.startswith(f)]
    assert hits == [], f"the decision module reached for storage: {hits}"


def test_generate_signal_takes_only_market_inputs_and_weights():
    """The whole learned layer enters through ONE parameter: weights."""
    from app.engines.ai_decision.signal_generator import generate_signal

    params = list(inspect.signature(generate_signal).parameters)
    assert params == ["symbol", "timeframe", "df", "engine_results", "mtf_trends", "weights"]


@pytest.mark.parametrize("field", [
    "hit_time", "detected_at", "closed_at", "engines_data",
    "explanation_tr", "explanation_en",
    "adaptive_weights", "tm_stats", "outcome_label_stats", "regime_stats",
])
def test_no_stored_field_is_read_by_the_decision(field):
    """Telemetry, display text and memory columns must not appear in the decision.

    F0-1A/OBS-1A already lock their own columns; this asserts the whole set at the
    one place a leak would matter. Note what is NOT in this list:
    invalidation_conditions is PRODUCED here (see the test below) — a stored column
    the decision writes is not a stored column the decision reads.
    """
    src = DECISION.read_text(encoding="utf-8")
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    assert field not in code, f"the decision path mentions {field}"


def test_invalidation_conditions_is_written_by_the_decision_not_read_back():
    """The distinction the test above must not blur.

    `signals.invalidation_conditions` is display text, but it ORIGINATES here: the
    decision composes the sentence and hands it out on GeneratedSignalData; the
    explanation generator renders it later. Output, never input — so it never closes
    a loop back into a decision.
    """
    tree = ast.parse(DECISION.read_text(encoding="utf-8"))
    reads = [n for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and n.attr == "invalidation_conditions"]
    assert reads == [], "the decision read invalidation_conditions off an object"

    from app.engines.ai_decision.signal_generator import GeneratedSignalData
    assert "invalidation_conditions" in GeneratedSignalData.__annotations__


def test_birth_telemetry_flows_out_of_the_decision_never_into_it():
    """signal_generator BUILDS birth telemetry. It must never consume it back —
    that would turn an observation into a feature behind our backs."""
    tree = ast.parse(DECISION.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "build_birth_telemetry"]
    assert len(calls) == 1, "birth telemetry should be built exactly once, as output"
    src = DECISION.read_text(encoding="utf-8")
    assert 'birth_telemetry["' not in src and "birth_telemetry.get(" not in src


# ── 4 · Characterisation: the model runs inside the fold TODAY ──────────────
def test_the_fold_currently_runs_the_model_itself():
    """Pinned, not endorsed — this IS the debt.

    fold_signal_into does log->feature AND feature->model in one pass, writing the
    model's output into the same row as the facts. That is why swapping the model
    would mean re-folding history, and why two models cannot run side by side.
    CP-F0-L2 would move this call to the actuator; when that lands, THIS test is the
    one that must be updated — deliberately, not silently.
    """
    src = inspect.getsource(fold_signal_into)
    assert "_recompute_adaptive_weights(" in src, "the model call left the fold — is this L2?"
    assert "mem.adaptive_weights = " in src, "the fold no longer stores the model output"


def test_the_actuator_reads_the_stored_model_rather_than_deriving_it():
    """The other half of the same coupling: get_effective_weights consumes the
    column instead of the feature. L2 would invert this."""
    src = inspect.getsource(get_effective_weights)
    assert "memory.adaptive_weights" in src
    assert "_recompute_adaptive_weights(" not in src


def test_a_fold_that_teaches_no_engine_lesson_leaves_the_model_untouched():
    """BREAKEVEN carries no directional lesson -> engine_stats and the model both
    stand still, so the invariant holds trivially. Locks that the fold does not
    republish a model on folds that did not move its input."""
    mem = _cell()
    for sig, perf, snap in _book(20):
        fold_signal_into(mem, sig, perf, snap)
    before_stats, before_model = dict(mem.engine_stats), dict(mem.adaptive_weights)

    fold_signal_into(mem, _sig(), _perf(SignalOutcome.BREAKEVEN), _snap())

    assert mem.total_signals == 21                       # the counter moved…
    assert mem.engine_stats == before_stats              # …the feature did not
    assert mem.adaptive_weights == before_model          # …nor the model
    assert mem.adaptive_weights == _recompute_adaptive_weights(mem.engine_stats)


# ── 6 · Actuator gate: characterised, not changed ──────────────────────────
def test_the_actuator_ignores_the_model_below_the_sample_gate():
    mem = _cell(total_signals=MIN_SAMPLES_FOR_ADAPTIVE - 1,
                adaptive_weights={"technical_analysis": 1.3})
    assert get_effective_weights("trend", mem) == regime_weights("trend")
    assert adaptive_is_active(mem) is False


def test_the_actuator_applies_the_model_at_and_above_the_gate():
    mem = _cell(total_signals=MIN_SAMPLES_FOR_ADAPTIVE,
                adaptive_weights={"technical_analysis": 1.3})
    weights = get_effective_weights("trend", mem)
    assert weights != regime_weights("trend")
    assert adaptive_is_active(mem) is True
    assert sum(weights.values()) == pytest.approx(1.0)   # always renormalised


def test_two_independent_gates_can_disagree():
    """R-2, pinned as a fact rather than fixed.

    MIN_ENGINE_SAMPLES gates whether a model exists; MIN_SAMPLES_FOR_ADAPTIVE gates
    whether the actuator uses one. They are separate numbers, so a cell can hold a
    model nobody applies, or clear the gate with no model to apply. Live counts when
    this was written: 4 of the former, 5 of the latter. Changing either threshold is
    a behaviour change and out of scope here.
    """
    assert MIN_ENGINE_SAMPLES < MIN_SAMPLES_FOR_ADAPTIVE

    # a model exists, but the actuator will not touch it
    has_model = _cell(total_signals=MIN_ENGINE_SAMPLES,
                      adaptive_weights={"technical_analysis": 1.3})
    assert has_model.adaptive_weights is not None
    assert adaptive_is_active(has_model) is False

    # past the actuator gate, but nothing was ever learned
    no_model = _cell(total_signals=MIN_SAMPLES_FOR_ADAPTIVE, adaptive_weights=None)
    assert adaptive_is_active(no_model) is False
    assert get_effective_weights("trend", no_model) == regime_weights("trend")


def test_no_memory_at_all_falls_back_to_the_regime_tilted_base():
    assert get_effective_weights("trend", None) == regime_weights("trend")
    assert adaptive_is_active(None) is False
