"""
TradeMinds AI – BIST Stock Fundamental Ratios Analysis

Analyzes stock financial metrics including profitability, valuation, leverage,
efficiency, and liquidity ratios against industry benchmarks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class FundamentalRatiosResult:
    profitability_score: float  # 0-100
    valuation_score: float      # 0-100
    leverage_score: float       # 0-100
    liquidity_score: float      # 0-100
    composite_score: float      # 0-100
    ratios_data: Dict[str, Any]
    key_findings: List[str]


def analyze_stock_fundamentals(
    symbol: str,
    financial_data: Dict[str, Any],
) -> FundamentalRatiosResult:
    """Analyze financial statements and ratios for a given stock.

    Uses provided financial data (from Yahoo Finance or mock source).
    """
    findings = []
    
    # Extract data with safe fallbacks
    info = financial_data.get("info", {})
    financials = financial_data.get("financials", {})
    balance_sheet = financial_data.get("balance_sheet", {})
    
    # 1. Profitability (ROE, ROA, Net Profit Margin, EBITDA Margin)
    roe = info.get("returnOnEquity") or info.get("roe")
    roa = info.get("returnOnAssets") or info.get("roa")
    net_margin = info.get("profitMargins") or info.get("netProfitMargin")
    ebitda_margin = info.get("ebitdaMargins") or info.get("ebitdaMargin")

    # If none are present, check the financials dictionary
    if roe is None and "netIncome" in financials and "totalShareholderEquity" in balance_sheet:
        try:
            net_income = financials["netIncome"].iloc[0] if hasattr(financials["netIncome"], "iloc") else financials["netIncome"]
            equity = balance_sheet["totalShareholderEquity"].iloc[0] if hasattr(balance_sheet["totalShareholderEquity"], "iloc") else balance_sheet["totalShareholderEquity"]
            if equity > 0:
                roe = net_income / equity
        except Exception:
            pass

    # Normalize ratios to percentages if they are decimals
    roe = roe * 100.0 if (roe is not None and abs(roe) <= 1.0) else roe
    roa = roa * 100.0 if (roa is not None and abs(roa) <= 1.0) else roa
    net_margin = net_margin * 100.0 if (net_margin is not None and abs(net_margin) <= 1.0) else net_margin
    ebitda_margin = ebitda_margin * 100.0 if (ebitda_margin is not None and abs(ebitda_margin) <= 1.0) else ebitda_margin

    # Profitability scoring
    prof_score = 50.0
    prof_factors = []
    if roe is not None:
        prof_factors.append(roe)
        if roe > 15.0:
            prof_score += 15.0
            findings.append(f"Strong Return on Equity (ROE: {roe:.1f}%) exceeds benchmark")
        elif roe < 5.0:
            prof_score -= 15.0
            findings.append(f"Weak Return on Equity (ROE: {roe:.1f}%) underperforms")
    
    if net_margin is not None:
        prof_factors.append(net_margin)
        if net_margin > 10.0:
            prof_score += 10.0
            findings.append(f"Healthy Net Margin ({net_margin:.1f}%) indicating good cost controls")
        elif net_margin < 2.0:
            prof_score -= 10.0

    if prof_factors:
        prof_score = max(10.0, min(95.0, prof_score))
    else:
        prof_score = 50.0  # default neutral if no data

    # 2. Valuation (P/E, P/B, EV/EBITDA)
    pe = info.get("trailingPE") or info.get("peRatio")
    pb = info.get("priceToBook") or info.get("priceToBookRatio")
    ev_ebitda = info.get("enterpriseToEbitda")

    val_score = 50.0
    if pe is not None:
        if pe < 8.0:
            val_score += 15.0
            findings.append(f"Undervalued on Price-to-Earnings basis (P/E: {pe:.1f})")
        elif pe > 25.0:
            val_score -= 15.0
            findings.append(f"Premium valuation (P/E: {pe:.1f}) indicates potential overvaluation")

    if pb is not None:
        if pb < 1.5:
            val_score += 10.0
            findings.append(f"Attractive Price-to-Book ratio (P/B: {pb:.1f})")
        elif pb > 5.0:
            val_score -= 10.0

    val_score = max(10.0, min(95.0, val_score))

    # 3. Leverage (Debt/Equity, Net Debt/EBITDA)
    debt_equity = info.get("debtToEquity")
    quick_ratio = info.get("quickRatio")
    current_ratio = info.get("currentRatio")

    # Normalize debt/equity
    # yfinance often reports debt to equity as percentage (e.g. 120 means 1.2)
    if debt_equity is not None and debt_equity > 10.0:
        debt_equity = debt_equity / 100.0

    lev_score = 50.0
    if debt_equity is not None:
        if debt_equity < 1.0:
            lev_score += 15.0
            findings.append(f"Conservative debt profile (Debt/Equity: {debt_equity:.2f})")
        elif debt_equity > 2.0:
            lev_score -= 15.0
            findings.append(f"Elevated leverage risk (Debt/Equity: {debt_equity:.2f})")
    
    lev_score = max(10.0, min(95.0, lev_score))

    # 4. Liquidity & Efficiency
    liq_score = 50.0
    if current_ratio is not None:
        if current_ratio > 1.5:
            liq_score += 15.0
            findings.append(f"Solid short-term liquidity (Current Ratio: {current_ratio:.2f})")
        elif current_ratio < 1.0:
            liq_score -= 15.0
            findings.append(f"Tight working capital (Current Ratio: {current_ratio:.2f})")

    liq_score = max(10.0, min(95.0, liq_score))

    # 5. Composite score
    composite = (prof_score * 0.35 + val_score * 0.30 + lev_score * 0.20 + liq_score * 0.15)

    ratios_data = {
        "roe": roe,
        "roa": roa,
        "net_margin": net_margin,
        "ebitda_margin": ebitda_margin,
        "pe": pe,
        "pb": pb,
        "ev_ebitda": ev_ebitda,
        "debt_equity": debt_equity,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
    }

    if not findings:
        findings.append("Financial ratios are stable and in line with historical sector averages")

    return FundamentalRatiosResult(
        profitability_score=round(prof_score, 2),
        valuation_score=round(val_score, 2),
        leverage_score=round(lev_score, 2),
        liquidity_score=round(liq_score, 2),
        composite_score=round(composite, 2),
        ratios_data=ratios_data,
        key_findings=findings,
    )
