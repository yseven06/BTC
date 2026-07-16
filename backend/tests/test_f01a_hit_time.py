"""CP-F0-1A: hit_time / detected_at recorded at resolution, beside closed_at.

closed_at means the hit bar on the bar-walk path and the wall clock on every other
one, so closed_at - generated_at is a duration inflated by detection lag (after
downtime, by the outage). These lock the split that makes the lag measurable:

    hit_time    — the bar the walk says the level was reached, when a bar can say
    detected_at — the wall clock at write
    closed_at   — UNCHANGED, sixteen readers depend on it

Telemetry only: nothing reads these back, no decision sees them. Runs the real loop
(the same harness as F0-1G) so the writes are locked where they happen, not in a
helper.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.backtesting import tracker
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome

NOW = datetime.now(timezone.utc)
ENTRY, TP1, TP2, TP3, SL = 100.0, 101.5, 103.0, 105.0, 97.0


class FakePerf:
    def __init__(self, **kw):
        self.hit_tp1 = self.hit_tp2 = self.hit_tp3 = False
        self.tp1_hit_at = self.tp2_hit_at = self.tp3_hit_at = None
        self.outcome = SignalOutcome.ACTIVE
        self.actual_return = self.max_drawdown = self.mfe_pct = None
        self.bars_to_outcome = self.closed_at = self.detail_label = None
        self.hit_time = self.detected_at = None          # F0-1A columns
        self.is_expired = False
        self.__dict__.update(kw)


class FakeCollector:
    def __init__(self, df=None, ticker=None):
        self.df, self.ticker = df, ticker
        self.ohlcv_calls = []

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, **kw):
        self.ohlcv_calls.append(limit)
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


# ── Bar-walk: hit_time is the BAR, detected_at is the CLOCK ─────────────────
@pytest.mark.asyncio
async def test_bar_walk_records_the_hit_bar_and_the_write_clock(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert perf.hit_time == df.index[1]                    # the stop bar itself
    assert perf.detected_at > NOW - timedelta(minutes=1)   # ~now, not the bar
    assert perf.hit_time < perf.detected_at                # the lag, made visible
    assert perf.closed_at == df.index[1]                   # closed_at UNCHANGED (G-7)


@pytest.mark.asyncio
async def test_the_lag_equals_how_long_detection_trailed_the_bar(loop_env):
    """A signal whose stop broke hours ago: closed_at hides the lag, the split shows it."""
    perf = FakePerf()
    sig = _signal(age_hours=6.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    lag = perf.detected_at - perf.hit_time
    assert lag > timedelta(hours=5)          # the bar is old; we only just looked
    assert perf.hit_time == df.index[1]


# ── Live-SL: hit_time comes off the same replay that fixed the ladder ───────
@pytest.mark.asyncio
async def test_live_sl_records_the_stop_bar_as_hit_time(loop_env):
    """closed_at is the wall clock here; hit_time is the bar the walk points at."""
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df, ticker=96.2))

    assert perf.detail_label == "live_sl_hit"
    assert perf.hit_time == df.index[1]                    # a real bar…
    assert perf.closed_at > NOW - timedelta(minutes=1)     # …while closed_at is now
    assert perf.detected_at == perf.closed_at
    assert perf.hit_time < perf.detected_at


@pytest.mark.asyncio
async def test_live_sl_with_a_tp1_in_the_gap_keeps_both_the_ladder_and_the_bar(loop_env):
    """F0-1H's fix and F0-1A's timestamp come from the SAME walk — neither regressed."""
    perf = FakePerf(hit_tp1=False)                         # stale across the gap
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([
        # low stays ABOVE entry, or the breakeven stop would trigger in this very
        # candle and the walk would resolve here instead of on the next bar.
        (100.0, 102.0, 100.2, 101.8),                      # TP1 banked → stop to BE
        (101.8, 101.9, 96.0, 96.2),                        # through BE and the old stop
    ], signal=sig)
    # ticker under the ORIGINAL stop, so the shortcut fires despite the stale flag
    await loop_env([sig], FakeCollector(df=df, ticker=96.2))

    assert perf.detail_label == "live_sl_hit"              # the shortcut owns this
    assert perf.outcome is SignalOutcome.WIN               # 1H: not a full-stop loss
    assert perf.actual_return == pytest.approx(0.75, abs=0.01)
    assert perf.hit_time == df.index[1]                    # 1A: the breakeven-stop bar
    assert perf.closed_at > NOW - timedelta(minutes=1)     # …closed_at is still now


# ── hit_time is NULL when no bar can name the hit ───────────────────────────
@pytest.mark.asyncio
async def test_expiry_leaves_hit_time_null_because_there_was_no_hit(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert perf.is_expired is True
    assert perf.hit_time is None                # nothing was hit — NULL by definition
    assert perf.detected_at is not None         # …but we know when we said so
    assert perf.closed_at is not None           # closed_at still set (unchanged)


@pytest.mark.asyncio
async def test_hold_expiry_leaves_hit_time_null(loop_env):
    """A HOLD has no trade plan, so there is no level to hit."""
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf,
                  signal_type="HOLD", entry_zone_low=None, entry_zone_high=None)
    await loop_env([sig], FakeCollector(df=None))

    assert perf.outcome is SignalOutcome.EXPIRED
    assert perf.hit_time is None
    assert perf.detected_at is not None
    assert perf.detected_at == perf.closed_at


@pytest.mark.asyncio
async def test_an_unresolved_signal_records_neither(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert sig.is_active is True
    assert perf.hit_time is None and perf.detected_at is None


@pytest.mark.asyncio
async def test_a_failed_fetch_records_neither_and_does_not_raise(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    await loop_env([sig], FakeCollector(df=None))

    assert sig.is_active is True
    assert perf.hit_time is None and perf.detected_at is None


# ── The columns are inert: nothing reads them ──────────────────────────────
def test_nothing_in_the_backend_reads_hit_time_or_detected_at():
    """F0-1A is telemetry. If a decision ever starts reading these, it is a new CP.

    Guards against the columns quietly acquiring a reader — the CP-OBS-1A pattern.
    Attribute access only (`.hit_time`), so prose in docstrings is not a "reader";
    a write is `.hit_time =` (but not `==`).
    """
    import pathlib
    import re

    app = pathlib.Path(tracker.__file__).parents[1]        # app/, not the whole venv
    touch = re.compile(r"\.(hit_time|detected_at)\b(?!\s*=(?!=))")
    readers = []
    for py in app.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#")[0]
            if touch.search(code):
                readers.append(f"{py.relative_to(app)}:{i}: {line.strip()[:70]}")
    assert readers == [], "hit_time/detected_at gained a reader:\n" + "\n".join(readers)


def test_exposure_probe_still_keys_off_closed_at():
    """CP-OBS-1A counts recent same-direction stops by closed_at. F0-1A must not
    have moved that column out from under it."""
    import pathlib
    sched = (pathlib.Path(tracker.__file__).parents[1] / "services" / "scheduler.py")
    src = sched.read_text(encoding="utf-8")
    assert "SignalPerformance.closed_at >= since_1h" in src
    assert "SignalPerformance.closed_at >= since_3h" in src
    assert "hit_time" not in src and "detected_at" not in src
