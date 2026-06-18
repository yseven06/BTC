"""
TradeMinds AI – CoinGecko Market Data Collector

Fetches market cap, supply details, tokenomics details, and metadata
for cryptocurrency assets.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx
import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class CoinGeckoCollector(BaseCollector):
    """CoinGecko API Collector for Crypto Metadata and Tokenomics."""

    def __init__(self) -> None:
        self.base_url = "https://api.coingecko.com/api/v3"
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch historical price charts from CoinGecko.

        Note: CoinGecko serves charts in days format (e.g. 1 day, 7 days, 30 days).
        We approximate to daily bars.
        """
        coin_id = self._symbol_to_id(symbol)
        url = f"{self.base_url}/coins/{coin_id}/market_chart"
        
        # Approximate days lookback
        days = "30"
        if limit > 90:
            days = "365"
        elif limit > 30:
            days = "90"

        params = {
            "vs_currency": "usd",
            "days": days,
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])

            # Compile into DataFrame
            df_prices = pd.DataFrame(prices, columns=["time", "close"])
            df_vols = pd.DataFrame(volumes, columns=["time", "volume"])
            
            df = pd.merge(df_prices, df_vols, on="time")
            df["timestamp"] = pd.to_datetime(df["time"], unit="ms")
            df.set_index("timestamp", inplace=True)
            
            # Since CoinGecko chart only yields price/volume, we approximate Open/High/Low to close
            df["open"] = df["close"].shift(1).fillna(df["close"])
            df["high"] = df[["open", "close"]].max(axis=1)
            df["low"] = df[["open", "close"]].min(axis=1)
            
            df = df[["open", "high", "low", "close", "volume"]]
            return df.tail(limit)

        except Exception as e:
            logger.error(f"Error fetching chart from CoinGecko for {symbol}: {str(e)}")
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch simple price and market metrics."""
        coin_id = self._symbol_to_id(symbol)
        url = f"{self.base_url}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": coin_id,
            "order": "market_cap_desc",
            "per_page": 1,
            "page": 1,
            "sparkline": False
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            results = response.json()
            if not results:
                raise ValueError(f"No results found for symbol {symbol}")
            
            data = results[0]
            return {
                "current_price": float(data["current_price"]),
                "price_change_24h": float(data.get("price_change_24h") or 0),
                "price_change_percentage_24h": float(data.get("price_change_percentage_24h") or 0),
                "high_24h": float(data.get("high_24h") or data["current_price"]),
                "low_24h": float(data.get("low_24h") or data["current_price"]),
                "volume_24h": float(data.get("total_volume") or 0),
                # Metadata fields
                "market_cap": float(data.get("market_cap") or 0),
                "fdv": float(data.get("fully_diluted_valuation") or 0),
                "circulating_supply": float(data.get("circulating_supply") or 0),
                "total_supply": float(data.get("total_supply") or 0),
                "max_supply": float(data.get("max_supply") or 0),
            }
        except Exception as e:
            logger.error(f"Error fetching market info from CoinGecko for {symbol}: {str(e)}")
            raise

    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """CoinGecko does not support orderbooks. Returns empty bids/asks."""
        return {"bids": [], "asks": []}

    @staticmethod
    def _symbol_to_id(symbol: str) -> str:
        """Map common ticker symbols to CoinGecko IDs."""
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "ADA": "cardano",
            "XRP": "ripple",
            "DOT": "polkadot",
            "DOGE": "dogecoin",
            "AVAX": "avalanche-2",
        }
        clean_symbol = symbol.replace("/USDT", "").replace("USDT", "").upper()
        return mapping.get(clean_symbol, clean_symbol.lower())

    async def close(self) -> None:
        await self.client.aclose()
