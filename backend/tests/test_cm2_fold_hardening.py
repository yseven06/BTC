"""CM2-1 fold-hardening: update_trade_mgmt_stats must SKIP legacy-contradictory
live-SL rows (KEY1-d predicate) and fold everything else unchanged."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from app.services.coin_memory import update_trade_mgmt_stats


def _path(**kw):
    base = dict(symbol="BTC", timeframe="4h", schema_version=2,
                still_forming_resolution=False, regime="trend",
                cur_reached_tp1=True, cur_reached_tp2=False, cur_reached_tp3=False,
                cur_gave_back_after_tp1=None, mfe_r=1.2, mae_r=0.5)
    base.update(kw)
    return NS(**base)


def test_cm2_1_skips_contradictory_live_sl():
    """A v1 contradictory live-SL row (still_forming + reached_tp1 + gave_back NULL)
    must return BEFORE any DB work — not folded, sample_count not touched."""
    db = AsyncMock()
    contra = _path(schema_version=1, still_forming_resolution=True,
                   cur_reached_tp1=True, cur_gave_back_after_tp1=None,
                   mfe_r=None, mae_r=None)
    asyncio.run(update_trade_mgmt_stats(db, contra))
    db.flush.assert_not_awaited()
    db.execute.assert_not_awaited()


def test_cm2_1_valid_v2_proceeds_and_folds():
    """A valid v2 row passes the guard and folds into both regime + _all buckets."""
    db = AsyncMock()
    mem = NS(tm_stats=None, tm_sample_count=0)
    result = NS(scalar_one_or_none=lambda: mem)

    async def fake_execute(*a, **k):
        return result
    db.execute = fake_execute

    asyncio.run(update_trade_mgmt_stats(db, _path()))
    db.flush.assert_awaited()
    assert mem.tm_sample_count == 1
    assert mem.tm_stats["trend"]["n"] == 1
    assert mem.tm_stats["_all"]["n"] == 1
    assert mem.tm_stats["trend"]["tp1"] == 1


def test_cm2_1_valid_v1_barwalk_not_skipped():
    """A valid v1 bar-walk row (NOT still_forming) must NOT be skipped — only the
    contradictory live-SL subset is filtered, valid history is preserved."""
    db = AsyncMock()
    mem = NS(tm_stats=None, tm_sample_count=0)
    result = NS(scalar_one_or_none=lambda: mem)

    async def fake_execute(*a, **k):
        return result
    db.execute = fake_execute

    asyncio.run(update_trade_mgmt_stats(
        db, _path(schema_version=1, still_forming_resolution=False)))
    db.flush.assert_awaited()
    assert mem.tm_sample_count == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} CM2-1 fold-hardening tests PASSED")
