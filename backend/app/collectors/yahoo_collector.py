"""
TradeMinds AI – Yahoo Finance BIST Collector

Fetches OHLCV + live price for BIST stocks (symbol format: THYAO.IS) via Yahoo's
public chart API (query1.finance.yahoo.com/v8/finance/chart) — a direct HTTP
call that needs no crumb/cookie auth and is resilient to the yfinance library
breakage that took BIST offline.

Caching / market-hours (Step 4):
  • A process-level cache keyed by (symbol, interval) for OHLCV and by symbol
    for the ticker. Transparent to every caller (prices route, scheduler,
    tracker).
  • Market CLOSED  → never call upstream when a cache entry exists (serve last
    known). Only an empty cache triggers a one-time seed.
  • Market OPEN    → dedupe within a short TTL; otherwise refresh INCREMENTALLY,
    downloading only a small recent window and merging it into the cached
    history (overlapping candles are updated, new ones appended) — the full
    history is never re-downloaded.
  • Replay windows (end_date != None) bypass the cache entirely.

Financials still go through yfinance and degrade gracefully (empty) — the
fundamental engine treats missing data as a neutral contribution.

A fresh httpx.AsyncClient is created per request (each call makes one HTTP GET)
so there is no shared client to leak — close() stays a no-op.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Any, Dict, Optional, Tuple

import httpx
import pandas as pd
import yfinance as yf

from app.collectors.base import BaseCollector
from app.services.market_hours import is_bist_open

logger = logging.getLogger(__name__)

_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Yahoo chart intervals. No native 4h → falls back to 1d (matches prior behavior).
_TF_MAP = {"15m": "15m", "1h": "1h", "1d": "1d", "1w": "1wk"}
_TF_MINUTES = {"15m": 15, "1h": 60, "1d": 1440, "1wk": 10080}

# ── Process-level cache (Step 4) ──────────────────────────────────────────────
# Reset on restart; re-seeds on first call. Bounded by (asset count × intervals).
_OHLCV_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}   # (fsym, interval) -> {"df", "ts"}
_TICKER_CACHE: Dict[str, Dict[str, Any]] = {}              # fsym -> {"data", "ts"}
_OHLCV_TTL = 60.0    # while open, don't refetch a series more than once / 60s
_TICKER_TTL = 30.0   # while open, ticker refresh cadence (matches frontend poll)
# Small recent window used for incremental refresh (merged into cached history).
_REFRESH_RANGE = {"1d": "1mo", "1wk": "6mo", "1h": "5d", "15m": "1d"}


def _format_symbol(symbol: str) -> str:
    s = symbol.upper()
    if not s.endswith(".IS") and len(s) == 5:
        s = f"{s}.IS"
    return s


def _merge_ohlcv(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Merge a fresh recent window into cached history: overlapping timestamps
    are updated with the new values, new candles appended. Deterministic."""
    combined = pd.concat([old, new])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined


class YahooCollector(BaseCollector):
    """Yahoo Finance collector for BIST stocks (direct chart API + cache)."""

    async def _chart(
        self,
        symbol: str,
        interval: str,
        *,
        range_: Optional[str] = None,
        period1: Optional[int] = None,
        period2: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call Yahoo's chart API and return the parsed `result[0]` block.
        Raises ValueError for unknown/delisted symbols or empty responses."""
        params: Dict[str, Any] = {"interval": interval, "includePrePost": "false"}
        if period1 is not None and period2 is not None:
            params["period1"] = period1
            params["period2"] = period2
        else:
            params["range"] = range_ or "3mo"

        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _UA}) as client:
            resp = await client.get(f"{_CHART_BASE}/{symbol}", params=params)

        try:
            payload = resp.json()
        except Exception:
            raise ValueError(f"Yahoo chart returned non-JSON for {symbol} (HTTP {resp.status_code})")

        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise ValueError(f"Yahoo chart error for {symbol}: {chart['error'].get('description')}")
        results = chart.get("result")
        if not results:
            raise ValueError(f"No Yahoo chart data for {symbol}")
        return results[0]

    async def _fetch_ohlcv_raw(
        self,
        fsym: str,
        interval: str,
        limit: int,
        end_date: Optional[int] = None,
        range_override: Optional[str] = None,
    ) -> pd.DataFrame:
        """Raw chart→DataFrame fetch (no cache). Returns the full fetched window
        (not tailed) so the caller can cache/merge/tail as needed."""
        period1 = period2 = None
        range_ = "3mo"
        if end_date is not None:
            period2 = int(end_date)
            lookback_min = _TF_MINUTES.get(interval, 1440) * max(limit, 1) * 2  # 2x margin for gaps
            period1 = period2 - lookback_min * 60
        elif range_override is not None:
            range_ = range_override
        else:
            if limit > 700:
                range_ = "5y"
            elif limit > 200:
                range_ = "2y"
            elif limit > 50:
                range_ = "6mo"
            if interval == "15m":
                range_ = "1mo"          # 15m: ~60d max
            elif interval == "1h" and range_ == "5y":
                range_ = "2y"           # 1h: ~730d max

        res = await self._chart(fsym, interval, range_=range_, period1=period1, period2=period2)
        ts = res.get("timestamp") or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        if not ts or not quote.get("close"):
            raise ValueError(f"No Yahoo OHLCV rows for {fsym}")

        df = pd.DataFrame(
            {
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "close": quote.get("close"),
                "volume": quote.get("volume"),
            },
            index=pd.to_datetime(ts, unit="s", utc=True),
        )
        df.index.name = "timestamp"
        df = df.dropna(subset=["close"])
        if df.empty:
            raise ValueError(f"No Yahoo OHLCV rows for {fsym}")
        return df

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        end_date: Optional[int] = None,
    ) -> pd.DataFrame:
        """Cached, market-hours-aware OHLCV. Columns open/high/low/close/volume,
        DatetimeIndex named 'timestamp'. Intervals 15m/1h/1d/1wk (others → 1d)."""
        fsym = _format_symbol(symbol)
        interval = _TF_MAP.get(timeframe, "1d")

        # Replay windows are arbitrary and uncached.
        if end_date is not None:
            df = await self._fetch_ohlcv_raw(fsym, interval, limit, end_date=end_date)
            return df.tail(limit)

        key = (fsym, interval)
        cached = _OHLCV_CACHE.get(key)
        now = _time.time()

        # Market CLOSED → serve cache, never hit upstream (seed once if empty).
        if not is_bist_open():
            if cached is not None:
                return cached["df"].tail(limit)
            df = await self._fetch_ohlcv_raw(fsym, interval, limit)
            _OHLCV_CACHE[key] = {"df": df, "ts": now}
            return df.tail(limit)

        # Market OPEN → TTL dedupe when cache is fresh enough.
        if cached is not None and (now - cached["ts"]) < _OHLCV_TTL and len(cached["df"]) >= limit:
            return cached["df"].tail(limit)

        # Refresh: incremental (small window + merge) when we already have enough
        # history; otherwise a full window fetch.
        if cached is not None and len(cached["df"]) >= limit:
            recent = await self._fetch_ohlcv_raw(
                fsym, interval, limit, range_override=_REFRESH_RANGE.get(interval, "1mo")
            )
            merged = _merge_ohlcv(cached["df"], recent)
            _OHLCV_CACHE[key] = {"df": merged, "ts": now}
            return merged.tail(limit)

        df = await self._fetch_ohlcv_raw(fsym, interval, limit)
        _OHLCV_CACHE[key] = {"df": df, "ts": now}
        return df.tail(limit)

    async def _fetch_ticker_raw(self, fsym: str) -> Dict[str, Any]:
        """Raw ticker from chart meta (no cache)."""
        res = await self._chart(fsym, "1d", range_="5d")
        meta = res.get("meta") or {}
        closes = [c for c in ((res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []) if c is not None]

        current_price = meta.get("regularMarketPrice")
        if current_price is None and closes:
            current_price = closes[-1]
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        if prev_close is None and len(closes) >= 2:
            prev_close = closes[-2]

        current_price = float(current_price) if current_price is not None else 0.0
        change = change_pct = 0.0
        if prev_close:
            change = current_price - float(prev_close)
            change_pct = (change / float(prev_close)) * 100.0

        return {
            "current_price": current_price,
            "price_change_24h": float(change),
            "price_change_percentage_24h": float(change_pct),
            "high_24h": float(meta.get("regularMarketDayHigh") or current_price),
            "low_24h": float(meta.get("regularMarketDayLow") or current_price),
            "volume_24h": float(meta.get("regularMarketVolume") or 0.0),
        }

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Cached, market-hours-aware live price + 24h stats."""
        fsym = _format_symbol(symbol)
        cached = _TICKER_CACHE.get(fsym)
        now = _time.time()

        # Market CLOSED → serve cache, never hit upstream (seed once if empty).
        if not is_bist_open():
            if cached is not None:
                return cached["data"]
            data = await self._fetch_ticker_raw(fsym)
            _TICKER_CACHE[fsym] = {"data": data, "ts": now}
            return data

        # Market OPEN → TTL dedupe.
        if cached is not None and (now - cached["ts"]) < _TICKER_TTL:
            return cached["data"]

        data = await self._fetch_ticker_raw(fsym)
        _TICKER_CACHE[fsym] = {"data": data, "ts": now}
        return data

    async def fetch_financials(self, symbol: str) -> Dict[str, Any]:
        """Fundamental sheets via yfinance. Degrades gracefully to empty dicts —
        the fundamental engine treats missing data as a neutral contribution.
        (yfinance's fundamentals endpoint is crumb-locked; direct-API port is a
        later phase.)"""
        fsym = _format_symbol(symbol)

        def _fetch_sheets():
            ticker = yf.Ticker(fsym)
            info = ticker.info
            financials = ticker.quarterly_financials
            balance_sheet = ticker.quarterly_balance_sheet
            return info, financials, balance_sheet

        try:
            info, financials, balance_sheet = await asyncio.to_thread(_fetch_sheets)
            return {
                "info": info,
                "financials": financials.to_dict() if not financials.empty else {},
                "balance_sheet": balance_sheet.to_dict() if not balance_sheet.empty else {},
            }
        except Exception as e:
            logger.warning("Financials unavailable for %s (graceful degrade): %s", symbol, e)
            return {"info": {}, "financials": {}, "balance_sheet": {}}

    async def fetch_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Yahoo does not serve orderbook depth."""
        return {"bids": [], "asks": []}

    async def close(self) -> None:
        """No persistent client (one created per request) — nothing to close."""
        return None
