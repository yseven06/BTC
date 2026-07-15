"""CP-OBS-1A exposure telemetry: additive `exposure` block in extra.birth.

Telemetry ONLY — the decision path stays byte-identical and NOTHING reads the
block back (live guards are future shadow work). Mirrors test_a8_birth_telemetry.
"""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.engines.ai_decision.birth_telemetry import (
    EXPOSURE_TELEMETRY_VERSION, build_exposure_telemetry, exposure_unavailable,
)
from app.services.intelligence import _enrich_birth, build_snapshot


# ── 1 · PURE formatter ───────────────────────────────────────────────────────
def _counts(**over):
    base = dict(direction="BULLISH", active_long=39, active_short=1,
                same_timeframe_active=22, same_direction_same_timeframe_active=21,
                concurrent_coin_count=41, same_direction_stop_1h=3,
                same_direction_stop_3h=7)
    base.update(over)
    return base


def test_exposure_formatter_shape_and_derivations():
    e = build_exposure_telemetry(**_counts())
    assert e["version"] == EXPOSURE_TELEMETRY_VERSION
    assert e["active_total"] == 40 and e["active_long"] == 39 and e["active_short"] == 1
    assert e["long_share"] == 0.975 and e["short_share"] == 0.025      # 39/40, 1/40
    # BULLISH → same=long, opposite=short (the 07-15 16:00 cluster shape)
    assert e["same_direction_active"] == 39 and e["opposite_direction_active"] == 1
    assert e["same_direction_same_timeframe_active"] == 21
    assert e["concurrent_coin_count"] == 41
    assert e["same_direction_stop_1h"] == 3 and e["same_direction_stop_3h"] == 7
    assert e["same_regime_active"] is None                              # optional → null


def test_exposure_formatter_direction_semantics():
    short = build_exposure_telemetry(**_counts(direction="BEARISH"))
    assert short["same_direction_active"] == 1 and short["opposite_direction_active"] == 39
    # NEUTRAL/HOLD → side-less question is undefined, not zero
    neutral = build_exposure_telemetry(**_counts(direction="NEUTRAL"))
    assert neutral["same_direction_active"] is None
    assert neutral["opposite_direction_active"] is None
    assert neutral["active_total"] == 40                               # totals still meaningful
    # empty book → shares are undefined (no division by zero)
    empty = build_exposure_telemetry(**_counts(active_long=0, active_short=0))
    assert empty["active_total"] == 0 and empty["long_share"] is None


def test_exposure_optional_regime_fields():
    e = build_exposure_telemetry(**_counts(), same_regime_active=12,
                                 same_direction_same_regime_active=11)
    assert e["same_regime_active"] == 12 and e["same_direction_same_regime_active"] == 11


# ── 4 · Failure mode ─────────────────────────────────────────────────────────
def test_exposure_unavailable_marker():
    u = exposure_unavailable("OperationalError")
    assert u["unavailable"] is True and u["reason"] == "OperationalError"
    assert u["version"] == EXPOSURE_TELEMETRY_VERSION
    assert "active_total" not in u          # a failed probe is NOT a zero reading
    assert len(exposure_unavailable("x" * 500)["reason"]) <= 120   # bounded


def test_collect_exposure_failopen_returns_marker():
    """A probe that raises must yield the marker, never propagate (signal is born).

    `begin_nested()` is a SYNC call returning an async CM, so a sync mock that
    raises reproduces a savepoint/DB failure faithfully."""
    from app.services.scheduler import _collect_exposure
    db = AsyncMock()
    db.begin_nested = MagicMock(side_effect=RuntimeError("boom"))
    out = asyncio.run(_collect_exposure(db, direction="BULLISH", timeframe="M15",
                                        regime_label=None, now=pd.Timestamp.utcnow()))
    assert out["unavailable"] is True and out["reason"] == "RuntimeError"
    assert "active_total" not in out          # marker, not a zero reading


# ── 2/3 · Wiring + byte-identical decision ───────────────────────────────────
def test_enrich_birth_exposure_additive_and_independent():
    exp = build_exposure_telemetry(**_counts())
    w = {"technical_analysis": 0.5}

    out = _enrich_birth({"direction": "bullish"}, w, True, "trending_bull", exp)
    assert out["exposure"]["active_long"] == 39                # exposure landed
    assert out["engine_weights_used"] == w                     # A8-1 layer intact
    assert out["direction"] == "bullish"                       # originals kept

    # exposure alone must NOT fabricate A8-1 keys
    only = _enrich_birth({"x": 1}, None, None, None, exp)
    assert only["exposure"] == exp and "engine_weights_used" not in only

    # BYTE-IDENTICAL: every pre-CP call path is untouched
    assert _enrich_birth({"x": 1}, None, None, None) == {"x": 1}
    assert _enrich_birth(None, w, True, "r", exp) is None
    assert _enrich_birth({"x": 1}, w, False, "r") == {
        "x": 1, "engine_weights_used": w, "adaptive_active": False, "regime": "r"}


def test_build_snapshot_exposure_wiring_and_backward_compat():
    exp = build_exposure_telemetry(**_counts())
    decision = {"birth_telemetry": {"direction": "bullish"}, "engine_results": [],
                "confidence_score": 70.0, "probability_score": 60.0}

    snap = build_snapshot("sig-1", decision, pd.DataFrame(), regime=None,
                          engine_weights={"technical_analysis": 0.5},
                          adaptive_active=True, exposure=exp)
    assert snap.extra["birth"]["exposure"]["long_share"] == 0.975
    assert snap.extra["birth"]["adaptive_active"] is True      # A8-1 still wired

    # no exposure arg → byte-identical to the pre-CP snapshot
    snap2 = build_snapshot("sig-2", decision, pd.DataFrame(), regime=None)
    assert snap2.extra["birth"] == {"direction": "bullish"}

    # decision fields are NEVER touched by the telemetry layer
    assert snap.composite_confidence == 70.0 and snap.composite_probability == 60.0
    assert decision["birth_telemetry"] == {"direction": "bullish"}   # input unmutated


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} CP-OBS-1A exposure-telemetry tests PASSED")
