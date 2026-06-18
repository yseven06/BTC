"""
TradeMinds AI – Abstract Base Collector

Defines interface protocols that all market collectors (crypto, stocks) must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import pandas as pd


class BaseCollector(ABC):
    """Abstract class for all external pricing feed collectors."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch historical candlestick bars.

        Returns:
            pd.DataFrame with DatetimeIndex and columns:
            ['open', 'high', 'low', 'close', 'volume']
        """
        ...

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current price ticker and 24h market statistics.

        Returns:
            Dict containing: current_price, price_change_24h,
            price_change_percentage_24h, high_24h, low_24h, volume_24h.
        """
        ...

    @abstractmethod
    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Fetch orderbook depth data (bids and asks arrays)."""
        ...
