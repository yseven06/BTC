"""
TradeMinds AI – Smart Money Concepts (SMC) Engine

Analyzes order blocks, Fair Value Gaps (FVG), breaker blocks, liquidity zones,
and premium/discount zones to produce a composite SMC EngineResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.engines.smc.concepts import SMCType, analyse_smc, SMCResult

logger = logging.getLogger(__name__)


class SMCEngine(BaseEngine):
    """Smart Money Concepts (SMC) Engine.

    Weight: 0.15 (15 % of composite score).
    """

    @property
    def name(self) -> str:
        return "smart_money_concepts"

    @property
    def weight(self) -> float:
        return 0.15

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        df: pd.DataFrame = ohlcv_data
        warnings: List[str] = []

        if len(df) < 20:
            warnings.append("Insufficient data for SMC analysis (<20 bars)")

        lookback = kwargs.get("smc_lookback", 50)
        smc_res: SMCResult = analyse_smc(df, lookback=lookback)

        # --- Scoring logic ---
        # Baseline score: 50.0 (neutral)
        score = 50.0

        # 1. Premium / Discount Zone (up to +/- 20 points)
        if smc_res.premium_discount:
            pd_info = smc_res.premium_discount
            if pd_info.current_zone == "discount":
                # discount is a buy zone; score increases as price gets closer to swing low
                score += (50.0 - pd_info.position_pct * 0.5)
            elif pd_info.current_zone == "premium":
                # premium is a sell zone; score decreases as price gets closer to swing high
                score -= (pd_info.position_pct * 0.5 - 25.0)
            # Ensure premium/discount contribution is capped
            score = max(30.0, min(70.0, score))

        # 2. Unmitigated Order Blocks (capped at ±15 points total regardless of count)
        # Without a per-concept cap, 10+ OBs in a volatile 50-bar window could push
        # the raw score above 100 before the final clamp, drowning out the
        # premium/discount zone signal that was already applied.
        unmitigated_bullish_ob = [ob for ob in smc_res.order_blocks if ob.ob_type == SMCType.BULLISH and not ob.mitigated]
        unmitigated_bearish_ob = [ob for ob in smc_res.order_blocks if ob.ob_type == SMCType.BEARISH and not ob.mitigated]

        bull_ob_delta = 0.0
        for ob in unmitigated_bullish_ob:
            ratio = getattr(ob, "volume_ratio", 1.0)
            confirmed = getattr(ob, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bull_ob_delta += 5.0 * multiplier
        score += min(bull_ob_delta, 15.0)

        bear_ob_delta = 0.0
        for ob in unmitigated_bearish_ob:
            ratio = getattr(ob, "volume_ratio", 1.0)
            confirmed = getattr(ob, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bear_ob_delta += 5.0 * multiplier
        score -= min(bear_ob_delta, 15.0)

        # 3. Unfilled Fair Value Gaps (capped at ±15 points total)
        unfilled_bullish_fvg = [fvg for fvg in smc_res.fair_value_gaps if fvg.fvg_type == SMCType.BULLISH and not fvg.filled]
        unfilled_bearish_fvg = [fvg for fvg in smc_res.fair_value_gaps if fvg.fvg_type == SMCType.BEARISH and not fvg.filled]

        bull_fvg_delta = 0.0
        for fvg in unfilled_bullish_fvg:
            ratio = getattr(fvg, "volume_ratio", 1.0)
            confirmed = getattr(fvg, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bull_fvg_delta += 5.0 * multiplier
        score += min(bull_fvg_delta, 15.0)

        bear_fvg_delta = 0.0
        for fvg in unfilled_bearish_fvg:
            ratio = getattr(fvg, "volume_ratio", 1.0)
            confirmed = getattr(fvg, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bear_fvg_delta += 5.0 * multiplier
        score -= min(bear_fvg_delta, 15.0)

        # 4. Breaker Blocks (capped at ±10 points total)
        # Bullish breaker block means a previously bearish OB was broken through, flipping to support.
        bullish_breaker = [bb for bb in smc_res.breaker_blocks if bb.bb_type == SMCType.BULLISH]
        bearish_breaker = [bb for bb in smc_res.breaker_blocks if bb.bb_type == SMCType.BEARISH]

        bull_bb_delta = 0.0
        for bb in bullish_breaker:
            ratio = getattr(bb, "volume_ratio", 1.0)
            confirmed = getattr(bb, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bull_bb_delta += 5.0 * multiplier
        score += min(bull_bb_delta, 10.0)

        bear_bb_delta = 0.0
        for bb in bearish_breaker:
            ratio = getattr(bb, "volume_ratio", 1.0)
            confirmed = getattr(bb, "volume_confirmed", True)
            multiplier = 1.2 if ratio >= 1.5 else (1.0 if confirmed else 0.3)
            bear_bb_delta += 5.0 * multiplier
        score -= min(bear_bb_delta, 10.0)

        # 5. Institutional Displacement (up to +/- 10 points)
        # Look at recent displacement candles (within last 5 candles)
        recent_displacement = [d for d in smc_res.displacement_candles if len(df) - d.index <= 5]
        for dc in recent_displacement:
            if dc.direction == SMCType.BULLISH:
                score += 5.0
            else:
                score -= 5.0

        score = max(0.0, min(100.0, score))
        bias = self._score_to_bias(score)

        # --- Confidence Calculation ---
        # Starts at 70%, increases if multiple concepts align, decreases on conflicting signs
        confidence = 70.0
        
        # Alignment check:
        bullish_indicators_count = (1 if len(unmitigated_bullish_ob) > 0 else 0) + \
                                   (1 if len(unfilled_bullish_fvg) > 0 else 0) + \
                                   (1 if len(bullish_breaker) > 0 else 0) + \
                                   (1 if smc_res.premium_discount and smc_res.premium_discount.current_zone == "discount" else 0)
                                   
        bearish_indicators_count = (1 if len(unmitigated_bearish_ob) > 0 else 0) + \
                                   (1 if len(unfilled_bearish_fvg) > 0 else 0) + \
                                   (1 if len(bearish_breaker) > 0 else 0) + \
                                   (1 if smc_res.premium_discount and smc_res.premium_discount.current_zone == "premium" else 0)

        if (bullish_indicators_count > 0 and bearish_indicators_count > 0):
            # Contradictory signals reduce confidence
            conflict_penalty = min(30.0, abs(bullish_indicators_count - bearish_indicators_count) * 10.0)
            confidence -= conflict_penalty
        else:
            # Complete alignment increases confidence
            alignment_bonus = (bullish_indicators_count + bearish_indicators_count) * 5.0
            confidence += alignment_bonus

        confidence = max(30.0, min(95.0, confidence))

        # --- Build Key Findings ---
        key_findings = self._build_findings(smc_res, unmitigated_bullish_ob, unmitigated_bearish_ob, unfilled_bullish_fvg, unfilled_bearish_fvg)

        # --- Supporting Data ---
        # Zone geometry (high/low/index) for chart overlays — previously only
        # counts were exposed, so the frontend had no coordinates to draw the
        # actual order block / FVG / breaker boxes on a candle chart.
        def _zone(z: Any, idx_field: str = "index") -> Dict[str, Any]:
            return {"high": z.high, "low": z.low, "index": getattr(z, idx_field)}

        supporting_data: Dict[str, Any] = {
            "unmitigated_bullish_ob_count": len(unmitigated_bullish_ob),
            "unmitigated_bullish_ob": [_zone(ob) for ob in unmitigated_bullish_ob[:5]],
            "unmitigated_bearish_ob": [_zone(ob) for ob in unmitigated_bearish_ob[:5]],
            "unfilled_bullish_fvg": [_zone(g) for g in unfilled_bullish_fvg[:5]],
            "unfilled_bearish_fvg": [_zone(g) for g in unfilled_bearish_fvg[:5]],
            "bullish_breaker_zones": [_zone(b, "breaker_index") for b in bullish_breaker[:5]],
            "bearish_breaker_zones": [_zone(b, "breaker_index") for b in bearish_breaker[:5]],
            "unmitigated_bearish_ob_count": len(unmitigated_bearish_ob),
            "unfilled_bullish_fvg_count": len(unfilled_bullish_fvg),
            "unfilled_bearish_fvg_count": len(unfilled_bearish_fvg),
            "bullish_breakers_count": len(bullish_breaker),
            "bearish_breakers_count": len(bearish_breaker),
            "premium_discount": {
                "swing_high": smc_res.premium_discount.swing_high if smc_res.premium_discount else None,
                "swing_low": smc_res.premium_discount.swing_low if smc_res.premium_discount else None,
                "equilibrium": smc_res.premium_discount.equilibrium if smc_res.premium_discount else None,
                "current_zone": smc_res.premium_discount.current_zone if smc_res.premium_discount else "neutral",
                "position_pct": smc_res.premium_discount.position_pct if smc_res.premium_discount else 50.0,
            } if smc_res.premium_discount else None,
            "recent_displacement_count": len(recent_displacement),
        }

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=key_findings[:8],
            supporting_data=supporting_data,
            warnings=warnings,
        )

    @staticmethod
    def _score_to_bias(score: float) -> SignalBias:
        if score >= 75:
            return SignalBias.STRONG_BULLISH
        if score >= 60:
            return SignalBias.BULLISH
        if score >= 40:
            return SignalBias.NEUTRAL
        if score >= 25:
            return SignalBias.BEARISH
        return SignalBias.STRONG_BEARISH

    @staticmethod
    def _build_findings(
        smc_res: SMCResult,
        bull_obs: List[Any],
        bear_obs: List[Any],
        bull_fvgs: List[Any],
        bear_fvgs: List[Any],
    ) -> List[str]:
        findings: List[str] = []

        if smc_res.premium_discount:
            pd_zone = smc_res.premium_discount.current_zone.upper()
            pos = smc_res.premium_discount.position_pct
            findings.append(f"Price is in {pd_zone} zone (Range position: {pos}%)")

        if bull_obs:
            findings.append(f"Detected {len(bull_obs)} unmitigated Bullish Order Block(s) below")
        if bear_obs:
            findings.append(f"Detected {len(bear_obs)} unmitigated Bearish Order Block(s) above")

        if bull_fvgs:
            findings.append(f"Detected {len(bull_fvgs)} unfilled Bullish Fair Value Gap(s)")
        if bear_fvgs:
            findings.append(f"Detected {len(bear_fvgs)} unfilled Bearish Fair Value Gap(s)")

        bull_breakers = [bb for bb in smc_res.breaker_blocks if bb.bb_type == SMCType.BULLISH]
        bear_breakers = [bb for bb in smc_res.breaker_blocks if bb.bb_type == SMCType.BEARISH]
        if bull_breakers:
            findings.append(f"Bullish Breaker Block acting as support")
        if bear_breakers:
            findings.append(f"Bearish Breaker Block acting as resistance")

        displacement_bull = [d for d in smc_res.displacement_candles if d.direction == SMCType.BULLISH]
        displacement_bear = [d for d in smc_res.displacement_candles if d.direction == SMCType.BEARISH]
        if len(displacement_bull) > len(displacement_bear):
            findings.append("Recent institutional buying pressure (bullish displacement)")
        elif len(displacement_bear) > len(displacement_bull):
            findings.append("Recent institutional selling pressure (bearish displacement)")

        # Equal Highs / Lows (Liquidity)
        eq_highs = [lz for lz in smc_res.liquidity_zones if lz.zone_type == "equal_highs" and not lz.swept]
        eq_lows = [lz for lz in smc_res.liquidity_zones if lz.zone_type == "equal_lows" and not lz.swept]
        if eq_highs:
            findings.append(f"Buy-side liquidity resting above equal highs at {eq_highs[0].price:.4f}")
        if eq_lows:
            findings.append(f"Sell-side liquidity resting below equal lows at {eq_lows[0].price:.4f}")

        return findings

