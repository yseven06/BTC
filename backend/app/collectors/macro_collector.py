"""
Zate Trade – Macro & Fundamental Data Collector

Aggregates data that is not coin/stock specific but moves entire markets:

  • TCMB EVDS  → Türkiye policy rate, CPI, USD/TRY (no key)
  • FRED       → US Fed Funds Rate, CPI, M2, DXY, 10Y yield (free API key)
  • KAP        → BIST company disclosures (public RSS feed)

KAP and TCMB endpoints are public — no auth needed. FRED requires a
free API key set via the FRED_API_KEY environment variable; if missing,
the collector returns None for FRED-sourced fields.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from app import log_redaction
from app.config import get_settings
from app.services.dependency_health import (
    EMPTY,
    NOT_CONFIGURED,
    OK,
    StatusMemory,
    classify_exception,
)

logger = logging.getLogger(__name__)

_MACRO_CACHE: Dict[str, Any] = {}
_MACRO_CACHE_EXPIRY: Dict[str, float] = {}

MACRO_CACHE_TTL = 900  # 15 minutes

# CP-MACRO-FRED-FETCH-KILLSWITCH — the `fallback_reason` for "a key exists but
# the fetch is switched off". Distinct from `no_api_key`, which would be a false
# record once a key is stored. `fallback_reason` is free-form in
# dependency_health.engine_entry, and this is NOT a `fetch_status`: adding a
# status would enter `worst_status`'s fixed precedence, and severity ordering is
# not what this describes.
FRED_FETCH_DISABLED_REASON = "fetch_disabled"

# CP-DEP-HEALTH-1 — remembers what produced each cached value so a cache hit can
# say whether it is serving real data or a cached failure. Parallel to the value
# cache above and deliberately separate from it: deleting this line would leave
# every cache key, TTL and eviction rule byte-identical.
_MACRO_STATUS = StatusMemory()


class MacroCollector:
    """Public macroeconomic data collector (TCMB + FRED + KAP)."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=12.0)
        # CP-DEP-HEALTH-1 — parallel status metadata. Every fetch below records
        # what happened here; NOTHING reads it to decide anything, no return
        # value changes shape, and no cache key, TTL or eviction is touched.
        # Keyed by the same cache_key the value cache uses, so the two line up.
        self.last_status: Dict[str, Dict[str, Any]] = {}
        # Read from settings (which loads from .env). Fallback to OS env.
        settings = get_settings()
        raw_key = (
            getattr(settings, "FRED_API_KEY", "")
            or os.environ.get("FRED_API_KEY", "")
        ).strip()

        # CP-MACRO-FRED-FETCH-KILLSWITCH. Two facts that used to be one.
        #
        # `fred_key_present` is INSTANCE STATE and is never returned from any
        # method: `GET /api/v1/macro/snapshot` serves `fetch_us_macro_snapshot()`'s
        # dict verbatim (api/routes/macro.py:28-33), so a field there would
        # publish secret-configuration state on a public surface. Same channel
        # discipline as CP-DEP-HEALTH-1, and for the same reason.
        self.fred_key_present = bool(raw_key)
        self.fred_fetch_enabled = bool(
            getattr(settings, "MACRO_FRED_FETCH_ENABLED", False))

        # THE GATE. Neutralising the key rather than adding a second condition to
        # every call site is deliberate: `if not self._fred_key` already guards
        # `fetch_fred_series` and `fetch_us_macro_snapshot`, so a disabled fetch
        # takes byte-identical code paths to an absent key — including the
        # `_note(NOT_CONFIGURED)` calls and `configured: False` — and there is no
        # third state for a future edit to get wrong.
        self._fred_key = raw_key if self.fred_fetch_enabled else ""

    def _note(self, key: str, status: str, *, cached: bool = False,
              age_s: Optional[float] = None) -> None:
        """Record one fetch outcome. Never raises — telemetry must not decide."""
        try:
            self.last_status[key] = {
                "fetch_status": status, "served_from_cache": bool(cached),
                "data_freshness_s": age_s,
            }
            if not cached:
                _MACRO_STATUS.record(key, status)
        except Exception:  # noqa: BLE001 — observability may never break a fetch
            pass

    # ── TCMB (Turkish Central Bank) ──────────────────────────────────────────

    async def fetch_tcmb_usd_try(self) -> Optional[float]:
        """
        USD/TRY effective selling rate from TCMB today.csv (no auth).
        Returns latest rate or None on failure.
        """
        now = time.time()
        cache_key = "usd_try"
        if cache_key in _MACRO_CACHE and now < _MACRO_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info("[MacroCollector] Using cached USD/TRY rate")
            return _MACRO_CACHE[cache_key]

        try:
            r = await self.client.get("https://www.tcmb.gov.tr/kurlar/today.xml")
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for currency in root.findall("Currency"):
                if currency.get("Kod") == "USD":
                    fx = currency.findtext("ForexSelling")
                    val = float(fx) if fx else None
                    if val is not None:
                        _MACRO_CACHE[cache_key] = val
                        _MACRO_CACHE_EXPIRY[cache_key] = now + MACRO_CACHE_TTL
                    return val
        except Exception as exc:
            logger.debug("TCMB USD/TRY fetch failed: %s", exc)
        return None

    async def fetch_tcmb_eur_try(self) -> Optional[float]:
        now = time.time()
        cache_key = "eur_try"
        if cache_key in _MACRO_CACHE and now < _MACRO_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info("[MacroCollector] Using cached EUR/TRY rate")
            return _MACRO_CACHE[cache_key]

        try:
            r = await self.client.get("https://www.tcmb.gov.tr/kurlar/today.xml")
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for currency in root.findall("Currency"):
                if currency.get("Kod") == "EUR":
                    fx = currency.findtext("ForexSelling")
                    val = float(fx) if fx else None
                    if val is not None:
                        _MACRO_CACHE[cache_key] = val
                        _MACRO_CACHE_EXPIRY[cache_key] = now + MACRO_CACHE_TTL
                    return val
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
            self._note(f"fred_{series_id}", NOT_CONFIGURED)
            return None

        now = time.time()
        cache_key = f"fred_{series_id}"
        if cache_key in _MACRO_CACHE and now < _MACRO_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info(f"[MacroCollector] Using cached FRED series {series_id}")
            seen = _MACRO_STATUS.lookup(cache_key)
            self._note(cache_key, seen["status"], cached=True, age_s=seen["age_s"])
            return _MACRO_CACHE[cache_key]

        # CP-MACRO-SHADOW-FETCH-SECRET-REDACTION — the SAME latent leak lives
        # here: httpx logs this request's full URL at INFO, and the URL below
        # carries `api_key`. The shadow path proved it in production on
        # 2026-07-31; this path has simply never been switched on. Armed before
        # the request rather than relying on `app.main` having run, because a
        # script that imports this collector directly is exactly the case that
        # would otherwise be unprotected. Idempotent.
        log_redaction.install()

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
                self._note(cache_key, EMPTY)
                return None
            val = obs[0].get("value")
            if val in (None, ".", ""):
                self._note(cache_key, EMPTY)
                return None
            result_val = float(val)
            _MACRO_CACHE[cache_key] = result_val
            _MACRO_CACHE_EXPIRY[cache_key] = now + MACRO_CACHE_TTL
            self._note(cache_key, OK)
            return result_val
        except Exception as exc:
            logger.debug("FRED %s fetch failed: %s", series_id, exc)
            # Only the exception's TYPE (and, for an HTTP error, its numeric
            # status) reaches the record — never `str(exc)`, which can carry a
            # URL with the api_key query parameter in it.
            self._note(cache_key, classify_exception(exc))
            return None

    async def fetch_us_macro_snapshot(self) -> Dict[str, Optional[float]]:
        """Bundle the headline US macro indicators in one call."""
        if not self._fred_key:
            # This branch returns before any fetch_fred_series call, so nothing
            # else would record the state. `configured: False` below already says
            # the key is absent; this makes it legible on the same channel as
            # every other outcome.
            for series in ("FEDFUNDS", "CPIAUCSL", "DGS10", "DTWEXBGS"):
                self._note(f"fred_{series}", NOT_CONFIGURED)
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

    @staticmethod
    def _parse_kap_date(raw: Optional[str]) -> Optional[str]:
        """KAP's "DD.MM.YYYY HH:MM:SS" is Turkey-local time with no offset
        marker — attach +03:00 explicitly so consumers get an unambiguous
        ISO 8601 timestamp instead of a string `Date()` can't parse."""
        if not raw:
            return None
        try:
            dt = datetime.strptime(raw, "%d.%m.%Y %H:%M:%S")
            return dt.replace(tzinfo=timezone(timedelta(hours=3))).isoformat()
        except ValueError:
            return None

    async def fetch_kap_disclosures(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Latest KAP material disclosures. KAP relaunched their site as a
        Next.js app — the old GET /tr/api/anasayfa-disclosures endpoint is
        gone; the real one is this POST search endpoint (memberTypes IGS =
        listed companies, DDK = independent audit firms — both needed to
        match what the KAP website itself shows on its homepage feed).
        """
        try:
            # Query a 2-day window, not just "today" — KAP's own notion of
            # "today" runs on Turkey-local time, and comparing strictly
            # against our UTC "today" string can miss everything near
            # midnight in either direction.
            today = datetime.utcnow()
            yesterday = today - timedelta(days=1)
            r = await self.client.post(
                "https://www.kap.org.tr/tr/api/disclosure/list/main",
                json={
                    "fromDate": yesterday.strftime("%d.%m.%Y"),
                    "toDate": today.strftime("%d.%m.%Y"),
                    "memberTypes": ["IGS", "DDK"],
                },
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            data = r.json()
            items = []
            for d in (data if isinstance(data, list) else [])[:limit]:
                basic = d.get("disclosureBasic") or {}
                disclosure_id = basic.get("disclosureId")
                items.append({
                    "title":     basic.get("title"),
                    "company":   basic.get("companyTitle"),
                    # KAP returns "DD.MM.YYYY HH:MM:SS" (Turkey-local, no
                    # offset) — JS `new Date()` can't parse that reliably,
                    # so it renders as "NaN gün önce" client-side. Convert
                    # to ISO 8601 here, at the source, rather than pushing
                    # a non-standard format on to every consumer.
                    "published": self._parse_kap_date(basic.get("publishDate")),
                    "category":  basic.get("disclosureCategory"),
                    "url":       f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}" if disclosure_id else None,
                })
            return items
        except Exception as exc:
            logger.debug("KAP fetch failed: %s", exc)
            return []

    async def close(self) -> None:
        await self.client.aclose()
