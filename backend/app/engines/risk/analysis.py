"""
TradeMinds AI – Risk Management Engine Helpers

Calculates volatility levels, position sizing metrics (Kelly, fixed fractional, ATR-based),
Risk/Reward ratios, and composite Risk Scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class VolatilityClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class RiskAnalysisResult:
    volatility_class: VolatilityClass
    atr_pct: float
    risk_score: float  # 1 to 10
    risk_level: RiskLevel
    recommended_position_pct: float  # Kelly or Fixed Fractional recommendation
    max_drawdown_pct: float
    rr_ratio: Optional[float] = None
    key_findings: List[str] = None


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    high_low = df["high"] - df["low"]
    high_cp = (df["high"] - df["close"].shift(1)).abs()
    low_cp = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def safe_last_atr(atr_series: pd.Series, current_price: float) -> float:
    """Last ATR value with a 2%-of-price fallback for NaN OR a genuine <= 0.

    A flat 14-bar window (illiquid / halted / pegged / frozen feed) yields ATR
    exactly 0.0 (not NaN), which the old NaN-only guard missed — every derived
    level then collapses onto entry (SL == entry == TP1 == TP2 == TP3) and the
    signal can never resolve. Single source for the fallback so the signal
    generator and the risk engine stay consistent (BUG-1). Byte-identical for any
    ATR > 0.
    """
    atr = float(atr_series.iloc[-1])
    if np.isnan(atr) or atr <= 0:
        return current_price * 0.02
    return atr


def analyze_risk(
    df: pd.DataFrame,
    asset_type: str = "crypto",
    portfolio_size: float = 10000.0,
    risk_pct: float = 2.0,  # risk 2% of portfolio per trade
    entry: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> RiskAnalysisResult:
    """Perform comprehensive risk assessment for the asset."""
    findings = []
    
    # 1. Volatility Assessment
    atr_series = calculate_atr(df)
    current_price = float(df["close"].iloc[-1])
    atr_val = safe_last_atr(atr_series, current_price)
    
    atr_pct = (atr_val / current_price) * 100.0
    
    # Volatility classification depends on asset class
    if asset_type == "crypto":
        # Crypto has higher base volatility thresholds
        if atr_pct > 8.0:
            vol_class = VolatilityClass.EXTREME
        elif atr_pct > 4.0:
            vol_class = VolatilityClass.HIGH
        elif atr_pct > 2.0:
            vol_class = VolatilityClass.MEDIUM
        else:
            vol_class = VolatilityClass.LOW
    else:
        # Stocks / Forex have lower thresholds
        if atr_pct > 4.0:
            vol_class = VolatilityClass.EXTREME
        elif atr_pct > 2.0:
            vol_class = VolatilityClass.HIGH
        elif atr_pct > 1.0:
            vol_class = VolatilityClass.MEDIUM
        else:
            vol_class = VolatilityClass.LOW

    findings.append(f"Volatility level: {vol_class.value.upper()} (ATR is {atr_pct:.2f}% of price)")

    # 2. Risk/Reward Ratio
    rr = None
    if entry is not None and stop_loss is not None and take_profit is not None:
        risk_dist = abs(entry - stop_loss)
        reward_dist = abs(take_profit - entry)
        if risk_dist > 0:
            rr = reward_dist / risk_dist
            findings.append(f"Risk/Reward Ratio: 1:{rr:.2f}")
            if rr < 1.5:
                findings.append("Warning: Risk/Reward ratio is suboptimal (< 1:1.5)")

    # 3. Position Sizing — fixed fractional: size = risk% / (SL distance %).
    # Use explicit None checks (a legitimate price of 0.0 must not fall through a
    # truthiness guard); when SL is not supplied fall back to a 2x ATR distance.
    # Refuse to size a degenerate stop (entry == SL -> sl_pct 0) rather than
    # silently emitting an arbitrary 5% (BUG-5).
    if entry is not None and stop_loss is not None:
        sl_dist = abs(entry - stop_loss)
    else:
        sl_dist = atr_val * 2.0
    sl_pct = (sl_dist / current_price) * 100.0 if current_price > 0 else 0.0

    if sl_pct > 0:
        recommended_pct = max(0.5, min(25.0, (risk_pct / sl_pct) * 100.0))  # cap 0.5%-25%
        findings.append(f"Recommended Position Size: {recommended_pct:.1f}% of portfolio (risking {risk_pct}% on trade)")
    else:
        recommended_pct = 0.0
        findings.append("Warning: stop-loss distance is zero or undefined — position size cannot be computed.")

    # 4. Max Drawdown in lookback period
    peak = df["close"].cummax()
    drawdown = (df["close"] - peak) / peak * 100.0
    max_dd = float(drawdown.min())

    findings.append(f"Historical Max Drawdown in recent lookback: {abs(max_dd):.2f}%")

    # 5. Composite Risk Score (1 to 10)
    # Volatility, asset class, drawdown contribution.
    # Crypto carries higher base risk than stocks/forex, but we start from a
    # neutral 5.0 and add an asset-class premium rather than jumping straight
    # to 7.0, which was causing every crypto signal to exceed the HOLD gate.
    base_risk = 5.0
    if asset_type == "crypto":
        base_risk += 1.0   # crypto premium: inherently more volatile than stocks
    elif asset_type == "stock":
        base_risk += 0.0
    elif asset_type == "forex":
        base_risk -= 1.0

    # Volatility modifier
    if vol_class == VolatilityClass.EXTREME:
        base_risk += 2.0
    elif vol_class == VolatilityClass.HIGH:
        base_risk += 1.0
    elif vol_class == VolatilityClass.LOW:
        base_risk -= 1.0

    # Drawdown modifier
    if abs(max_dd) > 20.0:
        base_risk += 1.5
    elif abs(max_dd) > 10.0:
        base_risk += 0.5

    # R:R modifier if available
    if rr is not None:
        if rr < 1.0:
            base_risk += 1.5
        elif rr > 2.5:
            base_risk -= 1.0

    risk_score = max(1.0, min(10.0, base_risk))

    if risk_score >= 8.0:
        risk_lvl = RiskLevel.VERY_HIGH
    elif risk_score >= 6.0:
        risk_lvl = RiskLevel.HIGH
    elif risk_score >= 4.0:
        risk_lvl = RiskLevel.MEDIUM
    else:
        risk_lvl = RiskLevel.LOW

    findings.append(f"Composite Risk Level: {risk_lvl.value.upper()} (Score: {risk_score:.1f}/10)")

    return RiskAnalysisResult(
        volatility_class=vol_class,
        atr_pct=round(atr_pct, 2),
        risk_score=round(risk_score, 1),
        risk_level=risk_lvl,
        recommended_position_pct=round(recommended_pct, 2),
        max_drawdown_pct=round(abs(max_dd), 2),
        rr_ratio=round(rr, 2) if rr is not None else None,
        key_findings=findings,
    )
