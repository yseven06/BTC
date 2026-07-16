"""CP-F1D-1 — label/resolution characterization locks (test-only).

F1-d (Label / Execution Fidelity) starts by PINNING what production does
today, before any versioning column or writer stamp exists. Nothing here
changes behavior; every assert states a measured fact of the current code, so
that CP-F1D-2/3 — and any future semantics change — turns silent drift into a
red test instead of an unmarked era boundary in stored data.

Four groups:
  A. Vocabulary — the 11 label strings, LABEL_TR completeness, thresholds.
  B. classify_resolution — first unit tests ever: every branch + boundaries.
  C. Cross-module drift locks — fidelity.py's duplicate label sets and
     outcome thresholds vs the canonical labels.py values.
  D. Writer topology (source-level, the F0-L1 pattern) — WHICH writer paths
     stamp detail_label, which write the EXPIRED enum, and where the ±0.5%
     outcome thresholds live. Counts are measured, not aspirational: editing
     one copy without its twins must fail here.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace as NS

import app
from app.backtesting import labels as L
from app.trade_mgmt import fidelity as F

APP_DIR = Path(app.__file__).resolve().parent


def _src(rel: str) -> str:
    return (APP_DIR / rel).read_text(encoding="utf-8")


def _enum_assigns(src: str, member: str) -> int:
    """Count `... = SignalOutcome.<member>` ASSIGNMENTS (comparisons like
    `==` / `!=` don't count — the char before `=` must not be `=` or `!`)."""
    return len(re.findall(rf"(?<![=!])=\s*SignalOutcome\.{member}\b", src))


TRACKER = "backtesting/tracker.py"
ENGINE = "backtesting/engine.py"
SCHEDULER = "services/scheduler.py"
ADMIN = "api/routes/admin.py"


# ── A. vocabulary ────────────────────────────────────────────────────────────

# The full stored vocabulary. These strings live in the DB (2360+ rows) and in
# the public API shape — renaming one forks stored history.
VOCAB = {
    "TP3_HIT": "tp3_hit",
    "TP2_HIT": "tp2_hit",
    "TP1_HIT": "tp1_hit",
    "TP1_THEN_BREAKEVEN": "tp1_then_breakeven",
    "SL_HIT": "sl_hit",
    "CORRECT_DIR_TIGHT_SL": "correct_dir_tight_sl",
    "LIVE_SL_HIT": "live_sl_hit",
    "EXPIRED_PROFIT": "expired_profit",
    "EXPIRED_LOSS": "expired_loss",
    "EXPIRED_FLAT": "expired_flat",
    "INVALIDATED_REVERSAL": "invalidated_reversal",
}


def test_vocabulary_exact_strings():
    for const, value in VOCAB.items():
        assert getattr(L, const) == value, f"{const} renamed — stored rows keep '{value}'"


def test_label_tr_covers_exactly_the_vocabulary():
    # No missing entry (an unknown label reaches the UI verbatim in EN via the
    # passthrough) and no orphan entry pointing at a retired label.
    assert set(L.LABEL_TR) == set(VOCAB.values())


def test_label_tr_passthrough_and_known():
    assert L.label_tr(None) == ""
    assert L.label_tr("") == ""
    assert L.label_tr("no_such_label") == "no_such_label"  # unknowns pass through verbatim
    assert L.label_tr(L.TP3_HIT) == "TP3 geldi"


def test_tight_sl_threshold_value():
    assert L.TIGHT_SL_MFE_THRESHOLD == 0.5


# ── B. classify_resolution — branch and boundary locks ──────────────────────

def _c(**over):
    base = dict(hit_tp1=False, hit_tp2=False, hit_tp3=False, resolved_by_sl=False,
                is_expired=False, pnl_pct=0.0, mfe_pct=0.0, entry=100.0, tp1=102.0)
    base.update(over)
    return L.classify_resolution(**base)


def test_tp_ladder_precedence():
    # A reached TP is the headline no matter how the trade later closed.
    assert _c(hit_tp3=True, hit_tp2=True, hit_tp1=True,
              resolved_by_sl=True, is_expired=True, pnl_pct=-1.0) == L.TP3_HIT
    assert _c(hit_tp2=True, hit_tp1=True, resolved_by_sl=True) == L.TP2_HIT
    assert _c(hit_tp1=True, pnl_pct=2.0) == L.TP1_HIT


def test_tp1_split_is_strictly_greater_than_half_percent():
    assert _c(hit_tp1=True, pnl_pct=0.51) == L.TP1_HIT
    assert _c(hit_tp1=True, pnl_pct=0.5) == L.TP1_THEN_BREAKEVEN  # boundary: strict >
    assert _c(hit_tp1=True, pnl_pct=-0.2) == L.TP1_THEN_BREAKEVEN


def test_tp1_beats_expiry():
    # Measured oddity, locked on purpose: a TP1-then-expired trade is labeled
    # tp1_*, never expired_* — is_expired is only consulted when no TP was hit.
    assert _c(hit_tp1=True, is_expired=True, pnl_pct=1.0) == L.TP1_HIT
    assert _c(hit_tp1=True, is_expired=True, pnl_pct=0.1) == L.TP1_THEN_BREAKEVEN


def test_expiry_band_boundaries():
    assert _c(is_expired=True, pnl_pct=0.51) == L.EXPIRED_PROFIT
    assert _c(is_expired=True, pnl_pct=0.5) == L.EXPIRED_FLAT    # +boundary is flat
    assert _c(is_expired=True, pnl_pct=-0.5) == L.EXPIRED_FLAT   # -boundary is flat
    assert _c(is_expired=True, pnl_pct=-0.51) == L.EXPIRED_LOSS


def test_tight_sl_boundary_is_inclusive():
    # entry 100 → tp1 102: distance 2.0; threshold 0.5 → MFE price move ≥ 1.0
    # counts as tight. mfe_pct 1.0 → move exactly 1.0 → tight (>=, inclusive).
    assert _c(resolved_by_sl=True, mfe_pct=1.0, pnl_pct=-2.0) == L.CORRECT_DIR_TIGHT_SL
    assert _c(resolved_by_sl=True, mfe_pct=0.99, pnl_pct=-2.0) == L.SL_HIT


def test_tight_sl_degenerate_geometry_falls_back_to_plain_stop():
    assert _c(resolved_by_sl=True, mfe_pct=50.0, tp1=100.0) == L.SL_HIT       # tp1 == entry
    assert _c(resolved_by_sl=True, mfe_pct=50.0, entry=0.0, tp1=2.0) == L.SL_HIT  # entry <= 0


def test_fallback_never_none():
    # No flags at all — shouldn't happen live, but the function still answers.
    assert _c(pnl_pct=-1.0) == L.SL_HIT
    assert _c(pnl_pct=0.0) == L.EXPIRED_FLAT   # 0 is not < 0
    assert _c(pnl_pct=1.0) == L.EXPIRED_FLAT


# ── C. cross-module drift locks ──────────────────────────────────────────────

def test_fidelity_duplicate_sets_match_canonical_vocabulary():
    # fidelity.py re-declares these as raw literals (labels.py not imported).
    # Until a hygiene commit derives them from the constants, THIS is the only
    # tie keeping the two copies of the vocabulary in sync.
    assert F._EXPIRY_LABELS == {L.EXPIRED_PROFIT, L.EXPIRED_LOSS, L.EXPIRED_FLAT}
    assert F._TP1_EXPIRY_LABELS == {L.TP1_HIT}
    assert F._LIVE_LABELS == {L.LIVE_SL_HIT}


def test_fidelity_outcome_thresholds_mirror_tracker():
    assert F.WIN_THR == 0.5
    assert F.LOSS_THR == -0.5


def test_unknown_label_is_treated_as_reconstructable():
    # Characterization of a real hazard, not an endorsement: a label the
    # fidelity sets don't know falls through exclude_reason() as if it were a
    # clean TP/SL-geometry row and joins the acceptance-gate set. Any NEW
    # label must ship with an explicit fidelity-exclusion decision.
    rec = NS(still_forming_resolution=False, detail_label="some_future_label",
             cur_reached_tp1=True, outcome="win", entry=100.0, sl=98.0, sl_dist_pct=2.0)
    assert F.exclude_reason(rec) is None
    assert F.is_reconstructable(rec) is True


# ── D. writer topology (source-level) ────────────────────────────────────────

def test_label_writer_topology():
    """Exactly three writer paths stamp detail_label; the other three
    (HOLD-expiry, admin invalidate, admin bulk-clean) leave it NULL."""
    tracker, sched, admin = _src(TRACKER), _src(SCHEDULER), _src(ADMIN)
    # tracker: live-SL constant + bar-walk classifier — and nothing else.
    assert len(re.findall(r"perf\.detail_label\s*=", tracker)) == 2
    assert tracker.count("perf.detail_label = labels.LIVE_SL_HIT") == 1
    assert tracker.count("labels.classify_resolution(") == 1  # single production caller
    # scheduler: exactly one label write (the reversal literal).
    assert len(re.findall(r"\.detail_label\s*=", sched)) == 1
    # admin: never touches detail_label — its EXPIRED rows carry a NULL label.
    assert "detail_label" not in admin


def test_expired_enum_topology_is_disjoint_from_expired_labels():
    """EXPIRED is double-encoded today (measured, locked as-is):
      - organic expiry (tracker bar-walk block) books WIN/LOSS/BREAKEVEN +
        is_expired=True + an expired_* LABEL — never the EXPIRED enum;
      - HOLD-expiry and both admin paths book the EXPIRED ENUM with a NULL
        label.
    The two populations are disjoint sets with different meanings; a fidelity
    design must not assume they align."""
    tracker, sched, admin = _src(TRACKER), _src(SCHEDULER), _src(ADMIN)
    assert _enum_assigns(tracker, "EXPIRED") == 1       # HOLD path only
    assert _enum_assigns(admin, "EXPIRED") == 2         # invalidate + bulk-clean
    assert _enum_assigns(sched, "EXPIRED") == 0
    assert _enum_assigns(sched, "INVALIDATED") == 1     # reversal writes INVALIDATED
    assert _enum_assigns(tracker, "INVALIDATED") == 0
    assert _enum_assigns(admin, "INVALIDATED") == 0


def test_scheduler_reversal_literals_match_labels_module():
    """The scheduler writes the reversal label AND its Turkish narration as raw
    literals (labels.py is not imported there). Until the hygiene commit routes
    them through the constants, this test keeps the copies in sync."""
    sched = _src(SCHEDULER)
    assert L.INVALIDATED_REVERSAL == "invalidated_reversal"
    assert 'detail_label = "invalidated_reversal"' in sched
    assert L.LABEL_TR[L.INVALIDATED_REVERSAL] == "Ters sinyalle geçersiz oldu"
    assert 'reason="Ters sinyalle geçersiz oldu"' in sched


def test_outcome_threshold_copies():
    """The ±0.5% WIN/LOSS outcome thresholds exist as FOUR independent copies:
    tracker live-SL, tracker bar-walk, the backtest engine, and fidelity's
    WIN_THR/LOSS_THR (locked above). No shared constant. This lock forces any
    threshold change to visit every copy — or to deliberately retire this test
    by introducing the shared constant."""
    tracker, engine = _src(TRACKER), _src(ENGINE)
    assert len(re.findall(r"pnl_pct > 0\.5\b", tracker)) == 2
    assert len(re.findall(r"pnl_pct < -0\.5\b", tracker)) == 2
    assert len(re.findall(r"pnl_pct > 0\.5\b", engine)) == 1
    assert len(re.findall(r"pnl_pct < -0\.5\b", engine)) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} F1D-1 label-characterization tests PASSED")
