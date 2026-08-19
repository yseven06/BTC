"""P2.2-a: candidate decision observability + shadow evaluation.

The twelve checks the sprint requires, in order. Each names the failure it
prevents rather than the code it touches.

Every test here is a pure unit test against fakes — no DB, no network, no
scheduler. That is deliberate: the repo has no conftest.py and no CI gate, so
nothing structurally stops a test from opening a connection, and a telemetry
suite is the last place that should be the first to try.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from sqlalchemy.dialects import postgresql

from app.models.decision_candidate import (
    CANDIDATE_POLICY_VERSION,
    CANDIDATE_SCHEMA_VERSION,
    REASON_CONFIDENCE_GATE,
    REASON_DUPLICATE_OR_EXISTING,
    REASON_NOT_ACTIONABLE,
    REASON_PUBLISHED,
    REASON_REVERSAL_DEFER,
    SHADOW_NO_FILL,
    SHADOW_STOP,
    SHADOW_TP1,
    SHADOW_UNDECIDABLE,
    SIMILARITY_UNAVAILABLE,
    SOURCE_SCHEDULER,
    VERDICT_DROPPED,
    VERDICT_PUBLISHED,
    VERDICT_SKIPPED,
    SignalDecisionCandidate,
)
from app.services import candidate_log
from app.services.shadow_eval import evaluate_candidate_shadow

BAR = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
NOW = BAR + timedelta(minutes=2)
ASSET = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SIG = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ROW = "cccccccc-cccc-cccc-cccc-cccccccccccc"

ENTRY_LOW, ENTRY_HIGH = 99.0, 101.0     # midpoint 100.0
SL, TP1, TP2, TP3 = 97.0, 101.5, 103.0, 105.0


# ── fixtures / doubles ──────────────────────────────────────────────────────
def _df(rows=None, start=BAR, freq="15min"):
    """OHLCV frame whose LAST bar is the scored bar (index[-1] == start)."""
    rows = rows or [(100.0, 100.5, 99.5, 100.0)]
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def _decision(**over):
    d = dict(
        symbol="BTCUSDT", timeframe="15m", signal_type="BUY", direction="bullish",
        confidence_score=71.5, probability_score=63.2, risk_score=5.0, risk_level="medium",
        entry_zone_low=ENTRY_LOW, entry_zone_high=ENTRY_HIGH, stop_loss=SL,
        tp1=TP1, tp2=TP2, tp3=TP3, invalidation_conditions="",
        birth_telemetry={"composite_score": 58.4, "atr_pct": 0.91},
        consensus_telemetry={
            "bull_count": 4, "bear_count": 1, "conflict_min_count": 1,
            "disagreement_penalty": 4.0, "mtf_penalty": 0.0,
            "threshold_signal_type": "BUY", "threshold_direction": "bullish",
            "engine_demoted": False,
        },
        engine_results=[
            {"engine_name": "technical_analysis", "score": 61.0, "bias": "bullish", "confidence": 80.0},
            {"engine_name": "volume_analysis", "score": 55.0, "bias": "neutral", "confidence": 65.0,
             "supporting_data": {"volume_trend_ratio": 1.23}},
        ],
        explanation_tr="", explanation_en="", generated_at=BAR.isoformat(),
        mtf_trends={"15m": "bullish"},
    )
    d.update(over)
    return d


def _regime():
    return NS(atr_pct=0.5, atr_pct_median=0.4, volume_ratio=1.1, adx=24.0, trend_direction="up")


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _db(insert_result=ROW):
    """Async-session double whose begin_nested() is a working async CM."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(insert_result))
    nested = AsyncMock()
    nested.__aenter__ = AsyncMock(return_value=nested)
    nested.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested)
    db.add = MagicMock()
    return db


def _kw(**over):
    kw = dict(
        asset_id=ASSET, symbol="BTCUSDT", timeframe="15m",
        decision=_decision(), df=_df(), evaluated_at=NOW,
        verdict=VERDICT_DROPPED, demotion_reason=REASON_NOT_ACTIONABLE,
        final_signal_type="HOLD", final_direction="neutral",
        regime_label="trending_bull", regime_result=_regime(),
        engine_weights={"technical_analysis": 0.17}, adaptive_active=True,
        last_close=100.0,
    )
    kw.update(over)
    return kw


# ── T1 · published candidate is recorded ────────────────────────────────────
@pytest.mark.asyncio
async def test_t1_published_candidate_is_recorded():
    db = _db()
    wrote = await candidate_log.record_candidate(
        db, **_kw(verdict=VERDICT_PUBLISHED, demotion_reason=REASON_PUBLISHED,
                  final_signal_type="BUY", final_direction="bullish", signal_id=SIG))
    assert wrote is True
    # One INSERT. The lineage resolver (CP-J) adds a SELECT to this path, so the
    # claim worth guarding is "exactly one write", not "exactly one statement".
    inserted = [c.args[0] for c in db.execute.await_args_list
                if "INSERT" in str(c.args[0]).upper()[:80]]
    assert len(inserted) == 1, f"expected 1 INSERT, saw {len(inserted)}"

    values = candidate_log.build_candidate_values(
        **_kw(verdict=VERDICT_PUBLISHED, demotion_reason=REASON_PUBLISHED,
              final_signal_type="BUY", final_direction="bullish", signal_id=SIG))
    assert values["verdict"] == VERDICT_PUBLISHED
    assert values["signal_id"] == SIG
    assert values["composite_score"] == 58.4
    assert values["composite_score_source"] == "birth_telemetry"
    # The two atr/volume families must land in separate columns — collapsing them
    # would silently mix incomparable measurements.
    assert values["atr_pct_regime"] == 0.5
    assert values["atr_pct_geometry"] == 0.91
    assert values["volume_ratio_regime"] == 1.1
    assert values["volume_ratio_geometry"] == 1.23


# ── T2 · rejected / HOLD candidate is recorded, with its reason ─────────────
@pytest.mark.asyncio
async def test_t2_rejected_candidate_is_recorded_with_reason():
    for reason in (REASON_NOT_ACTIONABLE, REASON_CONFIDENCE_GATE,
                   REASON_REVERSAL_DEFER, REASON_DUPLICATE_OR_EXISTING):
        values = candidate_log.build_candidate_values(**_kw(demotion_reason=reason))
        assert values["demotion_reason"] == reason
        assert values["signal_id"] is None, "a rejected candidate has no signal"
        # The trade idea the engines proposed must survive even though it was
        # never published — that is the whole point of the table.
        assert values["entry_zone_low"] == ENTRY_LOW
        assert values["stop_loss"] == SL
        assert values["engine_signal_type"] == "BUY"
        assert values["final_signal_type"] == "HOLD"


# ── T3 · a re-evaluation of the same bar does not duplicate ────────────────
def test_t3_statement_is_on_conflict_do_nothing_on_the_evaluation_key():
    captured = {}

    async def _execute(stmt, *a, **kw):
        captured["stmt"] = stmt
        return _Result(ROW)

    db = _db()
    db.execute = _execute
    import asyncio
    asyncio.run(candidate_log.record_candidate(db, **_kw()))
    sql = str(captured["stmt"].compile(dialect=postgresql.dialect()))

    assert "INSERT INTO signal_decision_candidates" in sql
    assert "ON CONFLICT (asset_id, timeframe, evaluated_bar_time, policy_version, source) DO NOTHING" in sql
    # DO NOTHING, never DO UPDATE: the row is immutable birth telemetry and a
    # retry must not rewrite history.
    assert "DO UPDATE" not in sql


def test_t3b_key_is_the_scored_bar_not_wall_clock():
    """Wall clock cannot identify an evaluation: a retry, a misfire replay and an
    admin trigger_job_now all produce a different `now` for the same bar."""
    a = candidate_log.build_candidate_values(**_kw(evaluated_at=NOW))
    b = candidate_log.build_candidate_values(**_kw(evaluated_at=NOW + timedelta(minutes=37)))
    assert a["evaluated_bar_time"] == b["evaluated_bar_time"] == BAR
    assert a["evaluated_at"] != b["evaluated_at"]


# ── T4 · shadow policy flags ───────────────────────────────────────────────
def test_t4_shadow_policy_flags_are_computed_from_the_recorded_primitives():
    """The sprint's shadow gates must be derivable from stored columns alone —
    if they need a value that was never captured, the table is the wrong shape."""
    v = candidate_log.build_candidate_values(**_kw())

    current_policy_pass = v["final_signal_type"] not in (None, "HOLD")
    confidence_75_pass = (v["confidence_score"] or 0) >= 75.0
    no_disagreement_pass = (v["conflict_min_count"] or 0) == 0
    composite_62_pass = (v["composite_score"] or 0) >= 62.0
    ranging_extreme_gate_pass = v["regime"] != "ranging"

    assert current_policy_pass is False        # this fixture was demoted to HOLD
    assert confidence_75_pass is False         # 71.5
    assert no_disagreement_pass is False       # conflict_min_count == 1
    assert composite_62_pass is False          # 58.4
    assert ranging_extreme_gate_pass is True   # trending_bull

    high = candidate_log.build_candidate_values(**_kw(
        decision=_decision(confidence_score=76.4,
                           birth_telemetry={"composite_score": 64.1, "atr_pct": 0.9},
                           consensus_telemetry={"bull_count": 5, "bear_count": 0,
                                                "conflict_min_count": 0,
                                                "disagreement_penalty": 0.0, "mtf_penalty": 0.0})))
    assert (high["confidence_score"] >= 75.0) is True
    assert (high["conflict_min_count"] == 0) is True
    assert (high["composite_score"] >= 62.0) is True


def test_t4b_disagreement_count_is_not_a_column():
    """Three defensible readings, three different integers. The primitives are
    stored instead so any definition stays derivable and none is baked in."""
    cols = set(SignalDecisionCandidate.__table__.columns.keys())
    assert "disagreement_count" not in cols
    assert {"conflict_min_count", "bull_count", "bear_count", "disagreement_penalty"} <= cols


# ── T5 · policy_version is recorded ────────────────────────────────────────
def test_t5_policy_version_is_recorded_and_in_the_key():
    v = candidate_log.build_candidate_values(**_kw())
    assert v["policy_version"] == CANDIDATE_POLICY_VERSION
    assert v["schema_version"] == CANDIDATE_SCHEMA_VERSION

    uq = [c for c in SignalDecisionCandidate.__table__.constraints
          if c.__class__.__name__ == "UniqueConstraint"]
    assert len(uq) == 1
    assert list(uq[0].columns.keys()) == [
        "asset_id", "timeframe", "evaluated_bar_time", "policy_version", "source"]

    col = SignalDecisionCandidate.__table__.c.policy_version
    assert col.nullable is False, "an unversioned row cannot be compared to anything"


# ── T6 · never entered, then price reached the stop ────────────────────────
def test_t6_setup_that_never_filled_is_never_entered_not_a_loss():
    """A short whose entry is far ABOVE price: the market walks away downward,
    never trades up into the zone, and the stop is never armed. Booking that as a
    stop would charge a loss to a trade nobody took."""
    bars = [(90.0, 90.5, 89.0, 89.2)] + [(89.0, 89.2, 87.0, 87.5) for _ in range(6)]
    df = _df([(100.0, 100.2, 99.8, 100.0)] + bars)

    out = evaluate_candidate_shadow(
        direction="bearish", entry_zone_low=119.0, entry_zone_high=121.0,
        stop_loss=123.0, tp1=115.0, tp2=112.0, tp3=110.0, df=df, bar_time=BAR)

    assert out["shadow_never_entered"] is True
    assert out["shadow_outcome"] == SHADOW_NO_FILL
    assert out["shadow_resolution_path"] == "no_fill"
    assert out["shadow_outcome"] != SHADOW_STOP
    # No walk may have been run — a return would mean a position was opened.
    assert out["shadow_return_pct"] is None
    assert out["shadow_bars_walked"] == 0


# ── T7 · entered, then stopped — a real stop ───────────────────────────────
def test_t7_entry_then_stop_is_a_real_stop():
    bars = [
        (100.0, 100.2, 99.8, 100.0),   # dips to the 100.0 midpoint → filled
        (99.8, 100.0, 96.5, 97.0),     # blows through SL 97.0
    ]
    df = _df([(101.0, 101.2, 100.8, 101.0)] + bars)

    out = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=ENTRY_LOW, entry_zone_high=ENTRY_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3, df=df, bar_time=BAR)

    assert out["shadow_never_entered"] is False
    assert out["shadow_entry_reached"] is True
    assert out["shadow_outcome"] == SHADOW_STOP
    assert out["shadow_return_pct"] < 0
    # Stopped from a full position = −1R by definition.
    assert out["shadow_r_multiple"] == pytest.approx(-1.0, abs=0.02)


# ── T8 · R after a TP1 break-even uses the ORIGINAL risk distance ──────────
def test_t8_r_multiple_uses_original_risk_not_the_breakeven_stop():
    """P2.1 hit this directly: once TP1 banks, the effective stop moves to entry,
    so a distance-to-effective-stop denominator is ZERO and every TP1-banked
    winner silently drops out of the R average — biasing measured expectancy down
    by ~0.11R. The denominator must stay the original entry→SL distance."""
    bars = [
        (100.0, 100.2, 99.8, 100.0),   # fill at 100.0
        (100.0, 101.8, 99.9, 101.6),   # TP1 101.5 banked
        (101.6, 101.7, 99.9, 100.1),   # drifts back to ~breakeven
    ]
    df = _df([(101.0, 101.2, 100.8, 101.0)] + bars)

    out = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=ENTRY_LOW, entry_zone_high=ENTRY_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3, df=df, bar_time=BAR)

    assert out["shadow_outcome"] == SHADOW_TP1
    assert out["shadow_r_multiple"] is not None, "R must never be undefined after a TP1 bank"

    # The denominator is |100.0 - 97.0| / 100.0 * 100 = 3.0 %, not 0.
    assert out["shadow_r_multiple"] == pytest.approx(out["shadow_return_pct"] / 3.0, abs=1e-3)


# ── T9 · scheduler retry idempotency ───────────────────────────────────────
@pytest.mark.asyncio
async def test_t9_retry_of_the_same_evaluation_writes_nothing_the_second_time():
    first = _db(insert_result=ROW)
    assert await candidate_log.record_candidate(first, **_kw()) is True

    # The DB resolved the conflict: RETURNING came back empty.
    retry = _db(insert_result=None)
    assert await candidate_log.record_candidate(retry, **_kw()) is False
    retry.add.assert_not_called()


@pytest.mark.asyncio
async def test_t9b_insert_runs_inside_a_savepoint():
    """Without a SAVEPOINT a constraint error aborts the caller's transaction —
    which may be holding a staged reversal close (the old signal's INVALIDATED
    outcome, its coin-memory fold, its lifecycle event). Fail-open would become
    fail-closed for the whole scan."""
    db = _db()
    await candidate_log.record_candidate(db, **_kw())
    db.begin_nested.assert_called_once()


@pytest.mark.asyncio
async def test_t9c_a_broken_write_never_escapes_to_the_caller():
    db = _db()
    db.execute = AsyncMock(side_effect=RuntimeError("db exploded"))
    assert await candidate_log.record_candidate(db, **_kw()) is False   # must not raise


@pytest.mark.asyncio
async def test_t9d_empty_frame_writes_no_unkeyed_row():
    empty = pd.DataFrame(columns=["open", "high", "low", "close"])
    db = _db()
    assert await candidate_log.record_candidate(db, **_kw(df=empty)) is False
    db.execute.assert_not_awaited()


# ── T10 · secret redaction ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t10_logs_carry_no_secret_and_no_full_row(caplog):
    db = _db()
    with caplog.at_level("DEBUG", logger="app.services.candidate_log"):
        await candidate_log.record_candidate(db, **_kw())

    text = caplog.text
    for forbidden in ("postgresql", "postgres.", "password", "@aws-", "pooler.supabase.com",
                      "DATABASE_URL", "JWT_SECRET"):
        assert forbidden not in text, f"log leaked {forbidden!r}"
    # Summary only — never the assembled row.
    assert "engine_scores" not in text and "entry_zone_low" not in text


@pytest.mark.asyncio
async def test_t10b_failure_log_does_not_echo_the_payload(caplog):
    db = _db()
    db.execute = AsyncMock(side_effect=RuntimeError("connection to server at 10.0.0.1 failed"))
    with caplog.at_level("WARNING", logger="app.services.candidate_log"):
        await candidate_log.record_candidate(db, **_kw())
    assert "fail-open" in caplog.text
    assert "entry_zone_low" not in caplog.text


# ── T11 · signal generation behaviour is byte-identical ────────────────────
def test_t11_consensus_export_is_output_only_and_changes_no_decision():
    """The Stage-F export added fields to GeneratedSignalData. If any branch had
    started reading them, the published verdict could move — which is the one
    thing this sprint may not do."""
    import inspect

    from app.engines.ai_decision import signal_generator as sg

    src = inspect.getsource(sg.generate_signal)
    # The new locals may only ever be WRITTEN before the return payload is built.
    assert "threshold_signal_type = signal_type" in src
    for banned in ("if threshold_signal_type", "if consensus_telemetry",
                   "elif threshold_signal_type", "while consensus_telemetry"):
        assert banned not in src, f"a branch reads telemetry: {banned!r}"

    # The thresholds and the disagreement coefficient are untouched.
    assert "composite_score >= 68.0" in src
    assert "composite_score >= 54.0" in src
    assert "composite_score >= 46.0" in src
    assert "composite_score >= 32.0" in src
    assert "min(bullish_count, bearish_count) * 4.0" in src


def test_t11b_candidate_hooks_are_fire_and_forget_in_the_scheduler():
    import inspect

    from app.services import scheduler

    src = inspect.getsource(scheduler._generate_signal)
    assert src.count("await record_candidate(") == 3, "all three terminal exits must be instrumented"
    # Never assigned, never branched on — the verdict is final before each call.
    for banned in ("= await record_candidate", "if await record_candidate",
                   "if record_candidate", "not await record_candidate"):
        assert banned not in src, f"the hook's result is consumed: {banned!r}"

    # The gates themselves are unchanged.
    assert "MIN_ACTIONABLE_CONFIDENCE = 65.0" in src
    assert "REVERSAL_MIN_CONFIDENCE = 72.0" in src


def test_t11c_every_demotion_cause_stays_distinguishable():
    import inspect

    from app.services import scheduler

    src = inspect.getsource(scheduler._generate_signal)
    for reason in ("REASON_CONFIDENCE_GATE", "REASON_REVERSAL_DEFER",
                   "REASON_NOT_ACTIONABLE", "REASON_DUPLICATE_OR_EXISTING"):
        assert reason in src, f"{reason} is never assigned — its cause would be unrecoverable"


# ── T12 · undecidable is never imputed as a result ────────────────────────
def test_t12_no_post_bars_is_undecidable_not_a_no_fill():
    """Absence of evidence is not evidence of absence: with no bars after the
    scored one, "did it fill?" has no answer and must not be recorded as "no"."""
    out = evaluate_candidate_shadow(
        direction="bullish", entry_zone_low=ENTRY_LOW, entry_zone_high=ENTRY_HIGH,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3, df=_df(), bar_time=BAR)

    assert out["shadow_outcome"] == SHADOW_UNDECIDABLE
    assert out["shadow_never_entered"] is None
    assert out["shadow_resolution_reason"] == "no_post_bars"


def test_t12b_similarity_is_labelled_absent_not_invented():
    v = candidate_log.build_candidate_values(**_kw())
    assert v["similarity_score"] is None
    assert v["similarity_status"] == SIMILARITY_UNAVAILABLE


def test_t12c_unserialisable_values_are_normalised_not_dropped():
    """Engine payloads carry numpy scalars, timestamps and NaN. Any of them raises
    on serialisation, and a raise here would cost the whole row."""
    import numpy as np

    safe = candidate_log._json_safe({
        "np": np.float64(1.5), "nan": float("nan"), "inf": float("inf"),
        "ts": BAR, "nested": {"list": [np.int64(3), "x"]},
    })
    assert safe["np"] == 1.5
    assert safe["nan"] is None and safe["inf"] is None
    assert safe["ts"] == BAR.isoformat()
    assert safe["nested"]["list"] == [3, "x"]

    import json
    json.dumps(safe)   # must not raise
