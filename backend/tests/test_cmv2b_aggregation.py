"""CMV2-B — forward aggregation, shadow-only.

What this checkpoint adds: raw sufficient statistics for trade-management metrics,
per (fold rule × cohort × facet), inside the CMV2-A namespace. What it does NOT
add: any derived rate, expectancy, PF, reliability tier, decay, or the faintest
influence on a live decision.

The tests are organised around the four ways an aggregation layer like this
usually goes quietly wrong:

  1. it aggregates something it should have excluded;
  2. it turns a MISSING measurement into a measured zero, which silently biases
     every mean that follows;
  3. it uses one denominator for metrics that do not share one — the exact defect
     CP-COIN-MEMORY-V2-FORENSIC found in v1's two win-rate denominators;
  4. it starts being read by a decision.

Plus the invariants that only bite later: cohorts must not merge, fold rules must
not merge, histograms must stay bounded, and a duplicate must not double-count.

No DB, no network, no clock. Pure fixtures.
"""
import asyncio
import hashlib
import inspect
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.backtesting import labels
from app.services import coin_memory as cm
from app.services.coin_memory import (
    CM_V2_AGG_KEY, CM_V2_AGGREGATION_VERSION, CM_V2_DIRECTIONS,
    CM_V2_FOLD_RULE_VERSION, CM_V2_MAX_COHORT_KEYS, CM_V2_METRIC_RULE_VERSION,
    CM_V2_NAMESPACE, CM_V2_OUTCOMES, CM_V2_REGIMES, CM_V2_SIGNED_R_EDGES,
    CM_V2_UNKNOWN, CM_V2_VOLATILITY_BUCKETS, TM_R_EDGES, _fold_into_bucket,
    cm_v2_cohort_key, cm_v2_path_metrics, observe_cm_v2_aggregates,
    observe_cm_v2_fold, update_trade_mgmt_stats, v1_tm_buckets,
)

BACKEND = Path(__file__).resolve().parents[1]

CLEAN_COHORT = {
    "decision_input_version": "closed_candle_v1",
    "decision_input_version_source": "candidate_extra",
    "policy_version": 1,
    "policy_version_source": "candidate_policy_version_column",
}
CK = "decision_input_version=closed_candle_v1|policy_version=1"


def _ipath(**kw):
    """An INCLUDED trade path: resolved cleanly, not still-forming, not ambiguous,
    every metric present. Each test then removes exactly one thing."""
    base = dict(
        signal_id="sig-1", symbol="BTC", timeframe="4h", schema_version=2,
        outcome="win", detail_label=labels.TP1_HIT, resolved_at=None,
        direction="bullish", regime="trending_bull", volatility_bucket="normal",
        still_forming_resolution=False, intrabar_ambiguous=False,
        sl_dist_pct=4.0, cur_realized_return=6.0,        # → realized_r = 1.5
        mfe_r=1.2, mae_r=0.5, mfe_pct=4.8, mae_pct=2.0, mfe_atr=2.0, mae_atr=0.8,
        bars_total=10, mfe_bar_idx=3, mae_bar_idx=6, cur_bars_to_tp1=3,
        cur_reached_tp1=True, cur_reached_tp2=False, cur_reached_tp3=False,
        cur_gave_back_after_tp1=False,
        entry_price=100.0, sl_price=96.0, tp1_price=103.0,
    )
    base.update(kw)
    return NS(**base)


class _FakeResult:
    def __init__(self, mem=None, row=None):
        self._mem, self._row = mem, row

    def scalar_one_or_none(self):
        return self._mem

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, mem, cohort_row=None):
        self.mem, self.cohort_row = mem, cohort_row
        self.executes = 0
        self.statements = []

    async def flush(self):
        return None

    async def execute(self, stmt=None, *a, **k):
        self.executes += 1
        self.statements.append(stmt)
        return _FakeResult(self.mem, self.cohort_row)

    def add(self, obj):
        return None


COHORT_ROW = ({"decision_input_version": "closed_candle_v1"}, 1)


def _fold(mem, path=None, cohort_row=COHORT_ROW):
    db = _FakeDB(mem, cohort_row)
    asyncio.run(update_trade_mgmt_stats(db, path or _ipath()))
    return mem


def _by_cohort(mem, rule=CM_V2_FOLD_RULE_VERSION, metric=CM_V2_METRIC_RULE_VERSION):
    """The cohort map for one (fold rule, metric rule) pair."""
    return (mem.tm_stats[CM_V2_NAMESPACE][CM_V2_AGG_KEY]
            ["by_fold_rule"][rule]["by_metric_rule"][metric]["by_cohort"])


def _node(mem, ck=CK, **kw):
    return _by_cohort(mem, **kw)[ck]


def _agg(mem, facet=None, key="all", ck=CK, **kw):
    """Reach into the stored blob for one bucket."""
    node = _node(mem, ck, **kw)
    return node[key] if facet is None else node[facet][key]


def _blob(mem):
    return mem.tm_stats[CM_V2_NAMESPACE][CM_V2_AGG_KEY]


def _cell():
    return NS(tm_stats=None, tm_sample_count=0)


# ══════════════════════════════════════════════════════════════════════════════
# 1 · CONTRACT
# ══════════════════════════════════════════════════════════════════════════════
def test_first_included_fold_creates_the_aggregate():
    mem = _fold(_cell())
    b = _blob(mem)
    assert b["aggregation_version"] == CM_V2_AGGREGATION_VERSION == "cm_v2_aggregation_1"
    assert b["metric_rule_version"] == CM_V2_METRIC_RULE_VERSION == "cm_v2_metric_1"
    assert list(b["by_fold_rule"]) == [CM_V2_FOLD_RULE_VERSION]
    assert list(b["by_fold_rule"][CM_V2_FOLD_RULE_VERSION]["by_metric_rule"]) == [
        CM_V2_METRIC_RULE_VERSION]
    assert list(_by_cohort(mem)) == [CK]
    assert b["population"] == "cmv2a_included_only"
    assert b["included_not_aggregated_n"] == 0
    assert _agg(mem)["included_fold_n"] == 1


def test_aggregate_is_absent_until_an_included_fold_arrives():
    mem = _fold(_cell(), _ipath(still_forming_resolution=True))
    ns = mem.tm_stats[CM_V2_NAMESPACE]
    assert ns[CM_V2_AGG_KEY] is None          # never fabricated
    assert ns["counts"]["observed"] == 1 and ns["counts"]["included"] == 0


def test_versions_come_from_one_source_not_scattered_literals():
    src = inspect.getsource(cm)
    assert src.count('"cm_v2_aggregation_1"') == 1
    assert src.count('"cm_v2_metric_1"') == 1


def test_cmv2a_fields_are_all_preserved():
    mem = _fold(_cell())
    ns = mem.tm_stats[CM_V2_NAMESPACE]
    for k in ("version", "fold_rule_version", "cohort", "counts", "last_fold",
              "recent_fold_ids", "dedupe_window", "duplicate_folds_skipped"):
        assert k in ns, k
    assert ns["counts"]["included"] == 1
    assert ns["cohort"]["decision_input_version"] == {"closed_candle_v1": 1}


def test_v1_buckets_are_untouched_by_the_aggregate():
    mem = _fold(_cell())
    v1 = v1_tm_buckets(mem.tm_stats)
    assert set(v1) == {"trending_bull", "_all"}
    assert v1["_all"]["n"] == 1 and mem.tm_sample_count == 1


def test_required_bucket_sections_all_exist():
    b = _agg(_fold(_cell()))
    assert set(b) == {"included_fold_n", "realized_r", "mfe_r", "mae_r",
                      "mfe_pct", "mae_pct", "mfe_atr", "mae_atr",
                      "tp_reach", "stop", "resolution_class", "give_back",
                      "outcomes"}


# ══════════════════════════════════════════════════════════════════════════════
# 2 · INCLUSION / EXCLUSION — one gate, CMV2-A's
# ══════════════════════════════════════════════════════════════════════════════
EXCLUDING = [
    pytest.param(dict(still_forming_resolution=True), id="still-forming"),
    pytest.param(dict(intrabar_ambiguous=True), id="intrabar-ambiguous"),
    pytest.param(dict(outcome="active"), id="active"),
]


@pytest.mark.parametrize("kw", EXCLUDING)
def test_excluded_folds_never_reach_the_aggregate(kw):
    mem = _fold(_cell(), _ipath(**kw))
    assert _blob(mem) is None
    assert mem.tm_stats["_all"]["n"] == 1          # v1 still folded it


@pytest.mark.parametrize("row,label", [
    (None, "candidate-missing"),
    (({"other": 1}, 1), "legacy-no-version"),
    (({"decision_input_version": None}, 1), "null-version"),
])
def test_missing_cohort_folds_never_reach_the_aggregate(row, label):
    mem = _fold(_cell(), _ipath(), cohort_row=row)
    assert _blob(mem) is None, label
    assert mem.tm_sample_count == 1


def test_inclusion_uses_exactly_one_predicate():
    """CMV2-B must not re-derive inclusion. Source-level: the aggregation call is
    guarded by the SAME `included` local the counters use."""
    src = inspect.getsource(observe_cm_v2_fold)
    assert "if included:" in src
    assert src.count("cm_v2_exclusions(") == 1     # the one gate, computed once


def test_a_mix_of_included_and_excluded_folds_counts_only_the_included():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a"))
    _fold(mem, _ipath(signal_id="b", still_forming_resolution=True))
    _fold(mem, _ipath(signal_id="c"))
    _fold(mem, _ipath(signal_id="d", intrabar_ambiguous=True))
    ns = mem.tm_stats[CM_V2_NAMESPACE]
    assert ns["counts"]["observed"] == 4 and ns["counts"]["included"] == 2
    assert _agg(mem)["included_fold_n"] == 2
    assert mem.tm_sample_count == 4                # v1 counted all four


# ══════════════════════════════════════════════════════════════════════════════
# 3 · DENOMINATORS — every metric owns its own
# ══════════════════════════════════════════════════════════════════════════════
def test_a_missing_metric_only_costs_its_own_denominator():
    """The load-bearing test. One fold, MFE absent, everything else present:
    included_fold_n advances, mfe_r.n does NOT, mfe_r.missing does, and no other
    metric notices."""
    mem = _fold(_cell(), _ipath(mfe_r=None, mfe_pct=None, mfe_atr=None))
    b = _agg(mem)
    assert b["included_fold_n"] == 1
    assert b["mfe_r"]["n"] == 0 and b["mfe_r"]["missing"] == 1
    assert b["mfe_r"]["sum"] == 0.0
    # the SCALAR accumulators must record the miss too, not just the distributions —
    # a sabotage run found this half untested
    assert b["mfe_pct"]["n"] == 0 and b["mfe_pct"]["missing"] == 1
    assert b["mfe_atr"]["n"] == 0 and b["mfe_atr"]["missing"] == 1
    assert b["mfe_pct"]["sum"] == 0.0 and b["mfe_atr"]["sum"] == 0.0
    assert b["mae_r"]["n"] == 1                    # untouched
    assert b["mae_pct"]["n"] == 1 and b["mae_pct"]["missing"] == 0
    assert b["realized_r"]["n"] == 1               # untouched
    assert b["tp_reach"]["tp1_eligible_n"] == 1    # untouched


def test_denominators_are_allowed_to_differ():
    """Documented explicitly: these counters need NOT be equal, and a test that
    demanded equality would be asserting a bug."""
    mem = _cell()
    _fold(mem, _ipath(signal_id="a"))                          # everything present
    _fold(mem, _ipath(signal_id="b", mfe_r=None))              # no MFE R
    _fold(mem, _ipath(signal_id="c", cur_reached_tp1=None,
                      cur_reached_tp2=None, cur_reached_tp3=None))
    _fold(mem, _ipath(signal_id="d", sl_dist_pct=None))        # no realized R
    b = _agg(mem)
    assert b["included_fold_n"] == 4
    assert b["mfe_r"]["n"] == 3
    assert b["realized_r"]["n"] == 3
    assert b["tp_reach"]["tp1_eligible_n"] == 3
    assert len({b["included_fold_n"], b["mfe_r"]["n"],
                b["tp_reach"]["tp1_eligible_n"]}) > 1


def test_missing_value_is_never_folded_in_as_zero():
    a = _agg(_fold(_cell(), _ipath(mae_r=None)))
    b = _agg(_fold(_cell(), _ipath(mae_r=0.0)))
    assert a["mae_r"] == {"n": 0, "sum": 0.0, "sumsq": 0.0,
                          "hist": [0] * (len(TM_R_EDGES) + 1), "missing": 1}
    assert b["mae_r"]["n"] == 1 and b["mae_r"]["missing"] == 0
    assert b["mae_r"]["hist"][0] == 1              # a real 0 lands in a bin


# ══════════════════════════════════════════════════════════════════════════════
# 4 · REALIZED R
# ══════════════════════════════════════════════════════════════════════════════
def test_realized_r_uses_the_canonical_helper_and_denominator():
    """R = realized% / sl_dist% via trade_geometry.safe_div — the SAME helper and
    the SAME denominator trade_path.py uses for mfe_r/mae_r, so 'R' means one
    thing repo-wide."""
    assert cm_v2_path_metrics(_ipath())["realized_r"] == pytest.approx(1.5)
    assert cm_v2_path_metrics(_ipath(cur_realized_return=-4.0,
                                    sl_dist_pct=4.0))["realized_r"] == pytest.approx(-1.0)
    src = inspect.getsource(cm.cm_v2_path_metrics)
    assert "safe_div(realized_pct, sl_dist)" in src


def test_realized_r_agrees_with_the_existing_backtest_implementation():
    """CROSS-IMPLEMENTATION consistency, not a claim.

    The repo already contains four realized-R computations (backtesting/engine.py
    `_realized_r`, trade_mgmt/replay.py `_observed_r`, trade_mgmt/fidelity.py inline,
    services/shadow_eval.py). CMV2-B deliberately adds no fifth FORMULA: it applies
    the same one — realized% / sl_dist% — through the shared safe_div, reading the
    denominator trade_path already stored instead of recomputing it from prices.

    This pins that equivalence against the unit-tested backtest version. If either
    side is ever changed, this fails instead of the two silently drifting.
    """
    from app.backtesting.engine import _realized_r

    for entry, sl, pnl in [(100.0, 96.0, 6.0), (100.0, 96.0, -4.0),
                           (100.0, 96.0, 0.0), (50.0, 47.5, 3.0),
                           (2.5, 2.3, -0.4), (100.0, 104.0, 8.0)]:
        sl_dist_pct = round(abs(entry - sl) / entry * 100.0, 4)   # trade_path.py:216
        mine = cm_v2_path_metrics(
            _ipath(cur_realized_return=pnl, sl_dist_pct=sl_dist_pct))["realized_r"]
        theirs = _realized_r(entry, sl, pnl)
        assert mine == pytest.approx(theirs, abs=1e-3), (entry, sl, pnl, mine, theirs)


def test_cmv2b_does_not_add_a_fifth_r_formula():
    """Source-level: the only division CMV2-B performs for R goes through safe_div.

    Measured on the CODE, with the docstring stripped — the docstring legitimately
    names safe_div when citing trade_path.py, and counting that as a call made this
    test fail for the wrong reason on its first run.
    """
    import ast

    tree = ast.parse(inspect.getsource(cm.cm_v2_path_metrics))
    fn = tree.body[0]
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) else fn.body
    code = "\n".join(ast.unparse(n) for n in body)

    assert code.count("safe_div(") == 1, code
    assert "/ 100.0" not in code and "* 100.0" not in code   # no re-derivation from prices
    assert "sl_dist_pct" in inspect.getsource(cm.cm_v2_path_metrics)


def test_the_zero_collapsing_r_variant_is_not_the_one_reused():
    """trade_mgmt/replay.py `_observed_r` returns 0.0 when the input is missing —
    exactly the 'missing becomes a measured zero' defect this checkpoint forbids.
    It is PRE-EXISTING and in another module (out of scope to change here), so this
    test's job is to prove CMV2-B did not inherit that semantic."""
    from app.trade_mgmt.replay import _observed_r

    blind = NS(cur_realized_return=None, sl_dist_pct=4.0)
    assert _observed_r(blind) == 0.0                       # their semantic
    assert cm_v2_path_metrics(_ipath(cur_realized_return=None))["realized_r"] is None
    assert "_observed_r" not in inspect.getsource(cm)


def test_realized_r_is_none_when_the_denominator_is_zero_or_missing():
    for kw in (dict(sl_dist_pct=0.0), dict(sl_dist_pct=None),
               dict(cur_realized_return=None)):
        assert cm_v2_path_metrics(_ipath(**kw))["realized_r"] is None


def test_realized_r_sign_split_and_sufficient_statistics():
    mem = _cell()
    for i, ret in enumerate((6.0, -4.0, 0.0, 12.0, -2.0)):   # R = 1.5,-1,0,3,-0.5
        _fold(mem, _ipath(signal_id=f"s{i}", cur_realized_return=ret))
    r = _agg(mem)["realized_r"]
    assert r["n"] == 5
    assert r["pos_n"] == 2 and r["neg_n"] == 2 and r["zero_n"] == 1
    assert r["sum"] == pytest.approx(1.5 - 1.0 + 0.0 + 3.0 - 0.5)
    assert r["sumsq"] == pytest.approx(1.5**2 + 1 + 0 + 9 + 0.25)
    assert r["pos_sum"] == pytest.approx(4.5)
    assert r["neg_abs_sum"] == pytest.approx(1.5)


def test_pf_is_left_as_raw_sums_and_never_computed_here():
    """No stored PF: a division now would freeze a denominator and, with no losses
    yet, would have to invent infinity. The raw pair is stored instead."""
    mem = _fold(_cell(), _ipath(cur_realized_return=6.0))     # winner only
    r = _agg(mem)["realized_r"]
    assert r["pos_sum"] > 0 and r["neg_abs_sum"] == 0.0
    assert "pf" not in r and "profit_factor" not in json.dumps(_blob(mem))


def test_invalidated_is_counted_but_kept_out_of_the_r_distribution():
    """Its close price reflects OUR reversal policy, not the thesis resolving.
    v1's INVALIDATED=LOSS mapping is a different layer and is untouched."""
    mem = _fold(_cell(), _ipath(outcome="invalidated",
                                detail_label=labels.INVALIDATED_REVERSAL))
    b = _agg(mem)
    assert b["included_fold_n"] == 1
    assert b["outcomes"]["invalidated"] == 1
    assert b["realized_r"]["n"] == 0
    assert b["realized_r"]["excluded_outcome_n"] == 1
    assert b["mfe_r"]["n"] == 1               # excursions are still real measurements


def test_expired_is_kept_in_the_r_distribution():
    mem = _fold(_cell(), _ipath(outcome="expired",
                                detail_label=labels.EXPIRED_LOSS))
    b = _agg(mem)
    assert b["outcomes"]["expired"] == 1 and b["realized_r"]["n"] == 1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_inf_are_rejected_rather_than_accumulated(bad):
    """An accumulator cannot un-add an inf; one bad row would poison the cell
    forever."""
    mem = _fold(_cell(), _ipath(mfe_r=bad, cur_realized_return=bad))
    b = _agg(mem)
    assert b["mfe_r"]["n"] == 0 and b["mfe_r"]["missing"] == 1
    assert b["realized_r"]["n"] == 0
    assert math.isfinite(b["mfe_r"]["sum"]) and math.isfinite(b["realized_r"]["sum"])


def test_extreme_but_finite_outliers_are_kept_in_the_overflow_bin():
    mem = _fold(_cell(), _ipath(cur_realized_return=4000.0, sl_dist_pct=4.0))
    r = _agg(mem)["realized_r"]
    assert r["n"] == 1 and r["hist"][-1] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 5 · MFE / MAE, UNITS AND HISTOGRAMS
# ══════════════════════════════════════════════════════════════════════════════
def test_units_do_not_mix():
    b = _agg(_fold(_cell()))
    assert b["mfe_r"]["sum"] == pytest.approx(1.2)     # R
    assert b["mfe_pct"]["sum"] == pytest.approx(4.8)   # percent
    assert b["mfe_atr"]["sum"] == pytest.approx(2.0)   # ATR
    for k in b:
        if isinstance(b[k], dict) and "sum" in b[k]:
            assert k.endswith(("_r", "_pct", "_atr")), f"{k} has no unit suffix"


def test_mfe_mae_reuse_the_v1_edge_set_so_the_two_stay_comparable():
    b = _agg(_fold(_cell()))
    assert len(b["mfe_r"]["hist"]) == len(TM_R_EDGES) + 1
    assert len(b["mae_r"]["hist"]) == len(TM_R_EDGES) + 1
    src = inspect.getsource(cm._empty_agg_bucket)
    assert "_TM_NBINS" in src


def test_realized_r_needs_its_own_signed_edges():
    """TM_R_EDGES starts at 0.25, so _bin_index maps EVERY negative value to bin 0
    and every loss would collapse into one bar. Asserted, so the separate edge set
    cannot be 'simplified' away later."""
    assert min(CM_V2_SIGNED_R_EDGES) < 0 < max(CM_V2_SIGNED_R_EDGES)
    assert min(TM_R_EDGES) > 0
    assert cm._bin_index(-2.0) == cm._bin_index(0.1) == 0          # the collapse
    assert cm._signed_bin_index(-2.0) != cm._signed_bin_index(0.1)  # fixed


def test_histograms_stay_bounded_over_many_folds():
    mem = _cell()
    for i in range(60):
        _fold(mem, _ipath(signal_id=f"s{i}", mfe_r=i * 0.31,
                          cur_realized_return=(i - 30) * 0.7))
    b = _agg(mem)
    assert len(b["mfe_r"]["hist"]) == len(TM_R_EDGES) + 1
    assert len(b["realized_r"]["hist"]) == len(CM_V2_SIGNED_R_EDGES) + 1
    assert sum(b["mfe_r"]["hist"]) == b["mfe_r"]["n"] == 60
    blob = json.dumps(_blob(mem))
    assert "raw" not in blob and len(blob) < 60_000


def test_no_unbounded_sample_list_is_kept():
    mem = _cell()
    for i in range(40):
        _fold(mem, _ipath(signal_id=f"s{i}"))
    def _no_long_lists(o, path="root"):
        if isinstance(o, list):
            assert len(o) <= max(len(CM_V2_SIGNED_R_EDGES) + 1, 32), path
        elif isinstance(o, dict):
            for k, v in o.items():
                _no_long_lists(v, f"{path}.{k}")
    _no_long_lists(_blob(mem))


def test_median_is_only_ever_approximate_from_buckets():
    """No exact median is stored, and nothing claims one — the histogram is the
    only ordering information kept."""
    blob = json.dumps(_blob(_fold(_cell())))
    assert "median" not in blob


# ══════════════════════════════════════════════════════════════════════════════
# 6 · STOP SEMANTICS — never generic LOSS
# ══════════════════════════════════════════════════════════════════════════════
def test_the_stop_label_sets_partition_every_known_label():
    """If a new label is added to labels.py and not classified, this fails —
    which is the point: it must land in a set deliberately, not by default."""
    both = labels.STOP_HIT_LABELS | labels.NON_STOP_TERMINAL_LABELS
    assert both == labels.ALL_DETAIL_LABELS
    assert not (labels.STOP_HIT_LABELS & labels.NON_STOP_TERMINAL_LABELS)
    assert labels.STOP_HIT_LABELS == {labels.SL_HIT, labels.CORRECT_DIR_TIGHT_SL,
                                      labels.LIVE_SL_HIT}


@pytest.mark.parametrize("label,expect", [
    (labels.SL_HIT, "stop"),
    (labels.CORRECT_DIR_TIGHT_SL, "stop"),
    (labels.LIVE_SL_HIT, "stop"),
    (labels.TP1_THEN_BREAKEVEN, "non_stop"),
    (labels.EXPIRED_LOSS, "non_stop"),
    (labels.EXPIRED_FLAT, "non_stop"),
    (labels.INVALIDATED_REVERSAL, "non_stop"),
    (labels.TP1_HIT, "non_stop"),
    (labels.TP3_HIT, "non_stop"),
    ("something_new_and_unknown", CM_V2_UNKNOWN),
    (None, CM_V2_UNKNOWN),
])
def test_stop_classification(label, expect):
    assert cm_v2_path_metrics(_ipath(detail_label=label))["stop"] == expect


def test_generic_loss_without_stop_evidence_is_not_a_stop():
    """outcome='loss' proves nothing about the stop being touched. EXPIRED_LOSS is
    a loss that never reached the stop."""
    mem = _fold(_cell(), _ipath(outcome="loss", detail_label=labels.EXPIRED_LOSS))
    st = _agg(mem)["stop"]
    assert st["stop_n"] == 0 and st["non_stop_n"] == 1 and st["eligible_n"] == 1
    assert _agg(mem)["outcomes"]["loss"] == 1


def test_tp1_then_breakeven_is_a_stop_close_but_not_a_stop_loss():
    mem = _fold(_cell(), _ipath(outcome="breakeven",
                                detail_label=labels.TP1_THEN_BREAKEVEN))
    assert _agg(mem)["stop"]["stop_n"] == 0
    assert _agg(mem)["stop"]["non_stop_n"] == 1


def test_unknown_label_does_not_enter_the_stop_denominator():
    mem = _fold(_cell(), _ipath(detail_label="brand_new_label"))
    st = _agg(mem)["stop"]
    assert st["unknown_n"] == 1 and st["eligible_n"] == 0
    assert st["eligible_n"] == st["stop_n"] + st["non_stop_n"]


def test_stop_eligible_always_equals_stop_plus_non_stop():
    mem = _cell()
    for i, lab in enumerate([labels.SL_HIT, labels.TP1_HIT, "junk",
                             labels.LIVE_SL_HIT, None, labels.EXPIRED_FLAT]):
        _fold(mem, _ipath(signal_id=f"s{i}", detail_label=lab))
    st = _agg(mem)["stop"]
    assert st["eligible_n"] == st["stop_n"] + st["non_stop_n"] == 4
    assert st["unknown_n"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 7 · TP REACH
# ══════════════════════════════════════════════════════════════════════════════
def test_tp_reach_counts_each_level():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=True, cur_reached_tp2=True,
                                cur_reached_tp3=True))
    tp = _agg(mem)["tp_reach"]
    assert tp["tp1_n"] == tp["tp2_n"] == tp["tp3_n"] == 1
    assert tp["tp1_eligible_n"] == tp["tp2_eligible_n"] == tp["tp3_eligible_n"] == 1


def test_null_tp_flag_is_not_false_it_is_not_eligible():
    mem = _fold(_cell(), _ipath(cur_reached_tp2=None))
    tp = _agg(mem)["tp_reach"]
    assert tp["tp2_eligible_n"] == 0 and tp["tp2_n"] == 0
    assert tp["tp1_eligible_n"] == 1


def test_tp_monotonicity_holds_on_forward_data():
    mem = _cell()
    for i, (a, b, c) in enumerate([(True, True, True), (True, True, False),
                                   (True, False, False), (False, False, False)]):
        _fold(mem, _ipath(signal_id=f"s{i}", cur_reached_tp1=a,
                          cur_reached_tp2=b, cur_reached_tp3=c))
    tp = _agg(mem)["tp_reach"]
    assert tp["tp1_n"] >= tp["tp2_n"] >= tp["tp3_n"]
    assert tp["inconsistent_n"] == 0


def test_an_unknown_tp1_is_not_reported_as_an_inconsistency():
    """`tp2=True, tp1=None` is UNKNOWN, not an anomaly. Treating NULL as False would
    manufacture the very inconsistency this counter is supposed to report — found by
    a sabotage run that reverted the predicate and went undetected."""
    mem = _fold(_cell(), _ipath(cur_reached_tp1=None, cur_reached_tp2=True,
                                cur_reached_tp3=False))
    tp = _agg(mem)["tp_reach"]
    assert tp["inconsistent_n"] == 0
    assert tp["tp1_eligible_n"] == 0 and tp["tp2_n"] == 1


def test_an_inconsistent_tp_row_is_made_visible_not_silently_repaired():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=False, cur_reached_tp2=True,
                                cur_reached_tp3=False))
    tp = _agg(mem)["tp_reach"]
    assert tp["inconsistent_n"] == 1
    assert tp["tp2_n"] == 1 and tp["tp1_n"] == 0     # recorded as observed, not fixed


# ══════════════════════════════════════════════════════════════════════════════
# 8 · GIVE-BACK — denominator is TP1-banked trades only
# ══════════════════════════════════════════════════════════════════════════════
def test_give_back_eligible_only_after_tp1():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=True, cur_gave_back_after_tp1=True))
    gb = _agg(mem)["give_back"]
    assert gb["eligible_n"] == 1 and gb["gave_back_n"] == 1


def test_a_trade_that_never_reached_tp1_is_not_a_give_back_question():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=False, cur_gave_back_after_tp1=None))
    gb = _agg(mem)["give_back"]
    assert gb == {"eligible_n": 0, "gave_back_n": 0,
                  "did_not_give_back_n": 0, "unknown_n": 0}


def test_did_not_give_back_requires_tp1_too():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=False, cur_gave_back_after_tp1=False))
    assert _agg(mem)["give_back"]["did_not_give_back_n"] == 0


def test_tp1_with_null_give_back_is_unknown_not_false():
    mem = _fold(_cell(), _ipath(cur_reached_tp1=True, cur_gave_back_after_tp1=None))
    gb = _agg(mem)["give_back"]
    assert gb["unknown_n"] == 1 and gb["eligible_n"] == 0


def test_give_back_denominator_is_never_all_trades():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a", cur_reached_tp1=True, cur_gave_back_after_tp1=True))
    _fold(mem, _ipath(signal_id="b", cur_reached_tp1=False, cur_gave_back_after_tp1=None))
    _fold(mem, _ipath(signal_id="c", cur_reached_tp1=False, cur_gave_back_after_tp1=None))
    b = _agg(mem)
    assert b["included_fold_n"] == 3
    assert b["give_back"]["eligible_n"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 9 · OUTCOME COUNTERS — observation only
# ══════════════════════════════════════════════════════════════════════════════
def test_outcomes_are_counted_separately():
    mem = _cell()
    for i, oc in enumerate(("win", "loss", "breakeven", "expired", "invalidated")):
        _fold(mem, _ipath(signal_id=f"s{i}", outcome=oc,
                          detail_label=labels.INVALIDATED_REVERSAL
                          if oc == "invalidated" else labels.TP1_HIT))
    oc = _agg(mem)["outcomes"]
    assert all(oc[k] == 1 for k in CM_V2_OUTCOMES)
    assert oc[CM_V2_UNKNOWN] == 0


def test_unknown_outcome_lands_in_unknown():
    mem = _fold(_cell(), _ipath(outcome="something_else"))
    assert _agg(mem)["outcomes"][CM_V2_UNKNOWN] == 1


def test_no_win_rate_is_derived_anywhere():
    """v1's two inconsistent win-rate denominators must not be inherited. Raw
    counters only — the derived rate is a CMV2-C decision with a versioned
    denominator contract."""
    blob = json.dumps(_blob(_fold(_cell())))
    for banned in ("win_rate", "winrate", "expectancy", "profit_factor",
                   "reliability", "tier", "decay", "half_life", "shrink"):
        assert banned not in blob


# ══════════════════════════════════════════════════════════════════════════════
# 9b · RESOLUTION CLASS — recovering what `outcome` throws away
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("label,cls", [
    (labels.SL_HIT, "stop"), (labels.CORRECT_DIR_TIGHT_SL, "stop"),
    (labels.LIVE_SL_HIT, "stop"),
    (labels.TP1_HIT, "target"), (labels.TP2_HIT, "target"),
    (labels.TP3_HIT, "target"), (labels.TP1_THEN_BREAKEVEN, "target"),
    (labels.EXPIRED_PROFIT, "expiry"), (labels.EXPIRED_LOSS, "expiry"),
    (labels.EXPIRED_FLAT, "expiry"),
    (labels.INVALIDATED_REVERSAL, "reversal"),
    ("brand_new", CM_V2_UNKNOWN), (None, CM_V2_UNKNOWN),
])
def test_resolution_class_covers_every_label(label, cls):
    assert cm.cm_v2_resolution_class(label) == cls
    mem = _fold(_cell(), _ipath(detail_label=label))
    assert _agg(mem)["resolution_class"][cls] == 1


def test_resolution_class_recovers_expiry_that_outcome_loses():
    """The reason this section exists. signal_trade_path.outcome takes only three
    values in production (loss/win/breakeven over 3112 rows) — an expiry is booked
    as one of those, so `outcomes` cannot see it. The label still can: 33 v2-eligible
    production rows are expiries."""
    mem = _cell()
    _fold(mem, _ipath(signal_id="a", outcome="loss", detail_label=labels.EXPIRED_LOSS))
    _fold(mem, _ipath(signal_id="b", outcome="win", detail_label=labels.EXPIRED_PROFIT))
    _fold(mem, _ipath(signal_id="c", outcome="loss", detail_label=labels.SL_HIT))
    b = _agg(mem)
    assert b["outcomes"]["loss"] == 2 and b["outcomes"]["expired"] == 0
    assert b["resolution_class"]["expiry"] == 2      # recovered anyway
    assert b["resolution_class"]["stop"] == 1


def test_resolution_class_partitions_every_included_fold():
    mem = _cell()
    for i, lab in enumerate([labels.SL_HIT, labels.TP3_HIT, labels.EXPIRED_FLAT,
                             labels.INVALIDATED_REVERSAL, "junk", None]):
        _fold(mem, _ipath(signal_id=f"s{i}", detail_label=lab))
    b = _agg(mem)
    assert sum(b["resolution_class"].values()) == b["included_fold_n"] == 6


def test_resolution_class_keys_are_bounded():
    mem = _fold(_cell(), _ipath(detail_label="anything_at_all"))
    assert set(_agg(mem)["resolution_class"]) == set(cm.CM_V2_RESOLUTION_CLASSES)


def test_live_sl_stop_is_currently_unreachable_in_the_included_cohort():
    """MEASURED: all 1279 live_sl_hit production rows carry
    still_forming_resolution=True, so CMV2-A excludes every one and `stop_n` can
    only ever be sl_hit + correct_dir_tight_sl today. The classification is kept
    complete anyway — if that exclusion is ever relaxed, the label must already have
    a home rather than falling into `unknown`."""
    live = _ipath(detail_label=labels.LIVE_SL_HIT, still_forming_resolution=True)
    mem = _fold(_cell(), live)
    assert _blob(mem) is None                        # excluded, as in production
    # but the classifier does know it, for the day the exclusion changes
    assert cm.cm_v2_resolution_class(labels.LIVE_SL_HIT) == "stop"


# ══════════════════════════════════════════════════════════════════════════════
# 9c · METRIC-RULE PARTITION AND RECONCILIATION
# ══════════════════════════════════════════════════════════════════════════════
def test_metric_rule_partitions_the_numbers_it_versions(monkeypatch):
    """The critique's sharpest finding. A flat version field would have left
    pre-bump observations inside the same sum/sumsq/hist with only the new label
    visible — so bumping the rule that governs the stop partition, a denominator or
    an edge set would silently blend two definitions."""
    mem = _fold(_cell(), _ipath(signal_id="a"))
    assert _agg(mem)["included_fold_n"] == 1

    monkeypatch.setattr(cm, "CM_V2_METRIC_RULE_VERSION", "cm_v2_metric_2")
    _fold(mem, _ipath(signal_id="b"))

    by_metric = (_blob(mem)["by_fold_rule"][CM_V2_FOLD_RULE_VERSION]["by_metric_rule"])
    assert set(by_metric) == {CM_V2_METRIC_RULE_VERSION, "cm_v2_metric_2"}
    assert by_metric[CM_V2_METRIC_RULE_VERSION]["by_cohort"][CK]["all"]["included_fold_n"] == 1
    assert by_metric["cm_v2_metric_2"]["by_cohort"][CK]["all"]["included_fold_n"] == 1


def test_included_folds_reconcile_against_cmv2a(monkeypatch):
    """sum(included_fold_n) + included_not_aggregated_n == CMV2-A counts.included.
    Without the second term the two denominators would differ with nothing saying
    why — a cohort-capped fold is counted by CMV2-A but not by any bucket."""
    mem = _cell()
    for i in range(CM_V2_MAX_COHORT_KEYS + 3):
        _fold(mem, _ipath(signal_id=f"s{i}"),
              cohort_row=({"decision_input_version": f"v{i}"}, 1))
    ns = mem.tm_stats[CM_V2_NAMESPACE]
    blob = _blob(mem)
    total = sum(node["all"]["included_fold_n"] for node in _by_cohort(mem).values())
    assert total + blob["included_not_aggregated_n"] == ns["counts"]["included"]
    assert blob["included_not_aggregated_n"] == 3


def test_population_marker_is_explicit():
    """The v1 buckets in the SAME column cover every foldable row; these cover only
    the included subset. A reader comparing the two means needs to be told."""
    assert _blob(_fold(_cell()))["population"] == "cmv2a_included_only"


# ══════════════════════════════════════════════════════════════════════════════
# 10 · FACETS
# ══════════════════════════════════════════════════════════════════════════════
def test_one_fold_advances_all_and_exactly_one_bucket_per_facet():
    mem = _fold(_cell(), _ipath(direction="bearish", regime="ranging",
                                volatility_bucket="high"))
    assert _agg(mem)["included_fold_n"] == 1
    assert _agg(mem, "direction", "bearish")["included_fold_n"] == 1
    assert _agg(mem, "regime", "ranging")["included_fold_n"] == 1
    assert _agg(mem, "volatility", "high")["included_fold_n"] == 1
    node = _node(mem)
    assert list(node["direction"]) == ["bearish"]     # lazy: nothing else created
    assert list(node["regime"]) == ["ranging"]


def test_facets_are_created_lazily_so_the_json_stays_small():
    mem = _fold(_cell())
    node = _node(mem)
    assert len(node["regime"]) == 1 < len(CM_V2_REGIMES)


@pytest.mark.parametrize("field,value,facet", [
    ("direction", "bullish", "direction"), ("direction", "bearish", "direction"),
    ("direction", "neutral", "direction"),
    ("regime", "trending_bear", "regime"), ("regime", "volatile_high", "regime"),
    ("regime", "breakout", "regime"), ("regime", "low_volume", "regime"),
    ("volatility_bucket", "low", "volatility"),
    ("volatility_bucket", "extreme", "volatility"),
])
def test_canonical_facet_values_are_accepted(field, value, facet):
    mem = _fold(_cell(), _ipath(**{field: value}))
    assert _agg(mem, facet, value)["included_fold_n"] == 1


FACETS = [("direction", "direction"), ("regime", "regime"),
          ("volatility_bucket", "volatility")]


@pytest.mark.parametrize("field,facet", FACETS)
@pytest.mark.parametrize("junk", ["LONG", "made_up", 42])
def test_off_whitelist_facet_value_is_measured_unknown(field, facet, junk):
    """Present but unrecognised → `unknown`. No arbitrary key is ever created."""
    mem = _fold(_cell(), _ipath(**{field: junk}))
    assert list(_node(mem)[facet]) == [CM_V2_UNKNOWN]


@pytest.mark.parametrize("field,facet", FACETS)
@pytest.mark.parametrize("absent", [None, "", "  "])
def test_absent_facet_value_is_not_recorded_not_unknown(field, facet, absent):
    """The distinction the critique caught: a NULL column means the facet was never
    measured, while MarketRegime has a real UNKNOWN member. Merging them would put
    "not measured" into the denominator of any future per-facet rate. Production
    incidence of NULL is 0/3112 today — the separation is for correctness, not for
    a problem currently visible."""
    mem = _fold(_cell(), _ipath(**{field: absent}))
    assert list(_node(mem)[facet]) == [cm.CM_V2_NOT_RECORDED]


def test_not_recorded_and_unknown_are_separate_buckets():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a", regime=None))          # never measured
    _fold(mem, _ipath(signal_id="b", regime="unknown"))     # measured as UNKNOWN
    node = _node(mem)
    assert set(node["regime"]) == {cm.CM_V2_NOT_RECORDED, CM_V2_UNKNOWN}
    assert node["regime"][cm.CM_V2_NOT_RECORDED]["included_fold_n"] == 1
    assert node["regime"][CM_V2_UNKNOWN]["included_fold_n"] == 1


def test_facet_case_is_normalised_not_duplicated():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a", direction="bullish"))
    _fold(mem, _ipath(signal_id="b", direction="BULLISH"))
    node = _node(mem)
    assert list(node["direction"]) == ["bullish"]
    assert node["direction"]["bullish"]["included_fold_n"] == 2


def test_facet_vocabularies_match_the_real_enums():
    from app.engines.market_regime.detector import MarketRegime
    from app.models.signal import Direction
    assert set(CM_V2_DIRECTIONS) == {d.value for d in Direction}
    assert set(CM_V2_REGIMES) == {r.value for r in MarketRegime}
    from app.backtesting.trade_path import volatility_bucket
    produced = {volatility_bucket(v) for v in (0.1, 0.9, 1.5, 5.0)}
    assert produced == set(CM_V2_VOLATILITY_BUCKETS)


def test_session_facet_is_deliberately_out_of_scope():
    blob = json.dumps(_blob(_fold(_cell())))
    assert "session" not in blob


# ══════════════════════════════════════════════════════════════════════════════
# 11 · COHORT AND FOLD-RULE SEPARATION
# ══════════════════════════════════════════════════════════════════════════════
def test_cohort_key_is_built_from_recorded_versions_only():
    assert cm_v2_cohort_key(CLEAN_COHORT) == CK
    src = inspect.getsource(cm_v2_cohort_key)
    for banned in ("resolved_at", "now(", "datetime", "utcnow", "created_at"):
        assert banned not in src


def test_different_cohorts_do_not_merge():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a"),
          cohort_row=({"decision_input_version": "closed_candle_v1"}, 1))
    _fold(mem, _ipath(signal_id="b"),
          cohort_row=({"decision_input_version": "closed_candle_v2"}, 1))
    _fold(mem, _ipath(signal_id="c"),
          cohort_row=({"decision_input_version": "closed_candle_v1"}, 2))
    by_cohort = _by_cohort(mem)
    assert len(by_cohort) == 3
    assert all(v["all"]["included_fold_n"] == 1 for v in by_cohort.values())


def test_same_cohort_accumulates():
    mem = _cell()
    for i in range(3):
        _fold(mem, _ipath(signal_id=f"s{i}"))
    assert len(_by_cohort(mem)) == 1
    assert _agg(mem)["included_fold_n"] == 3


def test_fold_rules_do_not_merge():
    mem = _fold(_cell())
    blob = _blob(mem)
    # simulate a prior era under a different fold rule
    blob["by_fold_rule"]["cm_v2_fold_0"] = {"by_metric_rule": {
        CM_V2_METRIC_RULE_VERSION: {"by_cohort": {CK: {"all": {"included_fold_n": 99}}}}}}
    mem.tm_stats = {**mem.tm_stats,
                    CM_V2_NAMESPACE: {**mem.tm_stats[CM_V2_NAMESPACE], CM_V2_AGG_KEY: blob}}
    _fold(mem, _ipath(signal_id="new"))
    by_rule = _blob(mem)["by_fold_rule"]
    old_era = by_rule["cm_v2_fold_0"]["by_metric_rule"][CM_V2_METRIC_RULE_VERSION]
    assert old_era["by_cohort"][CK]["all"]["included_fold_n"] == 99
    assert _agg(mem)["included_fold_n"] == 2


def test_cohort_key_cardinality_is_capped_and_the_drop_is_visible():
    mem = _cell()
    for i in range(CM_V2_MAX_COHORT_KEYS + 4):
        _fold(mem, _ipath(signal_id=f"s{i}"),
              cohort_row=({"decision_input_version": f"v{i}"}, 1))
    blob = _blob(mem)
    assert len(_by_cohort(mem)) == CM_V2_MAX_COHORT_KEYS
    assert blob["cohort_keys_dropped"] == 4          # counted, not silent


def test_last_included_fold_audit():
    mem = _fold(_cell(), _ipath(signal_id="audit-me"))
    lf = _blob(mem)["last_included_fold"]
    assert lf["signal_id"] == "audit-me" and lf["cohort_key"] == CK
    assert lf["folded_at"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# 12 · IDEMPOTENCY
# ══════════════════════════════════════════════════════════════════════════════
def test_duplicate_fold_does_not_double_count_the_aggregate():
    mem = _cell()
    _fold(mem, _ipath(signal_id="dup"))
    before = json.dumps(_blob(mem), sort_keys=True)
    _fold(mem, _ipath(signal_id="dup"))
    assert json.dumps(_blob(mem), sort_keys=True) == before
    assert _agg(mem)["included_fold_n"] == 1
    assert mem.tm_stats[CM_V2_NAMESPACE]["duplicate_folds_skipped"] == 1


def test_duplicate_fold_still_advances_v1():
    mem = _cell()
    _fold(mem, _ipath(signal_id="dup"))
    _fold(mem, _ipath(signal_id="dup"))
    assert mem.tm_sample_count == 2 and mem.tm_stats["_all"]["n"] == 2


def test_aggregate_survives_a_duplicate_rather_than_being_dropped():
    mem = _cell()
    _fold(mem, _ipath(signal_id="a"))
    _fold(mem, _ipath(signal_id="a"))                # duplicate
    assert _blob(mem) is not None
    assert _agg(mem)["included_fold_n"] == 1


def test_the_observer_does_not_mutate_the_prior_aggregate():
    """Shallow copies are not enough — the bucket being folded into sits several
    levels down with lists inside it. This is the bug the first implementation had."""
    first = observe_cm_v2_aggregates(None, _ipath(signal_id="a"), CLEAN_COHORT, "t0")
    frozen = json.dumps(first, sort_keys=True)
    observe_cm_v2_aggregates(first, _ipath(signal_id="b"), CLEAN_COHORT, "t1")
    assert json.dumps(first, sort_keys=True) == frozen


def test_the_aggregate_observer_is_pure_and_clockless():
    src = inspect.getsource(observe_cm_v2_aggregates)
    for banned in ("datetime.now", "utcnow", "time.time", "await", "db.", "select("):
        assert banned not in src
    a = observe_cm_v2_aggregates(None, _ipath(), CLEAN_COHORT, "fixed")
    b = observe_cm_v2_aggregates(None, _ipath(), CLEAN_COHORT, "fixed")
    assert a == b


def test_no_extra_db_query_or_write_per_fold():
    """CMV2-B is pure; it rides the CMV2-A cohort lookup and the same single
    tm_stats assignment. Still two executes, exactly as CMV2-A."""
    db = _FakeDB(_cell(), COHORT_ROW)
    asyncio.run(update_trade_mgmt_stats(db, _ipath()))
    assert db.executes == 2
    src = inspect.getsource(update_trade_mgmt_stats)
    assert src.count("mem.tm_stats =") == 2          # v1 commit, then + namespace


# ══════════════════════════════════════════════════════════════════════════════
# 13 · CORRUPT / LEGACY JSON
# ══════════════════════════════════════════════════════════════════════════════
CORRUPT_AGG = [
    pytest.param("a string", id="string"),
    pytest.param(42, id="int"),
    pytest.param([1, 2], id="list"),
    pytest.param({}, id="empty"),
    pytest.param({"by_fold_rule": "nope"}, id="by-rule-wrong-type"),
    pytest.param({"by_fold_rule": {CM_V2_FOLD_RULE_VERSION: "nope"}}, id="rule-wrong-type"),
    pytest.param({"by_fold_rule": {CM_V2_FOLD_RULE_VERSION: {"by_cohort": "nope"}}},
                 id="cohort-wrong-type"),
    pytest.param({"by_fold_rule": {CM_V2_FOLD_RULE_VERSION: {"by_cohort": {CK: "nope"}}}},
                 id="cohort-node-wrong-type"),
    pytest.param({"by_fold_rule": {CM_V2_FOLD_RULE_VERSION: {"by_cohort": {CK: {"all": "nope"}}}}},
                 id="bucket-wrong-type"),
    pytest.param({"aggregation_version": "cm_v2_aggregation_999"}, id="future-version"),
    pytest.param({"cohort_keys_dropped": -5}, id="negative-drop"),
]


@pytest.mark.parametrize("corrupt", CORRUPT_AGG)
def test_corrupt_aggregate_never_costs_the_v1_fold(corrupt):
    ns = {"version": cm.CM_V2_CONTRACT_VERSION,
          "fold_rule_version": CM_V2_FOLD_RULE_VERSION, CM_V2_AGG_KEY: corrupt}
    mem = NS(tm_stats={"_all": {"n": 4}, CM_V2_NAMESPACE: ns}, tm_sample_count=4)
    _fold(mem, _ipath())
    assert mem.tm_stats["_all"]["n"] == 5 and mem.tm_sample_count == 5
    b = _blob(mem)
    assert b["aggregation_version"] == CM_V2_AGGREGATION_VERSION
    assert _agg(mem)["included_fold_n"] >= 1
    json.dumps(b)


@pytest.mark.parametrize("corrupt", CORRUPT_AGG)
def test_corrupt_aggregate_repair_is_scoped_to_the_broken_bucket(corrupt):
    """A malformed sub-tree is rebuilt; sibling data that is still readable must
    survive so a rebuild does not become a silent wipe."""
    good = observe_cm_v2_aggregates(None, _ipath(signal_id="old"), CLEAN_COHORT, "t0")
    other = "decision_input_version=legacy|policy_version=1"
    good["by_fold_rule"][CM_V2_FOLD_RULE_VERSION]["by_metric_rule"][CM_V2_METRIC_RULE_VERSION]["by_cohort"][other] = \
        {"all": {"included_fold_n": 7}}
    if isinstance(corrupt, dict) and "by_fold_rule" not in corrupt:
        merged = {**good, **corrupt}
        out = observe_cm_v2_aggregates(merged, _ipath(signal_id="new"), CLEAN_COHORT, "t1")
        survivor = (out["by_fold_rule"][CM_V2_FOLD_RULE_VERSION]
                    ["by_metric_rule"][CM_V2_METRIC_RULE_VERSION]["by_cohort"])
        assert survivor[other]["all"]["included_fold_n"] == 7


def test_aggregator_raising_cannot_cost_the_v1_fold(monkeypatch):
    """The ordering guarantee at the CMV2-B level: v1 is assigned before the
    namespace block, so even a total failure of the aggregator leaves the v1 fold
    standing. The namespace is then simply absent for that fold — never half-written."""
    mem = NS(tm_stats={"_all": {"n": 7}}, tm_sample_count=7)
    monkeypatch.setattr(cm, "observe_cm_v2_aggregates",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _fold(mem, _ipath())
    assert mem.tm_stats["_all"]["n"] == 8 and mem.tm_sample_count == 8
    assert CM_V2_NAMESPACE not in mem.tm_stats


def test_missing_namespace_entirely_is_fine():
    mem = NS(tm_stats={"_all": {"n": 1}}, tm_sample_count=1)
    _fold(mem, _ipath())
    assert _agg(mem)["included_fold_n"] == 1


def test_very_large_prior_aggregate_stays_bounded():
    big = observe_cm_v2_aggregates(None, _ipath(signal_id="x"), CLEAN_COHORT, "t0")
    node = big["by_fold_rule"][CM_V2_FOLD_RULE_VERSION]["by_metric_rule"][CM_V2_METRIC_RULE_VERSION]["by_cohort"][CK]
    node["all"]["mfe_r"]["hist"] = [0] * 5000        # absurd
    node["regime"] = {f"junk_{i}": {"included_fold_n": i} for i in range(500)}
    ns = {"version": cm.CM_V2_CONTRACT_VERSION, CM_V2_AGG_KEY: big}
    mem = NS(tm_stats={"_all": {"n": 1}, CM_V2_NAMESPACE: ns}, tm_sample_count=1)
    _fold(mem, _ipath(signal_id="fresh"))
    b = _agg(mem)
    assert len(b["mfe_r"]["hist"]) == len(TM_R_EDGES) + 1   # re-bounded
    assert mem.tm_stats["_all"]["n"] == 2


def test_no_secret_shaped_value_can_enter_the_aggregate():
    mem = _fold(_cell(), _ipath(detail_label="SENTINEL-DSN-DO-NOT-USE",
                                regime="SENTINEL-host.invalid"))
    blob = json.dumps(_blob(mem))
    for banned in ("SENTINEL-DSN-DO-NOT-USE", "SENTINEL-host", "host.invalid"):
        assert banned not in blob


# ══════════════════════════════════════════════════════════════════════════════
# 14 · DECISION-PATH ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
DECISION_SOURCES = (
    "app/engines/ai_decision/signal_generator.py",
    "app/engines/ai_decision/engine.py",
    "app/services/scheduler.py",
    "app/services/intelligence.py",
    "app/services/candidate_log.py",
    "app/api/routes/signals.py",
)


@pytest.mark.parametrize("rel", DECISION_SOURCES)
def test_no_decision_or_api_source_mentions_the_aggregate(rel):
    text = (BACKEND / rel).read_text(encoding="utf-8")
    for banned in ("forward_aggregates", "cm_v2", "CM_V2", "cmv2",
                   "aggregation_version", "metric_rule_version"):
        assert banned not in text, f"{rel} references {banned}"


DECISION_FUNCS = ("resolve_weight_chain", "get_effective_weights",
                  "_decision_adaptive_weights", "_recompute_adaptive_weights",
                  "regime_weights", "adaptive_is_active", "fold_signal_into",
                  "load_effective_weights_meta", "weight_chain_snapshot",
                  "compute_coin_tm_summary")


@pytest.mark.parametrize("name", DECISION_FUNCS)
def test_no_decision_function_reads_the_aggregate(name):
    src = inspect.getsource(getattr(cm, name))
    for banned in ("forward_aggregates", "CM_V2_AGG_KEY", "realized_r"):
        assert banned not in src, f"{name}() references {banned}"


def test_aggregate_values_cannot_move_the_weight_chain():
    def _mem(agg):
        es = {e: {"total": 20 + i, "correct": 16 + i}
              for i, e in enumerate(cm.BASE_ENGINE_WEIGHTS)}
        tm = None if agg is None else {"_all": {"n": 5},
                                      CM_V2_NAMESPACE: {CM_V2_AGG_KEY: agg}}
        return NS(total_signals=40, engine_stats=es, adaptive_weights=None,
                  wins=0, losses=0, regime_stats={}, tm_stats=tm, tm_sample_count=5)

    baseline = cm.get_effective_weights("trending_bull", _mem(None))
    for agg in (None, {}, "junk", 10 ** 9,
                observe_cm_v2_aggregates(None, _ipath(), CLEAN_COHORT, "t"),
                {"by_fold_rule": {CM_V2_FOLD_RULE_VERSION: {"by_cohort": {CK: {
                    "all": {"realized_r": {"sum": 10 ** 9, "n": 10 ** 6}}}}}}}):
        assert cm.get_effective_weights("trending_bull", _mem(agg)) == baseline
        chain = cm.resolve_weight_chain("ranging", _mem(agg))
        assert chain.effective == cm.resolve_weight_chain("ranging", _mem(None)).effective


def test_existing_summary_reader_ignores_the_aggregate():
    from app.services.coin_memory import compute_coin_tm_summary
    bucket = {"n": 30, "mfe_r_sum": 45.0, "mae_r_sum": 27.0, "mfe_r_n": 30,
              "mae_r_n": 30, "mfe_r_sumsq": 70.0, "mae_r_sumsq": 25.0,
              "tp1": 18, "tp2": 9, "tp3": 3, "give_back": 6, "tight_sl": 1,
              "sub1_rr": 5, "realized_sum": 12.0, "realized_sumsq": 40.0,
              "realized_n": 30, "planned_rr_tp1_sum": 54.0, "planned_rr_tp1_n": 30,
              "bars_total_sum": 300, "bars_total_n": 30, "bars_to_tp1_sum": 90,
              "bars_to_tp1_n": 30, "mfe_atr_sum": 66.0, "mfe_atr_n": 30,
              "mae_atr_sum": 33.0, "mae_atr_n": 30}
    plain = NS(tm_stats={"_all": dict(bucket)}, tm_sample_count=30)
    withagg = NS(tm_stats={"_all": dict(bucket), CM_V2_NAMESPACE: {
        CM_V2_AGG_KEY: observe_cm_v2_aggregates(None, _ipath(), CLEAN_COHORT, "t")}},
        tm_sample_count=30)
    assert compute_coin_tm_summary(plain) == compute_coin_tm_summary(withagg)
    assert compute_coin_tm_summary(withagg, CM_V2_NAMESPACE)["regime"] == "_all"


# ══════════════════════════════════════════════════════════════════════════════
# 15 · FROZEN PARITY
# ══════════════════════════════════════════════════════════════════════════════
# Captured on 066a91e, before CMV2-A. Re-asserted here because CMV2-B touches the
# same module: the weight chain and the existing reader must still be identical.
FROZEN_WEIGHT_CHAIN_DIGEST = "93b20cd441168b74445c7b12aefa790a00c46cdf20ef4e4b709f0f45cfe11da6"
# The v1 tm_stats fold arithmetic. Captured DURING CMV2-B, which is only legitimate
# because an AST byte-comparison against ae9c44f showed _fold_into_bucket,
# _empty_bucket, _bin_index, TM_R_EDGES and _TM_NBINS to be byte-for-byte identical
# (27 of 28 compared units unchanged; the sole exception is observe_cm_v2_fold,
# which CMV2-B extends on purpose). So this digest equals a pre-change capture.
FROZEN_V1_BUCKET_DIGEST = "baf35ebe4625659607e5ba775c99b814c2fc79e8ee4c9835f6b7e3fa9b3190ab"

E9 = list(cm.BASE_ENGINE_WEIGHTS)


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _grid_mem(total, per_engine_total, correct_ratio):
    es = {}
    for i, e in enumerate(E9):
        t = per_engine_total + i
        c = int(round(t * correct_ratio))
        es[e] = {"total": t, "correct": c, "win_rate": round(c / t, 4) if t else 0.0}
    return NS(total_signals=total, engine_stats=es, adaptive_weights=None,
              wins=0, losses=0, regime_stats={}, tm_stats=None, tm_sample_count=0)


def test_frozen_weight_chain_digest_is_still_unmoved():
    rows = []
    for regime in [None, "unknown"] + sorted(cm._REGIME_TILTS):
        for m in [None,
                  _grid_mem(0, 0, 0.5), _grid_mem(5, 3, 0.5), _grid_mem(19, 11, 0.5),
                  _grid_mem(20, 11, 0.5),
                  _grid_mem(20, 12, 0.0), _grid_mem(20, 12, 0.25), _grid_mem(20, 12, 0.5),
                  _grid_mem(20, 12, 0.75), _grid_mem(20, 12, 1.0),
                  _grid_mem(60, 40, 0.33), _grid_mem(200, 150, 0.62)]:
            eff = cm.get_effective_weights(regime, m)
            chain = cm.resolve_weight_chain(regime, m)
            rows.append({
                "regime": regime,
                "effective": {k: round(float(v), 10) for k, v in sorted(eff.items())},
                "memory_applied": bool(chain.memory_applied),
                "chain_effective": {k: round(float(v), 10)
                                    for k, v in sorted(chain.effective.items())},
                "sum": round(sum(eff.values()), 10),
            })
    assert len(rows) == 96
    assert _digest(rows) == FROZEN_WEIGHT_CHAIN_DIGEST


def _v1_grid():
    """A deterministic run of paths through the UNCHANGED v1 bucket fold."""
    out = []
    for i in range(24):
        p = _ipath(
            signal_id=f"g{i}",
            regime=("trending_bull", "ranging", None)[i % 3],
            mfe_r=0.3 + i * 0.17, mae_r=0.1 + i * 0.09,
            cur_reached_tp1=i % 2 == 0, cur_reached_tp2=i % 4 == 0,
            cur_reached_tp3=i % 6 == 0,
            cur_gave_back_after_tp1=(i % 5 == 0) or None,
            bars_total=4 + i, cur_bars_to_tp1=(2 + i % 4) if i % 2 == 0 else None,
            cur_realized_return=(-1.0 + i * 0.3),
            mfe_atr=1.0 + i * 0.1, mae_atr=0.5 + i * 0.05,
            detail_label=(labels.CORRECT_DIR_TIGHT_SL if i % 7 == 0 else labels.TP1_HIT),
        )
        out.append(p)
    bucket = cm._empty_bucket()
    for p in out:
        _fold_into_bucket(bucket, p)
    return bucket


def test_frozen_v1_bucket_digest_is_unmoved():
    """CMV2-B must not have shifted the v1 bucket arithmetic by one decimal."""
    assert _digest(_v1_grid()) == FROZEN_V1_BUCKET_DIGEST


# ══════════════════════════════════════════════════════════════════════════════
# 16 · REBUILD / BACKFILL
# ══════════════════════════════════════════════════════════════════════════════
class _RebuildDB:
    def __init__(self, paths, mems):
        self._queue = [paths, mems]
        self.added = []

    async def execute(self, *a, **k):
        vals = self._queue.pop(0)
        return NS(scalars=lambda: NS(all=lambda: vals))

    def add(self, obj):
        self.added.append(obj)


def test_rebuild_preserves_the_aggregate_and_never_synthesizes_one():
    from app.models.intelligence import CoinMemory
    agg = observe_cm_v2_aggregates(None, _ipath(signal_id="old"), CLEAN_COHORT, "t0")
    ns = {"version": cm.CM_V2_CONTRACT_VERSION, "counts": {"observed": 1},
          CM_V2_AGG_KEY: agg}
    mem = CoinMemory(symbol="BTC", timeframe="4h", total_signals=0, wins=0, losses=0,
                     engine_stats={}, regime_stats={}, outcome_label_stats={},
                     tm_stats={"trend": {"n": 9}, CM_V2_NAMESPACE: ns},
                     tm_sample_count=9)
    asyncio.run(cm.rebuild_tm_stats(_RebuildDB([_ipath(signal_id="p1")], [mem])))
    assert mem.tm_stats[CM_V2_NAMESPACE][CM_V2_AGG_KEY] == agg   # carried, verbatim
    assert mem.tm_stats["trending_bull"]["n"] == 1               # v1 rebuilt


def test_rebuild_source_cannot_produce_an_aggregate():
    for fn in (cm._aggregate_tm_stats, cm.rebuild_tm_stats, cm.rebuild_coin_memory):
        src = inspect.getsource(fn)
        assert "observe_cm_v2_aggregates" not in src
        assert CM_V2_AGG_KEY not in src or fn is cm.rebuild_tm_stats


def test_only_one_function_writes_the_aggregate():
    """Exactly one CALLER. The aggregator itself is excluded — its own `def` line
    naturally contains its name and would otherwise self-match."""
    writers = [n for n in dir(cm)
               if callable(getattr(cm, n, None))
               and getattr(getattr(cm, n), "__module__", "") == cm.__name__
               and n != "observe_cm_v2_aggregates"
               and "observe_cm_v2_aggregates(" in _safe_src(getattr(cm, n))]
    assert writers == ["observe_cm_v2_fold"], writers


def _safe_src(obj):
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


# The migration set this checkpoint was written against, pinned by NAME.
#
# This guard used to close with `len(files) == 10 and files[-1] == "0010_..."`.
# That proved a LOCAL claim — CMV2-B moved no schema — with a GLOBAL fact:
# nothing has been added to the repo since. Only the first is CMV2-B's to make.
# scripts/migrate.py is built to apply NEW files ("only NEW migrations run"),
# so the global form was guaranteed to fail one day on a migration belonging to
# some other checkpoint entirely, saying nothing about this one.
CHECKPOINT_MIGRATIONS = frozenset({
    "0001_consent_log.sql", "0002_stripe_subscription.sql",
    "0003_per_user_notifications.sql", "0004_signal_snapshot_extra.sql",
    "0005_notify_lifecycle.sql", "0006_enable_rls.sql",
    "0007_rls_revoke_data_api.sql", "0008_signal_performance_times.sql",
    "0009_resolution_provenance.sql", "0010_candidate_log_rls.sql",
})

# The forward aggregates live inside the CMV2-A namespace in
# coin_memory.tm_stats — an existing JSON column. Reaching `coin_memory` with
# DDL is the move this checkpoint promised not to make.
GUARDED_TABLES = frozenset({"coin_memory"})

# The aggregate is a JSON key, never a schema object. Both spellings are
# checked because either would mean the same promise was broken.
GUARDED_MARKERS = ("cm_v2", "forward_aggregate")

_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_DDL_TABLE = re.compile(
    r"\b(?:create|alter|drop)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?"
    r'"?(?:public\.)?"?([a-z_][a-z0-9_]*)', re.I)


def _ddl_targets(sql: str) -> set:
    """Tables a migration CREATEs, ALTERs or DROPs.

    Comments are stripped first — 0001 carries the words "ALTER TABLE" inside a
    warning comment, and a guard that reads prose as DDL reports a schema move
    that never happened.
    """
    return {m.group(1).lower()
            for m in _DDL_TABLE.finditer(_SQL_COMMENT.sub(" ", sql))}


def test_no_new_column_and_no_new_migration():
    from app.models.intelligence import CoinMemory
    assert len(CoinMemory.__table__.columns) == 15
    assert not any("cm_v2" in c.name or "aggregate" in c.name
                   for c in CoinMemory.__table__.columns)
    mig = BACKEND / "migrations"
    present = {p.name for p in mig.glob("*.sql")}
    # Nothing this checkpoint was written against was removed, renamed, or had
    # a file renumbered into the middle of it.
    assert {n for n in present if n[:4] <= "0010"} == CHECKPOINT_MIGRATIONS
    for p in sorted(mig.glob("*.sql")):
        sql = p.read_text(encoding="utf-8").lower()
        assert not any(m in sql for m in GUARDED_MARKERS), p.name
        if p.name in CHECKPOINT_MIGRATIONS:
            continue
        assert not (_ddl_targets(sql) & GUARDED_TABLES), p.name


# ══════════════════════════════════════════════════════════════════════════════
# 17 · SIZE
# ══════════════════════════════════════════════════════════════════════════════
def test_payload_size_is_bounded_and_reported():
    empty = len(json.dumps(observe_cm_v2_aggregates(None, _ipath(), CLEAN_COHORT, "t")))
    mem = _cell()
    for i in range(200):
        _fold(mem, _ipath(
            signal_id=f"s{i}",
            direction=CM_V2_DIRECTIONS[i % 3],
            regime=CM_V2_REGIMES[i % len(CM_V2_REGIMES)],
            volatility_bucket=CM_V2_VOLATILITY_BUCKETS[i % 4],
            mfe_r=0.2 * (i % 30), cur_realized_return=(i % 21) - 10.0))
    full = len(json.dumps(_blob(mem)))
    # every facet bucket now exists, so this is close to the per-cohort ceiling
    assert full < 40_000, full
    assert empty < 6_000, empty
    print(f"\ncm_v2.forward_aggregates JSON: bir fold={empty}B  "
          f"200 fold/tum facetler={full}B")
