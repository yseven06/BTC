"""
One-off: activate the BIST pilot (5 liquid stocks) — Step 6 of the controlled
BIST re-enablement rollout.

Idempotent + reportable: flips is_active=True for EXACTLY these 5 stock symbols,
prints before/after per symbol, and reports active-stock / active-crypto counts
so it is evident the other 33 stocks and all crypto are untouched. Re-running is
a safe no-op. Hard safety: only acts on a symbol that exists AND is a STOCK.

Run (from backend/, venv active):  python -m scripts.activate_bist_pilot
"""

import asyncio
import logging

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models.asset import Asset, AssetType

logging.disable(logging.CRITICAL)  # silence SQL echo for a clean report

PILOT = ["THYAO.IS", "GARAN.IS", "AKBNK.IS", "ASELS.IS", "BIMAS.IS"]


async def _active(db, asset_type):
    return (
        await db.execute(
            select(func.count()).select_from(Asset).where(
                Asset.asset_type == asset_type, Asset.is_active == True  # noqa: E712
            )
        )
    ).scalar()


async def main() -> None:
    async with async_session_factory() as db:
        stock_before = await _active(db, AssetType.STOCK)
        crypto_before = await _active(db, AssetType.CRYPTO)
        print(f"ÖNCESİ: aktif hisse={stock_before} | aktif kripto={crypto_before}\n")

        print("PİLOT AKTİVASYON (tek tek):")
        changed = 0
        for sym in PILOT:
            a = (await db.execute(select(Asset).where(Asset.symbol == sym))).scalar_one_or_none()
            if a is None:
                print(f"  {sym}: BULUNAMADI — atlandı")
                continue
            if a.asset_type != AssetType.STOCK:
                print(f"  {sym}: hisse DEĞİL (type={a.asset_type.value}) — GÜVENLİK: atlandı")
                continue
            if a.is_active:
                print(f"  {sym}: zaten aktif (no-op)")
                continue
            a.is_active = True
            changed += 1
            print(f"  {sym}: is_active False -> True")

        await db.commit()

        stock_after = await _active(db, AssetType.STOCK)
        crypto_after = await _active(db, AssetType.CRYPTO)
        total_stock = (
            await db.execute(
                select(func.count()).select_from(Asset).where(Asset.asset_type == AssetType.STOCK)
            )
        ).scalar()

        print(
            f"\nSONRASI: aktif hisse={stock_after} | aktif kripto={crypto_after} | toplam hisse={total_stock}"
        )
        print(f"Değiştirilen: {changed} | dokunulmayan (inaktif) hisse: {total_stock - stock_after}")

        # Report-grade assertions
        assert crypto_after == crypto_before, "Kripto aktiflik DEĞİŞTİ — beklenmedik!"
        assert stock_after == stock_before + changed, "Hisse aktif sayısı tutarsız!"
        print("DOĞRULAMA: kripto aktiflik değişmedi ✓; yalnızca pilot hisseler etkilendi ✓")


if __name__ == "__main__":
    asyncio.run(main())
