"""CP-ENTRY-LIVESL-PROMOTION-FIX — the live-SL shortcut must not skip activation.

WHAT WENT WRONG IN PRODUCTION
-----------------------------
ONTUSDT M15 BEARISH (2026-08-06) was born `waiting_entry`, genuinely reached its
entry level at 00:15:00 (passive telemetry: entry_reached=true, zone penetration
100%), and was closed at 00:30:00 by the live-SL shortcut with a real, correct
BREAKEVEN of -0.2813%.

Its history, however, read:

    null -> waiting_entry
    waiting_entry -> closed          <-- the `active` phase never happened

The trade was real; the lifecycle record of it was not. The API therefore served
`live_status="waiting_entry"` + `status_reason="Giriş seviyesi henüz görülmedi"`
NEXT TO `outcome="breakeven", actual_return=-0.2813` — a surface that contradicts
itself.

THE ORDERING, NOT A PHANTOM FILL
--------------------------------
`active_signals` is `WHERE is_active == True`, which includes `waiting_entry`
rows. The live-SL shortcut resolves and `continue`s ~220 lines BEFORE the entry
activation gate, so a signal consumed by the shortcut never reaches the only
place that writes `waiting_entry -> active`.

MAVUSDT proves it was a race, not a systematic bypass: same M15, same BEARISH,
born 14 minutes later, promoted at 00:30:13 in the SAME pass family that closed
ONTUSDT at 00:30:00. Production blast radius: 84 live-SL closes, 83 with the
promotion row, 1 without.

WHAT THESE TESTS PIN
--------------------
1  proof present  -> waiting_entry -> active -> closed   (the fix)
2  normal gate    -> exactly one promotion, no duplicate  (no regression)
3  NO proof       -> no invented `active`                 (the dangerous direction)
4  already active -> no second promotion row
5  replay         -> idempotent
6  P&L / outcome / resolution identity unchanged

Deliberately NOT changed here: what a no-proof signal's terminal result should
be. That is a separate question about the live-SL path's own semantics; this CP
only restores the missing lifecycle transition.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.backtesting import lifecycle, tracker
from app.models.intelligence import SignalStatusHistory
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome

NOW = datetime.now(timezone.utc)

# ── The real ONTUSDT numbers (deterministic fixture, no DB dependency) ───────
ONT_ZONE_LOW = 0.03766
ONT_ZONE_HIGH = 0.037692
ONT_ENTRY = (ONT_ZONE_LOW + ONT_ZONE_HIGH) / 2.0     # 0.037676 — canonical midpoint
ONT_SL = 0.037782
ONT_TP1, ONT_TP2, ONT_TP3 = 0.03757, 0.037479, 0.037359
ONT_LIVE_BREACH = 0.03783                            # ticker at 00:30 — above SL


class FakePerf:
    def __init__(self, **kw):
        self.hit_tp1 = self.hit_tp2 = self.hit_tp3 = False
        self.tp1_hit_at = self.tp2_hit_at = self.tp3_hit_at = None
        self.outcome = SignalOutcome.ACTIVE
        self.actual_return = self.max_drawdown = self.mfe_pct = None
        self.bars_to_outcome = self.closed_at = self.detail_label = None
        self.detected_at = self.hit_time = None
        self.resolution_source = self.resolution_version = None
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

    def scalar_one_or_none(self):
        return None


def _ont_signal(*, live_status=lifecycle.WAITING_ENTRY, age_min=25.0, perf=None, **over):
    """ONTUSDT as it stood at the 00:30 pass."""
    gen = NOW - timedelta(minutes=age_min)
    base = dict(
        id="ont-1", asset_id="asset-ont", generated_at=gen,
        expires_at=gen + timedelta(hours=48),
        asset=NS(symbol="ONTUSDT", asset_type=NS(value="crypto"), id="asset-ont"),
        timeframe=Timeframe.M15, signal_type=NS(value="SELL"),
        direction=NS(value="bearish"),
        entry_zone_low=ONT_ZONE_LOW, entry_zone_high=ONT_ZONE_HIGH,
        stop_loss=ONT_SL, tp1=ONT_TP1, tp2=ONT_TP2, tp3=ONT_TP3,
        is_active=True, performance=perf if perf is not None else FakePerf(),
        live_status=live_status,
        live_status_since=gen if live_status else None,
        status_reason=None, status_updated_at=None, flipflop_prevented_count=0,
    )
    base.update(over)
    return NS(**base)


def _bars(rows, signal, *, start_after_gen_min=10, freq="15min"):
    idx = pd.date_range(signal.generated_at + timedelta(minutes=start_after_gen_min),
                        periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=idx).assign(volume=1.0)


def _bars_entry_touched(signal):
    """A post-birth bar whose HIGH reaches the entry level — a SHORT fills there.

    high 0.03770 >= entry 0.037676, so both the passive detector and the gate
    agree the entry was reached. Deliberately NOT beyond the stop, so the bar
    walk alone would not resolve it: only the live ticker does.
    """
    return _bars([(0.037660, 0.037700, 0.037650, 0.037690)], signal)


def _bars_entry_never_touched(signal):
    """Price stayed BELOW the entry level for a short — no fill, ever."""
    return _bars([(0.037600, 0.037640, 0.037560, 0.037620)], signal)


@pytest.fixture
def promo_env(monkeypatch):
    """Run the REAL loop; keep `apply_live_status`/`make_event` REAL.

    `test_f01g_tracker_loop`'s fixture stubs `tracker.make_event`, which is
    exactly what hides the rows this CP is about — so this fixture leaves the
    lifecycle writers alone and stubs only what leaves the process.
    """
    monkeypatch.setattr(tracker, "update_coin_memory", AsyncMock())
    monkeypatch.setattr(tracker, "notify_lifecycle", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_failopen", AsyncMock())
    monkeypatch.setattr(tracker, "_write_trade_path_live_sl_failopen", AsyncMock())
    # The gate is live in production; these tests are about its interaction
    # with the shortcut, so it must be on here too.
    monkeypatch.setattr(tracker, "entry_activation_enabled", lambda: True)
    tracker._tracking_in_flight = False

    added: list = []

    def run(signals, binance):
        monkeypatch.setattr(tracker, "BinanceCollector", lambda: binance)
        db = AsyncMock()

        # The loop issues TWO selects: the active-signal set first, then the
        # `proven_entry_ids` lookup. A single canned result would hand the
        # signal objects to `set(...)` and blow up on unhashable namespaces —
        # so answer by position: signals first, nothing after.
        calls = {"n": 0}

        async def _execute(*_a, **_kw):
            calls["n"] += 1
            return FakeResult(signals if calls["n"] == 1 else [])

        db.execute = _execute
        db.add = MagicMock(side_effect=added.append)
        db.commit = AsyncMock()
        return tracker._track_and_resolve_active_signals_impl(db)

    run.added = added
    return run


def _transitions(added):
    """(from_status, to_status) for every real history row the loop wrote."""
    return [(r.from_status, r.to_status) for r in added
            if isinstance(r, SignalStatusHistory)]


# ── TEST 1 · the ONTUSDT regression ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_1_live_sl_with_entry_proof_promotes_before_closing(promo_env):
    """waiting_entry -> active -> closed, in that order, on the live-SL path."""
    sig = _ont_signal()
    binance = FakeCollector(df=_bars_entry_touched(sig), ticker=ONT_LIVE_BREACH)
    await promo_env([sig], binance)

    trans = _transitions(promo_env.added)
    assert (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE) in trans, (
        f"the fill was proven but the promotion row was never written: {trans}")
    assert (lifecycle.ACTIVE, "closed") in trans, (
        f"the close must originate from `active`, not `waiting_entry`: {trans}")
    assert (lifecycle.WAITING_ENTRY, "closed") not in trans, (
        "the pre-fix contradiction is back")

    # Ordering: promotion strictly before the terminal row.
    order = [t for t in trans if t in {(lifecycle.WAITING_ENTRY, lifecycle.ACTIVE),
                                       (lifecycle.ACTIVE, "closed")}]
    assert order == [(lifecycle.WAITING_ENTRY, lifecycle.ACTIVE),
                     (lifecycle.ACTIVE, "closed")], order


@pytest.mark.asyncio
async def test_1b_the_trade_result_itself_is_untouched(promo_env):
    """Only the lifecycle record changes — P&L, outcome and identity do not."""
    sig = _ont_signal()
    binance = FakeCollector(df=_bars_entry_touched(sig), ticker=ONT_LIVE_BREACH)
    await promo_env([sig], binance)

    perf = sig.performance
    assert perf.detail_label == "live_sl_hit"
    assert perf.resolution_source == "live_sl"
    assert perf.outcome is SignalOutcome.BREAKEVEN
    # entry -> original stop for a short that never banked TP1
    expected = (ONT_ENTRY - ONT_SL) / ONT_ENTRY * 100.0
    assert perf.actual_return == pytest.approx(expected, abs=1e-9)
    assert perf.actual_return == pytest.approx(-0.2813, abs=5e-4)   # the real record
    assert sig.is_active is False


# ── TEST 2 · the normal gate path still promotes exactly once ────────────────
@pytest.mark.asyncio
async def test_2_normal_activation_path_writes_one_promotion(promo_env):
    """No live-SL breach: the gate promotes, and the shortcut adds nothing."""
    sig = _ont_signal()
    # Ticker safely INSIDE the stop -> no live hit; bars prove the entry.
    binance = FakeCollector(df=_bars_entry_touched(sig), ticker=0.037600)
    await promo_env([sig], binance)

    trans = _transitions(promo_env.added)
    promos = [t for t in trans if t == (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE)]
    assert len(promos) == 1, f"expected exactly one promotion, got {promos} in {trans}"


# ── TEST 3 · NO proof must never be turned into an `active` ──────────────────
@pytest.mark.asyncio
async def test_3_live_sl_without_entry_proof_invents_nothing(promo_env):
    """The dangerous direction: a stop breach is NOT by itself an entry proof."""
    sig = _ont_signal()
    binance = FakeCollector(df=_bars_entry_never_touched(sig), ticker=ONT_LIVE_BREACH)
    await promo_env([sig], binance)

    trans = _transitions(promo_env.added)
    assert (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE) not in trans, (
        f"an entry that never happened was invented: {trans}")
    assert sig.live_status != lifecycle.ACTIVE


# ── TEST 4 · an already-active signal gains no second promotion ──────────────
@pytest.mark.asyncio
async def test_4_already_active_gets_no_duplicate_promotion(promo_env):
    sig = _ont_signal(live_status=lifecycle.ACTIVE)
    binance = FakeCollector(df=_bars_entry_touched(sig), ticker=ONT_LIVE_BREACH)
    await promo_env([sig], binance)

    trans = _transitions(promo_env.added)
    assert (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE) not in trans, trans
    assert (lifecycle.ACTIVE, "closed") in trans, trans


# ── TEST 5 · replay is idempotent ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_5_replaying_the_same_pass_adds_no_duplicate(promo_env):
    """A second pass over the SAME signal object must not re-promote or re-close.

    `is_active` is cleared by the first resolution, so the second pass sees an
    empty active set — the loop's own guard against double resolution.
    """
    sig = _ont_signal()
    binance = FakeCollector(df=_bars_entry_touched(sig), ticker=ONT_LIVE_BREACH)
    await promo_env([sig], binance)
    first = list(_transitions(promo_env.added))

    live = [s for s in [sig] if s.is_active]
    await promo_env(live, binance)
    second = list(_transitions(promo_env.added))

    assert second == first, f"replay wrote extra rows: {second[len(first):]}"
    assert second.count((lifecycle.WAITING_ENTRY, lifecycle.ACTIVE)) == 1
    assert second.count((lifecycle.ACTIVE, "closed")) == 1


# ── TEST 6 · the 83 healthy cases: a bullish live-SL close is unchanged ──────
@pytest.mark.asyncio
async def test_6_bullish_live_sl_close_is_unchanged(promo_env):
    """Representative of the 83 production rows that already had the promotion."""
    sig = _ont_signal(
        direction=NS(value="bullish"), signal_type=NS(value="BUY"),
        entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=97.0,
        tp1=101.5, tp2=103.0, tp3=105.0, live_status=lifecycle.ACTIVE,
    )
    binance = FakeCollector(
        df=_bars([(100.0, 100.4, 99.6, 100.0)], sig), ticker=96.0)
    await promo_env([sig], binance)

    perf = sig.performance
    assert perf.detail_label == "live_sl_hit"
    assert perf.resolution_source == "live_sl"
    assert perf.outcome is SignalOutcome.LOSS
    assert perf.actual_return == pytest.approx((97.0 - 100.0) / 100.0 * 100.0, abs=1e-9)
    trans = _transitions(promo_env.added)
    assert (lifecycle.WAITING_ENTRY, lifecycle.ACTIVE) not in trans
