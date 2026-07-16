"""A8-1 adaptive birth telemetry: additive `engine_weights_used` + `adaptive_active`
in extra.birth. Telemetry ONLY — weights/decisions stay byte-identical."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from app.services.coin_memory import (
    adaptive_is_active, load_effective_weights, load_effective_weights_meta,
)
from app.services.intelligence import _enrich_birth


def _db_returning(mem):
    db = AsyncMock()
    result = NS(scalar_one_or_none=lambda: mem)

    async def ex(*a, **k):
        return result
    db.execute = ex
    return db


def _learned_stats():
    """engine_stats that recompute to a non-None adaptive model. F0-L2: the decision
    derives the model from THIS, not from a stored adaptive_weights column, so the
    fixtures below carry engine_stats instead of planting weights."""
    return {"technical_analysis": {"correct": 10, "total": 14},
            "market_structure": {"correct": 5, "total": 14}}


def test_adaptive_is_active_gate():
    # F0-L2: the flag is keyed off engine_stats (recomputed) like the decision, not
    # off the cached adaptive_weights column.
    assert adaptive_is_active(None) is False
    assert adaptive_is_active(NS(total_signals=25, engine_stats=_learned_stats())) is True
    assert adaptive_is_active(NS(total_signals=10, engine_stats=_learned_stats())) is False  # < 20
    assert adaptive_is_active(NS(total_signals=25, engine_stats={})) is False           # no feature
    assert adaptive_is_active(  # feature present but no engine over MIN_ENGINE_SAMPLES
        NS(total_signals=25, engine_stats={"technical_analysis": {"correct": 2, "total": 3}})
    ) is False


def test_meta_weights_byte_identical():
    """load_effective_weights_meta must return weights byte-identical to
    load_effective_weights (same get_effective_weights call) + the correct flag."""
    mem = NS(total_signals=25, engine_stats=_learned_stats())
    w1 = asyncio.run(load_effective_weights(_db_returning(mem), "BTC", "4h", "ranging"))
    w2, active = asyncio.run(load_effective_weights_meta(_db_returning(mem), "BTC", "4h", "ranging"))
    assert w1 == w2 and active is True

    mem2 = NS(total_signals=5, engine_stats={})
    w3, active3 = asyncio.run(load_effective_weights_meta(_db_returning(mem2), "BTC", "4h", "ranging"))
    w3b = asyncio.run(load_effective_weights(_db_returning(mem2), "BTC", "4h", "ranging"))
    assert w3 == w3b and active3 is False

    w4, active4 = asyncio.run(load_effective_weights_meta(_db_returning(None), "BTC", "4h", None))
    w4b = asyncio.run(load_effective_weights(_db_returning(None), "BTC", "4h", None))
    assert w4 == w4b and active4 is False   # no memory → base weights, inactive


def test_enrich_birth_additive_and_safe():
    w = {"technical_analysis": 0.5}
    out = _enrich_birth({"direction": "bullish"}, w, True, "trending_bull")
    assert out["engine_weights_used"] == w and out["adaptive_active"] is True
    assert out["regime"] == "trending_bull" and out["direction"] == "bullish"   # originals kept
    assert _enrich_birth(None, w, True, "r") is None                 # birth None → unchanged
    assert _enrich_birth({"x": 1}, None, None, None) == {"x": 1}     # no inputs → unchanged
    assert _enrich_birth({"x": 1}, w, False, "r")["adaptive_active"] is False


def test_build_snapshot_birth_wiring():
    import pandas as pd
    from app.services.intelligence import build_snapshot
    decision = {"birth_telemetry": {"direction": "bullish"}, "engine_results": [],
                "confidence_score": 70.0, "probability_score": 60.0}
    snap = build_snapshot("sig-1", decision, pd.DataFrame(), regime=None,
                          engine_weights={"technical_analysis": 0.5}, adaptive_active=True)
    birth = snap.extra["birth"]
    assert birth["engine_weights_used"] == {"technical_analysis": 0.5}
    assert birth["adaptive_active"] is True and "direction" in birth

    # backward-compat: no A8-1 args → birth unchanged (existing behavior)
    snap2 = build_snapshot("sig-2", decision, pd.DataFrame(), regime=None)
    assert snap2.extra["birth"] == {"direction": "bullish"}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} A8-1 birth-telemetry tests PASSED")
