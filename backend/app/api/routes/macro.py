"""
TradeMinds AI – Macro & Market-Wide Data Routes

Surfaces public macroeconomic data and BIST disclosures used by the
macro engine and frontend dashboards.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter

from app.collectors.macro_collector import MacroCollector

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/snapshot", summary="Macro snapshot — TR + US")
async def macro_snapshot() -> Dict[str, Any]:
    """Bundle TCMB FX + US headline macro into a single payload."""
    collector = MacroCollector()
    try:
        usd_try = await collector.fetch_tcmb_usd_try()
        eur_try = await collector.fetch_tcmb_eur_try()
        us = await collector.fetch_us_macro_snapshot()
        return {
            "turkey": {
                "usd_try": usd_try,
                "eur_try": eur_try,
            },
            "united_states": us,
        }
    finally:
        await collector.close()


@router.get("/kap-disclosures", summary="Latest KAP disclosures (BIST)")
async def kap_disclosures(limit: int = 15) -> Dict[str, Any]:
    """Latest material disclosures for BIST companies (public RSS)."""
    collector = MacroCollector()
    try:
        items = await collector.fetch_kap_disclosures(limit=limit)
        return {"items": items, "count": len(items)}
    finally:
        await collector.close()


@router.get("/bybit-funding/{symbol}", summary="Bybit funding rate for a perp symbol")
async def bybit_funding(symbol: str) -> Dict[str, Any]:
    """Current funding rate from Bybit (useful sentiment proxy)."""
    from app.collectors.bybit_collector import BybitCollector
    bybit = BybitCollector()
    try:
        return await bybit.fetch_funding_rate(symbol)
    finally:
        await bybit.close()
