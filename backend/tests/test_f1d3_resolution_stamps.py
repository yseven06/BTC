"""CP-F1D-3 — resolution-provenance stamps on all seven writer paths.

Every path that closes a SignalPerformance row now stamps WHO resolved it
(resolution_source) and under WHICH semantics (resolution_version). Telemetry
only — outcomes, labels, timestamps and every decision stay byte-identical;
these tests lock the stamps where they happen:

  - the four tracker paths run through the REAL loop (the F0-1G/F0-1A
    harness): bar_walk, expiry, live_sl, hold_expiry;
  - the reversal and admin paths have no loop harness — their stamps are
    locked at source level (the F0-L1 pattern), one assert per stamp site;
  - the version constant and the seven source identities are pinned exactly,
    like the label vocabulary in F1D-1 — these strings go into the DB;
  - fidelity.py hygiene: no raw label literal remains where the sets are now
    derived from the canonical vocabulary.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

import app
from app.backtesting import labels as L
from app.backtesting import tracker
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome

APP_DIR = Path(app.__file__).resolve().parent
NOW = datetime.now(timezone.utc)
ENTRY, TP1, TP2, TP3, SL = 100.0, 101.5, 103.0, 105.0, 97.0


def _src(rel: str) -> str:
    return (APP_DIR / rel).read_text(encoding="utf-8")


# ── constants: these strings go into the DB — pin them exactly ──────────────

def test_resolution_semantics_version_is_1():
    assert L.RESOLUTION_SEMANTICS_VERSION == 1


def test_source_identity_vocabulary():
    expected = {
        "RES_SRC_BAR_WALK": "bar_walk",
        "RES_SRC_LIVE_SL": "live_sl",
        "RES_SRC_EXPIRY": "expiry",
        "RES_SRC_HOLD_EXPIRY": "hold_expiry",
        "RES_SRC_REVERSAL": "reversal",
        "RES_SRC_ADMIN_INVALIDATE": "admin_invalidate",
        "RES_SRC_ADMIN_BULK_CLEAN": "admin_bulk_clean",
    }
    for const, value in expected.items():
        assert getattr(L, const) == value, f"{const} renamed — stored rows keep '{value}'"
    assert len(set(expected.values())) == 7          # all distinct
    # the first three deliberately reuse trade_path.extra's value family
    assert {L.RES_SRC_BAR_WALK, L.RES_SRC_LIVE_SL, L.RES_SRC_EXPIRY} == \
        {"bar_walk", "live_sl", "expiry"}


# ── the four tracker paths, through the real loop ────────────────────────────

class FakePerf:
    def __init__(self, **kw):
        self.hit_tp1 = self.hit_tp2 = self.hit_tp3 = False
        self.tp1_hit_at = self.tp2_hit_at = self.tp3_hit_at = None
        self.outcome = SignalOutcome.ACTIVE
        self.actual_return = self.max_drawdown = self.mfe_pct = None
        self.bars_to_outcome = self.closed_at = self.detail_label = None
        self.hit_time = self.detected_at = None
        self.resolution_version = self.resolution_source = None   # F1-d columns
        self.is_expired = False
        self.__dict__.update(kw)


class FakeCollector:
    def __init__(self, df=None, ticker=None):
        self.df, self.ticker = df, ticker

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, **kw):
        if self.df is None:
            raise RuntimeError("no data")
        return self.df

    async def fetch_ticker(self, symbol):
        if self.ticker is None:
            raise RuntimeError("no ticker")
        return {"current_price": self.ticker}

    async def close(self):
        pass


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _signal(age_hours=3.0, *, tf=Timeframe.M15, expires_in_hours=48.0, perf=None,
            signal_type="BUY", **over):
    gen = NOW - timedelta(hours=age_hours)
    base = dict(
        id="sig-1", asset_id="asset-1", generated_at=gen,
        expires_at=gen + timedelta(hours=expires_in_hours),
        asset=NS(symbol="BTCUSDT", asset_type=NS(value="crypto"), id="asset-1"),
        timeframe=tf, signal_type=NS(value=signal_type), direction=NS(value="bullish"),
        entry_zone_low=99.0, entry_zone_high=101.0,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3,
        is_active=True, performance=perf if perf is not None else FakePerf(),
        live_status=None, live_status_since=None, status_reason=None,
        status_updated_at=None, flipflop_prevented_count=0,
    )
    base.update(over)
    return NS(**base)


def _bars(rows, *, signal, start_after_gen_min=15):
    idx = pd.date_range(signal.generated_at + timedelta(minutes=start_after_gen_min),
                        periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=idx).assign(volume=1.0)


@pytest.fixture
def loop_env(monkeypatch):
    monkeypatch.setattr(tracker, "update_coin_memory", AsyncMock())
    monkeypatch.setattr(tracker, "notify_lifecycle", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_failopen", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_live_sl_failopen", AsyncMock())
    monkeypatch.setattr(tracker, "make_event", MagicMock(return_value=object()))
    tracker._tracking_in_flight = False

    def run(signals, binance):
        monkeypatch.setattr(tracker, "BinanceCollector", lambda: binance)
        monkeypatch.setattr(tracker, "YahooCollector", lambda: FakeCollector())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=FakeResult(signals))
        db.add, db.commit = MagicMock(), AsyncMock()
        return tracker._track_and_resolve_active_signals_impl(db)

    return run


@pytest.mark.asyncio
async def test_bar_walk_stamps_bar_walk(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert perf.resolution_source == "bar_walk"
    assert perf.resolution_version == 1
    assert perf.detail_label is not None            # the label write is untouched


@pytest.mark.asyncio
async def test_organic_expiry_stamps_expiry_not_bar_walk(loop_env):
    """Same write block as bar-walk — the stamp must follow is_expired_flag,
    mirroring the trade-path row's expiry-vs-walk split."""
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert perf.is_expired is True
    assert perf.resolution_source == "expiry"
    assert perf.resolution_version == 1
    # characterization intact: organic expiry books WIN/LOSS/BREAKEVEN, not EXPIRED
    assert perf.outcome in (SignalOutcome.WIN, SignalOutcome.LOSS, SignalOutcome.BREAKEVEN)


@pytest.mark.asyncio
async def test_live_sl_stamps_live_sl(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df, ticker=96.2))

    assert perf.detail_label == "live_sl_hit"       # the shortcut owns the row
    assert perf.resolution_source == "live_sl"
    assert perf.resolution_version == 1


@pytest.mark.asyncio
async def test_hold_expiry_stamps_hold_expiry(loop_env):
    """The EXPIRED-enum-with-NULL-label shape was indistinguishable from the
    admin paths until this stamp."""
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf,
                  signal_type="HOLD", entry_zone_low=None, entry_zone_high=None)
    await loop_env([sig], FakeCollector(df=None))

    assert perf.outcome is SignalOutcome.EXPIRED
    assert perf.detail_label is None                # unchanged: label stays NULL
    assert perf.resolution_source == "hold_expiry"
    assert perf.resolution_version == 1


@pytest.mark.asyncio
async def test_unresolved_and_failed_fetch_stamp_nothing(loop_env):
    p1, p2 = FakePerf(), FakePerf()
    s1 = _signal(age_hours=3.0, perf=p1)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=s1)
    await loop_env([s1], FakeCollector(df=df))              # walks, nothing resolves
    s2 = _signal(age_hours=3.0, perf=p2)
    await loop_env([s2], FakeCollector(df=None))            # fetch fails outright

    for p in (p1, p2):
        assert p.resolution_source is None and p.resolution_version is None


# ── reversal + admin: no loop harness — lock the stamps at source level ─────

def test_reversal_stamp_sits_beside_the_label_write():
    sched = _src("services/scheduler.py")
    assert "old_perf.resolution_source = labels.RES_SRC_REVERSAL" in sched
    assert "old_perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION" in sched


def test_admin_paths_stamp_their_distinct_identities():
    admin = _src("api/routes/admin.py")
    assert admin.count("resolution_source = labels.RES_SRC_ADMIN_INVALIDATE") == 1
    assert admin.count("resolution_source = labels.RES_SRC_ADMIN_BULK_CLEAN") == 1
    assert admin.count("resolution_version = labels.RESOLUTION_SEMANTICS_VERSION") == 2


def test_tracker_stamp_sites_use_the_constants():
    """Three stamp sites in the tracker (the shared bar-walk/expiry block picks
    by is_expired_flag), all through the labels constants — no raw literals."""
    trk = _src("backtesting/tracker.py")
    assert trk.count("perf.resolution_version = labels.RESOLUTION_SEMANTICS_VERSION") == 3
    assert "perf.resolution_source = labels.RES_SRC_LIVE_SL" in trk
    assert "perf.resolution_source = labels.RES_SRC_HOLD_EXPIRY" in trk
    assert "labels.RES_SRC_EXPIRY if is_expired_flag" in trk
    for raw in ('"bar_walk"', '"live_sl"', '"expiry"'):
        # the only remaining raw copies belong to the trade_path extra writers
        assert trk.count(raw) <= 2, f"unexpected raw {raw} literals in tracker"


def test_fidelity_sets_carry_no_raw_literals_anymore():
    fid = _src("trade_mgmt/fidelity.py")
    for raw in ('"expired_profit"', '"expired_loss"', '"expired_flat"',
                '"tp1_hit"', '"live_sl_hit"'):
        assert raw not in fid, f"fidelity.py still holds a literal copy: {raw}"
    assert "from app.backtesting import labels" in fid


if __name__ == "__main__":
    print("pytest ile calistirin (async harness fixture'lari gerekli)")
