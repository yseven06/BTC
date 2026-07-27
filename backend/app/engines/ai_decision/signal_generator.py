"""
Zate Trade – Signal Generator

Takes individual engine analysis results, computes a weighted composite score,
determines trade direction/strength, and calculates levels (Entry, Stop Loss,
Take Profits) based on ATR and support/resistance boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.engines.base import EngineResult, SignalBias
from app.engines.risk.analysis import calculate_atr, safe_last_atr
from app.engines.ai_decision.birth_telemetry import build_birth_telemetry

logger = logging.getLogger(__name__)


def _enforce_tp_order(direction: str, tp1: float, tp2: float, tp3: float):
    """P11-1: guarantee TP monotonicity in the profit direction. An SR override can
    set tp2 = a resistance/support beyond tp3, inverting the order. Pure sort of the
    three ALREADY-computed values — no fabricated levels, no magic numbers; a strict
    no-op (byte-identical) when already ordered. Bull ascending, bear descending.
    Caller applies it ONLY for actionable directions (HOLD levels are informational
    and never SR-overridden, so they are left untouched)."""
    tps = sorted((tp1, tp2, tp3), reverse=(direction == "bearish"))
    return tps[0], tps[1], tps[2]


def _price_round(value: float) -> float:
    """Round a price level to a precision that scales with its magnitude.

    A flat round(x, 4) is fine for BTC ($64,500.1234) but silently zeroes
    out micro-cap assets like PEPE (~$0.000003) — 4 decimal places truncates
    everything below 0.0001, so entry/SL/TP all collapse to 0.0000 even
    though the DB column (Numeric(20, 8)) has room for 8. Scale precision
    down with the price so small-cap signals keep meaningful levels.
    """
    if value == 0:
        return 0.0
    abs_v = abs(value)
    if abs_v >= 1:
        return round(value, 4)
    if abs_v >= 0.01:
        return round(value, 6)
    return round(value, 8)


@dataclass
class GeneratedSignalData:
    signal_type: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    direction: str    # bullish, bearish, neutral
    confidence_score: float  # 0-100
    probability_score: float  # 0-100
    risk_score: float       # 1-10
    risk_level: str         # low, medium, high, very_high
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    invalidation_conditions: str
    # Additive generation-time provenance (telemetry only — NOT a decision input).
    birth_telemetry: Optional[Dict[str, Any]] = None
    # Consensus primitives, exported for the candidate decision log (P2.2-a).
    # OUTPUT ONLY — nothing reads this back and no branch above depends on it.
    # These are function-locals that the scheduler cannot otherwise see; the
    # alternative was re-deriving them there from engine_results, which would
    # copy the disagreement coefficient into a second location that would
    # silently drift from this one.
    consensus_telemetry: Optional[Dict[str, Any]] = None
    # F1 provenance: which frame the features were measured on, and how far the
    # live price had already travelled past that bar's close. OUTPUT ONLY.
    # Recording the gap is the point — it is what lets "the closed bars pointed
    # the right way but price had already run" be counted later instead of
    # argued about.
    decision_input_telemetry: Optional[Dict[str, Any]] = None


# F1 decision-input contract. Bumped only when the MEANING of the decision input
# changes — this is the cohort boundary that separates candidates scored on a
# partially-formed candle from those scored on closed bars, and analysis that
# mixes the two would be comparing different systems.
DECISION_INPUT_VERSION = "closed_candle_v1"
CANDLE_POLICY = "closed_features_live_geometry"


# Base engine weights (sum to 1.00). The single source of truth for the
# default mix; the Adaptive Weight Engine tilts these per market-regime and
# per-coin learned performance, but always starts from here.
BASE_ENGINE_WEIGHTS: Dict[str, float] = {
    "technical_analysis":      0.17,
    "market_structure":        0.17,
    "smart_money_concepts":    0.13,
    "volume_analysis":         0.13,
    "candle_range_theory":     0.10,
    "onchain_analysis":        0.10,
    "risk_management":         0.08,
    "fundamental_analysis":    0.07,
    "macro_analysis":          0.05,
}


def generate_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    engine_results: List[EngineResult],
    mtf_trends: Dict[str, str] = None,
    weights: Dict[str, float] | None = None,
    current_price: float | None = None,
) -> GeneratedSignalData:
    """Consolidate scores from all engines, calculate entry/SL/TP levels, and form trade plan.

    Args:
        weights: Optional engine-weight override (regime/coin-adaptive). When
            None, the static BASE_ENGINE_WEIGHTS are used — identical to the
            previous fixed behaviour, so callers that don't opt in are unchanged.
    """
    # 1. Calculate weighted composite score (weights sum to ~1.00)
    engine_weights = weights if weights else BASE_ENGINE_WEIGHTS
    composite_score = 0.0
    for res in engine_results:
        weight = engine_weights.get(res.engine_name, 0.05)
        composite_score += res.score * weight

    # 2. Consensus / Disagreement Penalty
    biases = [res.bias for res in engine_results]
    bullish_count = sum(1 for b in biases if b in [SignalBias.BULLISH, SignalBias.STRONG_BULLISH])
    bearish_count = sum(1 for b in biases if b in [SignalBias.BEARISH, SignalBias.STRONG_BEARISH])
    
    disagreement_penalty = 0.0
    if bullish_count > 0 and bearish_count > 0:
        # Maximum penalty if split evenly, less if aligned
        disagreement_penalty = min(bullish_count, bearish_count) * 4.0

    # Apply penalty to composite score towards the neutral 50
    if composite_score > 50.0:
        composite_score = max(50.0, composite_score - disagreement_penalty)
    elif composite_score < 50.0:
        composite_score = min(50.0, composite_score + disagreement_penalty)

    # 3. Determine Signal Type and Direction — tuned for actionable signals
    if composite_score >= 68.0:
        signal_type = "STRONG_BUY"
        direction = "bullish"
    elif composite_score >= 54.0:
        signal_type = "BUY"
        direction = "bullish"
    elif composite_score >= 46.0:
        signal_type = "HOLD"
        direction = "neutral"
    elif composite_score >= 32.0:
        signal_type = "SELL"
        direction = "bearish"
    else:
        signal_type = "STRONG_SELL"
        direction = "bearish"

    # OBSERVATION ONLY (P2.2-a): remember what the composite bands alone decided,
    # before the consensus gate and the MTF layer below get to demote it. Two
    # plain assignments; nothing reads them until the return statement, so no
    # branch below can see or be affected by them. Without this, a HOLD in the
    # candidate log is ambiguous between "composite landed in the HOLD band" and
    # "composite said BUY and a gate took it away" — which is precisely the
    # distinction the calibration work needs.
    threshold_signal_type = signal_type
    threshold_direction = direction

    # --- SIGNAL QUALITY CONSENSUS ---
    # Quantity was never the goal — a handful of signals that genuinely
    # reach TP beats a high signal count padded with ones that get stopped
    # out. Backtested against the 103 currently-active signals before
    # picking these numbers: requiring SMC AND CRT to both individually
    # confirm passed only 17.5% of them — too strict for a platform with no
    # resolved win/loss history yet to validate that bar against. Needing 4
    # of the 6 engines (now incl. Fundamental) to agree, with SMC OR CRT as
    # one of those four, passed 66% — a real tightening from the old >=2-of-5
    # rule without going silent. Revisit these thresholds once enough
    # signals have actually resolved to measure true win rate per setting.
    if direction in ["bullish", "bearish"]:
        ta_res = next((res for res in engine_results if res.engine_name == "technical_analysis"), None)
        ms_res = next((res for res in engine_results if res.engine_name == "market_structure"), None)
        vol_res = next((res for res in engine_results if res.engine_name == "volume_analysis"), None)
        smc_res = next((res for res in engine_results if res.engine_name == "smart_money_concepts"), None)
        crt_res = next((res for res in engine_results if res.engine_name == "candle_range_theory"), None)
        fund_res = next((res for res in engine_results if res.engine_name == "fundamental_analysis"), None)
        risk_res = next((res for res in engine_results if res.engine_name == "risk_management"), None)

        ta_score = ta_res.score if ta_res else 50.0
        ms_score = ms_res.score if ms_res else 50.0
        vol_score = vol_res.score if vol_res else 50.0
        smc_score = smc_res.score if smc_res else 50.0
        crt_score = crt_res.score if crt_res else 50.0
        fund_score = fund_res.score if fund_res else 50.0

        pool = [ta_score, ms_score, vol_score, smc_score, crt_score, fund_score]

        if direction == "bullish":
            strong_conflicts = sum(1 for s in pool if s < 40)
            confirmations = sum(1 for s in pool if s > 53)
            smc_crt_confirm = smc_score > 53 or crt_score > 53

            risk_too_high = False
            if risk_res and "risk_score_raw" in risk_res.supporting_data:
                risk_too_high = risk_res.supporting_data["risk_score_raw"] >= 9.5

            # Need 4 of 6 engines confirming AND at least one of SMC/CRT
            # among them (see threshold note above).
            if strong_conflicts >= 2 or confirmations < 4 or not smc_crt_confirm or risk_too_high:
                logger.info(
                    f"Signal downgraded to HOLD for {symbol} (StrongConflicts: {strong_conflicts}, "
                    f"Confirmations: {confirmations}/6, SMC or CRT agree: {smc_crt_confirm}, ExtremeRisk: {risk_too_high})"
                )
                signal_type = "HOLD"
                direction = "neutral"

        elif direction == "bearish":
            strong_conflicts = sum(1 for s in pool if s > 60)
            confirmations = sum(1 for s in pool if s < 47)
            smc_crt_confirm = smc_score < 47 or crt_score < 47

            risk_too_high = False
            if risk_res and "risk_score_raw" in risk_res.supporting_data:
                risk_too_high = risk_res.supporting_data["risk_score_raw"] >= 9.5

            if strong_conflicts >= 2 or confirmations < 4 or not smc_crt_confirm or risk_too_high:
                logger.info(
                    f"Signal downgraded to HOLD for {symbol} (StrongConflicts: {strong_conflicts}, "
                    f"Confirmations: {confirmations}/6, SMC or CRT agree: {smc_crt_confirm}, ExtremeRisk: {risk_too_high})"
                )
                signal_type = "HOLD"
                direction = "neutral"

    # --- MULTI-TIMEFRAME CONFIRMATION LAYER ---
    mtf_penalty = 0.0
    if mtf_trends and direction in ["bullish", "bearish"]:
        disagreeing_tf_count = 0
        for tf in ["15m", "1h", "4h"]:
            tf_trend = mtf_trends.get(tf, "neutral")
            if tf_trend == "neutral":
                continue
            if direction == "bullish" and tf_trend == "bearish":
                disagreeing_tf_count += 1
            elif direction == "bearish" and tf_trend == "bullish":
                disagreeing_tf_count += 1

        if disagreeing_tf_count > 0:
            # Penalize confidence
            mtf_penalty = disagreeing_tf_count * 15.0
            
            # Downgrade signal strength
            if signal_type == "STRONG_BUY":
                signal_type = "BUY"
            elif signal_type == "STRONG_SELL":
                signal_type = "SELL"
            
            # If 2 or more timeframes disagree, downgrade BUY/SELL to HOLD entirely
            if disagreeing_tf_count >= 2:
                signal_type = "HOLD"
                direction = "neutral"
                
            logger.info(f"MTF alignment failure for {symbol}: {disagreeing_tf_count} timeframes disagreed. Signal set to {signal_type}.")

    # 4. Confidence and Probability Scores
    # Confidence is average engine confidence penalized by disagreement
    total_conf = sum(res.confidence for res in engine_results)
    avg_conf = total_conf / len(engine_results)
    confidence_score = max(20.0, min(98.0, avg_conf - disagreement_penalty * 1.5 - mtf_penalty))

    # Probability score: aligns technicals, market structure, and volume
    align_factors = []
    for res in engine_results:
        if res.engine_name in ["technical_analysis", "market_structure", "volume_analysis"]:
            align_factors.append(res.score)
    
    prob_base = sum(align_factors) / len(align_factors) if align_factors else 50.0
    # If direction is bearish, price going down is the "success outcome", so probability is high if score is low
    probability_score = prob_base if direction == "bullish" else (100.0 - prob_base)
    # Clamp probability score
    probability_score = max(35.0, min(95.0, probability_score))

    # 5. Risk Score and Level (Retrieve from Risk Engine)
    risk_engine_res = next((res for res in engine_results if res.engine_name == "risk_management"), None)
    if risk_engine_res and "risk_score_raw" in risk_engine_res.supporting_data:
        risk_score = risk_engine_res.supporting_data["risk_score_raw"]
        risk_level = risk_engine_res.supporting_data["risk_level"]
    else:
        # Risk engine produced no result — fail loud and default CONSERVATIVE
        # (high), not a neutral medium that would understate risk on an engine
        # failure (D5).
        logger.warning("Risk engine result missing for %s — defaulting to conservative HIGH risk.", symbol)
        risk_score = 7.0
        risk_level = "high"

    # 6. Trade Levels (Entry, SL, TPs) based on ATR and S/R
    #
    # F1 — two different prices, deliberately. `current_price` is the LIVE price
    # (the caller reads it from the full frame, forming candle included) and it
    # anchors every level, so a plan is never placed a full bar behind the
    # market. `df` here is the CLOSED-bar analysis frame, so ATR — a volatility
    # measurement — is not computed from a candle that is 2/15 complete.
    # Falling back to df's last close keeps direct callers working unchanged.
    analysis_close = float(df["close"].iloc[-1])
    current_price = float(current_price) if current_price is not None else analysis_close

    # Calculate ATR for scaling — from the closed frame (D2).
    atr_series = calculate_atr(df)
    _atr_last = float(atr_series.iloc[-1])
    atr_fallback_used = bool(np.isnan(_atr_last) or _atr_last <= 0)
    atr_raw = None if np.isnan(_atr_last) else _atr_last
    atr = safe_last_atr(atr_series, current_price)

    # Extract support and resistance if available from Market Structure Engine
    ms_engine_res = next((res for res in engine_results if res.engine_name == "market_structure"), None)
    nearest_sup = None
    nearest_res = None
    if ms_engine_res and "nearest_support" in ms_engine_res.supporting_data:
        nearest_sup = ms_engine_res.supporting_data["nearest_support"]
        nearest_res = ms_engine_res.supporting_data["nearest_resistance"]

    # SR-override provenance flags (additive telemetry — never change the levels).
    sr_override_tp1 = sr_override_tp2 = sr_override_sl = False

    # Initialize levels
    if direction == "bullish":
        # Entry Zone: from current price down to slightly above support or 0.5x ATR
        entry_zone_high = current_price
        entry_low_fallback = current_price - (atr * 0.5)
        entry_zone_low = nearest_sup if nearest_sup and nearest_sup < current_price else entry_low_fallback
        # Check to avoid abnormally large entry zones
        if entry_zone_low < current_price - (atr * 1.5):
            entry_zone_low = current_price - (atr * 0.5)
            
        # Stop Loss: below entry_zone_low by 1.5x ATR or below nearest support
        sl_fallback = entry_zone_low - (atr * 1.5)
        sr_override_sl = bool(nearest_sup and nearest_sup < entry_zone_low)
        stop_loss = (nearest_sup - (atr * 0.5)) if sr_override_sl else sl_fallback
        # In case stop loss is positive but too close
        if stop_loss >= entry_zone_low:
            stop_loss = entry_zone_low - (atr * 1.5)

        # Take Profit levels (Fibonacci/ATR expansions)
        tp1 = current_price + (atr * 1.5)
        tp2 = current_price + (atr * 3.0)
        tp3 = current_price + (atr * 5.0)
        
        # Override TP1/TP2 with nearest resistance if it fits.
        # P11-3 Lever 1B: an SR override may only push TP1 OUTWARD (a farther, still-
        # realistic target), never pull it IN. A resistance closer than the ATR TP1
        # would collapse the planned R:R, so in that case TP1 keeps its ATR distance
        # (the close resistance is a within-move watch level, not the target).
        if nearest_res and nearest_res > current_price:
            if nearest_res < tp2:
                if nearest_res >= tp1:        # only farther than the ATR TP1 → use it
                    tp1 = nearest_res
                    sr_override_tp1 = True
                # else: closer than the ATR TP1 → keep ATR TP1 (no inward pull)
            else:
                tp2 = nearest_res
                sr_override_tp2 = True

        invalidation_conditions = f"Close below stop loss level {_price_round(stop_loss)} on a 1-hour candle basis, or failure to break resistance level {_price_round(tp1)} within 48 hours."

    elif direction == "bearish":
        # Entry Zone: from current price up to slightly below resistance or 0.5x ATR
        entry_zone_low = current_price
        entry_high_fallback = current_price + (atr * 0.5)
        entry_zone_high = nearest_res if nearest_res and nearest_res > current_price else entry_high_fallback
        if entry_zone_high > current_price + (atr * 1.5):
            entry_zone_high = current_price + (atr * 0.5)

        # Stop Loss: above entry_zone_high by 1.5x ATR or above nearest resistance
        sl_fallback = entry_zone_high + (atr * 1.5)
        sr_override_sl = bool(nearest_res and nearest_res > entry_zone_high)
        stop_loss = (nearest_res + (atr * 0.5)) if sr_override_sl else sl_fallback
        if stop_loss <= entry_zone_high:
            stop_loss = entry_zone_high + (atr * 1.5)

        # Take Profit levels
        tp1 = current_price - (atr * 1.5)
        tp2 = current_price - (atr * 3.0)
        tp3 = current_price - (atr * 5.0)

        # Override with nearest support (P11-3 Lever 1B mirror: only push TP1 OUTWARD
        # — i.e. lower for a short — never pull it in. A support closer than the ATR
        # TP1 keeps the ATR distance, so the override can't collapse the planned R:R.)
        if nearest_sup and nearest_sup < current_price:
            if nearest_sup > tp2:
                if nearest_sup <= tp1:        # only farther (lower) than the ATR TP1 → use it
                    tp1 = nearest_sup
                    sr_override_tp1 = True
                # else: closer than the ATR TP1 → keep ATR TP1 (no inward pull)
            else:
                tp2 = nearest_sup
                sr_override_tp2 = True

        invalidation_conditions = f"Close above stop loss level {_price_round(stop_loss)} on a 1-hour candle basis, or failure to break support level {_price_round(tp1)} within 48 hours."

    else:
        # Neutral HOLD — still surface indicative levels so the user can read the
        # nearest reference price action, just clearly marked as informational.
        # We bias by the raw composite_score (above/below 50 = which side wins).
        if composite_score >= 50:
            # Lean bullish — show what would-be BUY targets look like
            entry_zone_low  = current_price * 0.998
            entry_zone_high = current_price
            stop_loss = current_price - (atr * 1.5)
            tp1 = current_price + (atr * 1.5)
            tp2 = current_price + (atr * 3.0)
            tp3 = current_price + (atr * 5.0)
        else:
            # Lean bearish — show what would-be SELL targets look like
            entry_zone_low  = current_price
            entry_zone_high = current_price * 1.002
            stop_loss = current_price + (atr * 1.5)
            tp1 = current_price - (atr * 1.5)
            tp2 = current_price - (atr * 3.0)
            tp3 = current_price - (atr * 5.0)
        invalidation_conditions = (
            "Bilgi amaçlıdır. Net AL/SAT sinyali yok — motorlar arasında uzlaşı sağlanamadı. "
            "Pozisyon açmadan önce daha güçlü onay bekleyin."
        )

    # P11-1: enforce TP monotonicity for ACTIONABLE signals (an SR override can invert
    # tp2/tp3 when a resistance/support sits beyond tp3). No-op when already ordered →
    # byte-identical for the vast majority; only fixes objectively broken ordering.
    # HOLD (informational, never SR-overridden) is intentionally left untouched.
    if direction in ("bullish", "bearish"):
        tp1, tp2, tp3 = _enforce_tp_order(direction, tp1, tp2, tp3)

    # Birth-time telemetry (additive observability — never re-read by the decision).
    # FAIL-OPEN: a telemetry error must NEVER break signal generation (priority #1).
    try:
        birth_telemetry = build_birth_telemetry(
            direction=direction, signal_type=signal_type, current_price=current_price,
            atr_used=atr, atr_raw=atr_raw, atr_fallback_used=atr_fallback_used,
            nearest_support=nearest_sup, nearest_resistance=nearest_res,
            sr_override_tp1=sr_override_tp1, sr_override_tp2=sr_override_tp2, sr_override_sl=sr_override_sl,
            entry_zone_low=_price_round(entry_zone_low), entry_zone_high=_price_round(entry_zone_high),
            stop_loss=_price_round(stop_loss), tp1=_price_round(tp1),
            tp2=_price_round(tp2), tp3=_price_round(tp3),
            risk_score=round(risk_score, 1), risk_level=risk_level,
            confidence_score=round(confidence_score, 2), probability_score=round(probability_score, 2),
            composite_score=round(composite_score, 2),
            risk_supporting=(risk_engine_res.supporting_data if risk_engine_res else None),
        )
    except Exception as _bt_exc:  # pragma: no cover — telemetry must not break the engine
        logger.warning("birth telemetry build failed for %s (ignored; signal unaffected): %s", symbol, _bt_exc)
        birth_telemetry = None

    # Consensus primitives for the candidate decision log (P2.2-a). Built here so
    # the disagreement coefficient stays defined in exactly one place (line ~120)
    # instead of being re-derived by the caller. Pure packaging of values already
    # computed above — it reads no new state and decides nothing.
    #
    # Deliberately NOT called "disagreement_count": that name has three defensible
    # readings that yield different integers. The primitives are exported instead
    # so any definition can be derived later without this file having picked one.
    consensus_telemetry = {
        "bull_count": bullish_count,
        "bear_count": bearish_count,
        "conflict_min_count": min(bullish_count, bearish_count) if (bullish_count and bearish_count) else 0,
        "disagreement_penalty": round(disagreement_penalty, 2),
        "mtf_penalty": round(mtf_penalty, 2),
        # What the composite bands alone produced, before the consensus/MTF gates.
        "threshold_signal_type": threshold_signal_type,
        "threshold_direction": threshold_direction,
        # Did a gate inside THIS function demote the call?
        "engine_demoted": signal_type != threshold_signal_type,
    }

    # F1 provenance. `atr_raw` is the un-substituted ATR: when it is missing the
    # ATR-normalised gap is left NULL rather than divided by the fallback, which
    # would produce a number that looks measured and is not.
    _gap_pct = (
        ((current_price - analysis_close) / analysis_close * 100.0)
        if analysis_close else None
    )
    decision_input_telemetry = {
        "decision_input_version": DECISION_INPUT_VERSION,
        "candle_policy": CANDLE_POLICY,
        "current_price": current_price,
        "analysis_close_price": analysis_close,
        "current_vs_analysis_close_pct": round(_gap_pct, 6) if _gap_pct is not None else None,
        "current_vs_analysis_close_atr": (
            round((current_price - analysis_close) / atr_raw, 6)
            if (atr_raw and atr_raw > 0) else None
        ),
        "atr_source": "closed_bars",
        "atr_fallback_used": atr_fallback_used,
    }

    # Return structured data
    return GeneratedSignalData(
        signal_type=signal_type,
        direction=direction,
        confidence_score=round(confidence_score, 2),
        probability_score=round(probability_score, 2),
        risk_score=round(risk_score, 1),
        risk_level=risk_level,
        entry_zone_low=_price_round(entry_zone_low),
        entry_zone_high=_price_round(entry_zone_high),
        stop_loss=_price_round(stop_loss),
        tp1=_price_round(tp1),
        tp2=_price_round(tp2),
        tp3=_price_round(tp3),
        invalidation_conditions=invalidation_conditions,
        birth_telemetry=birth_telemetry,
        consensus_telemetry=consensus_telemetry,
        decision_input_telemetry=decision_input_telemetry,
    )

