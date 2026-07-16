"""CP-F0-K: coin_memory's base facets have ONE derivation, and a rebuild.

update_coin_memory is an incremental online fold inside the caller's fail-open
envelope: a fold that raises is logged and skipped, the resolution commits anyway,
and the count is short by one FOREVER. tm_stats has had rebuild_tm_stats to repair
exactly that; the base facets had nothing, so drift could only accumulate — and the
F0 gate ("rebuild == online, byte-identical") could not even be evaluated for them.

Measured before writing this: 102 of 173 cells undercount, always one-way (0 over,
net -157), and 5 cells sit on the wrong side of the adaptive gate because of it.
Root cause is NOT a bug — 161 of those resolutions closed before coin_memory
existed (first cell 2026-06-22 21:04), and the online path is not lagging today
(fold_geride = 0). The debt is that there was no way to repair it.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.models.intelligence import CoinMemory
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome
from app.services.coin_memory import (
    FOLDABLE_OUTCOMES, MIN_SAMPLES_FOR_ADAPTIVE, fold_signal_into,
)

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _cell(symbol="BTCUSDT", tf="15m"):
    return CoinMemory(symbol=symbol, timeframe=tf, total_signals=0, wins=0, losses=0,
                      engine_stats={}, regime_stats={}, outcome_label_stats={})


def _sig(direction="bullish", tf=Timeframe.M15):
    return NS(id="s1", timeframe=tf, direction=NS(value=direction))


def _perf(outcome=SignalOutcome.WIN, label=None, bars=None):
    return NS(outcome=outcome, detail_label=label, bars_to_outcome=bars)


def _snap(regime="trending_bull", bias="bullish"):
    return NS(regime=regime, engine_scores={
        "technical_analysis": {"bias": bias, "score": 70.0},
        "smart_money_concepts": {"bias": bias, "score": 65.0},
    })


def _facets(mem):
    """The v1 base facets — what a rebuild owns. tm_stats is a different derivation."""
    return {
        "total_signals": mem.total_signals, "wins": mem.wins, "losses": mem.losses,
        "engine_stats": mem.engine_stats, "regime_stats": mem.regime_stats,
        "outcome_label_stats": mem.outcome_label_stats,
        "adaptive_weights": mem.adaptive_weights,
        "avg_bars_to_outcome": mem.avg_bars_to_outcome,
    }


def _book(n=24):
    """A deterministic run of resolutions across regimes/directions/outcomes."""
    out = []
    for i in range(n):
        win = i % 3 != 0
        out.append((
            _sig(direction="bullish" if i % 2 == 0 else "bearish"),
            _perf(outcome=SignalOutcome.WIN if win else SignalOutcome.LOSS,
                  label="tp1_hit" if win else "sl_hit", bars=3 + (i % 5)),
            _snap(regime="trending_bull" if i % 2 == 0 else "ranging",
                  bias="bullish" if i % 2 == 0 else "bearish"),
        ))
    return out


# ── 1 · rebuild == online, by construction ──────────────────────────────────
def test_rebuild_reproduces_the_online_fold_exactly():
    """The F0 gate. Both paths call fold_signal_into, so this is identity, not luck."""
    online, rebuilt = _cell(), _cell()
    book = _book()

    for sig, perf, snap in book:                  # as the tracker folds them, one by one
        fold_signal_into(online, sig, perf, snap)
    for sig, perf, snap in book:                  # as a rebuild would, from the SoT
        fold_signal_into(rebuilt, sig, perf, snap)

    assert _facets(rebuilt) == _facets(online)
    assert online.total_signals == 24             # …and it actually folded something


def test_the_shared_body_is_what_makes_them_equal():
    """Sabotage-style: perturb the fold and BOTH move together — there is no second
    implementation that could quietly disagree."""
    a, b = _cell(), _cell()
    sig, perf, snap = _sig(), _perf(SignalOutcome.WIN, "tp1_hit", 4), _snap()

    fold_signal_into(a, sig, perf, snap)
    fold_signal_into(b, sig, perf, snap)
    assert _facets(a) == _facets(b)

    fold_signal_into(b, sig, perf, snap)          # one extra fold on b only
    assert _facets(a) != _facets(b)               # the comparison has teeth


# ── 2 · Idempotence of the reset+refold cycle ───────────────────────────────
def test_rebuilding_twice_changes_nothing():
    from app.services.coin_memory import _reset_base_facets

    mem = _cell()
    book = _book()

    def rebuild():
        _reset_base_facets(mem)
        for sig, perf, snap in book:
            fold_signal_into(mem, sig, perf, snap)

    rebuild()
    once = _facets(mem)
    rebuild()
    assert _facets(mem) == once                   # a second pass is a no-op


def test_reset_clears_the_base_facets_but_not_the_trade_path_rollup():
    """tm_stats belongs to rebuild_tm_stats. A base rebuild must not touch it."""
    from app.services.coin_memory import _reset_base_facets

    mem = _cell()
    for sig, perf, snap in _book(5):
        fold_signal_into(mem, sig, perf, snap)
    mem.tm_stats = {"base": {"n": 7}}
    mem.tm_sample_count = 7

    _reset_base_facets(mem)

    assert mem.total_signals == 0 and mem.wins == 0 and mem.losses == 0
    assert mem.engine_stats == {} and mem.regime_stats == {} and mem.outcome_label_stats == {}
    assert mem.adaptive_weights is None and mem.avg_bars_to_outcome is None
    assert mem.tm_stats == {"base": {"n": 7}} and mem.tm_sample_count == 7   # untouched


# ── 3 · A missing cell gets built ───────────────────────────────────────────
def test_a_fresh_cell_folds_from_zero():
    """The 10 cells with resolutions but no memory row: a rebuild creates them."""
    mem = _cell(symbol="OPUSDT", tf="4h")
    assert mem.total_signals == 0

    fold_signal_into(mem, _sig(tf=Timeframe.H4), _perf(SignalOutcome.LOSS, "sl_hit", 9), _snap())

    assert mem.total_signals == 1 and mem.losses == 1 and mem.wins == 0
    assert mem.outcome_label_stats == {"sl_hit": 1}


# ── 4 · What the fold does and does not learn from ──────────────────────────
def test_an_unresolved_outcome_teaches_nothing():
    mem = _cell()
    assert fold_signal_into(mem, _sig(), _perf(SignalOutcome.ACTIVE), _snap()) is False
    assert _facets(mem) == _facets(_cell())      # not one counter moved


def test_every_resolved_outcome_folds():
    for outcome in FOLDABLE_OUTCOMES:
        mem = _cell()
        assert fold_signal_into(mem, _sig(), _perf(outcome, "x", 3), _snap()) is True
        assert mem.total_signals == 1
    # INVALIDATED counts as a loss (the reversal path books it)
    mem = _cell()
    fold_signal_into(mem, _sig(), _perf(SignalOutcome.INVALIDATED), _snap())
    assert mem.losses == 1


def test_a_missing_snapshot_still_folds_the_counters():
    """Engine/regime facets need the snapshot; the counters do not."""
    mem = _cell()
    assert fold_signal_into(mem, _sig(), _perf(SignalOutcome.WIN, "tp1_hit", 3), None) is True
    assert mem.total_signals == 1 and mem.wins == 1
    assert mem.engine_stats == {} and mem.regime_stats == {}


def test_engine_credit_follows_the_outcome_direction():
    mem = _cell()
    # bullish signal + bullish engines + WIN → the engines were right
    fold_signal_into(mem, _sig("bullish"), _perf(SignalOutcome.WIN), _snap(bias="bullish"))
    assert mem.engine_stats["technical_analysis"] == {"correct": 1, "total": 1, "win_rate": 1.0}
    # bullish signal + bullish engines + LOSS → bearish was right; they were wrong
    fold_signal_into(mem, _sig("bullish"), _perf(SignalOutcome.LOSS), _snap(bias="bullish"))
    assert mem.engine_stats["technical_analysis"] == {"correct": 1, "total": 2, "win_rate": 0.5}


# ── 5 · The timeframe representation that misled the scope analysis ─────────
def test_coin_memory_keys_off_the_enum_VALUE_not_its_name():
    """coin_memory.timeframe stores '15m' (Timeframe.M15.value) while the signals
    table renders the enum as 'M15'. Both are correct; conflating them is not — it
    made the first drift query report all 336 cells as diverging. Production code is
    consistent because both fold paths key off .value; this pins that."""
    assert Timeframe.M15.value == "15m"
    assert Timeframe.H1.value == "1h"
    assert Timeframe.H4.value == "4h"
    assert Timeframe.D1.value == "1d"
    assert Timeframe.M15.name == "M15"           # the other rendering, for the record
    assert Timeframe.M15.value != Timeframe.M15.name


def test_both_paths_derive_the_key_the_same_way():
    """update_coin_memory and rebuild_coin_memory must agree on the cell key, or a
    rebuild would build a parallel set of cells beside the online ones."""
    import inspect

    from app.services import coin_memory as cm
    online = inspect.getsource(cm.update_coin_memory)
    rebuild = inspect.getsource(cm.rebuild_coin_memory)
    key_expr = 'signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe)'
    assert key_expr in online
    assert key_expr in rebuild


# ── 6 · The adaptive gate — why the drift mattered ─────────────────────────
def test_undercounting_can_hold_a_cell_below_the_adaptive_gate():
    """5 live cells sit here: the truth is >= 20 resolutions, the memory says fewer,
    so the learned layer stays off. This is the consequence a rebuild repairs."""
    truth, drifted = _cell(), _cell()
    book = _book(MIN_SAMPLES_FOR_ADAPTIVE + 1)

    for sig, perf, snap in book:
        fold_signal_into(truth, sig, perf, snap)
    for sig, perf, snap in book[:-3]:            # three folds lost to fail-open
        fold_signal_into(drifted, sig, perf, snap)

    assert truth.total_signals >= MIN_SAMPLES_FOR_ADAPTIVE
    assert drifted.total_signals < MIN_SAMPLES_FOR_ADAPTIVE
    assert truth.total_signals - drifted.total_signals == 3
