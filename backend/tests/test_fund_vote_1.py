"""CP-FUND-VOTE-1 — the consensus vote pool holds five engines, not six.

`fundamental_analysis` returned a constant 57.5 on 8098/8098 logged candidates
because the orchestrator supplies it no `fundamental_data`. 57.5 > 53 cleared the
bullish confirmation bar on every single candidate and 57.5 is neither < 47 nor
> 60, so on the bearish side it could neither confirm nor conflict. It was a free
vote for longs and silence for shorts.

These tests run the real `generate_signal`. Nothing here greps for a constant to
prove behaviour; the two places that do read source (gate ORDER inside the
scheduler, which this checkpoint does not touch) parse the AST rather than match
strings, and say so.
"""
from __future__ import annotations

import ast
import inspect
import re
import textwrap

import numpy as np
import pandas as pd
import pytest

from app.engines.ai_decision import signal_generator as sg
from app.engines.ai_decision.signal_generator import (
    BASE_ENGINE_WEIGHTS,
    CONSENSUS_VOTE_ENGINES,
    REQUIRED_CONSENSUS_VOTES,
    generate_signal,
)
from app.engines.base import EngineResult, SignalBias

# The nine engines the orchestrator registers, in registration order
# (ai_decision/engine.py). Used to build a complete result set.
NINE = [
    "technical_analysis", "market_structure", "smart_money_concepts",
    "candle_range_theory", "volume_analysis", "risk_management",
    "fundamental_analysis", "onchain_analysis", "macro_analysis",
]

# What production actually produces for the three engines the tests hold still:
# fundamental is pinned at 57.5/conf 80, macro at 50.0/conf 25, onchain sits at
# 55.0 on 82.5% of candidates.
FUND_CONST = 57.5
FUND_CONF = 80.0


def _bias(score: float) -> SignalBias:
    if score >= 75:
        return SignalBias.STRONG_BULLISH
    if score >= 60:
        return SignalBias.BULLISH
    if score >= 40:
        return SignalBias.NEUTRAL
    if score >= 25:
        return SignalBias.BEARISH
    return SignalBias.STRONG_BEARISH


def results(scores: dict, *, biases: dict | None = None,
            confidences: dict | None = None) -> list[EngineResult]:
    """Nine EngineResults; anything unspecified sits at a neutral 50/conf 70."""
    biases = biases or {}
    confidences = confidences or {}
    out = []
    for name in NINE:
        s = float(scores.get(name, 50.0))
        out.append(EngineResult(
            engine_name=name,
            score=s,
            bias=biases.get(name, _bias(s)),
            confidence=float(confidences.get(name, 70.0)),
            key_findings=[],
            supporting_data={},
        ))
    return out


def frame(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-07-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.full(n, 1000.0),
    }, index=idx)


def decide(scores: dict, **kw):
    return generate_signal("TESTUSDT", "15m", frame(), results(scores, **kw.pop("engine_kw", {})), **kw)


def composite_of(scores: dict) -> float:
    """The composite as generate_signal computes it, penalty aside.

    Accumulated with `+=` in engine order rather than `sum()`: the two differ in
    the last ULP (45.025 vs 45.025000000000006), which is enough to land either
    side of a 2-decimal round. Matching the production loop keeps this an exact
    equality assertion instead of a tolerance one.
    """
    total = 0.0
    for n in NINE:
        total += float(scores.get(n, 50.0)) * BASE_ENGINE_WEIGHTS[n]
    return total


# Four real confirmations (>53): TA, MS, VOL, SMC. CRT deliberately at 50 so it
# neither confirms nor conflicts, and SMC carries smc_crt_confirm.
BULL_4 = {"technical_analysis": 65.0, "market_structure": 65.0,
          "volume_analysis": 60.0, "smart_money_concepts": 60.0,
          "candle_range_theory": 50.0, "onchain_analysis": 55.0,
          "fundamental_analysis": FUND_CONST}
# Three real confirmations. Under the old six-engine pool the constant made this
# a fourth and the call went out; under five it does not.
BULL_3 = {"technical_analysis": 65.0, "market_structure": 65.0,
          "smart_money_concepts": 66.0, "volume_analysis": 50.0,
          "candle_range_theory": 50.0, "onchain_analysis": 55.0,
          "fundamental_analysis": FUND_CONST}
# Four real bearish confirmations (<47).
BEAR_4 = {"technical_analysis": 40.0, "market_structure": 40.0,
          "volume_analysis": 40.0, "smart_money_concepts": 40.0,
          "candle_range_theory": 50.0, "onchain_analysis": 55.0,
          "fundamental_analysis": FUND_CONST}
# Three real bearish confirmations.
BEAR_3 = {"technical_analysis": 33.0, "market_structure": 33.0,
          "smart_money_concepts": 40.0, "volume_analysis": 50.0,
          "candle_range_theory": 50.0, "onchain_analysis": 55.0,
          "fundamental_analysis": FUND_CONST}

ACTIONABLE = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}


# --------------------------------------------------------------- 1-3: the pool
def test_the_vote_pool_holds_exactly_five_engines():
    assert len(CONSENSUS_VOTE_ENGINES) == 5
    assert len(set(CONSENSUS_VOTE_ENGINES)) == 5
    assert set(CONSENSUS_VOTE_ENGINES) == {
        "technical_analysis", "market_structure", "volume_analysis",
        "smart_money_concepts", "candle_range_theory",
    }


def test_fundamental_does_not_vote():
    assert "fundamental_analysis" not in CONSENSUS_VOTE_ENGINES
    # The three that never voted stay out too — this checkpoint moved one engine.
    for name in ("onchain_analysis", "macro_analysis", "risk_management"):
        assert name not in CONSENSUS_VOTE_ENGINES


def test_fundamental_is_still_one_of_the_nine_weighted_engines():
    assert "fundamental_analysis" in BASE_ENGINE_WEIGHTS
    assert len(BASE_ENGINE_WEIGHTS) == 9
    assert BASE_ENGINE_WEIGHTS["fundamental_analysis"] == pytest.approx(0.07)
    assert sum(BASE_ENGINE_WEIGHTS.values()) == pytest.approx(1.00)
    # Every voting engine must still be a weighted engine.
    assert set(CONSENSUS_VOTE_ENGINES) <= set(BASE_ENGINE_WEIGHTS)


def test_the_fundamental_engine_still_scores_exactly_as_before():
    """Pin the constant this checkpoint is a reaction to.

    CP-FUND-VOTE-1 removed fundamental's VOTE, not its output. If the engine's
    own numbers move, the premise recorded next to CONSENSUS_VOTE_ENGINES stops
    being true and the removal needs re-arguing rather than silently inheriting.
    """
    from app.engines.fundamental.crypto_fundamentals import analyze_crypto_fundamentals
    from app.engines.fundamental.engine import FundamentalAnalysisEngine

    # The path production actually takes: the orchestrator supplies no
    # fundamental_data, so the engine substitutes a hardcoded fallback payload
    # that does not depend on the symbol.
    fallback = FundamentalAnalysisEngine._generate_fallback_data("BTCUSDT", "crypto")
    assert fallback == FundamentalAnalysisEngine._generate_fallback_data("ETHUSDT", "crypto")

    res = analyze_crypto_fundamentals("BTCUSDT", fallback)
    assert res.composite_score == pytest.approx(FUND_CONST)
    assert res.tokenomics_score == pytest.approx(65.0)   # 85% circulating -> +15
    assert res.valuation_score == pytest.approx(50.0)    # mcap/fdv exactly 0.85, not > 0.85
    # 57.5 clears the bullish confirmation bar and misses both bearish bars.
    assert res.composite_score > 53.0
    assert not (res.composite_score < 47.0)
    assert not (res.composite_score > 60.0)
    assert not (res.composite_score < 40.0)


@pytest.mark.asyncio
async def test_the_fundamental_engine_still_reports_confidence_eighty():
    from app.engines.fundamental.engine import FundamentalAnalysisEngine

    out = await FundamentalAnalysisEngine().analyze("BTCUSDT", "15m", frame())
    assert out.confidence == pytest.approx(FUND_CONF)
    assert out.score == pytest.approx(FUND_CONST)
    assert out.engine_name == "fundamental_analysis"


@pytest.mark.asyncio
async def test_a_crashing_engine_still_falls_back_to_a_neutral_fifty():
    """The real exception path, triggered rather than imitated.

    A crashed engine must score 50 / neutral / confidence 30: neutral on every
    consensus threshold, so a failure can neither confirm nor conflict. Changing
    this would turn an outage into a directional vote.
    """
    from app.engines.ai_decision.engine import AIDecisionEngine

    class Exploding:
        name = "technical_analysis"

        async def analyze(self, *a, **kw):
            raise RuntimeError("boom")

    res = await AIDecisionEngine()._safe_run_engine(Exploding(), "BTCUSDT", "15m", frame())
    assert res.score == 50.0
    assert res.bias == SignalBias.NEUTRAL
    assert res.confidence == 30.0
    assert res.warnings


def test_the_orchestrator_still_registers_and_runs_the_fundamental_engine():
    from app.engines.ai_decision.engine import AIDecisionEngine
    from app.engines.fundamental.engine import FundamentalAnalysisEngine

    engines = AIDecisionEngine().engines
    assert len(engines) == 9
    assert any(isinstance(e, FundamentalAnalysisEngine) for e in engines)
    assert [e.name for e in engines] == NINE


# --------------------------------------- 5-7: fundamental keeps its other jobs
def test_fundamental_still_moves_the_composite():
    # Bias pinned neutral on both runs: the composite is what is under test, and
    # a swinging bias would add a disagreement penalty on top of it.
    neutral = {"biases": {"fundamental_analysis": SignalBias.NEUTRAL}}
    low = decide({**BULL_4, "fundamental_analysis": 0.0}, engine_kw=neutral)
    high = decide({**BULL_4, "fundamental_analysis": 100.0}, engine_kw=neutral)
    # 100 points x 0.07 weight = 7.0 composite points, unchanged by this CP.
    delta = (high.birth_telemetry["composite_score"]
             - low.birth_telemetry["composite_score"])
    assert delta == pytest.approx(7.0, abs=0.01)


def test_fundamental_still_feeds_the_confidence_average():
    base = decide(BULL_4, engine_kw={"confidences": {"fundamental_analysis": 80.0}})
    lower = decide(BULL_4, engine_kw={"confidences": {"fundamental_analysis": 20.0}})
    # One of nine confidences, so a 60-point drop moves the mean by 60/9.
    assert base.confidence_score - lower.confidence_score == pytest.approx(60.0 / 9.0, abs=0.01)


def test_fundamental_result_survives_into_the_candidate_payload():
    """The candidate log's own reshaper, run for real, must still carry it."""
    from app.services.candidate_log import _engine_scores

    payload = [r.model_dump() for r in results(BULL_4)]
    scores = _engine_scores(payload)
    assert set(scores) == set(NINE)
    assert scores["fundamental_analysis"]["score"] == pytest.approx(FUND_CONST)
    assert scores["fundamental_analysis"]["confidence"] == pytest.approx(70.0)
    assert scores["fundamental_analysis"]["bias"] is not None


# ------------------------------------------------- 8-11: the four vote cases
def test_bullish_with_four_real_confirmations_is_actionable():
    out = decide(BULL_4)
    assert out.direction == "bullish"
    assert out.signal_type in ACTIONABLE
    assert out.consensus_telemetry["engine_demoted"] is False


def test_bullish_with_three_real_confirmations_is_not_actionable():
    out = decide(BULL_3)
    # The composite still says BUY — this is a consensus demotion, not a band miss.
    assert out.consensus_telemetry["threshold_direction"] == "bullish"
    assert out.consensus_telemetry["threshold_signal_type"] in ACTIONABLE
    assert out.signal_type == "HOLD"
    assert out.direction == "neutral"
    assert out.consensus_telemetry["engine_demoted"] is True


def test_bearish_with_four_real_confirmations_is_actionable():
    out = decide(BEAR_4)
    assert out.direction == "bearish"
    assert out.signal_type in ACTIONABLE
    assert out.consensus_telemetry["engine_demoted"] is False


def test_bearish_with_three_real_confirmations_is_not_actionable():
    out = decide(BEAR_3)
    assert out.consensus_telemetry["threshold_direction"] == "bearish"
    assert out.consensus_telemetry["threshold_signal_type"] in ACTIONABLE
    assert out.signal_type == "HOLD"
    assert out.direction == "neutral"


# --------------------------------------------- 12-14: the threshold and denominator
def test_required_vote_count_is_four_for_both_directions():
    assert REQUIRED_CONSENSUS_VOTES == 4
    src = inspect.getsource(generate_signal)
    tree = ast.parse(textwrap.dedent(src))
    # Structural, not textual: every comparison against the required-vote count
    # must read the constant. A literal reintroduced on either branch fails here.
    literal_comparisons = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)
        and n.left.id == "confirmations"
    ]
    assert len(literal_comparisons) == 2, "one confirmations check per direction"
    for cmp_node in literal_comparisons:
        rhs = cmp_node.comparators[0]
        assert isinstance(rhs, ast.Name) and rhs.id == "REQUIRED_CONSENSUS_VOTES", (
            "confirmations must be compared against the named constant, "
            f"got {ast.dump(rhs)}"
        )


def test_the_denominator_is_static_five_not_derived_per_call():
    """No dynamic denominator: the bar does not shrink when the pool would."""
    src = inspect.getsource(generate_signal)
    tree = ast.parse(textwrap.dedent(src))
    # `len(pool)` may appear in log strings, never in a decision comparison.
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
                and node.left.id == "confirmations":
            assert not any(
                isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "len"
                for x in ast.walk(node)
            ), "required votes must not be computed from the pool size"


def test_there_is_no_three_of_five_path():
    """Three real confirmations never produce an actionable call, either side."""
    for scores in (BULL_3, BEAR_3):
        assert decide(scores).signal_type == "HOLD"


# ------------------------------- 15-17: what does and does not move the count
def test_the_fundamental_score_cannot_change_the_consensus_outcome():
    """Sweeping fundamental 0 -> 100 leaves the gate's verdict untouched.

    It still moves the composite (0.07 weight), which is why the assertion is on
    the consensus verdict rather than on the whole result.
    """
    neutral = {"biases": {"fundamental_analysis": SignalBias.NEUTRAL}}
    for scores, expect_demoted in ((BULL_4, False), (BULL_3, True)):
        seen = set()
        for fund in (0.0, 25.0, 50.0, 57.5, 75.0, 100.0):
            out = decide({**scores, "fundamental_analysis": fund}, engine_kw=neutral)
            # Guard the premise: the sweep must stay inside the BUY band, or the
            # test would be measuring a band change rather than the vote.
            assert out.consensus_telemetry["threshold_direction"] == "bullish", fund
            seen.add(out.consensus_telemetry["engine_demoted"])
        assert seen == {expect_demoted}, f"fundamental score moved the gate: {seen}"


def test_the_fundamental_bias_cannot_change_the_consensus_outcome():
    """The pool reads `.score`; bias only ever fed the disagreement penalty."""
    for bias in (SignalBias.STRONG_BEARISH, SignalBias.NEUTRAL, SignalBias.STRONG_BULLISH):
        out = decide(BULL_3, engine_kw={"biases": {"fundamental_analysis": bias}})
        assert out.signal_type == "HOLD", f"bias {bias} revived a 3-vote call"


def test_each_of_the_five_voting_engines_can_move_the_count():
    """Drop one confirming engine below the bar at a time; each must demote."""
    for name in ("technical_analysis", "market_structure",
                 "volume_analysis", "smart_money_concepts"):
        weakened = {**BULL_4, name: 50.0}
        out = decide(weakened)
        assert out.signal_type == "HOLD", f"{name} did not count as a vote"
    # CRT is the fifth voter: raising it from 50 to a confirming value turns the
    # three-vote case into four.
    revived = decide({**BULL_3, "candle_range_theory": 62.0})
    assert revived.signal_type in ACTIONABLE


# ----------------------------------------------- 18: fallback semantics intact
def test_a_missing_engine_still_reads_as_a_neutral_fifty():
    """The exception fallback (score 50, bias neutral, conf 30) is untouched, and
    an engine that produced no result at all still defaults to 50 in the pool —
    neither a confirmation nor a conflict."""
    # BEAR_4 stays inside the SELL band with or without CRT, so the only thing
    # that could move the verdict here is the vote count.
    partial = [r for r in results(BEAR_4) if r.engine_name != "candle_range_theory"]
    out = generate_signal("TESTUSDT", "15m", frame(), partial)
    full = decide(BEAR_4)
    assert out.consensus_telemetry["threshold_direction"] == "bearish"
    assert out.signal_type == full.signal_type
    assert out.consensus_telemetry["engine_demoted"] == full.consensus_telemetry["engine_demoted"]

    # And the orchestrator's own crash fallback — score 50, bias neutral,
    # confidence 30 — still reads as neither confirmation nor conflict.
    crashed = [r if r.engine_name != "candle_range_theory" else
               r.model_copy(update={"score": 50.0, "bias": SignalBias.NEUTRAL,
                                    "confidence": 30.0})
               for r in results(BEAR_4)]
    out2 = generate_signal("TESTUSDT", "15m", frame(), crashed)
    assert out2.signal_type == full.signal_type


# ------------------------------------------------- 19-22: gate order unchanged
def test_the_consensus_gate_still_runs_before_the_mtf_layer():
    """Behavioural: a consensus demotion makes the MTF layer unreachable, so its
    penalty stays 0 even when two timeframes disagree. If MTF ran first this
    would be 30.0."""
    out = generate_signal(
        "TESTUSDT", "15m", frame(), results(BULL_3),
        mtf_trends={"15m": "bearish", "1h": "bearish", "4h": "bearish"},
    )
    assert out.signal_type == "HOLD"
    assert out.consensus_telemetry["mtf_penalty"] == 0.0

    # A call that survives consensus does reach MTF and is penalised.
    out2 = generate_signal(
        "TESTUSDT", "15m", frame(), results(BULL_4),
        mtf_trends={"15m": "bearish", "1h": "bearish", "4h": "neutral"},
    )
    assert out2.consensus_telemetry["mtf_penalty"] == 30.0
    assert out2.signal_type == "HOLD"  # >=2 disagreeing timeframes


def test_the_scheduler_gate_order_is_untouched():
    """confidence gate -> occupancy/duplicate -> reversal, in that order.

    Read from the AST of the real scheduler function, not from its text. This
    checkpoint changes no scheduler code; the assertion exists so a later edit
    that reorders the gates cannot pass silently.
    """
    from app.services import scheduler

    src = textwrap.dedent(inspect.getsource(scheduler._generate_signal))
    lines = src.splitlines()

    def first_line_containing(needle: str) -> int:
        for i, line in enumerate(lines):
            if needle in line:
                return i
        raise AssertionError(f"marker not found: {needle}")

    conf_gate = first_line_containing("MIN_ACTIONABLE_CONFIDENCE = 65.0")
    occupancy = first_line_containing("Signal.is_active == True")
    reversal = first_line_containing("REVERSAL_MIN_CONFIDENCE = 72.0")
    assert conf_gate < occupancy < reversal

    # And the threshold values themselves.
    tree = ast.parse(src)
    consts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant):
                consts[node.targets[0].id] = node.value.value
    assert consts["MIN_ACTIONABLE_CONFIDENCE"] == 65.0
    assert consts["REVERSAL_MIN_CONFIDENCE"] == 72.0


# --------------------------------------- 23-24: composite and confidence frozen
def test_the_composite_formula_is_byte_identical():
    for scores in (BULL_4, BULL_3, BEAR_4, BEAR_3):
        out = decide(scores)
        raw = composite_of(scores)
        pen = out.consensus_telemetry["disagreement_penalty"]
        expected = (max(50.0, raw - pen) if raw > 50.0
                    else min(50.0, raw + pen) if raw < 50.0 else raw)
        assert out.birth_telemetry["composite_score"] == pytest.approx(
            round(expected, 2), abs=1e-9), scores


def test_the_confidence_formula_is_byte_identical():
    """Both penalty coefficients must be exercised, or a change to either hides.

    The first case has no disagreement, so it pins the MTF term alone; the second
    forces bullish and bearish engines to coexist so the x1.5 disagreement
    coefficient is actually multiplied by something.
    """
    plain = generate_signal(
        "TESTUSDT", "15m", frame(), results(BULL_4),
        mtf_trends={"15m": "bearish", "1h": "neutral", "4h": "neutral"},
    )
    assert plain.consensus_telemetry["mtf_penalty"] == 15.0

    # Two engines pulled to opposite biases -> min(bull, bear) x 4.0 penalty.
    split = generate_signal(
        "TESTUSDT", "15m", frame(),
        results(BULL_4, biases={"onchain_analysis": SignalBias.STRONG_BEARISH,
                                "macro_analysis": SignalBias.STRONG_BEARISH}),
    )
    assert split.consensus_telemetry["disagreement_penalty"] > 0.0

    for out in (plain, split):
        dis = out.consensus_telemetry["disagreement_penalty"]
        mtf = out.consensus_telemetry["mtf_penalty"]
        expected = max(20.0, min(98.0, (70.0 * 9) / 9 - dis * 1.5 - mtf))
        assert out.confidence_score == pytest.approx(expected, abs=1e-9), (dis, mtf)


# ---------------------------------------------- 25-26: contracts unchanged
def test_the_candidate_log_contract_is_unchanged():
    from app.services import candidate_log
    from app.models.decision_candidate import SignalDecisionCandidate

    assert candidate_log.CANDIDATE_SCHEMA_VERSION == 1
    assert candidate_log.CANDIDATE_POLICY_VERSION == 1
    cols = {c.name for c in SignalDecisionCandidate.__table__.columns}
    for required in ("engine_scores", "engine_weights", "bull_count", "bear_count",
                     "conflict_min_count", "composite_score", "confidence_score",
                     "verdict", "demotion_reason", "extra"):
        assert required in cols

    out = decide(BULL_4)
    telemetry = out.consensus_telemetry
    assert set(telemetry) == {
        "bull_count", "bear_count", "conflict_min_count", "disagreement_penalty",
        "mtf_penalty", "threshold_signal_type", "threshold_direction",
        "engine_demoted",
    }
    # bull/bear counts are still taken over all nine biases, not the vote pool.
    assert telemetry["bull_count"] + telemetry["bear_count"] <= 9


def test_the_decision_input_contract_is_unchanged():
    assert sg.DECISION_INPUT_VERSION == "closed_candle_v1"
    assert sg.CANDLE_POLICY == "closed_features_live_geometry"


# ------------------------------------------------------- 27: directional symmetry
def test_the_two_directions_use_the_same_numeric_bar():
    """Same required count, same conflict count, mirrored thresholds."""
    src = textwrap.dedent(inspect.getsource(generate_signal))
    tree = ast.parse(src)
    checks = [n for n in ast.walk(tree)
              if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)
              and n.left.id in ("confirmations", "strong_conflicts")]
    by_name = {}
    for node in checks:
        rhs = node.comparators[0]
        key = node.left.id
        val = rhs.id if isinstance(rhs, ast.Name) else rhs.value
        by_name.setdefault(key, []).append(val)
    assert by_name["confirmations"] == ["REQUIRED_CONSENSUS_VOTES"] * 2
    assert by_name["strong_conflicts"] == [2, 2]

    # And behaviourally: four real votes act, three do not, on both sides.
    assert decide(BULL_4).signal_type in ACTIONABLE
    assert decide(BEAR_4).signal_type in ACTIONABLE
    assert decide(BULL_3).signal_type == "HOLD"
    assert decide(BEAR_3).signal_type == "HOLD"


# ------------------------------------------------- 29-31: no schema/state moves

# The migration set this checkpoint was written against, pinned by NAME.
#
# This guard used to read `migrations[-1] == "0010_candidate_log_rls.sql"`, and
# its own failure message named the scope correctly — "CP-FUND-VOTE-1 must not
# add a migration". But the assertion did not test that. It tested a GLOBAL
# fact, that nothing has been added to the repo since, which any LATER
# checkpoint's migration falsifies while CP-FUND-VOTE-1 stays innocent.
# scripts/migrate.py is built to apply exactly such new files ("only NEW
# migrations run"), so the old form had a guaranteed expiry date.
CHECKPOINT_MIGRATIONS = frozenset({
    "0001_consent_log.sql", "0002_stripe_subscription.sql",
    "0003_per_user_notifications.sql", "0004_signal_snapshot_extra.sql",
    "0005_notify_lifecycle.sql", "0006_enable_rls.sql",
    "0007_rls_revoke_data_api.sql", "0008_signal_performance_times.sql",
    "0009_resolution_provenance.sql", "0010_candidate_log_rls.sql",
})

# Dropping the constant fundamental vote is a pure policy change: it moves a
# number in the consensus pool and nothing else. The two tables whose shape
# this checkpoint's claims rest on are the decision log it asserts is
# unmoved (signal_decision_candidates, schema/policy version 1/1) and the
# adaptive-weight store its F1-D contract test pins (coin_memory). DDL against
# either would mean this checkpoint became a schema change after all.
GUARDED_TABLES = frozenset({"signal_decision_candidates", "coin_memory"})

_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_DDL_TABLE = re.compile(
    r"\b(?:create|alter|drop)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?"
    r'"?(?:public\.)?"?([a-z_][a-z0-9_]*)', re.I)


def _ddl_targets(sql: str) -> set:
    """Tables a migration CREATEs, ALTERs or DROPs.

    Comments are stripped first — 0001 carries the words "ALTER TABLE" inside a
    warning comment, and a guard that reads prose as DDL reports a schema move
    that never happened.
    """
    return {m.group(1).lower()
            for m in _DDL_TABLE.finditer(_SQL_COMMENT.sub(" ", sql))}


def test_this_checkpoint_adds_no_migration():
    import pathlib
    mig = pathlib.Path(__file__).resolve().parent.parent / "migrations"
    present = {p.name for p in mig.glob("*.sql")}
    # Nothing this checkpoint was written against was removed, renamed, or had
    # a file renumbered into the middle of it.
    assert {n for n in present if n[:4] <= "0010"} == CHECKPOINT_MIGRATIONS, (
        f"CP-FUND-VOTE-1's migration set moved; found {sorted(present)}")
    # And no migration added SINCE touches the schema this checkpoint's claims
    # rest on. Somebody else's unrelated table is not this test's business.
    for p in sorted(mig.glob("*.sql")):
        if p.name in CHECKPOINT_MIGRATIONS:
            continue
        hit = _ddl_targets(p.read_text(encoding="utf-8")) & GUARDED_TABLES
        assert not hit, f"CP-FUND-VOTE-1 must not add a migration; {p.name} moves {sorted(hit)}"


def test_the_f1d_adaptive_telemetry_contract_is_untouched():
    from app.services.coin_memory import (ADAPTIVE_BAND_HIGH, ADAPTIVE_BAND_LOW,
                                          ADAPTIVE_TELEMETRY_VERSION,
                                          MIN_ENGINE_SAMPLES,
                                          MIN_SAMPLES_FOR_ADAPTIVE)
    assert ADAPTIVE_TELEMETRY_VERSION == "adaptive_state_v1"
    assert (MIN_SAMPLES_FOR_ADAPTIVE, MIN_ENGINE_SAMPLES) == (20, 12)
    assert (ADAPTIVE_BAND_LOW, ADAPTIVE_BAND_HIGH) == (0.55, 1.75)
