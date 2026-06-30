"""One-shot runner: rebuild coin_memory.tm_stats from signal_trade_path.

tm_stats is a DERIVABLE CACHE, so this is safe + idempotent. Reads the source of
truth (signal_trade_path), writes ONLY the tm_stats cache (CM2-1 legacy filter +
CM2-2 aggregates). Does not touch resolution_core / trade_path geometry or the v1
engine/regime weights.

Run:  PYTHONPATH=. python scripts/rebuild_tm_stats.py
"""
import asyncio

from app.database import async_session_factory
from app.services.coin_memory import rebuild_tm_stats


async def main() -> None:
    async with async_session_factory() as db:
        stats = await rebuild_tm_stats(db)
        await db.commit()
    print("tm_stats rebuild complete:", stats)


if __name__ == "__main__":
    asyncio.run(main())
