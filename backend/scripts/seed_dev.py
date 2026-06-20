"""
TradeMinds AI – Local Development Seed Script
==============================================
Run from the backend/ directory:

    python -m scripts.seed_dev

What this script does:
1. Creates all DB tables (CREATE TABLE IF NOT EXISTS — safe to re-run).
2. Seeds the four tracked assets: BTCUSDT, ETHUSDT, THYAO.IS, GARAN.IS.
3. Creates a dev user: dev@trademinds.io / password: devpass123
4. For each asset, fetches live OHLCV from Binance / Yahoo Finance.
   If the live feed is unavailable, falls back to synthetic OHLCV candles
   generated from a seeded random walk (clearly labelled as DEMO DATA).
5. Runs the full AI decision engine for each asset on the 1h timeframe.
6. Saves the resulting signals to the database.
7. Prints a valid JWT access token for the dev user so you can test
   authenticated endpoints (POST /generate) via Swagger at
   http://localhost:8000/docs.

This script is idempotent — running it multiple times is safe.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

# ── path setup so we can import from app ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session_factory, engine, init_db
from app.models.asset import Asset, AssetType
from app.models.user import User, AuthProvider, Language
from app.models.signal import Signal, SignalPerformance, SignalOutcome, SignalType, Direction, RiskLevel
from app.models.price_data import Timeframe as DBTimeframe
from app.auth.password import hash_password
from app.auth.jwt_handler import create_access_token
from app.engines.ai_decision.engine import AIDecisionEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── seed config ────────────────────────────────────────────────────────────────

DEV_EMAIL    = "dev@trademinds.io"
DEV_PASSWORD = "devpass123"
DEV_NAME     = "Dev Trader"

ASSETS = [
    # ── Major crypto ──
    {"symbol": "BTCUSDT",   "name": "Bitcoin",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ETHUSDT",   "name": "Ethereum",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "BNBUSDT",   "name": "BNB",            "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "SOLUSDT",   "name": "Solana",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "XRPUSDT",   "name": "Ripple",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ADAUSDT",   "name": "Cardano",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "DOGEUSDT",  "name": "Dogecoin",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "AVAXUSDT",  "name": "Avalanche",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "DOTUSDT",   "name": "Polkadot",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "MATICUSDT", "name": "Polygon",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "LINKUSDT",  "name": "Chainlink",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ATOMUSDT",  "name": "Cosmos",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "UNIUSDT",   "name": "Uniswap",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "LTCUSDT",   "name": "Litecoin",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "BCHUSDT",   "name": "Bitcoin Cash",   "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "NEARUSDT",  "name": "NEAR Protocol",  "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "APTUSDT",   "name": "Aptos",          "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ARBUSDT",   "name": "Arbitrum",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "OPUSDT",    "name": "Optimism",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "INJUSDT",   "name": "Injective",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "SUIUSDT",   "name": "Sui",            "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "FILUSDT",   "name": "Filecoin",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "AAVEUSDT",  "name": "Aave",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "SHIBUSDT",  "name": "Shiba Inu",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "TRXUSDT",   "name": "TRON",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ETCUSDT",   "name": "Ethereum Classic","asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "XLMUSDT",   "name": "Stellar",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ALGOUSDT",  "name": "Algorand",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "FTMUSDT",   "name": "Fantom",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "PEPEUSDT",  "name": "Pepe",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    # ── Eklenen popüler / izleme listesi coinleri ──
    {"symbol": "RVNUSDT",   "name": "Ravencoin",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "MINAUSDT",  "name": "Mina Protocol",  "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "RLCUSDT",   "name": "iExec RLC",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "CAKEUSDT",  "name": "PancakeSwap",    "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "MAGICUSDT", "name": "Magic",          "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "IMXUSDT",   "name": "Immutable",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "GMTUSDT",   "name": "STEPN",          "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "FETUSDT",   "name": "Fetch.ai",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "APEUSDT",   "name": "ApeCoin",        "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ICPUSDT",   "name": "Internet Computer","asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "MAVUSDT",   "name": "Maverick",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "COMPUSDT",  "name": "Compound",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "EGLDUSDT",  "name": "MultiversX",     "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "LPTUSDT",   "name": "Livepeer",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "DYDXUSDT",  "name": "dYdX",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "AXSUSDT",   "name": "Axie Infinity",  "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ALICEUSDT", "name": "My Neighbor Alice","asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "1INCHUSDT", "name": "1inch",          "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "KNCUSDT",   "name": "Kyber Network",  "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "RUNEUSDT",  "name": "Thorchain",      "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "SANDUSDT",  "name": "The Sandbox",    "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ENJUSDT",   "name": "Enjin Coin",     "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ONTUSDT",   "name": "Ontology",       "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "AUDIOUSDT", "name": "Audius",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "C98USDT",   "name": "Coin98",         "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "DUSKUSDT",  "name": "Dusk Network",   "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "COTIUSDT",  "name": "COTI",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "ARPAUSDT",  "name": "ARPA",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    {"symbol": "GALAUSDT",  "name": "Gala",           "asset_type": AssetType.CRYPTO, "market": "binance"},
    # ── BIST stocks — Türkiye'nin en büyük 20 şirketi ──
    {"symbol": "THYAO.IS",  "name": "Türk Hava Yolları","asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "GARAN.IS",  "name": "Garanti BBVA",     "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "AKBNK.IS",  "name": "Akbank",           "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "ISCTR.IS",  "name": "İş Bankası C",     "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "YKBNK.IS",  "name": "Yapı Kredi",       "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "HALKB.IS",  "name": "Halkbank",         "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "VAKBN.IS",  "name": "Vakıfbank",        "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "SISE.IS",   "name": "Şişe Cam",         "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "EREGL.IS",  "name": "Ereğli Demir",     "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "BIMAS.IS",  "name": "BİM Mağazalar",    "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "TUPRS.IS",  "name": "Tüpraş",           "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "ASELS.IS",  "name": "Aselsan",          "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "KCHOL.IS",  "name": "Koç Holding",      "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "SAHOL.IS",  "name": "Sabancı Holding",  "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "PETKM.IS",  "name": "Petkim",           "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "TCELL.IS",  "name": "Turkcell",         "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "TTKOM.IS",  "name": "Türk Telekom",     "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "FROTO.IS",  "name": "Ford Otosan",      "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "TOASO.IS",  "name": "Tofaş Oto",        "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "ENKAI.IS",  "name": "Enka İnşaat",      "asset_type": AssetType.STOCK, "market": "bist"},
    # ── Ek BIST hisseleri ──
    {"symbol": "SASA.IS",   "name": "SASA Polyester",   "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "DOHOL.IS",  "name": "Doğan Holding",    "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "PNSUT.IS",  "name": "Pınar Süt",        "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "KARSN.IS",  "name": "Karsan Otomotiv",  "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "ODAS.IS",   "name": "Odaş Elektrik",    "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "PAMEL.IS",  "name": "Pamel Yenilenebilir Enerji","asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "MRSHL.IS",  "name": "Marshall Boya",    "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "ELITE.IS",  "name": "Elite Naturel",    "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "INVEO.IS",  "name": "İnveo Yatırım Holding","asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "PRDGS.IS",  "name": "Pergamon Status",  "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "MEGAP.IS",  "name": "Mega Polietilen",  "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "EDIP.IS",   "name": "Edip Gayrimenkul", "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "AZTEK.IS",  "name": "Aztek Teknoloji",  "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "OBASE.IS",  "name": "Obase Bilgisayar", "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "BURCE.IS",  "name": "Burçelik",         "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "CMBTN.IS",  "name": "Çimbeton",         "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "KRPLS.IS",  "name": "Kartonsan",        "asset_type": AssetType.STOCK, "market": "bist"},
    {"symbol": "TRALT.IS",  "name": "Trakya Cam Alt",   "asset_type": AssetType.STOCK, "market": "bist"},
]

# ── synthetic OHLCV fallback ───────────────────────────────────────────────────

_SEED_PRICES = {
    "BTCUSDT":  65000.0,
    "ETHUSDT":  3400.0,
    "THYAO.IS": 295.0,
    "GARAN.IS": 72.0,
}

def _synthetic_ohlcv(symbol: str, n: int = 120, timeframe_hours: float = 1.0) -> pd.DataFrame:
    """
    Generate synthetic OHLCV candles using a seeded random walk.

    This is DEMO / FALLBACK DATA — only used when the live market feed is
    unavailable.  The candles are statistically plausible but not real prices.
    """
    log.warning("⚠  DEMO DATA: using synthetic OHLCV for %s (live feed unavailable)", symbol)
    rng = random.Random(hash(symbol) % (2**31))
    np_rng = np.random.default_rng(hash(symbol) % (2**31))

    base = _SEED_PRICES.get(symbol, 100.0)
    now  = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    freq = timedelta(hours=timeframe_hours)

    records = []
    price = base
    for i in range(n - 1, -1, -1):
        ts    = now - freq * i
        ret   = np_rng.normal(0.0002, 0.008)
        price = max(price * (1 + ret), 0.01)
        rng_h = rng.uniform(0.001, 0.012)
        rng_l = rng.uniform(0.001, 0.012)
        o = price * rng.uniform(0.998, 1.002)
        h = max(o, price) * (1 + rng_h)
        l = min(o, price) * (1 - rng_l)
        c = price
        vol = base * rng.uniform(100, 500)
        records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": vol})

    df = pd.DataFrame(records).set_index("timestamp")
    return df


async def _fetch_live_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 120) -> Optional[pd.DataFrame]:
    """Try to fetch live OHLCV; return None on any failure."""
    try:
        if symbol.endswith(".IS"):
            from app.collectors.yahoo_collector import YahooCollector
            collector = YahooCollector()
            df = await collector.fetch_ohlcv(symbol, timeframe, limit=limit)
            await collector.close()
        else:
            from app.collectors.binance_collector import BinanceCollector
            collector = BinanceCollector()
            df = await collector.fetch_ohlcv(symbol, timeframe, limit=limit)
            await collector.close()

        if df is None or df.empty or len(df) < 30:
            return None
        return df
    except Exception as exc:
        log.warning("Live OHLCV fetch failed for %s: %s", symbol, exc)
        return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _get_or_create_asset(session, spec: dict) -> Asset:
    result = await session.execute(select(Asset).where(Asset.symbol == spec["symbol"]))
    asset = result.scalar_one_or_none()
    if asset is None:
        asset = Asset(
            symbol=spec["symbol"],
            name=spec["name"],
            asset_type=spec["asset_type"],
            market=spec["market"],
            is_active=True,
        )
        session.add(asset)
        await session.flush()
        log.info("  Created asset: %s", spec["symbol"])
    else:
        log.info("  Asset already exists: %s", spec["symbol"])
    return asset


async def _get_or_create_dev_user(session) -> User:
    result = await session.execute(select(User).where(User.email == DEV_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=DEV_EMAIL,
            password_hash=hash_password(DEV_PASSWORD),
            full_name=DEV_NAME,
            provider=AuthProvider.EMAIL,
            language=Language.EN,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        log.info("  Created dev user: %s", DEV_EMAIL)
    else:
        log.info("  Dev user already exists: %s", DEV_EMAIL)
    return user


TF_MAP = {
    "1m":  DBTimeframe.M1,
    "5m":  DBTimeframe.M5,
    "15m": DBTimeframe.M15,
    "1h":  DBTimeframe.H1,
    "4h":  DBTimeframe.H4,
    "1d":  DBTimeframe.D1,
}

SIG_TYPE_MAP = {
    "STRONG_BUY":  SignalType.STRONG_BUY,
    "BUY":         SignalType.BUY,
    "HOLD":        SignalType.HOLD,
    "SELL":        SignalType.SELL,
    "STRONG_SELL": SignalType.STRONG_SELL,
}

DIR_MAP = {
    "bullish": Direction.BULLISH,
    "bearish": Direction.BEARISH,
    "neutral": Direction.NEUTRAL,
}

RISK_MAP = {
    "low":       RiskLevel.LOW,
    "medium":    RiskLevel.MEDIUM,
    "high":      RiskLevel.HIGH,
    "very_high": RiskLevel.VERY_HIGH,
}


async def _generate_and_save_signal(session, asset: Asset, timeframe: str = "1h") -> str:
    """
    Run the AI engine for the asset and persist the resulting signal.
    Returns a short summary string for the final report.
    """
    log.info("  Generating signal for %s (%s)…", asset.symbol, timeframe)

    # 1. Fetch OHLCV — try live, fall back to synthetic
    df = await _fetch_live_ohlcv(asset.symbol, timeframe, limit=120)
    data_source = "live"
    if df is None:
        df = _synthetic_ohlcv(asset.symbol, n=120, timeframe_hours=1.0)
        data_source = "DEMO/SYNTHETIC"

    # 2. Run the full engine suite
    try:
        engine_instance = AIDecisionEngine()
        decision = await engine_instance.analyze_and_decide(
            symbol=asset.symbol,
            timeframe=timeframe,
            ohlcv_data=df,
            asset_type=asset.asset_type.value,
            is_backtest=True,  # skip live MTF HTTP calls during seeding
        )
    except Exception as exc:
        log.error("  Engine failed for %s: %s", asset.symbol, exc)
        return f"{asset.symbol}: ENGINE ERROR — {exc}"

    # 3. Deactivate any previous active signal for this asset+timeframe
    old_q = select(Signal).where(
        Signal.asset_id == asset.id,
        Signal.timeframe == TF_MAP.get(timeframe, DBTimeframe.H1),
        Signal.is_active == True,
    )
    old_res = await session.execute(old_q)
    for old in old_res.scalars().all():
        old.is_active = False

    # 4. Persist new signal
    generated_at = datetime.now(timezone.utc)
    sig = Signal(
        asset_id=asset.id,
        signal_type=SIG_TYPE_MAP.get(decision["signal_type"], SignalType.HOLD),
        confidence_score=decision["confidence_score"],
        probability_score=decision["probability_score"],
        risk_score=decision["risk_score"],
        risk_level=RISK_MAP.get(str(decision["risk_level"]).lower(), RiskLevel.MEDIUM),
        direction=DIR_MAP.get(decision["direction"], Direction.NEUTRAL),
        entry_zone_low=decision["entry_zone_low"],
        entry_zone_high=decision["entry_zone_high"],
        stop_loss=decision["stop_loss"],
        tp1=decision["tp1"],
        tp2=decision["tp2"],
        tp3=decision["tp3"],
        invalidation_conditions=decision["invalidation_conditions"],
        engines_data=decision["engine_results"],
        explanation_tr=decision["explanation_tr"],
        explanation_en=decision["explanation_en"],
        is_active=True,
        timeframe=TF_MAP.get(timeframe, DBTimeframe.H1),
        generated_at=generated_at,
        expires_at=generated_at + timedelta(hours=48),
    )
    session.add(sig)
    await session.flush()

    perf = SignalPerformance(signal_id=sig.id, outcome=SignalOutcome.ACTIVE)
    session.add(perf)

    summary = (
        f"{asset.symbol}: {decision['signal_type']} | "
        f"conf={decision['confidence_score']:.1f}% | "
        f"dir={decision['direction']} | "
        f"data={data_source}"
    )
    log.info("  ✓ Saved: %s", summary)
    return summary


# ── main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "=" * 60)
    print("  TradeMinds AI — Local Dev Seed")
    print("=" * 60)

    # Step 1: ensure all tables exist
    log.info("\n[1/4] Initialising database schema…")
    await init_db()
    log.info("  Tables created / verified.")

    async with async_session_factory() as session:
        # Step 2: seed assets
        log.info("\n[2/4] Seeding assets…")
        assets: list[Asset] = []
        for spec in ASSETS:
            asset = await _get_or_create_asset(session, spec)
            assets.append(asset)
        await session.commit()

        # Step 3: seed dev user + print JWT
        log.info("\n[3/4] Creating dev user…")
        user = await _get_or_create_dev_user(session)
        await session.commit()

        token = create_access_token({"sub": str(user.id), "email": user.email})

        # Step 4: generate signals
        log.info("\n[4/4] Generating signals (1h timeframe)…")
        summaries = []
        for asset in assets:
            summary = await _generate_and_save_signal(session, asset, timeframe="1h")
            summaries.append(summary)
        await session.commit()

    # Final report
    print("\n" + "=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)
    print(f"\nDev user:  {DEV_EMAIL}")
    print(f"Password:  {DEV_PASSWORD}")
    print(f"\nJWT token (valid for 30 min — paste into Swagger Authorize):\n")
    print(f"  {token}")
    print(f"\nSignals generated:")
    for s in summaries:
        print(f"  • {s}")
    print(f"\nAPI endpoints to verify:")
    print(f"  GET  http://localhost:8000/api/v1/signals")
    print(f"  GET  http://localhost:8000/api/v1/signals/performance")
    print(f"  POST http://localhost:8000/api/v1/signals/generate/BTCUSDT  (use JWT above)")
    print(f"  Dashboard: http://localhost:3000")
    print()


if __name__ == "__main__":
    asyncio.run(main())
