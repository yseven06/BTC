"""CP-OBS-ENGINE-ERR — a crashed engine must be distinguishable from a neutral one.

`_safe_run_engine` substitutes (50.0, NEUTRAL, 30.0) when an engine raises. The
candidate log persists only {score, bias, confidence} per engine, and that
(50.0, neutral) pair is exactly what macro_analysis returns on 100% of the 8098
logged candidates and risk_management on 90% of them. The sole separator was a
confidence value no query reads, and which engine failed — or why — was recorded
nowhere at all.

This is observation only. Every test that touches the decision asserts it did
not move.
"""
from __future__ import annotations

import asyncio
import json
import re

import numpy as np
import pandas as pd
import pytest

from app.engines.ai_decision import engine as ai_engine
from app.engines.ai_decision.engine import (ENGINE_EXECUTION_TELEMETRY_VERSION,
                                            ENGINE_FALLBACK_BIAS,
                                            ENGINE_FALLBACK_CONFIDENCE,
                                            ENGINE_FALLBACK_SCORE,
                                            AIDecisionEngine,
                                            build_engine_execution_telemetry)
from app.engines.base import SignalBias

NINE = [
    "technical_analysis", "market_structure", "smart_money_concepts",
    "candle_range_theory", "volume_analysis", "risk_management",
    "fundamental_analysis", "onchain_analysis", "macro_analysis",
]


def frame(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-07-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.full(n, 1000.0),
    }, index=idx)


class Exploding:
    """An engine that raises whatever it was handed."""

    def __init__(self, name: str, exc: BaseException | None = None):
        self.name = name
        self._exc = exc or RuntimeError("boom")

    async def analyze(self, *a, **kw):
        raise self._exc


class Healthy:
    def __init__(self, name: str, score=50.0, bias=SignalBias.NEUTRAL, confidence=30.0):
        self.name = name
        self._s, self._b, self._c = score, bias, confidence

    async def analyze(self, *a, **kw):
        from app.engines.base import EngineResult
        return EngineResult(engine_name=self.name, score=self._s, bias=self._b,
                            confidence=self._c, key_findings=[], supporting_data={})


async def run_engine(e, failures=None):
    return await AIDecisionEngine()._safe_run_engine(
        e, "BTCUSDT", "15m", frame(), failures=failures)


# ------------------------------------------------------- the summary itself
def test_a_clean_run_reports_no_failures():
    t = build_engine_execution_telemetry(9, [])
    assert t == {
        "version": ENGINE_EXECUTION_TELEMETRY_VERSION,
        "engine_count": 9,
        "successful_engine_count": 9,
        "failed_engine_count": 0,
        "failed_engines": [],
        "fallback_used": False,
    }


def test_the_counts_are_derived_not_hardcoded():
    t = build_engine_execution_telemetry(9, [{"engine": "a"}, {"engine": "b"}])
    assert (t["engine_count"], t["successful_engine_count"],
            t["failed_engine_count"], t["fallback_used"]) == (9, 7, 2, True)
    # A different fleet size must follow the fleet, not a constant.
    t5 = build_engine_execution_telemetry(5, [{"engine": "a"}])
    assert (t5["engine_count"], t5["successful_engine_count"]) == (5, 4)


def test_the_version_is_stamped():
    assert ENGINE_EXECUTION_TELEMETRY_VERSION == "engine_execution_v1"
    assert build_engine_execution_telemetry(9, [])["version"] == "engine_execution_v1"


# ------------------------------------------------------------ one failure
@pytest.mark.asyncio
async def test_one_crashing_engine_is_named_with_its_fallback():
    failures = []
    res = await run_engine(Exploding("technical_analysis", ValueError("bad input")), failures)

    assert len(failures) == 1
    f = failures[0]
    assert f["engine"] == "technical_analysis"
    assert f["error_type"] == "ValueError"
    assert f["fallback_score"] == ENGINE_FALLBACK_SCORE == 50.0
    assert f["fallback_bias"] == ENGINE_FALLBACK_BIAS.value == "neutral"
    assert f["fallback_confidence"] == ENGINE_FALLBACK_CONFIDENCE == 30.0
    # And the telemetry describes the result that was actually returned.
    assert (res.score, res.bias, res.confidence) == (
        ENGINE_FALLBACK_SCORE, ENGINE_FALLBACK_BIAS, ENGINE_FALLBACK_CONFIDENCE)

    t = build_engine_execution_telemetry(9, failures)
    assert t["failed_engine_count"] == 1
    assert t["successful_engine_count"] == 8
    assert t["fallback_used"] is True
    assert [x["engine"] for x in t["failed_engines"]] == ["technical_analysis"]


@pytest.mark.asyncio
async def test_several_crashing_engines_are_all_recorded():
    failures = []
    for name, exc in (("macro_analysis", KeyError("k")),
                      ("onchain_analysis", TimeoutError()),
                      ("volume_analysis", ZeroDivisionError())):
        await run_engine(Exploding(name, exc), failures)

    t = build_engine_execution_telemetry(9, failures)
    assert t["failed_engine_count"] == 3
    assert t["successful_engine_count"] == 6
    assert [x["engine"] for x in t["failed_engines"]] == [
        "macro_analysis", "onchain_analysis", "volume_analysis"]
    assert [x["error_type"] for x in t["failed_engines"]] == [
        "KeyError", "TimeoutError", "ZeroDivisionError"]


# --------------------------------------------- the distinction being bought
@pytest.mark.asyncio
async def test_a_genuinely_neutral_engine_is_not_marked_as_failed():
    """The exact triple production's healthy macro engine would produce if its
    confidence ever landed on 30 — score, bias and confidence all identical to
    the crash fallback. It must still not be counted as a failure."""
    failures = []
    res = await run_engine(
        Healthy("macro_analysis", score=50.0, bias=SignalBias.NEUTRAL, confidence=30.0),
        failures)

    assert (res.score, res.bias, res.confidence) == (50.0, SignalBias.NEUTRAL, 30.0)
    assert failures == []
    t = build_engine_execution_telemetry(9, failures)
    assert t["failed_engine_count"] == 0
    assert t["fallback_used"] is False


@pytest.mark.asyncio
async def test_the_two_are_indistinguishable_without_this_telemetry():
    """Pins the problem, so a future 'we can already tell' cannot go unchecked."""
    from app.services.candidate_log import _engine_scores

    crashed = await run_engine(Exploding("macro_analysis"), [])
    healthy = await run_engine(
        Healthy("macro_analysis", 50.0, SignalBias.NEUTRAL, 30.0), [])

    a = _engine_scores([crashed.model_dump()])
    b = _engine_scores([healthy.model_dump()])
    assert a == b, "if these ever differ, the premise of this checkpoint changed"
    # Only the new field separates them.
    ta = build_engine_execution_telemetry(9, [{"engine": "macro_analysis"}])
    tb = build_engine_execution_telemetry(9, [])
    assert ta["fallback_used"] != tb["fallback_used"]


# ------------------------------------------------------------- redaction
@pytest.mark.asyncio
async def test_no_message_traceback_or_credential_reaches_the_record():
    # Assembled at runtime rather than written out: a literal credential-shaped
    # string in a tracked file is something every future secret scan has to be
    # told to ignore, and the test proves exactly as much either way.
    scheme, user, pw, host, tok = "postgre" + "sql", "svc", "hunter2", "db.internal", "abcd1234"
    secret = f"{scheme}://{user}:{pw}@{host}:5432/prod?token={tok}"
    failures = []
    await run_engine(Exploding("onchain_analysis", RuntimeError(f"connect failed {secret}")),
                     failures)

    blob = json.dumps(build_engine_execution_telemetry(9, failures))
    for needle in (secret, pw, tok, scheme + "://", host,
                   "connect failed", "Traceback", "File \"", "line "):
        assert needle not in blob, f"leaked: {needle}"
    assert set(failures[0]) == {"engine", "error_type", "error_fingerprint",
                                "fallback_score", "fallback_bias", "fallback_confidence"}


@pytest.mark.asyncio
async def test_the_fingerprint_groups_by_failure_mode_not_by_message():
    """Same engine, same exception type, same raise site -> same fingerprint even
    when the message differs; a different engine or type -> different."""
    f1, f2, f3, f4 = [], [], [], []
    await run_engine(Exploding("macro_analysis", RuntimeError("first")), f1)
    await run_engine(Exploding("macro_analysis", RuntimeError("second, quite different")), f2)
    await run_engine(Exploding("macro_analysis", ValueError("first")), f3)
    await run_engine(Exploding("onchain_analysis", RuntimeError("first")), f4)

    assert f1[0]["error_fingerprint"] == f2[0]["error_fingerprint"]
    assert f1[0]["error_fingerprint"] != f3[0]["error_fingerprint"]
    assert f1[0]["error_fingerprint"] != f4[0]["error_fingerprint"]
    assert len(f1[0]["error_fingerprint"]) == 16
    assert all(c in "0123456789abcdef" for c in f1[0]["error_fingerprint"])


# ------------------------------------------------- fail-open and isolation
@pytest.mark.asyncio
async def test_a_telemetry_failure_cannot_break_the_decision():
    """A collector that raises on append must not change what the engine returns."""
    class Hostile(list):
        def append(self, item):
            raise MemoryError("no room")

    res = await run_engine(Exploding("macro_analysis"), Hostile())
    assert (res.score, res.bias, res.confidence) == (50.0, SignalBias.NEUTRAL, 30.0)
    assert res.warnings


def test_the_summary_builder_is_fail_open():
    assert ai_engine._engine_execution_or_none(9, []) == build_engine_execution_telemetry(9, [])
    # An input the builder cannot handle degrades to None, never raises.
    assert ai_engine._engine_execution_or_none("nine", []) is None


@pytest.mark.asyncio
async def test_two_concurrent_analyses_do_not_share_a_collector():
    a, b = [], []
    await asyncio.gather(
        run_engine(Exploding("macro_analysis"), a),
        run_engine(Exploding("onchain_analysis"), b),
    )
    assert [x["engine"] for x in a] == ["macro_analysis"]
    assert [x["engine"] for x in b] == ["onchain_analysis"]


@pytest.mark.asyncio
async def test_omitting_the_collector_changes_nothing_about_the_result():
    with_collector = await run_engine(Exploding("macro_analysis"), [])
    without = await run_engine(Exploding("macro_analysis"), None)
    assert with_collector.model_dump() == without.model_dump()


# --------------------------------------------------- the decision is frozen
@pytest.mark.asyncio
async def test_a_successful_run_records_nine_successes_and_nothing_else():
    eng = AIDecisionEngine()
    assert [e.name for e in eng.engines] == NINE
    failures = []
    results = await asyncio.gather(*[
        eng._safe_run_engine(e, "BTCUSDT", "15m", frame(), failures=failures)
        for e in eng.engines
    ])
    t = build_engine_execution_telemetry(len(eng.engines), failures)
    assert t["engine_count"] == 9
    assert t["failed_engine_count"] == 0, t["failed_engines"]
    assert t["successful_engine_count"] == 9
    assert t["fallback_used"] is False
    assert [r.engine_name for r in results] == NINE


@pytest.mark.asyncio
async def test_a_crashed_engine_is_still_one_of_the_nine_results():
    """Dropping a failed engine from engine_results would silently reweight the
    composite and shrink the consensus pool. It stays, at its neutral fallback.
    """
    eng = AIDecisionEngine()
    eng.engines = [Exploding("macro_analysis") if e.name == "macro_analysis" else e
                   for e in eng.engines]

    out = await eng.analyze_and_decide("BTCUSDT", "1h", frame(120),
                                       is_backtest=True, mtf_data={})

    names = [r["engine_name"] for r in out["engine_results"]]
    assert names == NINE, names
    macro = next(r for r in out["engine_results"] if r["engine_name"] == "macro_analysis")
    assert (macro["score"], macro["bias"], macro["confidence"]) == (50.0, "neutral", 30.0)

    t = out["engine_execution_telemetry"]
    assert t["engine_count"] == 9
    assert t["failed_engine_count"] == 1
    assert t["successful_engine_count"] == 8
    assert t["fallback_used"] is True
    assert t["failed_engines"][0]["engine"] == "macro_analysis"


@pytest.mark.asyncio
async def test_a_second_analysis_does_not_inherit_the_first_ones_failures():
    """The collector is per-call. Instance state would make every later symbol
    on the same orchestrator report the first one's outage as its own."""
    eng = AIDecisionEngine()
    eng.engines = [Exploding("macro_analysis") if e.name == "macro_analysis" else e
                   for e in eng.engines]

    first = await eng.analyze_and_decide("BTCUSDT", "1h", frame(120),
                                         is_backtest=True, mtf_data={})
    assert first["engine_execution_telemetry"]["failed_engine_count"] == 1

    # Same orchestrator, engines now healthy: the previous failure must be gone.
    eng.engines = AIDecisionEngine().engines
    second = await eng.analyze_and_decide("ETHUSDT", "1h", frame(120),
                                          is_backtest=True, mtf_data={})
    t = second["engine_execution_telemetry"]
    assert t["failed_engine_count"] == 0, t["failed_engines"]
    assert t["failed_engines"] == []
    assert t["fallback_used"] is False


def test_the_consensus_and_scoring_contracts_are_untouched():
    from app.engines.ai_decision.signal_generator import (BASE_ENGINE_WEIGHTS,
                                                          CONSENSUS_VOTE_ENGINES,
                                                          REQUIRED_CONSENSUS_VOTES,
                                                          DECISION_INPUT_VERSION)
    assert len(CONSENSUS_VOTE_ENGINES) == 5
    assert "fundamental_analysis" not in CONSENSUS_VOTE_ENGINES
    assert REQUIRED_CONSENSUS_VOTES == 4
    assert len(BASE_ENGINE_WEIGHTS) == 9
    assert sum(BASE_ENGINE_WEIGHTS.values()) == pytest.approx(1.0)
    assert DECISION_INPUT_VERSION == "closed_candle_v1"
    # The fallback numbers themselves are what make an outage neutral on every
    # consensus threshold. Changing them would change decisions.
    assert ENGINE_FALLBACK_SCORE == 50.0
    assert ENGINE_FALLBACK_BIAS is SignalBias.NEUTRAL
    assert ENGINE_FALLBACK_CONFIDENCE == 30.0
    assert not (ENGINE_FALLBACK_SCORE > 53 or ENGINE_FALLBACK_SCORE < 40)   # bullish
    assert not (ENGINE_FALLBACK_SCORE < 47 or ENGINE_FALLBACK_SCORE > 60)   # bearish


# ------------------------------------------------ the candidate extra merge
def _candidate_extra(decision_extra: dict) -> dict:
    """Run the real build_candidate_values and return the extra it produced."""
    from app.services.candidate_log import build_candidate_values
    from datetime import datetime, timezone

    decision = {
        "signal_type": "HOLD", "direction": "neutral",
        "confidence_score": 60.0, "probability_score": 50.0,
        "risk_score": 5.0, "risk_level": "medium",
        "entry_zone_low": None, "entry_zone_high": None, "stop_loss": None,
        "tp1": None, "tp2": None, "tp3": None,
        "birth_telemetry": {"composite_score": 50.0},
        "consensus_telemetry": {"bull_count": 0, "bear_count": 0,
                                "threshold_signal_type": "HOLD",
                                "threshold_direction": "neutral",
                                "engine_demoted": False},
        "decision_input_telemetry": {"decision_input_version": "closed_candle_v1"},
        "engine_results": [],
        **decision_extra,
    }
    vals = build_candidate_values(
        asset_id=None, symbol="BTCUSDT", timeframe="15m", decision=decision,
        df=frame(), evaluated_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        verdict="dropped", demotion_reason="not_actionable",
    )
    return vals["extra"]


def test_the_candidate_extra_carries_the_new_field():
    tel = build_engine_execution_telemetry(9, [{"engine": "macro_analysis",
                                                "error_type": "RuntimeError",
                                                "error_fingerprint": "0123456789abcdef",
                                                "fallback_score": 50.0,
                                                "fallback_bias": "neutral",
                                                "fallback_confidence": 30.0}])
    extra = _candidate_extra({"engine_execution_telemetry": tel})
    got = extra["engine_execution_telemetry"]
    assert got["version"] == "engine_execution_v1"
    assert got["failed_engine_count"] == 1
    assert got["failed_engines"][0]["engine"] == "macro_analysis"


def test_the_merge_is_additive_and_overwrites_nothing():
    before = _candidate_extra({})
    after = _candidate_extra(
        {"engine_execution_telemetry": build_engine_execution_telemetry(9, [])})

    # Every pre-existing key survives with its value intact.
    for k, v in before.items():
        if k == "engine_execution_telemetry":
            continue
        assert after[k] == v, k
    assert set(after) - set(before) == set()          # the key exists either way
    assert before["engine_execution_telemetry"] is None
    assert after["engine_execution_telemetry"] is not None
    # The F1-D contract in particular.
    assert "adaptive_state_telemetry" in after
    assert "primary_demotion_reason" in after
    assert after["decision_input_version"] == "closed_candle_v1"


def test_an_absent_summary_records_null_rather_than_a_guess():
    extra = _candidate_extra({})
    assert extra["engine_execution_telemetry"] is None


# -------------------------------------------------------------- guards

# The migration set this checkpoint was written against, pinned by NAME.
#
# This guard used to read `migrations[-1] == "0010_candidate_log_rls.sql"`. Its
# failure message scoped the claim correctly — "CP-OBS-ENGINE-ERR must not add
# a migration" — but the assertion tested a GLOBAL fact instead: that nothing
# has been added to the repo since. Any LATER checkpoint's migration falsifies
# that while this one stays innocent, and scripts/migrate.py exists to apply
# exactly such files ("only NEW migrations run").
CHECKPOINT_MIGRATIONS = frozenset({
    "0001_consent_log.sql", "0002_stripe_subscription.sql",
    "0003_per_user_notifications.sql", "0004_signal_snapshot_extra.sql",
    "0005_notify_lifecycle.sql", "0006_enable_rls.sql",
    "0007_rls_revoke_data_api.sql", "0008_signal_performance_times.sql",
    "0009_resolution_provenance.sql", "0010_candidate_log_rls.sql",
})

# This checkpoint's whole schema claim, stated in test_the_candidate_schema_
# did_not_move: the new telemetry rides in the candidate row's existing JSON
# `extra`, so `engine_execution_telemetry` is NOT a column. A migration that
# reaches the candidate table, or that names the field at all, is that promise
# broken.
GUARDED_TABLES = frozenset({"signal_decision_candidates"})
GUARDED_MARKER = "engine_execution_telemetry"

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
        f"CP-OBS-ENGINE-ERR's migration set moved; found {sorted(present)}")
    for p in sorted(mig.glob("*.sql")):
        sql = p.read_text(encoding="utf-8")
        # The field is never schema, in any migration, ever.
        assert GUARDED_MARKER not in sql.lower(), p.name
        if p.name in CHECKPOINT_MIGRATIONS:
            continue
        hit = _ddl_targets(sql) & GUARDED_TABLES
        assert not hit, (
            f"CP-OBS-ENGINE-ERR must not add a migration; {p.name} moves {sorted(hit)}")


def test_the_candidate_schema_did_not_move():
    from app.models.decision_candidate import (CANDIDATE_POLICY_VERSION,
                                               CANDIDATE_SCHEMA_VERSION,
                                               SignalDecisionCandidate)
    assert (CANDIDATE_SCHEMA_VERSION, CANDIDATE_POLICY_VERSION) == (1, 1)
    # The new field rides in the existing JSON column — no new column.
    cols = {c.name for c in SignalDecisionCandidate.__table__.columns}
    assert "engine_execution_telemetry" not in cols
    assert "extra" in cols
