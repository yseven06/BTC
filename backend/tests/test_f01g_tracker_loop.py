"""CP-F0-1G: lock the tracker loop's WIRING, not its helpers.

F0-1B/1E/1H/1F shipped 41 tests. Every one of them tests a pure helper in
isolation, and none of them runs the loop that consumes it. Reverting all three
call sites at once —

    limit = _recovery_fetch_limit(...)          ->  limit = 100          (1B)
    _flags = _live_ladder_flags(...)            ->  _flags = None        (1H)
    if not _window_reaches_generation(...)      ->  if False:            (1F)

— left the whole suite green. These tests run the real loop against a fake db and
fake collectors so that each of those sabotages fails something. Everything the
CPs actually changed is exercised for real; only external side effects (network,
DB writes, notifications) are stubbed.

G-5/G-6 also settle the debt left when CP-F0-1D was cancelled as "already correct":
nothing anywhere asserted that a bar-walk resolution beats the wall-clock expiry.
G-7 pins today's mixed closed_at semantics ahead of F0-1A, so that CP's diff shows
what it actually changes.
"""
import logging
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
LOGGER = "app.backtesting.tracker"


# ── Doubles ─────────────────────────────────────────────────────────────────
class FakePerf:
    def __init__(self, **kw):
        self.hit_tp1 = self.hit_tp2 = self.hit_tp3 = False
        self.tp1_hit_at = self.tp2_hit_at = self.tp3_hit_at = None
        self.outcome = SignalOutcome.ACTIVE
        self.actual_return = self.max_drawdown = self.mfe_pct = None
        self.bars_to_outcome = self.closed_at = self.detail_label = None
        self.is_expired = False
        self.__dict__.update(kw)


class FakeCollector:
    """Records every fetch so a test can assert what the loop ASKED for."""

    def __init__(self, df=None, ticker=None):
        self.df, self.ticker = df, ticker
        self.ohlcv_calls, self.ticker_calls = [], []

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, **kw):
        self.ohlcv_calls.append({"symbol": symbol, "timeframe": timeframe, "limit": limit})
        if self.df is None:
            raise RuntimeError("no data for this symbol")
        return self.df

    async def fetch_ticker(self, symbol):
        self.ticker_calls.append(symbol)
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


def _signal(age_hours=2.0, *, tf=Timeframe.M15, symbol="BTCUSDT", asset_type="crypto",
            expires_in_hours=48.0, perf=None, **over):
    gen = NOW - timedelta(hours=age_hours)
    base = dict(
        id="sig-1", asset_id="asset-1", generated_at=gen,
        expires_at=gen + timedelta(hours=expires_in_hours),
        asset=NS(symbol=symbol, asset_type=NS(value=asset_type), id="asset-1"),
        timeframe=tf, signal_type=NS(value="BUY"), direction=NS(value="bullish"),
        entry_zone_low=99.0, entry_zone_high=101.0,
        stop_loss=SL, tp1=TP1, tp2=TP2, tp3=TP3,
        is_active=True, performance=perf if perf is not None else FakePerf(),
        live_status=None, live_status_since=None, status_reason=None,
        status_updated_at=None, flipflop_prevented_count=0,
    )
    base.update(over)
    return NS(**base)


def _bars(rows, *, start_after_gen_min=15, signal=None, freq="15min"):
    idx = pd.date_range(signal.generated_at + timedelta(minutes=start_after_gen_min),
                        periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=idx).assign(volume=1.0)


@pytest.fixture
def loop_env(monkeypatch):
    """Run the REAL loop; stub only what leaves the process."""
    monkeypatch.setattr(tracker, "update_coin_memory", AsyncMock())
    monkeypatch.setattr(tracker, "notify_lifecycle", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_failopen", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_live_sl_failopen", AsyncMock())
    monkeypatch.setattr(tracker, "make_event", MagicMock(return_value=object()))
    tracker._tracking_in_flight = False

    def run(signals, binance, yahoo=None):
        yahoo = yahoo or FakeCollector()
        monkeypatch.setattr(tracker, "BinanceCollector", lambda: binance)
        monkeypatch.setattr(tracker, "YahooCollector", lambda: yahoo)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=FakeResult(signals))
        db.add, db.commit = MagicMock(), AsyncMock()
        return tracker._track_and_resolve_active_signals_impl(db)

    return run


# ── G-1 · 1B wiring: the fetch must ASK for an age-scaled window ────────────
@pytest.mark.asyncio
async def test_g1_fetch_asks_for_an_age_scaled_window(loop_env):
    """Sabotage caught: reverting to `limit=100` makes this fail.

    30.1h sits mid-bar on purpose: the loop reads the real clock, so an age landing
    exactly on a bar boundary would round up or down with sub-second drift.
    """
    sig = _signal(age_hours=30.1)
    binance = FakeCollector(df=_bars([(100.0, 100.4, 99.6, 100.0)], signal=sig))
    await loop_env([sig], binance)

    assert binance.ohlcv_calls, "the loop never fetched"
    asked = binance.ohlcv_calls[0]["limit"]
    assert asked == 126, f"30.1h of M15 needs ceil(120.4)=121 bars + 5 buffer, asked {asked}"
    assert asked > 100                       # the pre-CP constant would fail here


@pytest.mark.asyncio
async def test_g1b_young_signal_still_asks_for_the_floor(loop_env):
    sig = _signal(age_hours=1.0)
    binance = FakeCollector(df=_bars([(100.0, 100.4, 99.6, 100.0)], signal=sig))
    await loop_env([sig], binance)
    assert binance.ohlcv_calls[0]["limit"] == 100


# ── G-2 · the Yahoo/BIST branch was deliberately left alone ────────────────
@pytest.mark.asyncio
async def test_g2_yahoo_branch_still_asks_for_a_fixed_100(loop_env):
    sig = _signal(age_hours=30.0, symbol="THYAO.IS", asset_type="stock")
    yahoo = FakeCollector(df=_bars([(100.0, 100.4, 99.6, 100.0)], signal=sig))
    binance = FakeCollector()
    await loop_env([sig], binance, yahoo)

    assert yahoo.ohlcv_calls[0]["limit"] == 100      # untouched by 1B
    assert binance.ohlcv_calls == []                 # crypto path not used


# ── G-3 · 1H wiring: the live shortcut must read the BARS ──────────────────
@pytest.mark.asyncio
async def test_g3_live_sl_books_the_ladder_from_the_bars_not_stale_perf(loop_env):
    """The gap case. perf says no TP1; the bars plainly show one.

    Sabotage caught: `_flags = None` books the full original-stop loss (-3%).
    """
    perf = FakePerf(hit_tp1=False)               # stale: nothing ran during the gap
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([
        (100.0, 102.0, 99.8, 101.8),             # TP1 banked -> stop to breakeven
        (101.8, 101.9, 96.0, 96.2),              # then through the original stop
    ], signal=sig)
    binance = FakeCollector(df=df, ticker=96.2)  # live price is under the stop

    await loop_env([sig], binance)

    assert binance.ticker_calls == ["BTCUSDT"]                # Pass-1 did fire
    assert perf.detail_label == "live_sl_hit"                 # …and it owns the close
    assert sig.is_active is False
    assert perf.outcome is SignalOutcome.WIN                  # NOT a full-stop LOSS
    assert perf.actual_return == pytest.approx(0.75, abs=0.01)
    assert perf.actual_return > 0                             # sabotage -> -3.0


@pytest.mark.asyncio
async def test_g3b_live_sl_without_a_tp1_is_still_a_full_stop_loss(loop_env):
    """The other 516/776 rows: 1H must not have moved these."""
    perf = FakePerf(hit_tp1=False)
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df, ticker=96.2))

    assert perf.outcome is SignalOutcome.LOSS
    assert perf.actual_return == pytest.approx(-3.0, abs=0.01)


# ── G-4 · 1F wiring: a short window must be reported ───────────────────────
@pytest.mark.asyncio
async def test_g4_short_window_is_reported(loop_env, caplog):
    """Sabotage caught: `if False:` silences this."""
    sig = _signal(age_hours=30.0)
    late = pd.date_range(sig.generated_at + timedelta(hours=5), periods=3,
                         freq="15min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 100.4, "low": 99.6, "close": 100.0,
                       "volume": 1.0}, index=late)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await loop_env([sig], FakeCollector(df=df))

    assert any("fetched window starts at" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_g4b_complete_window_is_silent(loop_env, caplog):
    sig = _signal(age_hours=3.0)
    idx = pd.date_range(sig.generated_at - timedelta(minutes=30), periods=6,
                        freq="15min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 100.4, "low": 99.6, "close": 100.0,
                       "volume": 1.0}, index=idx)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await loop_env([sig], FakeCollector(df=df))

    assert not any("fetched window starts at" in r.message for r in caplog.records)


# ── G-5/G-6 · the cancelled 1D's debt: TP/SL beats the wall clock ──────────
@pytest.mark.asyncio
async def test_g5_a_bar_walk_resolution_beats_an_elapsed_expiry(loop_env):
    """expires_at is long past AND the bars show a stop. The stop must win.

    This is what CP-F0-1D was cancelled for ("the `if not resolved:` guard is
    already correct") — nothing asserted it until now.
    """
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf)   # expired 2h ago
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))          # no ticker -> no live shortcut

    assert sig.is_active is False
    assert perf.is_expired is False                      # expiry did NOT claim it
    assert perf.detail_label != "expired_flat"
    assert perf.outcome is SignalOutcome.LOSS
    assert perf.actual_return == pytest.approx(-3.0, abs=0.01)


@pytest.mark.asyncio
async def test_g6_expiry_still_fires_when_the_bars_resolve_nothing(loop_env):
    """The other half of the same guard — it must not be dead code."""
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert sig.is_active is False
    assert perf.is_expired is True
    assert perf.bars_to_outcome == 2


@pytest.mark.asyncio
async def test_g6b_an_unexpired_unresolved_signal_stays_active(loop_env):
    perf = FakePerf()
    sig = _signal(age_hours=3.0, expires_in_hours=48.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.6, 100.0), (100.0, 100.3, 99.7, 100.1)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert sig.is_active is True
    assert perf.is_expired is False
    assert perf.closed_at is None
    assert perf.outcome is SignalOutcome.ACTIVE


# ── G-7 · characterization for F0-1A: closed_at means two different things ──
@pytest.mark.asyncio
async def test_g7_bar_walk_stamps_closed_at_with_the_BAR_time(loop_env):
    """Pinned, not endorsed. F0-1A will separate hit_time from detected_at; this
    records what closed_at means today so that CP's diff is legible."""
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df))

    assert perf.closed_at == df.index[1]                 # the bar, not the clock
    assert perf.closed_at < NOW - timedelta(hours=2)     # hours in the past


@pytest.mark.asyncio
async def test_g7b_live_sl_stamps_closed_at_with_the_WALL_CLOCK(loop_env):
    """The same column, the other meaning — this is the mix F0-1A untangles."""
    perf = FakePerf()
    sig = _signal(age_hours=3.0, perf=perf)
    df = _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=sig)
    await loop_env([sig], FakeCollector(df=df, ticker=96.2))

    assert perf.detail_label == "live_sl_hit"
    assert perf.closed_at > NOW - timedelta(minutes=1)   # ~now, NOT the bar time
    assert perf.closed_at not in list(df.index)


# ── G-8 · a failed fetch stays fail-safe ───────────────────────────────────
@pytest.mark.asyncio
async def test_g8_a_failed_fetch_leaves_the_signal_active(loop_env):
    """df is None -> skip. The signal must survive, not resolve on no evidence."""
    perf = FakePerf()
    sig = _signal(age_hours=50.0, expires_in_hours=48.0, perf=perf)   # expiry is due
    summary = await loop_env([sig], FakeCollector(df=None))           # fetch raises

    assert sig.is_active is True             # …and expiry did NOT fire regardless
    assert perf.is_expired is False
    assert perf.closed_at is None
    assert summary["resolved"] == 0 and summary["processed"] == 1


@pytest.mark.asyncio
async def test_g8b_one_dead_symbol_cannot_stop_the_others(loop_env):
    good_perf = FakePerf()
    dead = _signal(age_hours=3.0, symbol="DEADUSDT")
    good = _signal(age_hours=3.0, perf=good_perf, id="sig-2")

    class PerSymbol(FakeCollector):
        async def fetch_ohlcv(self, symbol, timeframe, limit=100, **kw):
            self.ohlcv_calls.append({"symbol": symbol, "timeframe": timeframe, "limit": limit})
            if symbol == "DEADUSDT":
                raise RuntimeError("delisted")
            return _bars([(100.0, 100.4, 99.5, 99.8), (99.8, 99.9, 96.0, 96.2)], signal=good)

    summary = await loop_env([dead, good], PerSymbol())

    assert dead.is_active is True                       # skipped
    assert good.is_active is False                      # still resolved
    assert good_perf.outcome is SignalOutcome.LOSS
    assert summary["processed"] == 2 and summary["resolved"] == 1
