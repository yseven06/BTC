"""
TradeMinds AI – Crypto Fundamentals Analysis Helpers

Analyzes cryptocurrency-specific fundamentals: Circulating supply ratio, Market Cap/FDV,
tokenomics scoring, and network valuation metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class CryptoFundamentalsResult:
    tokenomics_score: float  # 0-100
    valuation_score: float   # 0-100
    composite_score: float   # 0-100
    fundamental_data: Dict[str, Any]
    key_findings: List[str]


def analyze_crypto_fundamentals(
    symbol: str,
    crypto_data: Dict[str, Any],
) -> CryptoFundamentalsResult:
    """Analyze tokenomics, supply schedules, and valuation metrics for a crypto asset."""
    findings = []
    
    # Extract data from CoinGecko or another metadata payload
    market_data = crypto_data.get("market_data", {})
    circulating_supply = market_data.get("circulating_supply") or crypto_data.get("circulating_supply")
    total_supply = market_data.get("total_supply") or crypto_data.get("total_supply")
    max_supply = market_data.get("max_supply") or crypto_data.get("max_supply")
    mcap = market_data.get("market_cap", {}).get("usd") or crypto_data.get("market_cap")
    fdv = market_data.get("fully_diluted_valuation", {}).get("usd") or crypto_data.get("fdv")

    # 1. Supply Dilution check (Circulating vs Max/Total supply)
    circ_ratio = 100.0
    if circulating_supply and max_supply:
        circ_ratio = (circulating_supply / max_supply) * 100.0
    elif circulating_supply and total_supply:
        circ_ratio = (circulating_supply / total_supply) * 100.0

    tok_score = 50.0
    if circ_ratio > 90.0:
        tok_score += 25.0
        findings.append(f"Highly deflationary/mature supply structure ({circ_ratio:.1f}% circulating)")
    elif circ_ratio > 70.0:
        tok_score += 15.0
        findings.append(f"Reasonable supply distribution ({circ_ratio:.1f}% circulating)")
    elif circ_ratio < 40.0:
        tok_score -= 20.0
        findings.append(f"Inflation warning: High future dilution potential ({circ_ratio:.1f}% circulating)")

    # 2. Market Cap / FDV Ratio
    mcap_fdv_ratio = 1.0
    val_score = 50.0
    if mcap and fdv:
        mcap_fdv_ratio = mcap / fdv
        if mcap_fdv_ratio > 0.85:
            val_score += 20.0
            findings.append("Low dilution risk (Market Cap / FDV ratio > 0.85)")
        elif mcap_fdv_ratio < 0.40:
            val_score -= 20.0
            findings.append(f"Dilution risk: Substantial unlock pressure (Market Cap / FDV is {mcap_fdv_ratio:.2f})")

    # Composite Score
    composite = tok_score * 0.50 + val_score * 0.50

    fundamental_data = {
        "circulating_supply": circulating_supply,
        "total_supply": total_supply,
        "max_supply": max_supply,
        "market_cap": mcap,
        "fdv": fdv,
        "circulating_ratio": circ_ratio,
        "mcap_fdv_ratio": mcap_fdv_ratio,
    }

    if not findings:
        findings.append("Crypto supply metrics are standard and stable")

    return CryptoFundamentalsResult(
        tokenomics_score=round(tok_score, 2),
        valuation_score=round(val_score, 2),
        composite_score=round(composite, 2),
        fundamental_data=fundamental_data,
        key_findings=findings,
    )
