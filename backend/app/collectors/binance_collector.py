"""
Zate Trade – Binance Market Data Collector

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

    def __init__(self, include_extended: bool = False) -> None:
        """`include_extended` keeps the four optional kline fields.

        DEFAULT FALSE, AND THAT DEFAULT IS THE SAFETY ARGUMENT. This collector is
        shared by the signal sweeps, the tracker, the price and signal routes,
        the backtesting engine and the AI decision engine. Every one of them
        constructs `BinanceCollector()` with no arguments, so every one of them
        keeps a byte-identical six-column frame. Only a caller that explicitly
        asks — currently just the dormant OHLCV collector — sees the wider frame.

        The alternative, widening `fetch_ohlcv` for everybody, would have put a
        schema-shaped change in the live trading path to benefit a shadow store.
        """
        self.base_url = "https://api.binance.com/api/v3"
        # Shared client for connection pooling
        self.include_extended = include_extended
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        """Fetch historical candlesticks from Binance.

        Timeframes supported: 1m, 5m, 15m, 1h, 4h, 1d, 1w.

        end_time_ms (optional): Binance `endTime` in unix milliseconds —
        returns the `limit` candles ending at/before this point instead of
        the most recent ones. Used to replay a chart's state as of a past
        moment (e.g. a closed signal's resolution time), not just "now".
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
        params: Dict[str, Any] = {
            "symbol": formatted_symbol,
            "interval": interval,
            "limit": limit
        }
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

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

            # Set datetime index. UTC-aware: Binance timestamps are UTC, and
            # saying so lets a consumer compare them against `now` without
            # having to know that. `.timestamp()` and `tz_localize(None)` both
            # behave identically on aware and naive indexes, so the existing
            # chart and tracker consumers are unaffected.
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)

            # close_time is field 6 of every kline and is the exchange's own
            # answer to "has this bar finished?". It used to be dropped here,
            # which left the decision path unable to tell a closed bar from the
            # one still forming — see app/services/candle_window.py. Carried as a
            # column rather than replacing anything: every consumer reads OHLCV
            # by name, so an extra column changes nothing for them.
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

            # The forming candle is deliberately NOT removed here. The chart
            # (prices.py) and the tracker (tracker.py:294-311) both want it; only
            # the decision path needs it excluded, and that is its own concern.
            keep = ["open", "high", "low", "close", "volume", "close_time"]
            if self.include_extended:
                # Binance supplies these on every kline; they are optional in the
                # OHLCV schema, so a malformed value becomes NULL rather than
                # failing the bar. Coerced individually: one bad field must not
                # discard the other three, nor the bar itself.
                for src_col, out_col, caster in (
                    ("quote_asset_volume", "quote_volume", "float64"),
                    ("number_of_trades", "trade_count", "Int64"),
                    ("taker_buy_base_asset_volume", "taker_buy_base_volume", "float64"),
                    ("taker_buy_quote_asset_volume", "taker_buy_quote_volume", "float64"),
                ):
                    if src_col in df.columns:
                        df[out_col] = pd.to_numeric(df[src_col], errors="coerce")
                        if caster == "Int64":
                            df[out_col] = df[out_col].astype("Int64")
                        keep.append(out_col)
            df = df[keep]
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
