"""
Zate Trade – On-Chain Data Collector

Aggregates free, public on-chain metrics from multiple sources.
No API keys required — uses public endpoints with reasonable timeouts.

Sources:
  * Blockchain.info  → BTC hash rate, tx volume, transaction count
  * Mempool.space    → BTC mempool size, fees, congestion
  * Alternative.me   → Crypto Fear & Greed index
  * CoinGecko        → coin metadata: market cap rank, ATH distance, dev/social scores
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.services.dependency_health import (
    EMPTY,
    OK,
    StatusMemory,
    classify_exception,
    worst_status,
)

logger = logging.getLogger(__name__)

_ONCHAIN_CACHE: Dict[str, Any] = {}
_ONCHAIN_CACHE_EXPIRY: Dict[str, float] = {}

FNG_CACHE_TTL = 300       # 5 minutes
BTC_NET_CACHE_TTL = 300   # 5 minutes
GECKO_CACHE_TTL = 1800    # 30 minutes

# CP-DEP-HEALTH-1 — parallel record of what produced each cached value. This
# collector caches FAILURES (`_ONCHAIN_CACHE[key] = fallback`, 60 s) and serves
# them back indistinguishably from real data; this is what makes that visible.
# It touches no cache key, TTL or eviction rule.
_ONCHAIN_STATUS = StatusMemory()


class OnchainCollector:
    """Fetches on-chain market metrics from public sources."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=10.0)
        # Written by every fetch below, read by OnchainEngine for telemetry only.
        self.last_status: Dict[str, Dict[str, Any]] = {}

    def _note(self, key: str, status: str, *, cached: bool = False,
              age_s: Optional[float] = None,
              components: Optional[Dict[str, str]] = None) -> None:
        """Record one fetch outcome. Never raises."""
        try:
            entry: Dict[str, Any] = {
                "fetch_status": status, "served_from_cache": bool(cached),
                "data_freshness_s": age_s,
            }
            if components:
                entry["components"] = dict(components)
            self.last_status[key] = entry
            if not cached:
                _ONCHAIN_STATUS.record(key, status)
        except Exception:  # noqa: BLE001 — observability may never break a fetch
            pass

    async def fetch_btc_network(self) -> Dict[str, Any]:
        """
        Bitcoin network stats from blockchain.info & mempool.space.
        Returns dict with hash_rate, tx_count_24h, mempool_size, fast_fee.
        """
        now = time.time()
        cache_key = "btc_network"
        if cache_key in _ONCHAIN_CACHE and now < _ONCHAIN_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info("[OnchainCollector] Using cached BTC network stats")
            seen = _ONCHAIN_STATUS.lookup(cache_key)
            self._note(cache_key, seen["status"], cached=True, age_s=seen["age_s"])
            return _ONCHAIN_CACHE[cache_key]

        # Per-endpoint outcomes for the three-way fan-out below. This call merges
        # whatever came back and caches the result as a success for 300 s even
        # when two of three endpoints failed, so a single aggregate status would
        # hide the partial case entirely.
        endpoint_status: Dict[str, str] = {}

        out: Dict[str, Any] = {
            "hash_rate_ths": None,
            "tx_count_24h": None,
            "mempool_tx_count": None,
            "fast_fee_sat_vb": None,
        }

        async def _get(url: str, tag: str) -> Optional[Any]:
            try:
                r = await self.client.get(url)
                r.raise_for_status()
                payload = r.json() if "json" in r.headers.get("content-type", "") else r.text
                # `tag` is a fixed literal from the three call sites below — the
                # URL itself is never recorded.
                endpoint_status[tag] = OK if payload else EMPTY
                return payload
            except Exception as exc:
                logger.debug("Onchain fetch failed (%s): %s", url, exc)
                endpoint_status[tag] = classify_exception(exc)
                return None

        results = await asyncio.gather(
            _get("https://api.blockchain.info/stats", "stats"),
            _get("https://mempool.space/api/mempool", "mempool"),
            _get("https://mempool.space/api/v1/fees/recommended", "fees"),
        )
        stats, mempool, fees = results

        if isinstance(stats, dict):
            out["hash_rate_ths"]    = stats.get("hash_rate")
            out["tx_count_24h"]     = stats.get("n_tx")
            out["miners_revenue"]   = stats.get("miners_revenue_usd")
            out["btc_in_circulation"] = stats.get("totalbc")

        if isinstance(mempool, dict):
            out["mempool_tx_count"] = mempool.get("count")
            out["mempool_vsize"]    = mempool.get("vsize")

        if isinstance(fees, dict):
            out["fast_fee_sat_vb"]   = fees.get("fastestFee")
            out["medium_fee_sat_vb"] = fees.get("halfHourFee")

        _ONCHAIN_CACHE[cache_key] = out
        _ONCHAIN_CACHE_EXPIRY[cache_key] = now + BTC_NET_CACHE_TTL
        self._note(cache_key, worst_status(endpoint_status.values()),
                   components=endpoint_status)
        return out

    async def fetch_fear_greed(self) -> Dict[str, Any]:
        """Crypto Fear & Greed Index from alternative.me."""
        now = time.time()
        cache_key = "fear_greed"
        if cache_key in _ONCHAIN_CACHE and now < _ONCHAIN_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info("[OnchainCollector] Using cached Fear & Greed index")
            seen = _ONCHAIN_STATUS.lookup(cache_key)
            self._note(cache_key, seen["status"], cached=True, age_s=seen["age_s"])
            return _ONCHAIN_CACHE[cache_key]

        try:
            r = await self.client.get("https://api.alternative.me/fng/?limit=2")
            r.raise_for_status()
            data = r.json()
            items = data.get("data", [])
            if not items:
                res = {"value": None, "classification": None, "delta_24h": None}
                _ONCHAIN_CACHE[cache_key] = res
                _ONCHAIN_CACHE_EXPIRY[cache_key] = now + FNG_CACHE_TTL
                self._note(cache_key, EMPTY)
                return res
            current = int(items[0]["value"])
            prev    = int(items[1]["value"]) if len(items) > 1 else current
            res = {
                "value": current,
                "classification": items[0].get("value_classification"),
                "delta_24h": current - prev,
            }
            _ONCHAIN_CACHE[cache_key] = res
            _ONCHAIN_CACHE_EXPIRY[cache_key] = now + FNG_CACHE_TTL
            self._note(cache_key, OK)
            return res
        except Exception as exc:
            logger.debug("Fear & Greed fetch failed: %s", exc)
            fallback = {"value": None, "classification": None, "delta_24h": None}
            # Cache brief failure state to avoid hammering on fail
            _ONCHAIN_CACHE[cache_key] = fallback
            _ONCHAIN_CACHE_EXPIRY[cache_key] = now + 60  # Cache failure for 1 minute
            # The cached value above is a FAILURE. Recording that here is what
            # lets the next 60 s of cache hits report `stale_cache` instead of
            # presenting the failure as data.
            self._note(cache_key, classify_exception(exc))
            return fallback

    async def fetch_coin_metadata(self, coin_id: str) -> Dict[str, Any]:
        """
        Fetch supply/social/dev metrics for a coin from CoinGecko.
        coin_id is the gecko id (e.g. "bitcoin", "ethereum").
        """
        now = time.time()
        cache_key = f"gecko_meta_{coin_id}"
        if cache_key in _ONCHAIN_CACHE and now < _ONCHAIN_CACHE_EXPIRY.get(cache_key, 0.0):
            logger.info(f"[OnchainCollector] Using cached CoinGecko metadata for {coin_id}")
            seen = _ONCHAIN_STATUS.lookup(cache_key)
            self._note(cache_key, seen["status"], cached=True, age_s=seen["age_s"])
            return _ONCHAIN_CACHE[cache_key]

        try:
            r = await self.client.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "true",
                    "developer_data": "true",
                    "sparkline": "false",
                },
            )
            r.raise_for_status()
            data = r.json()
            md = data.get("market_data", {}) or {}
            ath  = md.get("ath", {}).get("usd")
            cur  = md.get("current_price", {}).get("usd")
            ath_pct = md.get("ath_change_percentage", {}).get("usd")
            res = {
                "market_cap_rank": data.get("market_cap_rank"),
                "current_price_usd": cur,
                "ath_usd": ath,
                "ath_distance_pct": ath_pct,  # negative = below ATH
                "circulating_supply": md.get("circulating_supply"),
                "total_supply":      md.get("total_supply"),
                "max_supply":        md.get("max_supply"),
                "developer_score":   data.get("developer_score"),
                "community_score":   data.get("community_score"),
                "public_interest_score": data.get("public_interest_score"),
            }
            _ONCHAIN_CACHE[cache_key] = res
            _ONCHAIN_CACHE_EXPIRY[cache_key] = now + GECKO_CACHE_TTL
            self._note(cache_key, OK if res else EMPTY)
            return res
        except Exception as exc:
            logger.debug("CoinGecko metadata fetch failed for %s: %s", coin_id, exc)
            fallback = {}
            # Cache brief failure state to avoid hammering on fail
            _ONCHAIN_CACHE[cache_key] = fallback
            _ONCHAIN_CACHE_EXPIRY[cache_key] = now + 60
            self._note(cache_key, classify_exception(exc))
            return fallback

    async def close(self) -> None:
        await self.client.aclose()


# Symbol → CoinGecko id mapping for the major assets we track.
SYMBOL_TO_GECKO_ID: Dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2",
    "DOTUSDT":  "polkadot",
    "MATICUSDT": "matic-network",
    "LINKUSDT": "chainlink",
    "ATOMUSDT": "cosmos",
}


def symbol_to_gecko_id(symbol: str) -> Optional[str]:
    """Map a trading symbol like BTCUSDT to a CoinGecko coin id."""
    return SYMBOL_TO_GECKO_ID.get(symbol.upper())
