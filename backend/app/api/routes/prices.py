"""
TradeMinds AI – Live Price Endpoint

Provides a lightweight ticker endpoint for any asset.
Crypto → Binance REST (no auth), Stocks → Yahoo Finance.
Used by the frontend for stock prices (WebSocket handles crypto directly).
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status

from app.collectors.binance_collector import BinanceCollector
from app.collectors.yahoo_collector import YahooCollector

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/ticker/{symbol}",
    summary="Get live ticker price for any asset",
)
async def get_ticker(symbol: str) -> Dict[str, Any]:
    """
    Fetch current price and 24h stats for the given symbol.
    Crypto symbols (no dot) → Binance. Stock symbols (ends in .IS etc.) → Yahoo.
    """
    is_stock = "." in symbol or symbol.upper().endswith(".IS")

    if is_stock:
        yahoo = YahooCollector()
        try:
            data = await yahoo.fetch_ticker(symbol)
            return {"symbol": symbol.upper(), **data}
        except Exception as exc:
            logger.warning("Yahoo ticker failed for %s: %s", symbol, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not fetch ticker for {symbol}",
            )
        finally:
            await yahoo.close()
    else:
        binance = BinanceCollector()
        try:
            data = await binance.fetch_ticker(symbol)
            return {"symbol": symbol.upper(), **data}
        except Exception as exc:
            logger.warning("Binance ticker failed for %s: %s", symbol, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not fetch ticker for {symbol}",
            )
        finally:
            await binance.close()


@router.get(
    "/tickers",
    summary="Get live tickers for multiple assets",
)
async def get_tickers(symbols: str) -> Dict[str, Any]:
    """
    Fetch tickers for multiple comma-separated symbols.
    Example: /tickers?symbols=BTCUSDT,ETHUSDT,THYAO.IS
    """
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    results: Dict[str, Any] = {}

    crypto_syms = [s for s in sym_list if "." not in s]
    stock_syms = [s for s in sym_list if "." in s]

    if crypto_syms:
        binance = BinanceCollector()
        try:
            for sym in crypto_syms:
                try:
                    results[sym] = await binance.fetch_ticker(sym)
                except Exception as exc:
                    logger.warning("Binance ticker failed for %s: %s", sym, exc)
                    results[sym] = None
        finally:
            await binance.close()

    if stock_syms:
        yahoo = YahooCollector()
        try:
            for sym in stock_syms:
                try:
                    results[sym] = await yahoo.fetch_ticker(sym)
                except Exception as exc:
                    logger.warning("Yahoo ticker failed for %s: %s", sym, exc)
                    results[sym] = None
        finally:
            await yahoo.close()

    return results


@router.get(
    "/ohlcv/{symbol}",
    summary="Get OHLCV candles for charting",
)
async def get_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 200,
) -> Dict[str, Any]:
    """
    Returns OHLCV candles in lightweight-charts compatible format:
        [{ time: <unix-seconds>, open, high, low, close, volume }, ...]
    Crypto via Binance, stocks (.IS) via Yahoo.
    """
    is_stock = "." in symbol or symbol.upper().endswith(".IS")
    candles = []

    if is_stock:
        yahoo = YahooCollector()
        try:
            df = await yahoo.fetch_ohlcv(symbol, timeframe, limit=limit)
        finally:
            await yahoo.close()
    else:
        binance = BinanceCollector()
        try:
            df = await binance.fetch_ohlcv(symbol, timeframe, limit=limit)
        finally:
            await binance.close()

    if df is None or df.empty:
        return {"symbol": symbol.upper(), "timeframe": timeframe, "candles": []}

    for idx, row in df.iterrows():
        candles.append({
            "time":   int(idx.timestamp()),
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row["volume"]),
        })

    return {"symbol": symbol.upper(), "timeframe": timeframe, "candles": candles}
