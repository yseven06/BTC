"""CMV2-A — Coin Memory v2 data contract & versioning.

What this checkpoint is, and what it deliberately is NOT:

  IS      an additive, versioned `cm_v2` namespace inside coin_memory.tm_stats
          that records the fold rule, the cohort MIX, per-reason v2 ineligibility
          counters, and a last-fold audit stamp.
  IS NOT  a v2 metric (CMV2-B), recency/decay/reliability (CMV2-C), or any change
          to adaptive weights, confidence, composite, publish gating or v1 fold
          eligibility.

So the tests come in three families, and the third is the one that matters most:

  1. the contract exists and says what it claims;
  2. the exclusion semantics are exactly as specified (multi-label);
  3. NOTHING about v1 or the decision path moved — proven by frozen digests over
     the weight chain and the tm_stats reader API, by source-level guards that no
     decision module can even mention the namespace, and by sabotage: for every
     way the namespace can be corrupt, absent or duplicated, the v1 fold and the
     v1 decision must come out untouched.

No DB, no network, no clock dependency. Pure fixtures throughout.
"""
import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.engines.ai_decision.signal_generator import BASE_ENGINE_WEIGHTS
from app.models.intelligence import CoinMemory
from app.services import coin_memory as cm
from app.services.coin_memory import (
    CM_V2_COHORT_LEGACY, CM_V2_COHORT_UNKNOWN, CM_V2_CONTRACT_VERSION,
    CM_V2_DEDUPE_WINDOW, CM_V2_EXCLUSION_REASONS, CM_V2_FOLD_RULE_VERSION,
    CM_V2_NAMESPACE, _resolve_fold_cohort, cm_v2_exclusions,
    compute_coin_tm_summary, get_effective_weights, observe_cm_v2_fold,
    resolve_weight_chain, unknown_cohort, update_trade_mgmt_stats, v1_tm_buckets,
)

E9 = list(BASE_ENGINE_WEIGHTS)
BACKEND = Path(__file__).resolve().parents[1]

# The EXTERNAL contract value of the namespace key, written out independently of
# the implementation. Deliberately NOT `CM_V2_NAMESPACE` — a test that takes its
# expectation from the constant it is guarding moves with it, and then a rename
# passes. That is not hypothetical: a sabotage run in CP-CMV2-M3 renamed
# `CM_V2_NAMESPACE` and this entire suite stayed green, because the contract
# family pinned the two VERSION strings as literals (see
# `test_contract_namespace_is_created_on_a_fresh_cell`) but checked the namespace
# with `in` — symbol presence, not value.
#
# It is an external contract because it is a persisted JSON key: every
# `coin_memory.tm_stats` row already on disk carries it, and renaming it makes
# every one of them unreadable by the reader that expects it.
EXPECTED_CM_V2_NAMESPACE = "cm_v2"


# ══════════════════════════════════════════════════════════════════════════════
# Doubles
# ══════════════════════════════════════════════════════════════════════════════
def _path(**kw):
    """One SignalTradePath row. Same shape the CM2/F0 suites use, plus the fields
    CMV2-A reads (signal_id, outcome, resolved_at, the two ambiguity flags)."""
    base = dict(
        signal_id="sig-1", symbol="BTC", timeframe="4h", schema_version=2,
        outcome="win", resolved_at=None, regime="trend",
        intrabar_ambiguous=False, still_forming_resolution=False,
        cur_reached_tp1=True, cur_reached_tp2=False, cur_reached_tp3=False,
        cur_gave_back_after_tp1=None, mfe_r=1.2, mae_r=0.5,
        mfe_atr=2.0, mae_atr=0.8, bars_total=10, cur_bars_to_tp1=3,
        cur_realized_return=1.5, entry_price=100.0, sl_price=96.0,
        tp1_price=103.0, detail_label=None,
    )
    base.update(kw)
    return NS(**base)


CLEAN_COHORT = {
    "decision_input_version": "closed_candle_v1",
    "decision_input_version_source": "candidate_extra",
    "policy_version": 1,
    "policy_version_source": "candidate_policy_version_column",
}


class _FakeResult:
    """Serves both accessors so the order of the two SELECTs under test is
    irrelevant to the fixture."""

    def __init__(self, mem=None, row=None):
        self._mem, self._row = mem, row

    def scalar_one_or_none(self):
        return self._mem

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, mem, cohort_row=None, raise_on_execute=False):
        self.mem, self.cohort_row = mem, cohort_row
        self.raise_on_execute = raise_on_execute
        self.executes = 0
        self.statements = []

    async def flush(self):
        return None

    async def execute(self, stmt=None, *a, **k):
        self.executes += 1
        self.statements.append(stmt)
        if self.raise_on_execute:
            raise RuntimeError("cohort lookup exploded")
        return _FakeResult(self.mem, self.cohort_row)

    def add(self, obj):
        return None


def _fold(mem, path=None, cohort_row=("extra", 1), db=None):
    """Drive the REAL online path once and return the cell."""
    row = None
    if cohort_row is not None:
        extra, pol = cohort_row
        row = ({"decision_input_version": "closed_candle_v1"} if extra == "extra"
               else extra, pol)
    db = db or _FakeDB(mem, row)
    asyncio.run(update_trade_mgmt_stats(db, path or _path()))
    return mem


def _ns(mem):
    return mem.tm_stats[CM_V2_NAMESPACE]


# ══════════════════════════════════════════════════════════════════════════════
# 1 · CONTRACT
# ══════════════════════════════════════════════════════════════════════════════
def test_contract_namespace_is_created_on_a_fresh_cell():
    mem = _fold(NS(tm_stats=None, tm_sample_count=0))
    assert CM_V2_NAMESPACE in mem.tm_stats
    ns = _ns(mem)
    assert ns["version"] == CM_V2_CONTRACT_VERSION == "cm_v2_contract_1"
    assert ns["fold_rule_version"] == CM_V2_FOLD_RULE_VERSION == "cm_v2_fold_1"
    assert ns["counts"]["observed"] == 1
    assert ns["counts"]["by_fold_rule"] == {CM_V2_FOLD_RULE_VERSION: 1}


def test_contract_namespace_key_is_pinned_to_its_external_literal():
    """The namespace KEY is pinned by value, not by symbol.

    `test_contract_namespace_is_created_on_a_fresh_cell` asserts
    `CM_V2_NAMESPACE in mem.tm_stats`, which passes for ANY value the constant
    happens to hold. This asserts the value itself, against a literal this file
    owns, so a rename fails here and nowhere else has to notice.
    """
    assert CM_V2_NAMESPACE == EXPECTED_CM_V2_NAMESPACE
    assert cm.CM_V2_NAMESPACE == EXPECTED_CM_V2_NAMESPACE


def test_contract_namespace_key_appears_literally_in_a_produced_payload():
    """The pin has to hold on the ARTEFACT, not only on the constant. A fold
    writes the key into `tm_stats`; that is the byte a stored row carries and
    the byte a reader looks for."""
    mem = _fold(NS(tm_stats=None, tm_sample_count=0))
    assert EXPECTED_CM_V2_NAMESPACE in mem.tm_stats, \
        f"the fold did not write the {EXPECTED_CM_V2_NAMESPACE!r} key"
    # And it survives serialisation — this is a persisted JSON column.
    assert f'"{EXPECTED_CM_V2_NAMESPACE}"' in json.dumps(mem.tm_stats)
    # The v1 reader must strip exactly this key and no other.
    assert EXPECTED_CM_V2_NAMESPACE not in v1_tm_buckets(mem.tm_stats)
    assert v1_tm_buckets({EXPECTED_CM_V2_NAMESPACE: {"x": 1}, "_all": {"n": 3}}) \
        == {"_all": {"n": 3}}


def test_contract_namespace_literal_is_defined_exactly_once_in_code():
    """One definition, no scattered copies — the same rule the two version
    strings already follow.

    Walks the AST rather than counting text: the literal also occurs inside a
    COMMENT in `coin_memory.py` (a note about a caller passing regime="cm_v2"),
    and a raw `src.count(...)` would read that as a second definition and fail
    for a reason that has nothing to do with the contract.
    """
    import ast
    tree = ast.parse(inspect.getsource(cm))
    literals = [n for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and n.value == EXPECTED_CM_V2_NAMESPACE]
    assert len(literals) == 1, \
        f"the namespace literal is written {len(literals)} times in code"

    # …and that one occurrence is the constant's own definition.
    defs = [n for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "CM_V2_NAMESPACE"
                    for t in n.targets)]
    assert len(defs) == 1, "CM_V2_NAMESPACE is assigned more than once"
    assert isinstance(defs[0].value, ast.Constant)
    assert defs[0].value.value == EXPECTED_CM_V2_NAMESPACE


def test_contract_versions_come_from_one_source_not_scattered_literals():
    """The values must be defined once. A literal repeated inside the namespace
    builder would silently drift the day one of them is bumped."""
    src = inspect.getsource(cm)
    # Each literal appears exactly once: at its constant definition.
    assert src.count('"cm_v2_contract_1"') == 1
    assert src.count('"cm_v2_fold_1"') == 1
    body = inspect.getsource(cm._empty_cm_v2)
    assert "CM_V2_CONTRACT_VERSION" in body and "cm_v2_contract_1" not in body


def test_contract_required_fields_are_all_present():
    ns = _ns(_fold(NS(tm_stats=None, tm_sample_count=0)))
    assert set(ns) >= {"version", "fold_rule_version", "cohort", "counts", "last_fold"}
    assert set(ns["cohort"]) == {"decision_input_version", "policy_version"}
    assert set(ns["counts"]) == {"observed", "included", "excluded", "by_fold_rule"}
    assert set(ns["counts"]["excluded"]) == set(CM_V2_EXCLUSION_REASONS)
    assert set(ns["last_fold"]) >= {"signal_id", "outcome", "resolved_at", "folded_at"}


def test_contract_v1_buckets_are_byte_identical_with_and_without_the_namespace():
    """The proof that the namespace is ADDITIVE: fold the same row into two cells,
    one of which already carries a namespace, and the v1 buckets must match."""
    a = _fold(NS(tm_stats=None, tm_sample_count=0))
    b = _fold(NS(tm_stats={CM_V2_NAMESPACE: {"junk": True}}, tm_sample_count=0))
    assert v1_tm_buckets(a.tm_stats) == v1_tm_buckets(b.tm_stats)
    assert a.tm_sample_count == b.tm_sample_count == 1


def test_contract_existing_v1_buckets_are_preserved_untouched():
    prior = {"trend": {"n": 3, "mfe_r_sum": 1.0}, "_all": {"n": 3, "mfe_r_sum": 1.0}}
    mem = _fold(NS(tm_stats={k: dict(v) for k, v in prior.items()}, tm_sample_count=3))
    for bucket in v1_tm_buckets(mem.tm_stats).values():
        assert bucket["n"] == 4                       # folded on top, not replaced
    assert mem.tm_sample_count == 4


def test_contract_pre_cmv2_json_upgrades_safely():
    """A cell written before this checkpoint has tm_stats but no namespace."""
    mem = _fold(NS(tm_stats={"_all": {"n": 9}}, tm_sample_count=9))
    assert _ns(mem)["counts"]["observed"] == 1        # starts counting from now
    assert mem.tm_stats["_all"]["n"] == 10           # v1 kept accumulating


def test_contract_absent_tm_stats_upgrades_safely():
    mem = _fold(NS(tm_stats=None, tm_sample_count=None))
    assert _ns(mem)["counts"]["observed"] == 1
    assert mem.tm_sample_count == 1


def test_contract_counters_accumulate_across_folds():
    mem = NS(tm_stats=None, tm_sample_count=0)
    for i in range(5):
        _fold(mem, _path(signal_id=f"s{i}"))
    ns = _ns(mem)
    assert ns["counts"]["observed"] == 5 == ns["counts"]["included"]
    assert ns["counts"]["by_fold_rule"][CM_V2_FOLD_RULE_VERSION] == 5


# ══════════════════════════════════════════════════════════════════════════════
# 2 · COHORT RESOLUTION — every branch of the chain, no date inference
# ══════════════════════════════════════════════════════════════════════════════
def _cohort(row, raise_on_execute=False, path=None):
    db = _FakeDB(None, row, raise_on_execute=raise_on_execute)
    return asyncio.run(_resolve_fold_cohort(db, path or _path()))


def test_cohort_recorded_version_is_read_from_the_candidate_extra():
    c = _cohort(({"decision_input_version": "closed_candle_v1"}, 1))
    assert c["decision_input_version"] == "closed_candle_v1"
    assert c["decision_input_version_source"] == "candidate_extra"
    assert c["policy_version"] == 1
    assert c["policy_version_source"] == "candidate_policy_version_column"


def test_cohort_candidate_row_without_the_version_key_is_provably_legacy():
    """A positive finding, not a guess: candidate logging was live and the version
    field did not exist yet."""
    c = _cohort(({"primary_demotion_reason": "x"}, 1))
    assert c["decision_input_version"] == CM_V2_COHORT_LEGACY
    assert c["decision_input_version_source"] == "candidate_row_without_version"
    assert c["policy_version"] == 1                   # the column is still a fact


def test_cohort_null_version_is_unknown_not_legacy():
    """The field existed and was not populated — a defect, not a cohort. Calling
    it `legacy` would file a bug as a population."""
    for bad in (None, "", "   "):
        c = _cohort(({"decision_input_version": bad}, 2))
        assert c["decision_input_version"] == CM_V2_COHORT_UNKNOWN
        assert c["decision_input_version_source"] == "candidate_version_null"


def test_cohort_missing_candidate_row_is_unknown():
    c = _cohort(None)
    assert c["decision_input_version"] == CM_V2_COHORT_UNKNOWN
    assert c["decision_input_version_source"] == "candidate_missing"
    assert c["policy_version"] == CM_V2_COHORT_UNKNOWN
    assert c["policy_version_source"] == "unavailable"


def test_cohort_lookup_failure_degrades_to_unknown_and_never_raises():
    c = _cohort(None, raise_on_execute=True)
    assert c["decision_input_version_source"] == "lookup_failed"
    assert c["decision_input_version"] == CM_V2_COHORT_UNKNOWN


def test_cohort_missing_signal_id_is_unknown():
    c = _cohort(({"decision_input_version": "closed_candle_v1"}, 1),
                path=_path(signal_id=None))
    assert c["decision_input_version_source"] == "no_signal_id"


def test_cohort_never_infers_a_version_from_a_timestamp():
    """The prohibition, at source level: no date/deploy-boundary comparison may
    appear in the resolver. A timestamp can suggest a cohort; it cannot record one."""
    src = inspect.getsource(_resolve_fold_cohort)
    for banned in ("resolved_at", "created_at", "evaluated_at >", "F1_DEPLOY",
                   "datetime(", "now(", "utcnow"):
        assert banned not in src.split('"""')[2], f"date inference leaked in: {banned}"


def test_cohort_is_a_histogram_so_a_mixed_cell_cannot_hide_it():
    """CP-COIN-MEMORY-V2-FORENSIC §7: a cell mixes cohorts. A scalar label would
    report the last fold's cohort as if it were the cell's."""
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id="a"), cohort_row=({"decision_input_version": "closed_candle_v1"}, 1))
    _fold(mem, _path(signal_id="b"), cohort_row=({"other": 1}, 1))
    _fold(mem, _path(signal_id="c"), cohort_row=None)
    hist = _ns(mem)["cohort"]["decision_input_version"]
    assert hist == {"closed_candle_v1": 1, CM_V2_COHORT_LEGACY: 1, CM_V2_COHORT_UNKNOWN: 1}


def test_cohort_lookup_is_one_bounded_query_per_fold():
    """No N+1 and no scan. Asserted STRUCTURALLY on the statement actually handed to
    the session — an earlier version of this test grepped the source for ".limit(1)",
    which a comment containing that text could satisfy. The compiled SQL cannot lie."""
    db = _FakeDB(NS(tm_stats=None, tm_sample_count=0),
                 ({"decision_input_version": "closed_candle_v1"}, 1))
    asyncio.run(update_trade_mgmt_stats(db, _path()))

    assert db.executes == 2                       # the cell SELECT + one cohort SELECT
    sql = str(db.statements[-1]).upper()
    assert "SIGNAL_DECISION_CANDIDATES" in sql
    assert "LIMIT" in sql, "the cohort lookup must be bounded"
    assert "WHERE" in sql and "SIGNAL_ID" in sql   # indexed predicate, not a scan


# ══════════════════════════════════════════════════════════════════════════════
# 3 · EXCLUSION SEMANTICS — multi-label, and v1 eligibility untouched
# ══════════════════════════════════════════════════════════════════════════════
def test_exclusion_active_outcome():
    assert cm_v2_exclusions(_path(outcome="active"), CLEAN_COHORT)["active"] is True
    assert cm_v2_exclusions(_path(outcome="ACTIVE"), CLEAN_COHORT)["active"] is True
    assert cm_v2_exclusions(_path(outcome=NS(value="active")), CLEAN_COHORT)["active"] is True
    assert cm_v2_exclusions(_path(outcome="win"), CLEAN_COHORT)["active"] is False


def test_exclusion_intrabar_ambiguous():
    e = cm_v2_exclusions(_path(intrabar_ambiguous=True), CLEAN_COHORT)
    assert e["intrabar_ambiguous"] is True and e["still_forming_resolution"] is False


def test_exclusion_still_forming_resolution():
    e = cm_v2_exclusions(_path(still_forming_resolution=True), CLEAN_COHORT)
    assert e["still_forming_resolution"] is True and e["intrabar_ambiguous"] is False


def test_exclusion_missing_decision_input_version_covers_legacy_and_unknown():
    for div in (CM_V2_COHORT_LEGACY, CM_V2_COHORT_UNKNOWN, None, ""):
        c = {**CLEAN_COHORT, "decision_input_version": div}
        assert cm_v2_exclusions(_path(), c)["missing_decision_input_version"] is True
    assert cm_v2_exclusions(_path(), CLEAN_COHORT)["missing_decision_input_version"] is False


def test_exclusion_missing_policy_version():
    c = {**CLEAN_COHORT, "policy_version": CM_V2_COHORT_UNKNOWN}
    assert cm_v2_exclusions(_path(), c)["missing_policy_version"] is True
    assert cm_v2_exclusions(_path(), CLEAN_COHORT)["missing_policy_version"] is False


def test_exclusion_is_multi_label_and_counters_need_not_sum_to_observed():
    """The declared semantics. One fold, four reasons — so `excluded` totals
    OVERCOUNT relative to `observed`, by design."""
    path = _path(outcome="active", intrabar_ambiguous=True,
                 still_forming_resolution=True)
    cohort = unknown_cohort()
    fired = cm_v2_exclusions(path, cohort)
    assert sum(fired.values()) == 5                   # all five at once

    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, path, cohort_row=None)
    ns = _ns(mem)
    assert ns["counts"]["observed"] == 1
    assert ns["counts"]["included"] == 0
    assert sum(ns["counts"]["excluded"].values()) == 5 > ns["counts"]["observed"]


def test_exclusion_included_means_no_reason_fired():
    mem = _fold(NS(tm_stats=None, tm_sample_count=0))
    ns = _ns(mem)
    assert ns["counts"]["included"] == 1
    assert sum(ns["counts"]["excluded"].values()) == 0
    assert ns["last_fold"]["included"] is True


def test_exclusion_never_changes_v1_fold_eligibility():
    """The load-bearing guarantee: a row v1 folds today is still folded, with the
    same numbers, no matter how many v2 exclusions fire on it."""
    ineligible = _path(outcome="active", intrabar_ambiguous=True,
                       still_forming_resolution=True)
    a = _fold(NS(tm_stats=None, tm_sample_count=0), ineligible, cohort_row=None)
    b = NS(tm_stats=None, tm_sample_count=0)
    asyncio.run(_fold_v1_only(b, ineligible))
    assert v1_tm_buckets(a.tm_stats) == b.tm_stats
    assert a.tm_sample_count == b.tm_sample_count == 1
    assert _ns(a)["counts"]["included"] == 0          # v2 says no…
    assert a.tm_stats["_all"]["n"] == 1               # …v1 still folded it


async def _fold_v1_only(mem, path):
    """v1's fold with the namespace suppressed — the control arm for the test
    above. Uses the real fold, then drops the namespace."""
    await update_trade_mgmt_stats(_FakeDB(mem, None), path)
    mem.tm_stats = v1_tm_buckets(mem.tm_stats)


# ══════════════════════════════════════════════════════════════════════════════
# 4 · IDEMPOTENCY / DUPLICATE GUARD — with its limit stated, not oversold
# ══════════════════════════════════════════════════════════════════════════════
def test_duplicate_fold_of_the_same_signal_does_not_double_count():
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id="dup"))
    _fold(mem, _path(signal_id="dup"))
    ns = _ns(mem)
    assert ns["counts"]["observed"] == 1
    assert ns["duplicate_folds_skipped"] == 1


def test_duplicate_guard_leaves_every_other_counter_alone():
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id="dup"))
    before = json.dumps({k: v for k, v in _ns(mem).items()
                         if k != "duplicate_folds_skipped"}, sort_keys=True)
    _fold(mem, _path(signal_id="dup"))
    after = json.dumps({k: v for k, v in _ns(mem).items()
                        if k != "duplicate_folds_skipped"}, sort_keys=True)
    assert before == after


def test_duplicate_guard_does_not_gate_the_v1_counters():
    """v1 has its own, stronger guard (signal_trade_path.signal_id is UNIQUE and
    _persist_trade_path_once refuses the repeat before this function is reached).
    The v2 ring must never reach across and suppress a v1 fold."""
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id="dup"))
    _fold(mem, _path(signal_id="dup"))
    assert mem.tm_sample_count == 2                   # v1 counted both
    assert mem.tm_stats["_all"]["n"] == 2
    assert _ns(mem)["counts"]["observed"] == 1        # v2 counted one


def test_duplicate_ring_is_bounded():
    mem = NS(tm_stats=None, tm_sample_count=0)
    for i in range(CM_V2_DEDUPE_WINDOW + 10):
        _fold(mem, _path(signal_id=f"s{i}"))
    ns = _ns(mem)
    assert len(ns["recent_fold_ids"]) == CM_V2_DEDUPE_WINDOW
    assert ns["dedupe_window"] == CM_V2_DEDUPE_WINDOW
    assert ns["counts"]["observed"] == CM_V2_DEDUPE_WINDOW + 10


def test_duplicate_guard_limit_is_real_and_documented():
    """HONEST LIMIT, asserted rather than hoped: a repeat OLDER than the window is
    NOT caught. Full idempotency needs a per-fold ledger, which needs a migration
    — out of scope here. This test exists so the limit cannot be forgotten."""
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id="old"))
    for i in range(CM_V2_DEDUPE_WINDOW):
        _fold(mem, _path(signal_id=f"s{i}"))
    assert "old" not in _ns(mem)["recent_fold_ids"]
    _fold(mem, _path(signal_id="old"))                # escapes the ring
    assert _ns(mem)["duplicate_folds_skipped"] == 0
    assert _ns(mem)["counts"]["observed"] == CM_V2_DEDUPE_WINDOW + 2


def test_a_row_without_a_signal_id_is_observed_but_never_enters_the_ring():
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(signal_id=None))
    _fold(mem, _path(signal_id=None))
    ns = _ns(mem)
    assert ns["counts"]["observed"] == 2 and ns["recent_fold_ids"] == []


def test_concurrent_folds_are_last_write_wins_not_merged():
    """No false assurance: two observers built from the SAME snapshot each carry
    only their own fold, so a genuine concurrent write would LOSE one observation.
    The v1 counters are unaffected (they are a DB-level increment inside the
    caller's transaction). Characterised, NOT claimed fixed."""
    base = observe_cm_v2_fold(None, _path(signal_id="a"), CLEAN_COHORT, "t0")
    left = observe_cm_v2_fold(base, _path(signal_id="b"), CLEAN_COHORT, "t1")
    right = observe_cm_v2_fold(base, _path(signal_id="c"), CLEAN_COHORT, "t2")
    assert left["counts"]["observed"] == right["counts"]["observed"] == 2
    assert left != right                              # neither contains the other's fold


# ══════════════════════════════════════════════════════════════════════════════
# 5 · PURITY
# ══════════════════════════════════════════════════════════════════════════════
def test_observer_is_pure_and_does_not_mutate_its_input():
    existing = observe_cm_v2_fold(None, _path(signal_id="a"), CLEAN_COHORT, "t0")
    frozen = json.dumps(existing, sort_keys=True)
    observe_cm_v2_fold(existing, _path(signal_id="b"), CLEAN_COHORT, "t1")
    assert json.dumps(existing, sort_keys=True) == frozen


def test_observer_has_no_clock_of_its_own():
    """`folded_at` is injected, so the function is exactly reproducible in a test —
    the same reason fold_signal_into takes no clock."""
    src = inspect.getsource(observe_cm_v2_fold)
    for banned in ("datetime.now", "utcnow", "time.time", "date.today"):
        assert banned not in src
    a = observe_cm_v2_fold(None, _path(), CLEAN_COHORT, "fixed")
    b = observe_cm_v2_fold(None, _path(), CLEAN_COHORT, "fixed")
    assert a == b


def test_observer_does_no_io():
    src = inspect.getsource(observe_cm_v2_fold)
    for banned in ("await", "db.", "select(", "session"):
        assert banned not in src


# ══════════════════════════════════════════════════════════════════════════════
# 6 · NAMESPACE ISOLATION — the decision path cannot see this
# ══════════════════════════════════════════════════════════════════════════════
def _mem(total=40, per_engine=20, ratio=0.8, tm_stats=None):
    es = {e: {"total": per_engine + i, "correct": int(round((per_engine + i) * ratio))}
          for i, e in enumerate(E9)}
    return NS(total_signals=total, engine_stats=es, adaptive_weights=None,
              wins=0, losses=0, regime_stats={},
              tm_stats=tm_stats, tm_sample_count=0)


def test_isolation_namespace_values_cannot_move_the_adaptive_weights():
    """Same memory, wildly different namespaces — identical effective weights."""
    baseline = get_effective_weights("trending_bull", _mem(tm_stats=None))
    for junk in (
        {CM_V2_NAMESPACE: {"counts": {"observed": 10 ** 9, "included": 0}}},
        {CM_V2_NAMESPACE: {"version": "cm_v2_contract_999",
                           "fold_rule_version": "hostile"}},
        {CM_V2_NAMESPACE: {"cohort": {"decision_input_version": {"legacy": 10 ** 6}}}},
        {CM_V2_NAMESPACE: None},
        {},
    ):
        assert get_effective_weights("trending_bull", _mem(tm_stats=junk)) == baseline


def test_isolation_deleting_the_namespace_changes_no_decision():
    with_ns = _mem(tm_stats={CM_V2_NAMESPACE: {"counts": {"observed": 5}},
                             "_all": {"n": 5}})
    without = _mem(tm_stats={"_all": {"n": 5}})
    for regime in (None, "ranging", "trending_bear", "volatile_high"):
        a, b = resolve_weight_chain(regime, with_ns), resolve_weight_chain(regime, without)
        assert a.effective == b.effective
        assert a.memory_applied == b.memory_applied


def test_isolation_corrupt_namespace_does_not_break_the_decision():
    for corrupt in ("a string", 42, [1, 2, 3], {"counts": "not-a-dict"}, float("nan")):
        mem = _mem(tm_stats={CM_V2_NAMESPACE: corrupt, "_all": {"n": 5}})
        w = get_effective_weights("trending_bull", mem)
        assert set(w) == set(E9) and abs(sum(w.values()) - 1.0) < 1e-9


DECISION_SOURCES = (
    "app/engines/ai_decision/signal_generator.py",
    "app/engines/ai_decision/engine.py",
    "app/services/scheduler.py",
    "app/services/intelligence.py",
    "app/services/candidate_log.py",
)


@pytest.mark.parametrize("rel", DECISION_SOURCES)
def test_isolation_no_decision_source_even_mentions_the_namespace(rel):
    """Source-level guard, not convention. If a decision module ever needs to read
    this, that is a policy change and must fail here first."""
    text = (BACKEND / rel).read_text(encoding="utf-8")
    for banned in ("cm_v2", "CM_V2", "cmv2"):
        assert banned not in text, f"{rel} references {banned}"


DECISION_FUNCS = ("resolve_weight_chain", "get_effective_weights",
                  "_decision_adaptive_weights", "_recompute_adaptive_weights",
                  "regime_weights", "adaptive_is_active", "fold_signal_into",
                  "load_effective_weights_meta", "weight_chain_snapshot")


@pytest.mark.parametrize("name", DECISION_FUNCS)
def test_isolation_no_decision_function_inside_coin_memory_reads_it(name):
    """The namespace lives in this module, so the guard has to be function-level
    here: the weight chain and the v1 fold must not touch it."""
    src = inspect.getsource(getattr(cm, name))
    for banned in ("cm_v2", "CM_V2"):
        assert banned not in src, f"{name}() references {banned}"


def test_isolation_ast_confirms_the_namespace_is_written_by_exactly_one_function():
    """Only update_trade_mgmt_stats may assign it. A second writer would be a
    second contract."""
    writers = [n for n in dir(cm)
               if callable(getattr(cm, n, None)) and getattr(getattr(cm, n), "__module__", "") == cm.__name__
               and "CM_V2_NAMESPACE:" in _safe_src(getattr(cm, n))]
    assert writers == ["update_trade_mgmt_stats"], writers


def _safe_src(obj):
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# 7 · BACKWARD COMPATIBILITY of the existing tm_stats reader
# ══════════════════════════════════════════════════════════════════════════════
def _bucket(n):
    return {"n": n, "mfe_r_sum": 1.5 * n, "mae_r_sum": 0.9 * n,
            "mfe_r_sumsq": 4.0 * n, "mae_r_sumsq": 2.0 * n,
            "mfe_r_n": n, "mae_r_n": n, "tp1": n // 2, "tp2": n // 4,
            "tp3": n // 8, "give_back": n // 5, "realized_sum": 0.4 * n,
            "realized_sumsq": 1.2 * n, "realized_n": n,
            "planned_rr_tp1_sum": 1.8 * n, "planned_rr_tp1_n": n,
            "sub1_rr": n // 6, "tight_sl": n // 7,
            "bars_total_sum": 10 * n, "bars_total_n": n,
            "bars_to_tp1_sum": 3 * n, "bars_to_tp1_n": n,
            "mfe_atr_sum": 2.2 * n, "mfe_atr_n": n,
            "mae_atr_sum": 1.1 * n, "mae_atr_n": n}


def test_api_reader_output_is_identical_with_and_without_the_namespace():
    """compute_coin_tm_summary is the ONLY consumer (signals.py) — its output must
    not shift by one field."""
    for n in (0, 5, 10, 30):
        plain = NS(tm_stats={"_all": _bucket(n)}, tm_sample_count=n)
        withns = NS(tm_stats={"_all": _bucket(n),
                              CM_V2_NAMESPACE: {"counts": {"observed": n}}},
                    tm_sample_count=n)
        for regime in (None, "trending_bull"):
            assert compute_coin_tm_summary(plain, regime) == \
                   compute_coin_tm_summary(withns, regime)


def test_api_reader_never_mistakes_the_namespace_for_a_regime_bucket():
    """The reader resolves `regime if regime in tm else "_all"`. Before CMV2-A
    hardened it, regime="cm_v2" matched the namespace and the caller was served the
    contract blob as a bucket (it degraded to has_data=False rather than producing a
    wrong number, but it was still the wrong object). Now the namespace is filtered
    out before the lookup, so the request falls through to `_all` like any other
    unknown regime. Unreachable in production — regimes come from the detector — but
    the isolation claim now holds by construction."""
    mem = NS(tm_stats={"_all": _bucket(30),
                       CM_V2_NAMESPACE: {"counts": {"observed": 7}}},
             tm_sample_count=30)
    out = compute_coin_tm_summary(mem, CM_V2_NAMESPACE)
    assert out["has_data"] is True and out["n"] == 30
    assert out["regime"] == "_all"                # fell through, not served the blob
    assert out == compute_coin_tm_summary(mem, "some_regime_that_does_not_exist")
    assert out["metrics"] == compute_coin_tm_summary(mem, None)["metrics"]


def test_api_reader_ignores_the_namespace_even_as_the_only_key():
    """A cell whose ONLY tm_stats key is the namespace has no trade data at all —
    it must report exactly that, not a zero-filled bucket."""
    mem = NS(tm_stats={CM_V2_NAMESPACE: {"counts": {"observed": 7}}}, tm_sample_count=0)
    out = compute_coin_tm_summary(mem)
    assert out["has_data"] is False and out["n"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 8 · FROZEN PARITY — digests captured on 066a91e, BEFORE this checkpoint
# ══════════════════════════════════════════════════════════════════════════════
FROZEN_WEIGHT_CHAIN_DIGEST = "93b20cd441168b74445c7b12aefa790a00c46cdf20ef4e4b709f0f45cfe11da6"
FROZEN_TM_SUMMARY_DIGEST = "39e45c5e9ab0c081d6254b833d614dffe0352a1c5e538e68df9c1d49ff5fc114"


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


def test_frozen_weight_chain_digest_is_unmoved():
    """96 (regime × memory) cases through the FULL chain — base → regime → memory →
    normalise. This is the number CMV2-A must not touch, and the reason the digest
    was captured before a line was written."""
    rows = []
    for regime in [None, "unknown"] + sorted(cm._REGIME_TILTS):
        for m in [None,
                  _grid_mem(0, 0, 0.5), _grid_mem(5, 3, 0.5), _grid_mem(19, 11, 0.5),
                  _grid_mem(20, 11, 0.5),
                  _grid_mem(20, 12, 0.0), _grid_mem(20, 12, 0.25), _grid_mem(20, 12, 0.5),
                  _grid_mem(20, 12, 0.75), _grid_mem(20, 12, 1.0),
                  _grid_mem(60, 40, 0.33), _grid_mem(200, 150, 0.62)]:
            eff = get_effective_weights(regime, m)
            chain = resolve_weight_chain(regime, m)
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


def test_frozen_tm_summary_digest_is_unmoved():
    """57 cases through the tm_stats reader API — the one existing consumer."""
    def bucket(n, seed):
        b = _bucket(n)
        b.update({"mfe_r_sum": 1.5 * n + seed, "mae_r_sum": 0.9 * n + seed,
                  "mfe_r_sumsq": 4.0 * n + seed, "mae_r_sumsq": 2.0 * n + seed,
                  "mfe_r_n": max(0, n - 2), "mae_r_n": max(0, n - 1),
                  "hist_mfe_r": [(i + seed) % 5 for i in range(9)],
                  "hist_mae_r": [(i + seed) % 3 for i in range(9)],
                  "mfe_atr_n": max(0, n - 2), "mae_atr_n": max(0, n - 1),
                  "bars_to_tp1_n": n // 2})
        return b

    rows = []
    for n in (0, 1, 5, 9, 10, 11, 30, 67):
        for seed in (0, 3):
            tm = {"_all": bucket(n, seed), "trending_bull": bucket(max(0, n - 3), seed)}
            for regime in (None, "trending_bull", "ranging"):
                rows.append({"n": n, "seed": seed, "regime": regime,
                             "out": compute_coin_tm_summary(
                                 NS(tm_stats=tm, tm_sample_count=n), regime)})
        rows.append({"n": n, "seed": "none", "regime": None,
                     "out": compute_coin_tm_summary(NS(tm_stats=None, tm_sample_count=0))})
    rows.append({"n": "nomem", "seed": "-", "regime": None,
                 "out": compute_coin_tm_summary(None)})
    assert len(rows) == 57
    assert _digest(rows) == FROZEN_TM_SUMMARY_DIGEST


# ══════════════════════════════════════════════════════════════════════════════
# 9 · MIGRATION BAN
# ══════════════════════════════════════════════════════════════════════════════
FROZEN_COIN_MEMORY_COLUMNS = {
    "id", "symbol", "timeframe", "total_signals", "wins", "losses",
    "engine_stats", "regime_stats", "outcome_label_stats", "adaptive_weights",
    "avg_bars_to_outcome", "tm_stats", "tm_sample_count",
    "created_at", "last_updated_at",
}


def test_no_new_column_was_added_to_coin_memory():
    assert {c.name for c in CoinMemory.__table__.columns} == FROZEN_COIN_MEMORY_COLUMNS


def test_no_migration_file_was_added_for_this_checkpoint():
    files = sorted(p.name for p in (BACKEND / "migrations").glob("*.sql"))
    assert len(files) == 10, files
    assert files[-1] == "0010_candidate_log_rls.sql"
    for p in (BACKEND / "migrations").glob("*.sql"):
        assert "cm_v2" not in p.read_text(encoding="utf-8").lower()


# ══════════════════════════════════════════════════════════════════════════════
# 10 · SABOTAGE — every corruption must cost the observation, never the fold
# ══════════════════════════════════════════════════════════════════════════════
SABOTAGE_NAMESPACES = [
    pytest.param("a string", id="non-dict-string"),
    pytest.param(42, id="non-dict-int"),
    pytest.param([1, 2, 3], id="non-dict-list"),
    pytest.param(None, id="null"),
    pytest.param({}, id="empty-dict"),
    pytest.param({"counts": "not-a-dict"}, id="counts-wrong-type"),
    pytest.param({"counts": {"observed": "many", "excluded": None}}, id="counts-junk"),
    pytest.param({"counts": {"observed": -5}}, id="negative-observed"),
    pytest.param({"counts": {"observed": True}}, id="bool-as-count"),
    pytest.param({"cohort": {"decision_input_version": "scalar"}}, id="cohort-scalar"),
    pytest.param({"recent_fold_ids": "not-a-list"}, id="ring-wrong-type"),
    pytest.param({"recent_fold_ids": [1, None, {"a": 1}]}, id="ring-junk-members"),
    pytest.param({"last_fold": "nope"}, id="last-fold-wrong-type"),
    pytest.param({"version": "cm_v2_contract_999"}, id="future-contract-version"),
    pytest.param({"duplicate_folds_skipped": -1}, id="negative-dup-count"),
]


@pytest.mark.parametrize("corrupt", SABOTAGE_NAMESPACES)
def test_sabotage_corrupt_namespace_still_folds_v1_and_rebuilds_the_namespace(corrupt):
    mem = NS(tm_stats={"_all": {"n": 4}, CM_V2_NAMESPACE: corrupt}, tm_sample_count=4)
    _fold(mem, _path())
    assert mem.tm_stats["_all"]["n"] == 5             # v1 folded regardless
    assert mem.tm_sample_count == 5
    ns = _ns(mem)
    assert ns["version"] == CM_V2_CONTRACT_VERSION     # namespace re-established
    assert ns["counts"]["observed"] >= 1
    assert ns["counts"]["observed"] >= 0 and ns["duplicate_folds_skipped"] >= 0
    json.dumps(ns)                                    # still serialisable


def test_sabotage_missing_tm_stats_entirely():
    for tm in (None, {}):
        mem = NS(tm_stats=tm, tm_sample_count=0)
        _fold(mem, _path())
        assert mem.tm_stats["_all"]["n"] == 1 and _ns(mem)["counts"]["observed"] == 1


def test_sabotage_tm_stats_is_not_a_dict_at_all():
    """v1 itself does `dict(mem.tm_stats or {})`, so a non-dict raises inside the v1
    half — which the CALLER's fail-open envelope owns. What must be true is that
    CMV2-A did not widen that blast radius: the failure is the same one v1 already
    had, and no namespace is written from a broken cell."""
    mem = NS(tm_stats="corrupt-string", tm_sample_count=0)
    with pytest.raises((ValueError, TypeError)):
        asyncio.run(update_trade_mgmt_stats(_FakeDB(mem, None), _path()))
    assert mem.tm_stats == "corrupt-string"           # untouched, nothing invented


def test_sabotage_unknown_outcome_value():
    for outcome in (None, "", "weird_new_state", 123, NS(value="???")):
        mem = NS(tm_stats=None, tm_sample_count=0)
        _fold(mem, _path(outcome=outcome))
        ns = _ns(mem)
        assert ns["counts"]["observed"] == 1
        assert ns["counts"]["excluded"]["active"] == 0   # unknown != active


def test_sabotage_missing_candidate_telemetry_is_recorded_not_guessed():
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(), cohort_row=None)
    ns = _ns(mem)
    assert ns["cohort"]["decision_input_version"] == {CM_V2_COHORT_UNKNOWN: 1}
    assert ns["counts"]["excluded"]["missing_decision_input_version"] == 1
    assert ns["last_fold"]["decision_input_version"] == CM_V2_COHORT_UNKNOWN


def test_sabotage_cohort_lookup_raises_but_the_v1_fold_survives():
    mem = NS(tm_stats={"_all": {"n": 2}}, tm_sample_count=2)
    db = _FakeDB(mem, None)
    calls = {"n": 0}
    real_execute = db.execute

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:                            # the cohort SELECT
            raise RuntimeError("boom")
        return await real_execute(*a, **k)

    db.execute = flaky
    asyncio.run(update_trade_mgmt_stats(db, _path()))
    assert mem.tm_stats["_all"]["n"] == 3              # v1 folded
    assert mem.tm_sample_count == 3
    # _resolve_fold_cohort swallows its own failure → the namespace still lands.
    assert _ns(mem)["cohort"]["decision_input_version"] == {CM_V2_COHORT_UNKNOWN: 1}


def test_sabotage_observer_itself_raising_cannot_cost_the_v1_fold(monkeypatch):
    """The ordering guarantee: v1 is assigned BEFORE the namespace block, so even a
    total failure of the observer leaves the v1 fold standing."""
    mem = NS(tm_stats={"_all": {"n": 7}}, tm_sample_count=7)
    monkeypatch.setattr(cm, "observe_cm_v2_fold",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    asyncio.run(update_trade_mgmt_stats(_FakeDB(mem, None), _path()))
    assert mem.tm_stats["_all"]["n"] == 8              # v1 committed
    assert mem.tm_sample_count == 8
    assert CM_V2_NAMESPACE not in mem.tm_stats         # namespace simply absent


def test_sabotage_very_large_existing_namespace_is_bounded_back_down():
    huge = {
        "version": CM_V2_CONTRACT_VERSION,
        "counts": {"observed": 10 ** 7, "included": 10 ** 6,
                   "excluded": {r: 10 ** 5 for r in CM_V2_EXCLUSION_REASONS},
                   "by_fold_rule": {f"rule_{i}": i + 1 for i in range(500)}},
        "cohort": {"decision_input_version": {f"v{i}": i + 1 for i in range(2000)},
                   "policy_version": {str(i): i + 1 for i in range(2000)}},
        "recent_fold_ids": [f"old-{i}" for i in range(5000)],
    }
    mem = NS(tm_stats={"_all": {"n": 1}, CM_V2_NAMESPACE: huge}, tm_sample_count=1)
    _fold(mem, _path(signal_id="fresh"))
    ns = _ns(mem)
    assert len(ns["recent_fold_ids"]) == CM_V2_DEDUPE_WINDOW   # ring re-bounded
    assert ns["recent_fold_ids"][-1] == "fresh"
    assert ns["counts"]["observed"] == 10 ** 7 + 1             # carried, not reset
    assert mem.tm_stats["_all"]["n"] == 2


def test_sabotage_namespace_stays_json_serialisable_under_every_corruption():
    for corrupt in [c.values[0] for c in SABOTAGE_NAMESPACES]:
        mem = NS(tm_stats={CM_V2_NAMESPACE: corrupt}, tm_sample_count=0)
        _fold(mem, _path())
        json.dumps(mem.tm_stats)


def test_sabotage_no_secret_or_url_can_enter_the_namespace():
    """The namespace records provenance, never payloads. A path carrying hostile
    strings in fields CMV2-A does not read must not carry them into the contract.

    Sentinels are deliberately synthetic (`.invalid` is RFC-2606 reserved) so this
    fixture can never be mistaken for a real credential by a reader or a scanner."""
    mem = NS(tm_stats=None, tm_sample_count=0)
    _fold(mem, _path(detail_label="SENTINEL-DSN-SHAPED-VALUE-DO-NOT-USE",
                     symbol="BTC", regime="SENTINEL-URL-host.invalid-path"))
    blob = json.dumps(_ns(mem))
    for banned in ("SENTINEL-DSN-SHAPED-VALUE-DO-NOT-USE", "SENTINEL-URL",
                   "host.invalid"):
        assert banned not in blob


# ══════════════════════════════════════════════════════════════════════════════
# 11 · REBUILD INTERACTION
# ══════════════════════════════════════════════════════════════════════════════
class _RebuildDB:
    """rebuild_tm_stats issues exactly two queries, in order: the trade paths, then
    the cells. Served positionally."""

    def __init__(self, paths, mems):
        self._queue = [paths, mems]
        self.added = []

    async def execute(self, *a, **k):
        vals = self._queue.pop(0)
        return NS(scalars=lambda: NS(all=lambda: vals))

    def add(self, obj):
        self.added.append(obj)


def _cell(tm_stats=None, tm_sample_count=0):
    return CoinMemory(symbol="BTC", timeframe="4h", total_signals=0, wins=0, losses=0,
                      engine_stats={}, regime_stats={}, outcome_label_stats={},
                      tm_stats=tm_stats, tm_sample_count=tm_sample_count)


def test_rebuild_preserves_the_namespace_rather_than_wiping_it():
    """BEHAVIOURAL, not a source check. rebuild_tm_stats resets the v1 buckets from
    the SoT; the namespace is a fold-EVENT ledger it cannot reproduce (`folded_at` is
    wall clock), so it must be carried forward VERBATIM. Wiping it would destroy the
    audit trail on the first admin rebuild; recomputing it would fabricate stamps."""
    ns = {"version": CM_V2_CONTRACT_VERSION, "counts": {"observed": 12},
          "last_fold": {"signal_id": "old", "folded_at": "2026-07-01T00:00:00+00:00"}}
    mem = _cell(tm_stats={"trend": {"n": 99}, CM_V2_NAMESPACE: dict(ns)},
                tm_sample_count=99)

    asyncio.run(cm.rebuild_tm_stats(_RebuildDB([_path(signal_id="p1")], [mem])))

    assert mem.tm_stats[CM_V2_NAMESPACE] == ns        # carried forward, untouched
    assert mem.tm_stats["trend"]["n"] == 1           # v1 rebuilt from the SoT
    assert mem.tm_sample_count == 1                  # …and recounted from it


def test_rebuild_does_not_invent_a_namespace_where_none_existed():
    mem = _cell(tm_stats={"trend": {"n": 5}}, tm_sample_count=5)
    asyncio.run(cm.rebuild_tm_stats(_RebuildDB([_path(signal_id="p1")], [mem])))
    assert CM_V2_NAMESPACE not in mem.tm_stats
    assert mem.tm_stats["trend"]["n"] == 1


def test_rebuild_keeps_the_namespace_even_when_the_cell_has_no_paths_left():
    """The v1 buckets legitimately go to nothing; the ledger must not go with them."""
    ns = {"version": CM_V2_CONTRACT_VERSION, "counts": {"observed": 3}}
    mem = _cell(tm_stats={"trend": {"n": 4}, CM_V2_NAMESPACE: dict(ns)}, tm_sample_count=4)
    asyncio.run(cm.rebuild_tm_stats(_RebuildDB([], [mem])))
    assert mem.tm_stats == {CM_V2_NAMESPACE: ns}
    assert mem.tm_sample_count == 0


def test_rebuild_still_writes_only_the_tm_facet():
    src = inspect.getsource(cm.rebuild_tm_stats)
    assert set(re.findall(r"mem\.(\w+)\s*=", src)) == {"tm_stats", "tm_sample_count"}


def test_rebuild_does_not_synthesize_a_namespace_where_none_existed():
    src = inspect.getsource(cm._aggregate_tm_stats)
    assert "cm_v2" not in src and "CM_V2" not in src


def test_v1_helper_strips_only_the_namespace():
    tm = {"_all": {"n": 1}, "trend": {"n": 1}, CM_V2_NAMESPACE: {"x": 1}}
    assert v1_tm_buckets(tm) == {"_all": {"n": 1}, "trend": {"n": 1}}
    assert v1_tm_buckets(None) == {} and v1_tm_buckets({}) == {}
