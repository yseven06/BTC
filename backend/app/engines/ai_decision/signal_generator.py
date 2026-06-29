"""
TradeMinds AI – Signal Generator

Takes individual engine analysis results, computes a weighted composite score,
determines trade direction/strength, and calculates levels (Entry, Stop Loss,
Take Profits) based on ATR and support/resistance boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.engines.base import EngineResult, SignalBias
from app.engines.risk.analysis import calculate_atr

logger = logging.getLogger(__name__)


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
    current_price = float(df["close"].iloc[-1])
    
    # Calculate ATR for scaling
    atr_series = calculate_atr(df)
    atr = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else current_price * 0.02

    # Extract support and resistance if available from Market Structure Engine
    ms_engine_res = next((res for res in engine_results if res.engine_name == "market_structure"), None)
    nearest_sup = None
    nearest_res = None
    if ms_engine_res and "nearest_support" in ms_engine_res.supporting_data:
        nearest_sup = ms_engine_res.supporting_data["nearest_support"]
        nearest_res = ms_engine_res.supporting_data["nearest_resistance"]

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
        stop_loss = (nearest_sup - (atr * 0.5)) if nearest_sup and nearest_sup < entry_zone_low else sl_fallback
        # In case stop loss is positive but too close
        if stop_loss >= entry_zone_low:
            stop_loss = entry_zone_low - (atr * 1.5)

        # Take Profit levels (Fibonacci/ATR expansions)
        tp1 = current_price + (atr * 1.5)
        tp2 = current_price + (atr * 3.0)
        tp3 = current_price + (atr * 5.0)
        
        # Override TP1/TP2 with nearest resistance if it fits
        if nearest_res and nearest_res > current_price:
            if nearest_res < tp2:
                tp1 = nearest_res
            else:
                tp2 = nearest_res

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
        stop_loss = (nearest_res + (atr * 0.5)) if nearest_res and nearest_res > entry_zone_high else sl_fallback
        if stop_loss <= entry_zone_high:
            stop_loss = entry_zone_high + (atr * 1.5)

        # Take Profit levels
        tp1 = current_price - (atr * 1.5)
        tp2 = current_price - (atr * 3.0)
        tp3 = current_price - (atr * 5.0)

        # Override with nearest support
        if nearest_sup and nearest_sup < current_price:
            if nearest_sup > tp2:
                tp1 = nearest_sup
            else:
                tp2 = nearest_sup

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
    )

