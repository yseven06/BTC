"""
TradeMinds AI – Bybit Market Data Collector

Public Bybit v5 REST API. No API key required for market data.
Useful for futures/perp data and as a fallback to Binance.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# Bybit v5 timeframe codes (minutes)
_BYBIT_TF = {
    "1m":   "1",   "5m":   "5",   "15m": "15",
    "30m":  "30",  "1h":   "60",  "4h":  "240",
    "1d":   "D",   "1w":   "W",
}


class BybitCollector(BaseCollector):
    """Bybit linear (USDT-margined) public market data collector."""

    def __init__(self) -> None:
        self.base_url = "https://api.bybit.com/v5"
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch klines from Bybit linear futures."""
        formatted = symbol.replace("/", "").upper()
        interval  = _BYBIT_TF.get(timeframe, "60")

        try:
            r = await self.client.get(
                f"{self.base_url}/market/kline",
                params={
                    "category": "linear",
                    "symbol": formatted,
                    "interval": interval,
                    "limit": min(limit, 1000),
                },
            )
            r.raise_for_status()
            data = r.json()
            klines = data.get("result", {}).get("list", [])
            # Bybit returns newest first — reverse for chronological order
            klines = list(reversed(klines))

            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume", "turnover"
            ])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df["timestamp"] = pd.to_datetime(df["open_time"].astype(int), unit="ms")
            df.set_index("timestamp", inplace=True)
            return df[["open", "high", "low", "close", "volume"]]
        except Exception as exc:
            logger.error("Bybit OHLCV fetch failed for %s: %s", symbol, exc)
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch 24h ticker stats."""
        formatted = symbol.replace("/", "").upper()
        try:
            r = await self.client.get(
                f"{self.base_url}/market/tickers",
                params={"category": "linear", "symbol": formatted},
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("result", {}).get("list", [])
            if not items:
                return {}
            t = items[0]
            return {
                "current_price": float(t.get("lastPrice", 0)),
                "price_change_24h": float(t.get("price24hPcnt", 0)) * float(t.get("lastPrice", 0)),
                "price_change_percentage_24h": float(t.get("price24hPcnt", 0)) * 100,
                "high_24h": float(t.get("highPrice24h", 0)),
                "low_24h":  float(t.get("lowPrice24h", 0)),
                "volume_24h": float(t.get("volume24h", 0)),
                "open_interest": float(t.get("openInterest", 0)),
                "funding_rate": float(t.get("fundingRate", 0)),
            }
        except Exception as exc:
            logger.error("Bybit ticker fetch failed for %s: %s", symbol, exc)
            raise

    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Fetch orderbook depth."""
        formatted = symbol.replace("/", "").upper()
        try:
            r = await self.client.get(
                f"{self.base_url}/market/orderbook",
                params={"category": "linear", "symbol": formatted, "limit": 50},
            )
            r.raise_for_status()
            result = r.json().get("result", {})
            return {
                "bids": [[float(p), float(q)] for p, q in result.get("b", [])],
                "asks": [[float(p), float(q)] for p, q in result.get("a", [])],
            }
        except Exception as exc:
            logger.error("Bybit orderbook fetch failed for %s: %s", symbol, exc)
            raise

    async def fetch_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Current funding rate — useful signal for perp markets."""
        formatted = symbol.replace("/", "").upper()
        try:
            r = await self.client.get(
                f"{self.base_url}/market/funding/history",
                params={"category": "linear", "symbol": formatted, "limit": 1},
            )
            r.raise_for_status()
            items = r.json().get("result", {}).get("list", [])
            if not items:
                return {"funding_rate": None}
            return {"funding_rate": float(items[0].get("fundingRate", 0))}
        except Exception as exc:
            logger.debug("Bybit funding rate failed: %s", exc)
            return {"funding_rate": None}

    async def close(self) -> None:
        await self.client.aclose()
