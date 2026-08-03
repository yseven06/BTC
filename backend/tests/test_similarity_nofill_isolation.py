"""CP-ENTRY-SIMILARITY-NOFILL-ISOLATION — 21 cases + 10 sabotage tests.

The pre-enable audit found one blocker, and it was a quiet one. Similarity keeps
the coarse outcome of a real trade for rows where no position ever opened:
`expired_without_entry` is stored as EXPIRED and `invalidated_before_entry` as
INVALIDATED. The candidate pool admits both outcomes, and `losses` counts every
INVALIDATED. So the moment the entry gate is switched on, a setup that was
superseded while still WAITING would be reported to the user as a loss it never
took — and its label could become `most_common_outcome`, "the typical way this
setup ends".

Nothing raises. The number just quietly gets worse.

What must NOT be excluded is the other half of the contract: `invalidated_reversal`
is a real trade that filled and was then superseded, a plain EXPIRED with no
no-fill label is a real trade that ran out of time, and a legacy row whose
detail_label is NULL is simply unclassified. "We do not know" must never be
promoted to "it never filled".
"""

from __future__ import annotations

import hashlib
import inspect
import pathlib

import pytest

from app.backtesting import labels as L
from app.models.signal import SignalOutcome
from app.services import similarity as SIM
from app.services.entry_validity import (
    NO_FILL_DETAIL_LABELS,
    is_no_fill,
    is_no_fill_label,
)
from app.services.similarity import MIN_SIMILAR_MATCHES, _Candidate, summarize_similar

QDIR = "bullish"
QFP = {"e1": "bullish", "e2": "bullish"}


def cand(outcome, label, *, direction=QDIR):
    """A candidate at distance 0 from the query — so only the filter decides."""
    return _Candidate(
        direction=direction, regime="trending_bull", confidence=70.0,
        volatility_ratio=1.0, fingerprint=dict(QFP),
        outcome=outcome, detail_label=label,
    )


def summarise(candidates):
    return summarize_similar(
        q_direction=QDIR, q_regime="trending_bull", q_confidence=70.0,
        q_volatility_ratio=1.0, q_fingerprint=dict(QFP), candidates=candidates,
    )


def wins(n, label="tp1_hit"):
    return [cand(SignalOutcome.WIN.value, label) for _ in range(n)]


def losses(n, label="sl_hit"):
    return [cand(SignalOutcome.LOSS.value, label) for _ in range(n)]


NO_FILL_EXPIRED = (SignalOutcome.EXPIRED.value, "expired_without_entry")
NO_FILL_INVALID = (SignalOutcome.INVALIDATED.value, "invalidated_before_entry")


# ── 1-2 · the two no-fill labels never reach the pool ────────────────────────
@pytest.mark.parametrize("outcome,label", [NO_FILL_EXPIRED, NO_FILL_INVALID])
def test_01_02_no_fill_rows_do_not_enter_the_pool(outcome, label):
    base = wins(8)
    clean = summarise(base)
    polluted = summarise(base + [cand(outcome, label) for _ in range(20)])
    assert polluted == clean, f"{label} changed the verdict"


# ── 3 · they never reach the loss counter ────────────────────────────────────
def test_03_no_fill_rows_are_not_counted_as_losses():
    """The sharpest edge: INVALIDATED is counted as a loss at similarity.py's
    `losses` line, so an unfilled row would be a loss the user never took."""
    out = summarise(wins(8) + [cand(*NO_FILL_INVALID) for _ in range(10)])
    assert out["losses"] == 0
    assert out["wins"] == 8
    assert out["win_rate"] == 100.0


# ── 4 · they never reach the label census ────────────────────────────────────
def test_04_no_fill_labels_do_not_win_the_common_outcome_vote():
    out = summarise(wins(8, "tp1_hit") + [cand(*NO_FILL_EXPIRED) for _ in range(50)])
    assert out["most_common_outcome"] == "tp1_hit"


# ── 5 · nothing leaks into the user-facing verdict ───────────────────────────
def test_05_no_fill_labels_never_appear_in_the_returned_payload():
    out = summarise(wins(8) + [cand(*NO_FILL_EXPIRED), cand(*NO_FILL_INVALID)])
    blob = repr(out)
    for label in NO_FILL_DETAIL_LABELS:
        assert label not in blob


# ── 6-11 · everything real is preserved ──────────────────────────────────────
def test_06_invalidated_reversal_stays_in_the_pool():
    """A reversal that superseded a FILLED trade is a real outcome, and it has
    always counted as a loss. That classification is deliberately untouched."""
    out = summarise(wins(8) + [cand(SignalOutcome.INVALIDATED.value,
                                    L.INVALIDATED_REVERSAL) for _ in range(4)])
    assert out["match_count"] == 12
    assert out["losses"] == 4, "invalidated_reversal must still count as a loss"


def test_07_other_real_invalidated_outcomes_are_preserved():
    """INVALIDATED with a NULL label predates the no-fill labels entirely."""
    out = summarise(wins(8) + [cand(SignalOutcome.INVALIDATED.value, None)
                               for _ in range(3)])
    assert out["match_count"] == 11 and out["losses"] == 3


@pytest.mark.parametrize("label", [L.EXPIRED_PROFIT, L.EXPIRED_LOSS, L.EXPIRED_FLAT, None])
def test_08_ordinary_expired_is_preserved(label):
    out = summarise(wins(8) + [cand(SignalOutcome.EXPIRED.value, label)
                               for _ in range(5)])
    assert out["match_count"] == 13


def test_09_ordinary_loss_is_preserved():
    out = summarise(wins(6) + losses(6))
    assert out["match_count"] == 12 and out["losses"] == 6 and out["wins"] == 6


def test_10_ordinary_win_is_preserved():
    out = summarise(wins(10))
    assert out["match_count"] == 10 and out["wins"] == 10


def test_11_breakeven_is_preserved():
    out = summarise(wins(8) + [cand(SignalOutcome.BREAKEVEN.value,
                                    L.TP1_THEN_BREAKEVEN) for _ in range(4)])
    assert out["match_count"] == 12
    assert out["wins"] == 8 and out["losses"] == 0  # breakeven is neither, unchanged


# ── 12 · legacy NULL labels are NOT no-fill ──────────────────────────────────
def test_12_null_detail_label_is_never_treated_as_no_fill():
    """The whole checkpoint exists to stop "unknown" being coerced into a
    verdict. A legacy row with no label is unclassified, not unfilled."""
    assert is_no_fill_label(None) is False
    assert is_no_fill_label("") is False
    assert is_no_fill({}) is False
    out = summarise([cand(SignalOutcome.WIN.value, None) for _ in range(9)])
    assert out["match_count"] == 9 and out["wins"] == 9


# ── 13 · a pool of ONLY no-fill rows must not fabricate a percentage ─────────
def test_13_a_pool_of_only_no_fill_rows_reports_no_data():
    out = summarise([cand(*NO_FILL_EXPIRED) for _ in range(40)]
                    + [cand(*NO_FILL_INVALID) for _ in range(40)])
    assert out["has_data"] is False
    assert out["match_count"] == 0
    assert "win_rate" not in out, "a rate was invented from an empty pool"
    assert out["needed"] == MIN_SIMILAR_MATCHES


# ── 14 · the sample size shrinks by exactly the excluded rows ────────────────
def test_14_sample_size_drops_by_exactly_the_no_fill_count():
    real = wins(10) + losses(5)
    out_clean = summarise(real)
    out_mixed = summarise(real + [cand(*NO_FILL_INVALID) for _ in range(7)])
    assert out_clean["match_count"] == 15
    assert out_mixed["match_count"] == 15, "excluded rows still inflated the sample"


# ── 15 · the API contract keeps every key ────────────────────────────────────
def test_15_the_returned_key_set_is_unchanged():
    rich = summarise(wins(8))
    assert set(rich) == {"has_data", "match_count", "wins", "losses",
                         "win_rate", "most_common_outcome"}
    poor = summarise(wins(2))
    assert set(poor) == {"has_data", "match_count", "needed"}


# ── 16 · with the flags off, nothing changes ────────────────────────────────
def test_16_pre_gate_fixtures_are_bit_for_bit_unchanged():
    """No-fill labels can only be written once the gate is on. A pool built from
    today's production vocabulary must therefore be untouched by the filter."""
    today = (wins(5, L.TP3_HIT) + losses(4, L.SL_HIT)
             + [cand(SignalOutcome.BREAKEVEN.value, L.TP1_THEN_BREAKEVEN)]
             + [cand(SignalOutcome.INVALIDATED.value, L.INVALIDATED_REVERSAL)]
             + [cand(SignalOutcome.EXPIRED.value, L.EXPIRED_PROFIT)]
             + [cand(SignalOutcome.LOSS.value, L.LIVE_SL_HIT)]
             + [cand(SignalOutcome.LOSS.value, L.CORRECT_DIR_TIGHT_SL)])
    out = summarise(today)
    assert out["match_count"] == len(today)
    assert out["wins"] == 5
    assert out["losses"] == 4 + 1 + 1 + 1  # sl_hit + reversal + live_sl + tight_sl


# ── 17 · with the gate on, the new rows are excluded ────────────────────────
def test_17_gate_on_simulation_excludes_the_new_rows():
    pre = summarise(wins(6) + losses(4))
    post = summarise(wins(6) + losses(4)
                     + [cand(*NO_FILL_EXPIRED) for _ in range(9)]
                     + [cand(*NO_FILL_INVALID) for _ in range(9)])
    assert post == pre, "turning the gate on changed the similarity verdict"


# ── 18-19 · the neighbouring guards are untouched ───────────────────────────
def test_18_coin_memory_early_return_is_unchanged():
    from app.services.coin_memory import NO_FILL_DETAIL_LABELS as CM_SET, fold_signal_into
    src = inspect.getsource(fold_signal_into)
    assert src.index("NO_FILL_DETAIL_LABELS") < src.index("is_loss =")
    assert "is_loss = outcome in (SignalOutcome.LOSS, SignalOutcome.INVALIDATED)" in src
    assert CM_SET == {L.EXPIRED_WITHOUT_ENTRY, L.INVALIDATED_BEFORE_ENTRY}


def test_19_the_two_no_fill_sets_agree():
    """Two modules already spell this set independently — coin_memory from the
    label constants, entry_validity from literals, because it is a pure leaf.
    Similarity now imports the second. Drift between them would silently mean
    two different answers to the same question, so pin the agreement."""
    from app.services.coin_memory import NO_FILL_DETAIL_LABELS as CM_SET
    assert CM_SET == NO_FILL_DETAIL_LABELS == {
        "expired_without_entry", "invalidated_before_entry"}


def test_19b_adaptive_guard_is_unchanged():
    from app.services.coin_memory import _recompute_adaptive_weights
    assert "engine_stats" in inspect.signature(_recompute_adaptive_weights).parameters


# ── 20 · Pass B is untouched ────────────────────────────────────────────────
def test_20_pass_b_does_not_consume_similarity_or_the_flags():
    from app.services import shadow_eval
    src = inspect.getsource(shadow_eval)
    assert "similarity" not in src
    assert "entry_activation_enabled" not in src


# ── 21 · the source pin moves deliberately ──────────────────────────────────
EXPECTED_SIMILARITY_SHA = "dfb29e3b56113de50b9d3001c4e8ff34d4c75f4ec9ba76f6c53feaa5d84904af"


def test_21_similarity_source_pin_is_updated_deliberately():
    """similarity.py was byte-frozen because earlier checkpoints claimed parity
    on it being untouched. This checkpoint changes it ON PURPOSE — the exclusion
    could not live anywhere else, because `find_similar_setups` builds its own
    pool and takes no filter argument. So the pin moves, and it moves here, once.

    Newlines are normalised: git stores LF, Windows checkouts get CRLF, and a
    raw byte hash would make this test's verdict depend on the developer's OS.
    """
    src = inspect.getsource(SIM).encode("utf-8").replace(b"\r\n", b"\n")
    assert hashlib.sha256(src).hexdigest() == EXPECTED_SIMILARITY_SHA


def test_21b_the_gate_constants_are_still_pinned():
    assert (SIM.MIN_SIMILAR_MATCHES, SIM.TOP_K, SIM.MAX_DISTANCE) == (8, 50, 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# SABOTAGE — the wrong version, shown to disagree, before the right one is pinned
# ══════════════════════════════════════════════════════════════════════════════
def test_S1_filter_removed_entirely():
    """Without the filter, 20 unfilled rows swamp 8 real wins."""
    naive = [c for c in wins(8) + [cand(*NO_FILL_INVALID) for _ in range(20)]]
    unfiltered_losses = sum(1 for c in naive if c.outcome in (
        SignalOutcome.LOSS.value, SignalOutcome.INVALIDATED.value))
    assert unfiltered_losses == 20                      # what the old code saw
    assert summarise(naive)["losses"] == 0              # what it sees now


def test_S2_only_expired_excluded():
    """Excluding EXPIRED alone leaves invalidated_before_entry counted as a loss."""
    pool = wins(8) + [cand(*NO_FILL_INVALID) for _ in range(5)]
    half_filtered = [c for c in pool if c.detail_label != "expired_without_entry"]
    assert len(half_filtered) == 13                     # the wrong filter keeps them
    assert summarise(pool)["match_count"] == 8


def test_S3_all_invalidated_excluded():
    """Excluding every INVALIDATED throws away real reversal outcomes."""
    pool = wins(8) + [cand(SignalOutcome.INVALIDATED.value, L.INVALIDATED_REVERSAL)
                      for _ in range(4)]
    over_filtered = [c for c in pool if c.outcome != SignalOutcome.INVALIDATED.value]
    assert len(over_filtered) == 8                      # the wrong filter drops them
    assert summarise(pool)["match_count"] == 12         # we keep them


def test_S4_outcome_used_instead_of_detail_label():
    """`outcome` cannot distinguish the two: both no-fill rows and real ones
    share EXPIRED / INVALIDATED. Only the label separates them."""
    real = cand(SignalOutcome.INVALIDATED.value, L.INVALIDATED_REVERSAL)
    fake = cand(*NO_FILL_INVALID)
    assert real.outcome == fake.outcome                 # indistinguishable by outcome
    assert is_no_fill_label(real.detail_label) is False
    assert is_no_fill_label(fake.detail_label) is True


def test_S5_invalidated_reversal_wrongly_excluded():
    out = summarise(wins(8) + [cand(SignalOutcome.INVALIDATED.value,
                                    L.INVALIDATED_REVERSAL) for _ in range(4)])
    assert out["match_count"] == 12 and out["losses"] == 4


def test_S6_no_fill_rows_re_admitted_to_the_loss_count():
    out = summarise(wins(8) + [cand(*NO_FILL_INVALID) for _ in range(6)])
    assert out["losses"] == 0 and out["match_count"] == 8


def test_S7_filter_applied_after_the_common_outcome_vote():
    """Filtering late still lets the label win the census. 50 unfilled rows
    against 8 real ones is exactly that scenario."""
    pool = wins(8, "tp1_hit") + [cand(*NO_FILL_EXPIRED) for _ in range(50)]
    late = {}
    for c in pool:                                       # census BEFORE filtering
        if c.detail_label:
            late[c.detail_label] = late.get(c.detail_label, 0) + 1
    assert max(late, key=late.get) == "expired_without_entry"   # the wrong answer
    assert summarise(pool)["most_common_outcome"] == "tp1_hit"  # ours


def test_S8_filter_made_an_optional_caller_parameter():
    """A filter the caller can forget is a filter that will be forgotten. The
    exclusion must be unconditional inside similarity, not opt-in."""
    sig = inspect.signature(summarize_similar)
    for banned in ("exclude_no_fill", "include_no_fill", "filter_no_fill",
                   "skip_no_fill", "no_fill"):
        assert banned not in sig.parameters
    assert banned not in inspect.signature(SIM.find_similar_setups).parameters


def test_S9_a_copy_of_the_label_list_instead_of_the_helper():
    """A second spelling of the set is how two modules start disagreeing."""
    src = inspect.getsource(SIM)
    assert "is_no_fill_label" in src, "similarity no longer uses the canonical helper"
    assert '"expired_without_entry"' not in src, "the label list was inlined"
    assert '"invalidated_before_entry"' not in src, "the label list was inlined"
    assert "NO_FILL_DETAIL_LABELS = " not in src, "a local copy of the set was defined"


def test_S10_source_changed_without_moving_the_pin():
    """The pin must track the file. If similarity.py changes again, this fails
    until someone re-derives the parity claim — which is the point of a pin."""
    src = inspect.getsource(SIM).encode("utf-8").replace(b"\r\n", b"\n")
    actual = hashlib.sha256(src).hexdigest()
    assert actual == EXPECTED_SIMILARITY_SHA, (
        f"similarity.py changed to {actual} — re-derive the claim, do not just "
        "paste the new hash")
