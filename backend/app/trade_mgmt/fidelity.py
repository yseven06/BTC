"""
Fidelity check — does replay(FixedCurrent) reproduce the tracker's observed
results?

The Phase-1 acceptance gate: before trusting ANY alternative policy, the replay
engine must independently reconstruct current production behavior. Per resolved
path we compare:
  • realized return  — replay R  vs  observed (cur_realized_return / sl_dist)
  • outcome          — replay R → win/loss/breakeven (tracker ±0.5% thresholds)
  • give-back        — replay.gave_back vs cur_gave_back_after_tp1

TP1/TP2/TP3 flags are INPUTS to the replay (not re-detected), so they are
consistent by construction — the independent validations are realized + outcome.

Reconstructability (authoritative, from labels.classify_resolution):
  reconstructable  : tp3_hit, tp2_hit, tp1_then_breakeven, sl_hit,
                     correct_dir_tight_sl   (resolved purely by TP/SL geometry)
  NOT reconstructable (summary lacks the close price / live price):
     - expired_profit / expired_loss / expired_flat   → expiry close not stored
     - tp1_hit                                          → TP1 then expiry-in-profit
     - live_sl_hit / still_forming_resolution           → mid-candle live price
  low-precision: micro-cap rows whose 8-decimal stored prices cannot reproduce
     the stored sl_dist_pct (internal-consistency check; not circular).

These categories are reported SEPARATELY (not counted against strict fidelity),
because no policy — current or future — can be reconstructed for them from the
stored summary. Acceptance is judged on the reconstructable set.

Pure/deterministic; no IO. Operates on already-loaded records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.policies.catalog import FixedCurrent
from app.trade_mgmt.replay import replay
from app.trade_mgmt.types import PathRecord

WIN_THR = 0.5
LOSS_THR = -0.5
REALIZED_TOL_R = 0.02          # R-space tolerance (compounded rounding)
PRECISION_TOL_PCT = 0.05       # |derived_sl_dist - stored_sl_dist_pct| absolute %

_EXPIRY_LABELS = {"expired_profit", "expired_loss", "expired_flat"}
_TP1_EXPIRY_LABELS = {"tp1_hit"}          # TP1 then expiry-in-profit (close not stored)
_LIVE_LABELS = {"live_sl_hit"}


@dataclass(frozen=True)
class FidelityRow:
    signal_id: str
    eligible: bool
    exclude_reason: Optional[str]
    observed_r: Optional[float]
    replay_r: float
    abs_err_r: Optional[float]
    realized_match: bool
    observed_outcome: Optional[str]
    replay_outcome: Optional[str]
    outcome_match: bool
    observed_giveback: bool
    replay_giveback: bool
    giveback_match: bool
    exit_reason: str
    detail_label: Optional[str]


def _classify(pnl_pct: Optional[float]) -> Optional[str]:
    if pnl_pct is None:
        return None
    if pnl_pct > WIN_THR:
        return "win"
    if pnl_pct < LOSS_THR:
        return "loss"
    return "breakeven"


def _low_precision(rec: PathRecord) -> bool:
    """Stored 8-decimal prices can't reproduce the stored sl_dist_pct → the
    price-derived R-multiples are unreliable. Internal-consistency check."""
    if rec.entry and rec.sl and rec.sl_dist_pct:
        derived = abs(rec.entry - rec.sl) / rec.entry * 100.0
        return abs(derived - rec.sl_dist_pct) > PRECISION_TOL_PCT
    return False


def exclude_reason(rec: PathRecord) -> Optional[str]:
    """Why a row is NOT reconstructable from the stored summary — record-only and
    policy-independent (shared by fidelity + scoring). None → reconstructable."""
    label = (rec.detail_label or "")
    if rec.still_forming_resolution or label in _LIVE_LABELS:
        return "live_sl/still_forming"
    if not rec.cur_reached_tp1 and (rec.outcome or "").lower() != "loss":
        return "observed_fallback"   # no-TP1 non-SL (expiry/flat) — close not stored
    if label in _EXPIRY_LABELS:
        return "expiry"
    if label in _TP1_EXPIRY_LABELS:
        return "tp1_then_expiry"
    if _low_precision(rec):
        return "low_precision"
    return None


def is_reconstructable(rec: PathRecord) -> bool:
    """True if replay can faithfully reconstruct this row from the summary."""
    return exclude_reason(rec) is None


def compare_record(rec: PathRecord, policy: Optional[Policy] = None) -> FidelityRow:
    policy = policy or FixedCurrent()
    res = replay(rec, policy)
    sl_dist = rec.sl_dist_pct if rec.sl_dist_pct else None

    observed_r = (
        round(rec.cur_realized_return / sl_dist, 4)
        if (rec.cur_realized_return is not None and sl_dist)
        else None
    )
    replay_r = res.realized_r
    abs_err = abs(replay_r - observed_r) if observed_r is not None else None
    realized_match = abs_err is not None and abs_err <= REALIZED_TOL_R

    replay_pct = replay_r * sl_dist if sl_dist else None
    replay_outcome = _classify(replay_pct)
    observed_outcome = (rec.outcome or "").lower() or None
    outcome_match = replay_outcome == observed_outcome

    replay_gb = bool(res.gave_back)
    observed_gb = bool(rec.cur_gave_back_after_tp1)
    gb_match = replay_gb == observed_gb

    reason = exclude_reason(rec)

    return FidelityRow(
        signal_id=rec.signal_id, eligible=reason is None, exclude_reason=reason,
        observed_r=observed_r, replay_r=replay_r, abs_err_r=abs_err, realized_match=realized_match,
        observed_outcome=observed_outcome, replay_outcome=replay_outcome, outcome_match=outcome_match,
        observed_giveback=observed_gb, replay_giveback=replay_gb, giveback_match=gb_match,
        exit_reason=res.exit_reason, detail_label=rec.detail_label,
    )


def _rate(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def run_fidelity(records: List[PathRecord], policy: Optional[Policy] = None) -> Dict[str, Any]:
    rows = [compare_record(r, policy) for r in records]
    elig = [x for x in rows if x.eligible]

    def agg(group: List[FidelityRow]) -> Dict[str, Any]:
        n = len(group)
        rmatch = sum(1 for x in group if x.realized_match)
        omatch = sum(1 for x in group if x.outcome_match)
        gmatch = sum(1 for x in group if x.giveback_match)
        errs = [x.abs_err_r for x in group if x.abs_err_r is not None]
        return {
            "n": n,
            "realized_match": rmatch, "realized_rate": _rate(rmatch, n),
            "outcome_match": omatch, "outcome_rate": _rate(omatch, n),
            "giveback_match": gmatch, "giveback_rate": _rate(gmatch, n),
            "mean_abs_err_r": round(sum(errs) / len(errs), 5) if errs else None,
            "max_abs_err_r": round(max(errs), 5) if errs else None,
        }

    excl_breakdown: Dict[str, int] = {}
    for x in rows:
        if x.exclude_reason:
            excl_breakdown[x.exclude_reason] = excl_breakdown.get(x.exclude_reason, 0) + 1

    eligible_stats = agg(elig)
    accept = (
        eligible_stats["n"] > 0
        and eligible_stats["realized_rate"] >= 99.0
        and eligible_stats["outcome_rate"] >= 99.0
        and eligible_stats["giveback_rate"] >= 99.0
    )
    mismatches = [x for x in elig if not (x.realized_match and x.outcome_match and x.giveback_match)]
    return {
        "total": len(rows),
        "eligible": eligible_stats,
        "excluded_total": len(rows) - len(elig),
        "excluded_breakdown": excl_breakdown,
        "all": agg(rows),
        "accept": accept,
        "mismatches": mismatches,
    }
