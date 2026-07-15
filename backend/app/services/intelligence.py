"""
Adaptive Signal Intelligence — service layer.

Builds the SignalSnapshot for a freshly-generated signal and (later phases)
updates CoinMemory when signals resolve. Kept separate from the scheduler so
the signal-generation flow stays readable and this logic is unit-testable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

from app.engines.market_regime import RegimeResult, detect_regime
from app.models.intelligence import SignalSnapshot

logger = logging.getLogger(__name__)


def _extract_engine_scores(engine_results: list[dict]) -> Dict[str, Dict[str, Any]]:
    """Condense the verbose engine_results list into a compact per-engine map
    of just the numbers we need for later outcome attribution."""
    out: Dict[str, Dict[str, Any]] = {}
    for res in engine_results or []:
        name = res.get("engine_name")
        if not name:
            continue
        out[name] = {
            "score": round(float(res.get("score", 50.0)), 2),
            "bias": res.get("bias"),
            "confidence": round(float(res.get("confidence", 0.0)), 2),
        }
    return out


def _find_engine(engine_results: list[dict], name: str) -> Optional[dict]:
    for res in engine_results or []:
        if res.get("engine_name") == name:
            return res
    return None


def build_snapshot(
    signal_id,
    decision: Dict[str, Any],
    df: pd.DataFrame,
    regime: Optional[RegimeResult] = None,
    engine_weights: Optional[Dict[str, float]] = None,
    adaptive_active: Optional[bool] = None,
    exposure: Optional[Dict[str, Any]] = None,
) -> SignalSnapshot:
    """Construct (but do not persist) a SignalSnapshot from the decision payload.

    The caller (scheduler) adds it to the session in the same transaction as
    the Signal so the two are always written together.

    Args:
        signal_id: PK of the just-flushed Signal row.
        decision: The AIDecisionEngine payload.
        df: The OHLCV frame the signal was computed from.
        regime: Pre-computed regime (so the scheduler can compute it once and
            reuse it). If None, it is computed here.
    """
    engine_results = decision.get("engine_results", []) or []
    engine_scores = _extract_engine_scores(engine_results)

    if regime is None:
        try:
            regime = detect_regime(df)
        except Exception as exc:  # never let snapshot break signal flow
            logger.warning("[Intelligence] regime detection failed: %s", exc)
            regime = None

    # Sentiment / positioning context lives in the onchain engine's output.
    onchain = _find_engine(engine_results, "onchain_analysis") or {}
    onchain_sd = onchain.get("supporting_data", {}) or {}
    fear_greed = onchain_sd.get("fear_greed_value")
    ath_distance = onchain_sd.get("ath_distance_pct")

    volatility_ratio = None
    atr_pct = None
    volume_ratio = None
    trend_direction = None
    regime_label = None
    regime_data = None
    if regime is not None:
        atr_pct = regime.atr_pct
        volume_ratio = regime.volume_ratio
        trend_direction = regime.trend_direction
        regime_label = regime.regime.value
        regime_data = regime.to_dict()
        if regime.atr_pct_median and regime.atr_pct_median > 0:
            volatility_ratio = round(regime.atr_pct / regime.atr_pct_median, 4)

    return SignalSnapshot(
        signal_id=signal_id,
        engine_scores=engine_scores,
        regime=regime_label,
        regime_data=regime_data,
        atr_pct=atr_pct,
        volatility_ratio=volatility_ratio,
        volume_ratio=volume_ratio,
        trend_direction=trend_direction,
        fear_greed=int(fear_greed) if isinstance(fear_greed, (int, float)) else None,
        ath_distance_pct=ath_distance if isinstance(ath_distance, (int, float)) else None,
        composite_confidence=decision.get("confidence_score"),
        composite_probability=decision.get("probability_score"),
        mtf_trends=decision.get("mtf_trends", {}),
        extra={"birth": _enrich_birth(decision.get("birth_telemetry"),
                                      engine_weights, adaptive_active, regime_label,
                                      exposure)},
    )


def _enrich_birth(birth, engine_weights, adaptive_active, regime_label, exposure=None):
    """A8-1 (ADDITIVE telemetry): stamp the engine weights actually used + whether
    the coin's learned (adaptive) layer was applied + the regime, so a future
    adaptive-vs-base measurement is possible. NEVER re-read by any decision. Safe if
    birth is None or the inputs are absent (returns the input unchanged).

    CP-OBS-1A adds `exposure` (aggregate directional exposure at birth) as a second
    INDEPENDENT additive layer: each layer only applies when its own inputs are
    present, so passing exposure alone can never fabricate A8-1 keys (and vice
    versa) — every pre-existing call path stays byte-identical."""
    if not isinstance(birth, dict):
        return birth
    out = birth
    if engine_weights is not None or adaptive_active is not None:
        out = {
            **out,
            "engine_weights_used": engine_weights,
            "adaptive_active": bool(adaptive_active) if adaptive_active is not None else None,
            "regime": regime_label,
        }
    if exposure is not None:
        out = {**out, "exposure": exposure}
    return out
