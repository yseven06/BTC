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
                cur_gave_back_after_tp1=None, mfe_r=1.2, mae_r=0.5,
                # CM2-2 fields the fold now reads
                mfe_atr=2.0, mae_atr=0.8, bars_total=10, cur_bars_to_tp1=3,
                cur_realized_return=1.5, entry_price=100.0, sl_price=96.0,
                tp1_price=103.0, detail_label=None)
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


def _mem_with(tm_stats):
    return NS(tm_stats=tm_stats, tm_sample_count=0 if tm_stats is None else 5)


def _fake_db(mem):
    db = AsyncMock()
    result = NS(scalar_one_or_none=lambda: mem)

    async def fake_execute(*a, **k):
        return result
    db.execute = fake_execute
    return db


def test_cm2_2_new_aggregates_folded():
    """All CM2-2 additive aggregates land in the bucket with correct values."""
    mem = _mem_with(None)
    p = _path(mfe_r=2.0, mae_r=0.5, mfe_atr=3.0, mae_atr=0.8, bars_total=10,
              cur_bars_to_tp1=3, cur_realized_return=1.5,
              entry_price=100.0, sl_price=96.0, tp1_price=103.0,
              detail_label="correct_dir_tight_sl")
    asyncio.run(update_trade_mgmt_stats(_fake_db(mem), p))
    b = mem.tm_stats["_all"]
    assert b["mfe_atr_sum"] == 3.0 and b["mfe_atr_n"] == 1
    assert b["mae_atr_sum"] == 0.8 and b["mae_atr_n"] == 1
    assert b["bars_total_sum"] == 10 and b["bars_total_n"] == 1
    assert b["bars_to_tp1_sum"] == 3 and b["bars_to_tp1_n"] == 1
    assert b["realized_sum"] == 1.5 and b["realized_n"] == 1 and b["realized_sumsq"] == 2.25
    assert b["mfe_r_n"] == 1 and b["mae_r_n"] == 1
    assert b["mfe_r_sumsq"] == 4.0 and b["mae_r_sumsq"] == 0.25
    assert b["planned_rr_tp1_n"] == 1 and abs(b["planned_rr_tp1_sum"] - 0.75) < 1e-9
    assert b["sub1_rr"] == 1               # planned R:R 0.75 < 1.0
    assert b["tight_sl"] == 1              # canonical CORRECT_DIR_TIGHT_SL label
    # additive-list contract: regime bucket == _all (single fold this cell)
    assert mem.tm_stats["trend"]["realized_sum"] == b["realized_sum"]


def test_cm2_2_legacy_bucket_no_crash_and_extends():
    """Folding into a pre-CM2-2 bucket (old keys only) must not KeyError; old keys
    still increment, new keys appear. (Full consistency comes from CM2-3 rebuild.)"""
    legacy = {"n": 5, "mfe_r_sum": 10.0, "mae_r_sum": 3.0,
              "hist_mfe_r": [0] * 9, "hist_mae_r": [0] * 9,
              "tp1": 2, "tp2": 1, "tp3": 0, "give_back": 1}
    mem = _mem_with({"trend": dict(legacy), "_all": dict(legacy)})
    asyncio.run(update_trade_mgmt_stats(_fake_db(mem), _path(mfe_r=1.0, mae_r=0.4)))
    b = mem.tm_stats["_all"]
    assert b["n"] == 6                      # old key incremented
    assert b["mfe_r_sum"] == 11.0           # old sum extended
    assert b["mfe_r_n"] == 1                # NEW key appeared
    assert "realized_sum" in b and "planned_rr_tp1_n" in b and "mfe_atr_sum" in b


def test_cm2_3_aggregate_rebuild_and_contract():
    """_aggregate_tm_stats folds many paths, skips contradictory rows, and keeps the
    additive-list contract: _all.n == sum of regime buckets' n."""
    from app.services.coin_memory import _aggregate_tm_stats
    paths = [
        _path(regime="trend", mfe_r=2.0, mae_r=0.5),
        _path(regime="trend", mfe_r=1.0, mae_r=1.0),
        _path(regime="range", mfe_r=0.5, mae_r=0.5),
        _path(schema_version=1, still_forming_resolution=True, cur_reached_tp1=True,
              cur_gave_back_after_tp1=None, mfe_r=None, mae_r=None),  # contradictory → skip
    ]
    cells, counts, skipped = _aggregate_tm_stats(paths)
    assert skipped == 1
    key = ("BTC", "4h")
    assert counts[key] == 3
    tm = cells[key]
    regime_n = sum(b["n"] for k, b in tm.items() if k != "_all")
    assert tm["_all"]["n"] == 3 == regime_n           # additive-list contract
    assert tm["trend"]["n"] == 2 and tm["range"]["n"] == 1
    assert tm["_all"]["mfe_r_n"] == 3                  # CM2-2 per-field count consistent


def test_cm2_3_rebuild_idempotent():
    """Rebuilding twice over the same paths yields identical cells/counts."""
    from app.services.coin_memory import _aggregate_tm_stats
    paths = [_path(regime="trend"), _path(regime="range"), _path(regime="trend")]
    a_cells, a_counts, a_skip = _aggregate_tm_stats(paths)
    b_cells, b_counts, b_skip = _aggregate_tm_stats(paths)
    assert a_counts == b_counts and a_skip == b_skip
    assert a_cells[("BTC", "4h")]["_all"] == b_cells[("BTC", "4h")]["_all"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} CM2-1 fold-hardening tests PASSED")
