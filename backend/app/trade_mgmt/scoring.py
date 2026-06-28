"""
Policy scoring + comparison — common metrics over a replayed record set.

Scores any Policy on the SAME reconstructable record set so policies are
compared apples-to-apples. FixedCurrent is the baseline; other policies report
their uplift vs it. Pure/deterministic; no IO.

Metrics (all in R-multiples; R = entry↔SL distance):
  expectancy_r   — mean realized R (the headline)
  median_r, p25_r — center + left tail (p25 guards "don't worsen the bad cases")
  avg_win_r / avg_loss_r
  win_rate       — % of trades with realized_r > 0
  profit_factor  — Σ wins / |Σ losses|  (None when no losing trades)
  giveback_rate  — % of TP1-reached trades whose remainder gave back (policy-dependent)
  mean_confidence — replay confidence (｜trail≈approx lowers it)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.trade_mgmt.fidelity import is_reconstructable
from app.trade_mgmt.policies.base import Policy
from app.trade_mgmt.policies.catalog import FixedCurrent
from app.trade_mgmt.replay import replay
from app.trade_mgmt.types import PathRecord


def _pct(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(s):
        return s[lo] + (s[lo + 1] - s[lo]) * frac
    return s[lo]


@dataclass(frozen=True)
class PolicyScore:
    policy: str
    n: int
    expectancy_r: float
    median_r: float
    p25_r: float
    avg_win_r: float
    avg_loss_r: float
    win_rate: float
    profit_factor: Optional[float]   # None = no losing trades
    giveback_rate: float
    mean_confidence: float


def score_policy(records: List[PathRecord], policy: Policy) -> PolicyScore:
    """Score one policy over already-filtered records (caller ensures the set)."""
    results = [(r, replay(r, policy)) for r in records]
    rs = [res.realized_r for _, res in results]
    n = len(rs)
    if n == 0:
        return PolicyScore(policy.name, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, 0.0, 0.0)

    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x < 0]
    pos, neg = sum(wins), -sum(losses)
    pf = round(pos / neg, 3) if neg > 0 else None  # None = no losses (undefined PF)

    tp1 = [(r, res) for r, res in results if r.cur_reached_tp1]
    gb = sum(1 for _, res in tp1 if res.gave_back)

    return PolicyScore(
        policy=policy.name, n=n,
        expectancy_r=round(sum(rs) / n, 4),
        median_r=round(_pct(rs, 0.5), 4),
        p25_r=round(_pct(rs, 0.25), 4),
        avg_win_r=round(sum(wins) / len(wins), 4) if wins else 0.0,
        avg_loss_r=round(sum(losses) / len(losses), 4) if losses else 0.0,
        win_rate=round(100.0 * len(wins) / n, 1),
        profit_factor=pf,
        giveback_rate=round(100.0 * gb / len(tp1), 1) if tp1 else 0.0,
        mean_confidence=round(sum(res.confidence for _, res in results) / n, 3),
    )


def compare_policies(
    records: List[PathRecord],
    policies: List[Policy],
    *,
    only_reconstructable: bool = True,
) -> Dict[str, Any]:
    """Compare policies on a common record set. policies[0] is the baseline.

    Returns the filtered n, each PolicyScore, and per-policy uplift vs baseline
    (expectancy_r / giveback_rate / p25_r deltas)."""
    recs = [r for r in records if is_reconstructable(r)] if only_reconstructable else list(records)
    scores = [score_policy(recs, p) for p in policies]
    base = scores[0] if scores else None

    rows = []
    for s in scores:
        uplift = None
        if base is not None:
            uplift = {
                "expectancy_r": round(s.expectancy_r - base.expectancy_r, 4),
                "giveback_rate": round(s.giveback_rate - base.giveback_rate, 1),
                "p25_r": round(s.p25_r - base.p25_r, 4),
            }
        rows.append({"score": s, "uplift_vs_baseline": uplift})

    return {
        "n": len(recs),
        "baseline": base.policy if base else None,
        "rows": rows,
    }


def compare_segments(
    records: List[PathRecord],
    policies: List[Policy],
    segment_key: Callable[[PathRecord], str],
    *,
    min_n: int = 1,
) -> Dict[str, Dict[str, Any]]:
    """Run compare_policies per segment (e.g. by regime/timeframe). Segments
    below min_n are still returned but flagged via their small n."""
    buckets: Dict[str, List[PathRecord]] = {}
    for r in records:
        if not is_reconstructable(r):
            continue
        buckets.setdefault(segment_key(r), []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for key, recs in buckets.items():
        out[key] = compare_policies(recs, policies, only_reconstructable=False)
    return {k: out[k] for k in sorted(out, key=lambda k: -out[k]["n"])}


def default_baseline() -> List[Policy]:
    """The baseline-only policy list (FixedCurrent). Step 5 appends alternatives."""
    return [FixedCurrent()]
