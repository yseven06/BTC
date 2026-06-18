"""
TradeMinds AI – Macro & Fundamental Data Collector

Aggregates data that is not coin/stock specific but moves entire markets:

  • TCMB EVDS  → Türkiye policy rate, CPI, USD/TRY (no key)
  • FRED       → US Fed Funds Rate, CPI, M2, DXY, 10Y yield (free API key)
  • KAP        → BIST company disclosures (public RSS feed)

KAP and TCMB endpoints are public — no auth needed. FRED requires a
free API key set via the FRED_API_KEY environment variable; if missing,
the collector returns None for FRED-sourced fields.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class MacroCollector:
    """Public macroeconomic data collector (TCMB + FRED + KAP)."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=12.0)
        # Read from settings (which loads from .env). Fallback to OS env.
        settings = get_settings()
        self._fred_key = (
            getattr(settings, "FRED_API_KEY", "")
            or os.environ.get("FRED_API_KEY", "")
        ).strip()

    # ── TCMB (Turkish Central Bank) ──────────────────────────────────────────

    async def fetch_tcmb_usd_try(self) -> Optional[float]:
        """
        USD/TRY effective selling rate from TCMB today.csv (no auth).
        Returns latest rate or None on failure.
        """
        try:
            r = await self.client.get("https://www.tcmb.gov.tr/kurlar/today.xml")
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for currency in root.findall("Currency"):
                if currency.get("Kod") == "USD":
                    fx = currency.findtext("ForexSelling")
                    return float(fx) if fx else None
        except Exception as exc:
            logger.debug("TCMB USD/TRY fetch failed: %s", exc)
        return None

    async def fetch_tcmb_eur_try(self) -> Optional[float]:
        try:
            r = await self.client.get("https://www.tcmb.gov.tr/kurlar/today.xml")
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for currency in root.findall("Currency"):
                if currency.get("Kod") == "EUR":
                    fx = currency.findtext("ForexSelling")
                    return float(fx) if fx else None
        except Exception:
            return None
        return None

    # ── FRED (US Macro) ──────────────────────────────────────────────────────

    async def fetch_fred_series(self, series_id: str) -> Optional[float]:
        """
        Fetch the most recent observation for a FRED series.

        Common series_ids:
          • FEDFUNDS   — Federal Funds Effective Rate
          • CPIAUCSL   — CPI, all urban consumers
          • DGS10      — 10-year Treasury yield
          • DTWEXBGS   — Broad USD index
          • M2SL       — M2 money supply
        """
        if not self._fred_key:
            return None
        try:
            r = await self.client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._fred_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
            )
            r.raise_for_status()
            obs = r.json().get("observations", [])
            if not obs:
                return None
            val = obs[0].get("value")
            if val in (None, ".", ""):
                return None
            return float(val)
        except Exception as exc:
            logger.debug("FRED %s fetch failed: %s", series_id, exc)
            return None

    async def fetch_us_macro_snapshot(self) -> Dict[str, Optional[float]]:
        """Bundle the headline US macro indicators in one call."""
        if not self._fred_key:
            return {
                "fed_funds_rate":   None,
                "cpi":              None,
                "ten_year_yield":   None,
                "usd_broad_index":  None,
                "configured":       False,
            }
        ff, cpi, y10, dxy = await asyncio.gather(
            self.fetch_fred_series("FEDFUNDS"),
            self.fetch_fred_series("CPIAUCSL"),
            self.fetch_fred_series("DGS10"),
            self.fetch_fred_series("DTWEXBGS"),
        )
        return {
            "fed_funds_rate": ff,
            "cpi": cpi,
            "ten_year_yield": y10,
            "usd_broad_index": dxy,
            "configured": True,
        }

    # ── KAP (BIST company disclosures) ───────────────────────────────────────

    async def fetch_kap_disclosures(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Latest KAP material disclosures (RSS feed). Returns title, link, pubdate.
        """
        try:
            r = await self.client.get("https://www.kap.org.tr/tr/api/anasayfa-disclosures")
            r.raise_for_status()
            data = r.json()
            items = []
            for d in data[:limit] if isinstance(data, list) else []:
                items.append({
                    "title":      d.get("baslik") or d.get("title"),
                    "company":    d.get("sirket") or d.get("companyName"),
                    "published":  d.get("yayinTarihi") or d.get("publishDate"),
                    "category":   d.get("kategori"),
                    "url":        f"https://www.kap.org.tr{d.get('url')}" if d.get("url") else None,
                })
            return items
        except Exception as exc:
            logger.debug("KAP fetch failed: %s", exc)
            return []

    async def close(self) -> None:
        await self.client.aclose()
