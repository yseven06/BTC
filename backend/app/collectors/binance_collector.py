"""
TradeMinds AI – Binance Market Data Collector

Fetches live prices, orderbooks, and historical candlesticks from the Binance API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx
import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class BinanceCollector(BaseCollector):
    """Binance Spot API Collector for Crypto Assets."""

    def __init__(self) -> None:
        self.base_url = "https://api.binance.com/api/v3"
        # Shared client for connection pooling
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch historical candlesticks from Binance.

        Timeframes supported: 1m, 5m, 15m, 1h, 4h, 1d, 1w.
        """
        # Format symbol to uppercase and remove slashes (e.g. BTC/USDT -> BTCUSDT)
        formatted_symbol = symbol.replace("/", "").upper()
        
        # Map timeframes
        tf_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"
        }
        interval = tf_map.get(timeframe, "1h")

        url = f"{self.base_url}/klines"
        params = {
            "symbol": formatted_symbol,
            "interval": interval,
            "limit": limit
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Parse Kline list to DataFrame
            # Index: Open Time
            columns = [
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
            ]
            df = pd.DataFrame(data, columns=columns)
            
            # Convert types to float
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)

            # Set datetime index
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
            df.set_index("timestamp", inplace=True)
            
            # Select required columns
            df = df[["open", "high", "low", "close", "volume"]]
            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV from Binance for {symbol}: {str(e)}")
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price and 24h market stats."""
        formatted_symbol = symbol.replace("/", "").upper()
        url = f"{self.base_url}/ticker/24hr"
        params = {"symbol": formatted_symbol}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return {
                "current_price": float(data["lastPrice"]),
                "price_change_24h": float(data["priceChange"]),
                "price_change_percentage_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker from Binance for {symbol}: {str(e)}")
            raise

    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Fetch orderbook depth."""
        formatted_symbol = symbol.replace("/", "").upper()
        url = f"{self.base_url}/depth"
        params = {"symbol": formatted_symbol, "limit": 100}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Map to standardized format
            return {
                "bids": [[float(price), float(qty)] for price, qty in data.get("bids", [])],
                "asks": [[float(price), float(qty)] for price, qty in data.get("asks", [])],
            }
        except Exception as e:
            logger.error(f"Error fetching orderbook from Binance for {symbol}: {str(e)}")
            raise

    async def close(self) -> None:
        """Close client connection pool."""
        await self.client.aclose()
