"""CP-6.4-B: SignalTradePath writes must be idempotent at the DATABASE level.

The defect these tests lock down: signal_id is UNIQUE
(ix_signal_trade_path_signal_id), and the write used to be `db.add(row)`. The
INSERT was therefore emitted by the flush inside update_trade_mgmt_stats — which
runs INSIDE the caller's fail-open try. On a second resolution pass over the same
signal the flush raised IntegrityError; the except swallowed it, but PostgreSQL
had already aborted the transaction, so every later statement in the same sweep
died with 'current transaction is aborted'. One duplicate killed the whole pass.

The fix moves conflict resolution into the database
(`INSERT ... ON CONFLICT (signal_id) DO NOTHING RETURNING id`), so no exception
is raised and the transaction stays usable. RETURNING also tells the caller
whether it actually wrote the row, which is what keeps the Coin Memory rollup
from double-counting on a repeat pass.
"""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.backtesting import tracker
from app.backtesting.trade_path import compute_trade_path
from app.models.intelligence import SignalTradePath, TRADE_PATH_SCHEMA_VERSION
from app.models.price_data import Timeframe

NOW = datetime.now(timezone.utc)
SIGNAL_ID = "11111111-1111-1111-1111-111111111111"
ASSET_ID = "22222222-2222-2222-2222-222222222222"
ROW_ID = "33333333-3333-3333-3333-333333333333"


def _row(**over):
    """A realistic resolved trade-path row, built the way the tracker builds it."""
    kw = dict(
        signal_id=SIGNAL_ID, asset_id=ASSET_ID, symbol="BTCUSDT", timeframe="15m",
        direction="bullish", regime="trending_up", resolved_at=NOW,
        outcome="tp1_hit", detail_label="correct_direction",
        entry=100.0, sl=97.0, tp1=101.5, tp2=103.0, tp3=105.0,
        mfe_pct=2.5, mae_pct=0.8, bars_total=12, mfe_bar_idx=7, mae_bar_idx=2,
        atr_pct=1.2, volatility_ratio=1.1, generated_at=NOW,
        reached_tp1=True, reached_tp2=False, reached_tp3=False,
        realized_return=1.5,
    )
    kw.update(over)
    return compute_trade_path(**kw)


class _Result:
    """Stands in for the Result of an INSERT ... RETURNING id."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _db(insert_result):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(insert_result))
    db.add, db.flush = MagicMock(), AsyncMock()
    return db


async def _emitted_sql(row):
    """Compile the statement the PRODUCTION helper actually emits.

    Deliberately not a local re-implementation: a test that rebuilds the INSERT
    itself passes even when the real conflict target is wrong (verified — that
    exact sabotage went undetected until this capture was introduced)."""
    captured = {}

    async def _execute(stmt, *a, **kw):
        captured["stmt"] = stmt
        return _Result(ROW_ID)

    db = AsyncMock()
    db.execute = _execute
    await tracker._persist_trade_path_once(db, row)
    return str(captured["stmt"].compile(dialect=postgresql.dialect()))


# ── 1 · the statement really is an ON CONFLICT DO NOTHING on signal_id ──────
@pytest.mark.asyncio
async def test_statement_is_on_conflict_do_nothing_targeting_signal_id():
    sql = await _emitted_sql(_row())
    assert "INSERT INTO signal_trade_path" in sql
    assert "ON CONFLICT (signal_id) DO NOTHING" in sql
    assert "RETURNING signal_trade_path.id" in sql
    # DO NOTHING, never DO UPDATE — the row is immutable by contract.
    assert "DO UPDATE" not in sql


# ── 2 · defaults survive: id / created_at must NOT be sent as NULL ──────────
@pytest.mark.asyncio
async def test_none_columns_are_omitted_so_defaults_apply():
    row = _row()
    sql = await _emitted_sql(row)
    # created_at is NOT NULL with server_default now(); sending NULL would fail.
    assert "created_at" not in sql
    # schema_version and source ARE set on the row, so they must be written.
    assert "schema_version" in sql and "source" in sql
    assert row.schema_version == TRADE_PATH_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_false_valued_columns_are_kept_not_dropped_as_falsy():
    """intrabar_ambiguous is NOT NULL and legitimately False — a truthiness
    filter instead of an `is not None` filter would silently drop it."""
    row = _row()
    assert row.intrabar_ambiguous is False
    assert "intrabar_ambiguous" in await _emitted_sql(row)


# ── 3 · first write inserts and folds the rollup ────────────────────────────
@pytest.mark.asyncio
async def test_first_write_persists_and_folds(monkeypatch, caplog):
    fold = AsyncMock()
    monkeypatch.setattr(tracker, "update_trade_mgmt_stats", fold)
    monkeypatch.setattr(tracker, "compute_trade_path", lambda **kw: _row())
    monkeypatch.setattr(tracker, "build_entry_telemetry", MagicMock(return_value=None))
    db = _db(ROW_ID)          # RETURNING gave us an id => the row was written
    db.execute = AsyncMock(side_effect=[_Result(None), _Result(ROW_ID)])  # snapshot, insert

    with caplog.at_level("WARNING", logger="app.backtesting.tracker"):
        await tracker._write_trade_path_failopen(
            db, _signal(), _perf(), entry=100.0, sl=97.0, tp1=101.5, tp2=103.0, tp3=105.0,
            mfe_pct=2.5, mae_pct=0.8, bars_total=12, mfe_bar_idx=7, mae_bar_idx=2,
            tp1_bar_idx=6, post_tp1_mfe=1.0, post_tp1_mae=0.2, intrabar_ambiguous=False,
            still_forming=False, realized_return=1.5, outcome_val="tp1_hit",
            detail_label="correct_direction")

    _assert_clean(caplog)
    assert fold.await_count == 1, "a freshly written row must be folded into tm_stats"
    db.add.assert_not_called()   # the ORM add() path caused the abort — it must be gone


# ── 4 · repeat write is a no-op: no duplicate, no double-fold, no raise ─────
@pytest.mark.asyncio
async def test_repeat_write_does_not_duplicate_or_double_fold(monkeypatch, caplog):
    fold = AsyncMock()
    monkeypatch.setattr(tracker, "update_trade_mgmt_stats", fold)
    monkeypatch.setattr(tracker, "compute_trade_path", lambda **kw: _row())
    monkeypatch.setattr(tracker, "build_entry_telemetry", MagicMock(return_value=None))
    db = _db(None)            # RETURNING empty => the conflict clause swallowed it
    db.execute = AsyncMock(side_effect=[_Result(None), _Result(None)])  # snapshot, insert

    with caplog.at_level("WARNING", logger="app.backtesting.tracker"):
        await tracker._write_trade_path_failopen(
            db, _signal(), _perf(), entry=100.0, sl=97.0, tp1=101.5, tp2=103.0, tp3=105.0,
            mfe_pct=2.5, mae_pct=0.8, bars_total=12, mfe_bar_idx=7, mae_bar_idx=2,
            tp1_bar_idx=6, post_tp1_mfe=1.0, post_tp1_mae=0.2, intrabar_ambiguous=False,
            still_forming=False, realized_return=1.5, outcome_val="tp1_hit",
            detail_label="correct_direction")

    # A duplicate must be an ORDINARY no-op, not a swallowed error: nothing is
    # logged, nothing is folded, and no exception ever reaches the fail-open net.
    _assert_clean(caplog)
    assert fold.await_count == 0, "an already-recorded row must not be counted twice"
    db.add.assert_not_called()


# ── 5 · the live-SL variant is idempotent too ───────────────────────────────
@pytest.mark.asyncio
async def test_live_sl_write_is_idempotent(monkeypatch, caplog):
    fold = AsyncMock()
    monkeypatch.setattr(tracker, "update_trade_mgmt_stats", fold)
    monkeypatch.setattr(tracker, "compute_trade_path", lambda **kw: _row())
    monkeypatch.setattr(tracker, "build_entry_telemetry", MagicMock(return_value=None))
    db = _db(None)
    db.execute = AsyncMock(side_effect=[_Result(None), _Result(None)])

    with caplog.at_level("WARNING", logger="app.backtesting.tracker"):
        await tracker._write_trade_path_live_sl_failopen(
            db, _signal(), _perf(), entry=100.0, sl=97.0, live_price=96.5, realized_return=-3.0)

    _assert_clean(caplog)
    assert fold.await_count == 0
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_live_sl_first_write_still_folds(monkeypatch, caplog):
    fold = AsyncMock()
    monkeypatch.setattr(tracker, "update_trade_mgmt_stats", fold)
    monkeypatch.setattr(tracker, "compute_trade_path", lambda **kw: _row())
    monkeypatch.setattr(tracker, "build_entry_telemetry", MagicMock(return_value=None))
    db = _db(ROW_ID)
    db.execute = AsyncMock(side_effect=[_Result(None), _Result(ROW_ID)])

    with caplog.at_level("WARNING", logger="app.backtesting.tracker"):
        await tracker._write_trade_path_live_sl_failopen(
            db, _signal(), _perf(), entry=100.0, sl=97.0, live_price=96.5, realized_return=-3.0)

    _assert_clean(caplog)
    assert fold.await_count == 1


# ── 6 · the helper's contract, exercised directly ───────────────────────────
@pytest.mark.asyncio
async def test_helper_returns_true_when_written_false_on_conflict():
    assert await tracker._persist_trade_path_once(_db(ROW_ID), _row()) is True
    assert await tracker._persist_trade_path_once(_db(None), _row()) is False


@pytest.mark.asyncio
async def test_helper_never_uses_orm_add():
    """The abort came from the ORM flush. The helper must emit its own INSERT."""
    db = _db(ROW_ID)
    await tracker._persist_trade_path_once(db, _row())
    db.add.assert_not_called()
    db.flush.assert_not_awaited()
    assert db.execute.await_count == 1


# ── 7 · fail-open is preserved: a genuine error still cannot escape ─────────
@pytest.mark.asyncio
async def test_unexpected_error_is_still_swallowed(monkeypatch, caplog):
    monkeypatch.setattr(tracker, "compute_trade_path", lambda **kw: _row())
    monkeypatch.setattr(tracker, "build_entry_telemetry", MagicMock(return_value=None))
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_Result(None), RuntimeError("db exploded")])
    db.add = MagicMock()

    with caplog.at_level("WARNING", logger="app.backtesting.tracker"):
        await tracker._write_trade_path_failopen(     # must NOT raise
            db, _signal(), _perf(), entry=100.0, sl=97.0, tp1=101.5, tp2=103.0, tp3=105.0,
            mfe_pct=2.5, mae_pct=0.8, bars_total=12, mfe_bar_idx=7, mae_bar_idx=2,
            tp1_bar_idx=6, post_tp1_mfe=1.0, post_tp1_mae=0.2, intrabar_ambiguous=False,
            still_forming=False, realized_return=1.5, outcome_val="tp1_hit",
            detail_label="correct_direction")

    assert "TradePath instrumentation failed" in caplog.text


# ── doubles ─────────────────────────────────────────────────────────────────
def _assert_clean(caplog):
    """No fail-open warning may have fired. Without this, a broken test double
    would raise inside the try, get swallowed, and leave the fold count at 0 —
    making the 'no double-fold' assertions pass for entirely the wrong reason."""
    assert "instrumentation failed" not in caplog.text, caplog.text


def _signal():
    # timeframe must be the real enum: _map_db_timeframe looks it up in a dict,
    # and a SimpleNamespace is unhashable (it defines __eq__, so __hash__ is None).
    return NS(id=SIGNAL_ID, asset_id=ASSET_ID, asset=NS(symbol="BTCUSDT"),
              timeframe=Timeframe.M15, direction=NS(value="bullish"),
              entry_zone_low=99.0, entry_zone_high=101.0,
              tp1=101.5, tp2=103.0, tp3=105.0, generated_at=NOW)


def _perf():
    return NS(hit_tp1=True, hit_tp2=False, hit_tp3=False, closed_at=NOW,
              outcome=NS(value="tp1_hit"), detail_label="correct_direction")
