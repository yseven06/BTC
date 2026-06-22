"""
TradeMinds AI – Yahoo Finance BIST Collector

Uses yfinance to fetch market data and balance sheets for BIST stocks (symbol format: THYAO.IS).
Runs blocking yfinance calls inside asyncio.to_thread for high concurrency.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class YahooCollector(BaseCollector):
    """Yahoo Finance Collector for BIST Stocks."""

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        end_date: Optional[int] = None,
    ) -> pd.DataFrame:
        """Fetch historical prices using yfinance.

        Intervals supported: 15m, 1h, 1d, 1wk.
        Runs inside to_thread to keep the event loop non-blocking.

        end_date (optional): unix seconds — fetch a window ending at this
        point instead of "now". Used to replay a chart's past state (e.g. a
        closed signal's resolution time).
        """
        # Format BIST symbols (e.g. THYAO -> THYAO.IS)
        formatted_symbol = symbol.upper()
        if not formatted_symbol.endswith(".IS") and len(formatted_symbol) == 5:
            formatted_symbol = f"{formatted_symbol}.IS"

        tf_map = {
            "15m": "15m", "1h": "1h", "1d": "1d", "1w": "1wk"
        }
        interval = tf_map.get(timeframe, "1d")

        # Select period based on limit
        period = "3mo"
        if limit > 700:
            period = "5y"
        elif limit > 200:
            period = "2y"
        elif limit > 50:
            period = "6mo"

        # yfinance's `period` window always ends "now" — to replay a past
        # state we need `start`/`end` instead, with a lookback wide enough
        # to still gather `limit` candles ending at that point.
        TF_MINUTES = {"15m": 15, "1h": 60, "1d": 1440, "1w": 10080}
        start_dt = end_dt = None
        if end_date is not None:
            end_dt = datetime.fromtimestamp(end_date, tz=timezone.utc)
            lookback_minutes = TF_MINUTES.get(interval, 1440) * limit * 2  # 2x margin for weekends/holidays
            start_dt = end_dt - timedelta(minutes=lookback_minutes)

        def _fetch():
            ticker = yf.Ticker(formatted_symbol)
            if end_dt is not None:
                df = ticker.history(start=start_dt, end=end_dt, interval=interval)
            else:
                df = ticker.history(period=period, interval=interval)
            return df

        try:
            df = await asyncio.to_thread(_fetch)
            if df.empty:
                raise ValueError(f"No yfinance historical data found for {formatted_symbol}")

            # Normalize columns
            df.rename(
                columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume"
                },
                inplace=True
            )
            df = df[["open", "high", "low", "close", "volume"]]
            df.index.name = "timestamp"
            
            return df.tail(limit)

        except Exception as e:
            logger.error(f"Error fetching historical data from yfinance for {symbol}: {str(e)}")
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price and 24h stats."""
        formatted_symbol = symbol.upper()
        if not formatted_symbol.endswith(".IS") and len(formatted_symbol) == 5:
            formatted_symbol = f"{formatted_symbol}.IS"

        def _fetch_info():
            ticker = yf.Ticker(formatted_symbol)
            # Retrieve basic history to get current price and change percentage
            history = ticker.history(period="2d")
            return ticker.info, history

        try:
            info, history = await asyncio.to_thread(_fetch_info)
            
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            price_change = 0.0
            price_change_pct = 0.0

            if not history.empty and len(history) >= 2:
                prev_close = float(history["Close"].iloc[0])
                current_price = float(history["Close"].iloc[-1])
                price_change = current_price - prev_close
                price_change_pct = (price_change / prev_close) * 100.0
            elif current_price is None and not history.empty:
                current_price = float(history["Close"].iloc[-1])

            # Safety fallback for current price
            if current_price is None:
                current_price = 0.0

            return {
                "current_price": float(current_price),
                "price_change_24h": float(price_change),
                "price_change_percentage_24h": float(price_change_pct),
                "high_24h": float(info.get("dayHigh") or current_price),
                "low_24h": float(info.get("dayLow") or current_price),
                "volume_24h": float(info.get("volume") or 0.0),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker from yfinance for {symbol}: {str(e)}")
            raise

    async def fetch_financials(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data sheets (income statement, balance sheet)."""
        formatted_symbol = symbol.upper()
        if not formatted_symbol.endswith(".IS") and len(formatted_symbol) == 5:
            formatted_symbol = f"{formatted_symbol}.IS"

        def _fetch_sheets():
            ticker = yf.Ticker(formatted_symbol)
            # retrieve info dict, financials and balance sheet DataFrames
            info = ticker.info
            financials = ticker.quarterly_financials
            balance_sheet = ticker.quarterly_balance_sheet
            return info, financials, balance_sheet

        try:
            info, financials, balance_sheet = await asyncio.to_thread(_fetch_sheets)
            
            # Map financial data to standard dictionaries
            return {
                "info": info,
                "financials": financials.to_dict() if not financials.empty else {},
                "balance_sheet": balance_sheet.to_dict() if not balance_sheet.empty else {},
            }
        except Exception as e:
            logger.error(f"Error fetching financials from yfinance for {symbol}: {str(e)}")
            return {"info": {}, "financials": {}, "balance_sheet": {}}

    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Yahoo Finance does not serve orderbook depth. Return empty."""
        return {"bids": [], "asks": []}

    async def close(self) -> None:
        """No-op: yfinance manages its own session per call, nothing to close."""
        return None
