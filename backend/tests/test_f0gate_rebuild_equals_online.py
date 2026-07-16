"""CP-F0-G2 — the F0 gate: rebuild == online.

What the gate means here is CODE DETERMINISM: given the same input sequence, the
online fold and the rebuild fold produce the same output. It is deliberately NOT
"a rebuild of the live DB equals the live DB" — that is false today by design (157
resolutions closed before coin_memory existed) and its remedy is the rebuild
OPERATION, not a code fix. A gate that goes red for something only an operation can
fix is the wrong instrument.

coin_memory has two independent derivations, each with an online path and a rebuild:

    A  base facets  update_coin_memory      / rebuild_coin_memory   -> fold_signal_into
    B  tm_stats     update_trade_mgmt_stats / rebuild_tm_stats      -> _fold_key + _fold_into_bucket

F0-K locked A. B's claim to share its logic lives only in a docstring ("SAME logic
as the online fold") — structurally true today, but nothing fails if someone hand-
optimises _aggregate_tm_stats tomorrow. That is exactly the lesson F0-K taught: an
untested "same logic" claim is not a guarantee. These lock B's half, plus what
neither CP covered — that the two rebuilds do not clobber each other.

No production code, no DB, no rebuild is run here.
"""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from app.models.intelligence import CoinMemory
from app.models.price_data import Timeframe
from app.models.signal import SignalOutcome
from app.services.coin_memory import (
    _aggregate_tm_stats, _fold_key, _reset_base_facets, fold_signal_into,
    update_trade_mgmt_stats,
)


# ── Doubles ─────────────────────────────────────────────────────────────────
def _path(**kw):
    """Mirrors tests/test_cm2_fold_hardening.py's shape — one SignalTradePath row."""
    base = dict(symbol="BTC", timeframe="4h", schema_version=2,
                still_forming_resolution=False, regime="trend",
                cur_reached_tp1=True, cur_reached_tp2=False, cur_reached_tp3=False,
                cur_gave_back_after_tp1=None, mfe_r=1.2, mae_r=0.5,
                mfe_atr=2.0, mae_atr=0.8, bars_total=10, cur_bars_to_tp1=3,
                cur_realized_return=1.5, entry_price=100.0, sl_price=96.0,
                tp1_price=103.0, detail_label=None)
    base.update(kw)
    return NS(**base)


def _paths(n=12):
    """A deterministic run of trade paths across regimes and shapes."""
    out = []
    for i in range(n):
        out.append(_path(
            regime="trend" if i % 3 == 0 else ("range" if i % 3 == 1 else None),
            mfe_r=0.3 + i * 0.17, mae_r=0.1 + i * 0.09,
            cur_reached_tp1=i % 2 == 0, cur_reached_tp2=i % 4 == 0,
            cur_reached_tp3=i % 6 == 0, cur_gave_back_after_tp1=(i % 5 == 0) or None,
            bars_total=4 + i, cur_bars_to_tp1=(2 + i % 4) if i % 2 == 0 else None,
            cur_realized_return=(-1.0 + i * 0.3),
        ))
    return out


def _online_fold(paths):
    """Drive the REAL online path (update_trade_mgmt_stats) over `paths`, against a
    fake session, and return the cell it built."""
    mem = NS(tm_stats=None, tm_sample_count=0)
    db = AsyncMock()

    async def fake_execute(*a, **k):
        return NS(scalar_one_or_none=lambda: mem)

    db.execute = fake_execute
    for p in paths:
        asyncio.run(update_trade_mgmt_stats(db, p))
    return mem


# ── B · online == rebuild. The gate's missing half. ─────────────────────────
def test_b_online_and_rebuild_agree_on_every_bucket():
    """update_trade_mgmt_stats vs _aggregate_tm_stats over the same rows.

    Both call _fold_key then _fold_into_bucket over (regime or "unknown", "_all").
    This asserts the docstring instead of trusting it.
    """
    paths = _paths()
    online = _online_fold(paths)
    cells, counts, skipped = _aggregate_tm_stats(paths)

    key = ("BTC", "4h")
    assert skipped == 0
    assert counts[key] == online.tm_sample_count == len(paths)
    assert cells[key] == online.tm_stats                 # bucket-for-bucket, value-for-value


def test_b_the_comparison_has_teeth():
    """One extra fold on one side must break it — otherwise the test above proves
    nothing (F0-K's lesson, applied to its own check)."""
    paths = _paths()
    online = _online_fold(paths + [_path()])             # one more
    cells, _, _ = _aggregate_tm_stats(paths)
    assert cells[("BTC", "4h")] != online.tm_stats


def test_b_agrees_on_the_skip_filter_too():
    """_fold_key is the single source of the CM2-1 legacy guard. Both paths must
    drop the same rows, or the rebuild would resurrect what the online path refused."""
    contra = _path(schema_version=1, still_forming_resolution=True,
                   cur_reached_tp1=True, cur_gave_back_after_tp1=None,
                   mfe_r=None, mae_r=None)
    assert _fold_key(contra) is None                     # the guard fires…

    good = _paths(6)
    online = _online_fold(good + [contra])               # …online skips it
    cells, counts, skipped = _aggregate_tm_stats(good + [contra])

    assert skipped == 1                                  # …rebuild skips it too
    assert counts[("BTC", "4h")] == online.tm_sample_count == 6
    assert cells[("BTC", "4h")] == online.tm_stats


def test_b_is_order_insensitive():
    """_fold_into_bucket accumulates sums/counts/histograms and rounds each step, so
    a different fold order must land on the same bucket. Locks that the rebuild's
    created_at ordering is a convenience, not a correctness dependency."""
    paths = _paths()
    forward, _, _ = _aggregate_tm_stats(paths)
    backward, _, _ = _aggregate_tm_stats(list(reversed(paths)))
    assert forward == backward


def test_b_regimeless_rows_land_in_the_unknown_bucket_on_both_paths():
    paths = [_path(regime=None), _path(regime=None)]
    online = _online_fold(paths)
    cells, _, _ = _aggregate_tm_stats(paths)

    assert "unknown" in online.tm_stats and "_all" in online.tm_stats
    assert cells[("BTC", "4h")] == online.tm_stats


# ── The two derivations must not clobber each other ─────────────────────────
def _cell():
    return CoinMemory(symbol="BTC", timeframe="4h", total_signals=0, wins=0, losses=0,
                      engine_stats={}, regime_stats={}, outcome_label_stats={})


def _sig(direction="bullish"):
    return NS(id="s1", timeframe=Timeframe.H4, direction=NS(value=direction))


def _perf(outcome=SignalOutcome.WIN, bars=5):
    return NS(outcome=outcome, detail_label="tp1_hit", bars_to_outcome=bars)


def _snap():
    return NS(regime="trend", engine_scores={"technical_analysis": {"bias": "bullish"}})


def _base(mem):
    return (mem.total_signals, mem.wins, mem.losses, mem.engine_stats,
            mem.regime_stats, mem.outcome_label_stats, mem.avg_bars_to_outcome)


def _tm(mem):
    return (mem.tm_stats, mem.tm_sample_count)


def test_a_rebuild_leaves_the_tm_facet_alone():
    """_reset_base_facets is A's rebuild starting point — B's facet must survive it."""
    mem = _cell()
    fold_signal_into(mem, _sig(), _perf(), _snap())
    mem.tm_stats, mem.tm_sample_count = {"trend": {"n": 3}}, 3

    _reset_base_facets(mem)

    assert _base(mem) == (0, 0, 0, {}, {}, {}, None)      # A reset
    assert _tm(mem) == ({"trend": {"n": 3}}, 3)           # B untouched


def test_b_rebuild_writes_only_the_tm_facet():
    """rebuild_tm_stats assigns tm_stats/tm_sample_count and nothing else. Asserted
    at source level: the base facets must not appear on its left-hand sides."""
    import inspect
    import re

    from app.services import coin_memory as cm
    src = inspect.getsource(cm.rebuild_tm_stats)
    assigned = set(re.findall(r"mem\.(\w+)\s*=", src))
    assert assigned == {"tm_stats", "tm_sample_count"}, f"also writes: {assigned}"


def test_the_two_rebuilds_commute():
    """Whichever runs first, the cell ends up the same. They own disjoint facets, so
    order must not matter — if it ever does, one of them is reaching too far."""
    def run(order):
        mem = _cell()
        steps = {
            "A": lambda: (_reset_base_facets(mem),
                          fold_signal_into(mem, _sig(), _perf(), _snap())),
            "B": lambda: (setattr(mem, "tm_stats", {"trend": {"n": 2}}),
                          setattr(mem, "tm_sample_count", 2)),
        }
        for s in order:
            steps[s]()
        return _base(mem), _tm(mem)

    assert run("AB") == run("BA")


def test_neither_rebuild_invents_a_cell_the_source_data_does_not_have():
    """Both create cells only for keys present in their source. An empty source
    must produce an empty result — not a stray cell."""
    cells, counts, skipped = _aggregate_tm_stats([])
    assert cells == {} and counts == {} and skipped == 0

    mem = _cell()
    assert fold_signal_into(mem, _sig(), NS(outcome=SignalOutcome.ACTIVE,
                                            detail_label=None, bars_to_outcome=None),
                            _snap()) is False
    assert mem.total_signals == 0                        # nothing folded, nothing invented


# ── A · order sensitivity: characterised, not fixed ─────────────────────────
def _replay(book):
    mem = _cell()
    for s, p, sn in book:
        fold_signal_into(mem, s, p, sn)
    return mem


def test_a_accumulating_facets_do_not_care_about_order():
    book = [(_sig(), _perf(bars=b), _snap()) for b in (2, 40, 3, 50, 4)]
    fwd, rev = _replay(book), _replay(list(reversed(book)))

    assert fwd.total_signals == rev.total_signals == 5
    assert fwd.wins == rev.wins and fwd.losses == rev.losses
    assert fwd.engine_stats == rev.engine_stats
    assert fwd.regime_stats == rev.regime_stats
    assert fwd.outcome_label_stats == rev.outcome_label_stats


def test_avg_bars_to_outcome_is_order_safe_while_every_fold_reports_bars():
    """(prev*(n-1) + x)/n IS a true running mean when every fold contributes, so it
    equals the arithmetic mean and order cannot move it."""
    book = [(_sig(), _perf(bars=b), _snap()) for b in (2, 40, 3, 50, 4)]
    fwd, rev = _replay(book), _replay(list(reversed(book)))

    assert fwd.avg_bars_to_outcome == rev.avg_bars_to_outcome == 19.8
    assert fwd.avg_bars_to_outcome == round(sum([2, 40, 3, 50, 4]) / 5, 2)


def test_avg_bars_to_outcome_turns_order_sensitive_once_a_fold_reports_none():
    """The precise condition behind rebuild_coin_memory's documented limit.

    n is total_signals, which counts EVERY fold, while the sum only takes folds that
    HAVE bars_to_outcome. A fold with none still advances n, so the folds around the
    gap get reweighted by WHERE the gap falls — and replaying in another order moves
    the value. This is the one field rebuild cannot promise to reproduce, because the
    true historical order is not recoverable.

    Characterised, NOT fixed: correcting the divisor changes a stored value on a live
    behaviour path and is its own decision, outside this gate.
    """
    book = [
        (_sig(), _perf(bars=2), _snap()),
        (_sig(), _perf(bars=None), _snap()),      # contributes to n, not to the sum
        (_sig(), _perf(bars=50), _snap()),
    ]
    fwd, rev = _replay(book), _replay(list(reversed(book)))

    assert fwd.total_signals == rev.total_signals == 3      # the counters still agree
    assert fwd.avg_bars_to_outcome != rev.avg_bars_to_outcome
    assert fwd.avg_bars_to_outcome == round((2 * 2 + 50) / 3, 2)      # 18.0
    assert rev.avg_bars_to_outcome == round((50 * 2 + 2) / 3, 2)      # 34.0
    # Neither is the plain mean of {2, 50} — that is the odd divisor, on display.
    assert 26.0 not in (fwd.avg_bars_to_outcome, rev.avg_bars_to_outcome)


def test_a_same_order_is_exactly_reproducible():
    """The gate's actual pass criterion: same sequence in, same everything out."""
    book = [(_sig(), _perf(bars=b), _snap()) for b in (2, 40, 3, 50, 4)]

    a, b = _cell(), _cell()
    for s, p, sn in book:
        fold_signal_into(a, s, p, sn)
    for s, p, sn in book:
        fold_signal_into(b, s, p, sn)

    assert _base(a) == _base(b)
    assert a.avg_bars_to_outcome == b.avg_bars_to_outcome   # incl. the order-sensitive one
