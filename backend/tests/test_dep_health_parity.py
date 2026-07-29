"""CP-DEP-HEALTH-1 — the decision must be byte-identical before and after.

This file is the parity gate. It pins a deterministic grid of `generate_signal`
inputs to an expected-output digest and pins `build_candidate_values`' existing
`extra` keys, so any drift in the decision path — or any overwrite of an existing
telemetry key — fails here rather than in production.

The digest was frozen from HEAD `bd772ed`, BEFORE the dependency-health telemetry
existed. It is deliberately not recomputed by the test: a self-recomputing
baseline proves nothing.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from app.engines.ai_decision.signal_generator import generate_signal
from app.engines.base import EngineResult, SignalBias
from app.services import candidate_log

NINE = [
    "technical_analysis", "market_structure", "smart_money_concepts",
    "candle_range_theory", "volume_analysis", "risk_management",
    "fundamental_analysis", "onchain_analysis", "macro_analysis",
]

# The eight fields the checkpoint contract requires to stay identical.
PARITY_FIELDS = (
    "signal_type", "direction", "confidence_score", "composite_score",
    "disagreement_penalty", "mtf_penalty", "risk_score",
)

_BIAS_ORDER = [SignalBias.STRONG_BEARISH, SignalBias.BEARISH, SignalBias.NEUTRAL,
               SignalBias.BULLISH, SignalBias.STRONG_BULLISH]


def _frame(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-07-01", periods=n, freq="15min", tz="UTC")
    close = np.linspace(100.0, 104.0, n)
    return pd.DataFrame(
        {"open": close, "high": close * 1.004, "low": close * 0.996,
         "close": close, "volume": np.linspace(900.0, 1100.0, n)},
        index=idx,
    )


def _results(case: int) -> list[EngineResult]:
    """A deterministic, reproducible spread of engine outputs for `case`."""
    out = []
    for i, name in enumerate(NINE):
        score = float((case * 7 + i * 13) % 101)
        conf = 30.0 + float((case * 11 + i * 17) % 61)
        bias = _BIAS_ORDER[(case + i) % len(_BIAS_ORDER)]
        out.append(EngineResult(
            engine_name=name, score=score, bias=bias, confidence=conf,
            key_findings=[], supporting_data={"risk_score_raw": float(case % 11),
                                              "risk_level": "medium"},
        ))
    return out


_MTF_CASES = (
    None,
    {},
    {"15m": "neutral", "1h": "neutral", "4h": "neutral"},
    {"15m": "bearish", "1h": "neutral", "4h": "neutral"},
    {"15m": "bearish", "1h": "bearish", "4h": "neutral"},
    {"15m": "bearish", "1h": "bearish", "4h": "bearish"},
    {"15m": "bullish", "1h": "bullish", "4h": "bullish"},
    {"15m": "bullish", "1h": "bearish", "4h": "neutral"},
)

GRID_SIZE = 240


def _grid():
    df = _frame()
    for case in range(GRID_SIZE):
        mtf = _MTF_CASES[case % len(_MTF_CASES)]
        yield case, generate_signal(
            "TESTUSDT", ("15m", "1h", "4h", "1d")[case % 4], df,
            _results(case), mtf_trends=mtf, current_price=104.0,
        )


def _digest() -> str:
    h = hashlib.sha256()
    for case, out in _grid():
        row = {"case": case}
        for f in PARITY_FIELDS:
            v = getattr(out, f, None)
            if v is None:
                v = (out.consensus_telemetry or {}).get(f)
            if v is None:
                v = (out.birth_telemetry or {}).get(f)
            row[f] = round(float(v), 6) if isinstance(v, (int, float)) else v
        h.update(json.dumps(row, sort_keys=True, default=str).encode())
    return h.hexdigest()


# Frozen at bd772ed, before any dependency-health code existed.
FROZEN_DECISION_DIGEST = "47d50e6b0560a6c8c8534b97b6d2e3d726eebe91214e255d7d06f9e80ede21c0"


def test_decision_grid_digest_is_unchanged():
    assert _digest() == FROZEN_DECISION_DIGEST, (
        "the decision path changed — dependency-health telemetry must be "
        "purely additive and must not touch signal_type, direction, "
        "confidence_score, composite_score, disagreement_penalty, mtf_penalty "
        "or risk_score"
    )


# ── extra: every key that existed before must survive untouched ────────────
FROZEN_EXTRA_KEYS = {
    "primary_demotion_reason",
    "decision_input_version", "candle_policy", "current_price",
    "decision_current_price_source", "analysis_close_price",
    "last_analysis_bar_open_time", "last_analysis_bar_close_time",
    "last_analysis_bar_closed", "current_vs_analysis_close_pct",
    "current_vs_analysis_close_atr",
    "threshold_signal_type", "threshold_direction", "engine_demoted",
    "entry_frame_caveat", "adaptive_state_telemetry",
    "engine_execution_telemetry",
}


def _values(**over):
    out = generate_signal("TESTUSDT", "15m", _frame(), _results(3),
                          mtf_trends={"15m": "bearish", "1h": "bearish", "4h": "neutral"})
    decision = {
        "signal_type": out.signal_type, "direction": out.direction,
        "confidence_score": out.confidence_score,
        "probability_score": out.probability_score,
        "risk_score": out.risk_score, "risk_level": out.risk_level,
        "entry_zone_low": out.entry_zone_low, "entry_zone_high": out.entry_zone_high,
        "stop_loss": out.stop_loss, "tp1": out.tp1, "tp2": out.tp2, "tp3": out.tp3,
        "birth_telemetry": out.birth_telemetry,
        "consensus_telemetry": out.consensus_telemetry,
        "decision_input_telemetry": {"decision_input_version": "closed_candle_v1"},
        "engine_results": _results(3),
        "mtf_trends": {"15m": "bearish", "1h": "bearish", "4h": "neutral"},
        "engine_execution_telemetry": {"version": "engine_execution_v1"},
    }
    decision.update(over.pop("decision", {}))
    return candidate_log.build_candidate_values(
        asset_id="a" * 8, symbol="TESTUSDT", timeframe="15m", decision=decision,
        df=_frame(), evaluated_at=pd.Timestamp("2026-07-29T12:00:00Z").to_pydatetime(),
        verdict="dropped", demotion_reason="not_actionable",
        primary_demotion_reason="not_actionable", **over)


def test_every_pre_existing_extra_key_still_exists():
    extra = _values()["extra"]
    missing = FROZEN_EXTRA_KEYS - set(extra)
    assert not missing, f"dependency-health telemetry removed keys: {sorted(missing)}"


def test_pre_existing_extra_values_are_untouched():
    """The new namespace must not overwrite or reshape anything already there."""
    extra = _values()["extra"]
    assert extra["primary_demotion_reason"] == "not_actionable"
    assert extra["decision_input_version"] == "closed_candle_v1"
    assert extra["engine_execution_telemetry"] == {"version": "engine_execution_v1"}
    assert extra["entry_frame_caveat"] == "reading_a_midpoint; birth-candle not re-appended"


def test_the_candidate_row_column_set_is_unchanged():
    """No new column may appear — the checkpoint forbids migrations."""
    cols = set(_values())
    assert "dependency_health_v1" not in cols, "must live inside extra, not as a column"
    assert "dependency_health" not in cols
