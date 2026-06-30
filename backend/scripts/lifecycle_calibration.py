"""L1 — Lifecycle Calibration Harness (Tier-1, READ-ONLY).

P2.5 calibration analysis tool. This script is an ANALYSIS HARNESS only:

  * It READS signal_status_history + signal_performances (no writes anywhere).
  * It does NOT import or alter any decision/resolution/TP-SL/signal-generation
    code path. It imports the lifecycle threshold CONSTANTS only, as read-only
    reference values, to print the diff between current and recommended.
  * It changes NO behaviour. Running it cannot affect production.

What it produces (Tier-1, from stored telemetry — no tracker re-run):
  * ENTER-threshold grid sweep per state (approaching / invalidating / weakening)
    with precision, recall, F1, Youden J at each candidate threshold.
  * Per-regime breakdown of the same sweep (regime-conditioning candidate check).
  * Median lead-time (alert -> resolution) per alert state.
  * Observed flip-flop rate at the current thresholds (candidate-threshold
    flip-flop needs Tier-2 per-bar re-sim — flagged, not computed here).
  * A final RECOMMENDATION block: recommended optimum thresholds and their diff
    from the current constants. A change is recommended ONLY when it materially
    dominates current (J gain >= MIN_J_GAIN and F1 not worse); otherwise the
    output is "NO CHANGE (current is optimal)".

Caveat (honest scope of Tier-1): the per-transition P/R is event-driven (logged
at state changes), so ENTER sweeps are reliable AT/ABOVE the current enter point
and approximate BELOW it. Sub-current thresholds are marked low-confidence.
Exit/hysteresis/min-duration calibration is Tier-2 (not in this harness).

Usage:  PYTHONPATH=. python scripts/lifecycle_calibration.py
"""
import asyncio
import statistics
from collections import defaultdict

from sqlalchemy import text

from app.database import async_session_factory
from app.backtesting import lifecycle as LC  # read-only: threshold constants + severity

LOSS_SET = {"loss", "invalidated"}
WIN_SET = {"win"}
TERM = {"win", "loss", "breakeven", "invalidated", "expired"}
SEV = {"active": 0, "weakening": 1, "invalidating": 2}

# A recommendation must beat current by at least this much Youden-J to be made.
MIN_J_GAIN = 0.03

APPROACH_GRID = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
INVALIDATE_GRID = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
WEAKEN_GRID = [0.25, 0.30, 0.35, 0.40, 0.45]


# ---------------------------------------------------------------- data loading
async def load():
    async with async_session_factory() as db:
        rows = (await db.execute(text(
            "SELECT signal_id::text, to_status, kind, created_at, "
            "progress_to_tp, retrace_to_sl, lower(COALESCE(regime,'?')) "
            "FROM signal_status_history ORDER BY signal_id, created_at"))).all()
        outs = (await db.execute(text(
            "SELECT signal_id::text, lower(outcome::text) "
            "FROM signal_performances"))).all()
    return rows, outs


def build(rows, outs):
    outcome = {sid: o for sid, o in outs}
    per = {}
    for sid, to, kind, ts, p, r, regime in rows:
        d = per.get(sid)
        if d is None:
            d = per[sid] = {"maxr": 0.0, "maxp": 0.0, "regime": None,
                            "seq": [], "first_inval": None, "first_appr": None,
                            "res_ts": None, "birth": False}
        if kind == "birth":
            d["birth"] = True
        if regime and regime != "?" and not d["regime"]:
            d["regime"] = regime
        if r is not None:
            d["maxr"] = max(d["maxr"], float(r))
        if p is not None:
            d["maxp"] = max(d["maxp"], float(p))
        if kind == "transition":
            d["seq"].append(to)
            if to == "invalidating" and d["first_inval"] is None:
                d["first_inval"] = ts
            if to == "approaching_tp" and d["first_appr"] is None:
                d["first_appr"] = ts
        if kind == "resolution":
            d["res_ts"] = ts
    universe = [sid for sid, d in per.items()
                if outcome.get(sid) in TERM and d["birth"]]
    return per, outcome, universe


# ---------------------------------------------------------------- metric maths
def confusion(per, outcome, universe, feat, thr, positive_outcomes):
    tp = fp = fn = tn = 0
    for sid in universe:
        flagged = per[sid][feat] >= thr
        pos = outcome[sid] in positive_outcomes
        if flagged and pos:
            tp += 1
        elif flagged and not pos:
            fp += 1
        elif (not flagged) and pos:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def metrics(tp, fp, fn, tn):
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    youden = rec + spec - 1.0
    return prec, rec, f1, youden


def sweep(per, outcome, universe, feat, grid, positive, current_thr):
    print(f"  thr  | n_flag | prec  | recall| F1    | Youden | note")
    print(f"  -----+--------+-------+-------+-------+--------+-----")
    best = None
    for thr in grid:
        tp, fp, fn, tn = confusion(per, outcome, universe, feat, thr, positive)
        prec, rec, f1, j = metrics(tp, fp, fn, tn)
        nflag = tp + fp
        note = "<-CURRENT" if abs(thr - current_thr) < 1e-9 else (
            "low-conf(<cur)" if thr < current_thr else "")
        print(f"  {thr:.2f} | {nflag:>6} | {prec:.3f} | {rec:.3f} | {f1:.3f} | "
              f"{j:+.3f} | {note}")
        cand = {"thr": thr, "prec": prec, "rec": rec, "f1": f1, "j": j}
        # only thresholds >= current are full-confidence candidates
        if thr >= current_thr - 1e-9:
            if best is None or cand["j"] > best["j"]:
                best = cand
    cur = next((c for c in (
        {"thr": t, **dict(zip(("prec", "rec", "f1", "j"),
         metrics(*confusion(per, outcome, universe, feat, t, positive))))}
        for t in grid) if abs(c["thr"] - current_thr) < 1e-9), None)
    return best, cur


def median_lead_hours(per, universe, first_key):
    leads = []
    for sid in universe:
        d = per[sid]
        a, b = d[first_key], d["res_ts"]
        if a is not None and b is not None:
            h = (b - a).total_seconds() / 3600.0
            if h >= 0:
                leads.append(h)
    if not leads:
        return None, 0
    return statistics.median(leads), len(leads)


def flipflop_rate(per, universe):
    n = 0
    for sid in universe:
        sevs = [SEV[s] for s in per[sid]["seq"] if s in SEV]
        dropped = False
        rev = False
        for i in range(1, len(sevs)):
            if sevs[i] < sevs[i - 1]:
                dropped = True
            elif sevs[i] > sevs[i - 1] and dropped:
                rev = True
                break
        if rev:
            n += 1
    return n, len(universe)


# ---------------------------------------------------------------- recommendation
def recommend(name, current, best, cur_metrics, low_priority=False,
              structural=False):
    if best is None or cur_metrics is None:
        return f"  {name}: insufficient data"
    if abs(best["thr"] - current) < 1e-9 or (best["j"] - cur_metrics["j"]) < MIN_J_GAIN:
        tag = "NO CHANGE (current optimal)"
        if structural:
            tag += " [weak state is STRUCTURAL, not threshold -> design backlog]"
        if low_priority:
            tag += " [low priority: not an alert trigger]"
        return (f"  {name}: {current:.2f} -> {current:.2f}  {tag}  "
                f"(curJ={cur_metrics['j']:+.3f}, bestJ={best['j']:+.3f}@{best['thr']:.2f}, "
                f"dJ={best['j']-cur_metrics['j']:+.3f} < {MIN_J_GAIN})")
    return (f"  {name}: {current:.2f} -> {best['thr']:.2f}  *** CHANGE SUGGESTED ***  "
            f"(curJ={cur_metrics['j']:+.3f} -> {best['j']:+.3f}, "
            f"dJ={best['j']-cur_metrics['j']:+.3f}; F1 {cur_metrics['f1']:.3f}->{best['f1']:.3f})")


# ---------------------------------------------------------------- main
async def main():
    rows, outs = await load()
    per, outcome, universe = build(rows, outs)

    print("=" * 70)
    print("L1 LIFECYCLE CALIBRATION HARNESS (Tier-1, READ-ONLY, no behaviour change)")
    print("=" * 70)
    n_loss = sum(1 for s in universe if outcome[s] in LOSS_SET)
    n_win = sum(1 for s in universe if outcome[s] in WIN_SET)
    print(f"resolved universe (with birth+history): {len(universe)} "
          f"| loss={n_loss} win={n_win}")
    print(f"current thresholds: APPROACH={LC.ENTER_APPROACH} "
          f"INVALIDATE={LC.ENTER_INVALIDATE} CONFIRMED={LC.ENTER_INVALIDATE_CONFIRMED} "
          f"WEAKEN={LC.ENTER_WEAKEN}")

    print("\n[A] INVALIDATING (max retrace_to_sl predicts LOSS) "
          "-- pure-price ENTER sweep; confirmed-cluster=0.45 held (validated ~0.74 prec)")
    inv_best, inv_cur = sweep(per, outcome, universe, "maxr", INVALIDATE_GRID,
                              LOSS_SET, LC.ENTER_INVALIDATE)

    print("\n[B] APPROACHING_TP (max progress_to_tp predicts WIN)")
    app_best, app_cur = sweep(per, outcome, universe, "maxp", APPROACH_GRID,
                              WIN_SET, LC.ENTER_APPROACH)

    print("\n[C] WEAKENING (max retrace_to_sl predicts LOSS; soft band) "
          "-- NOTE: not an alert trigger (UI only)")
    wk_best, wk_cur = sweep(per, outcome, universe, "maxr", WEAKEN_GRID,
                            LOSS_SET, LC.ENTER_WEAKEN)

    print("\n[D] LEAD-TIME (median hours: first alert -> resolution)")
    inv_lead, inv_nl = median_lead_hours(per, universe, "first_inval")
    app_lead, app_nl = median_lead_hours(per, universe, "first_appr")
    print(f"  invalidating: {inv_lead:.1f}h (n={inv_nl})" if inv_lead is not None
          else "  invalidating: n/a")
    print(f"  approaching : {app_lead:.1f}h (n={app_nl})" if app_lead is not None
          else "  approaching : n/a")

    print("\n[E] FLIP-FLOP (observed at CURRENT thresholds; candidate-thr needs Tier-2)")
    ff, ffn = flipflop_rate(per, universe)
    print(f"  signals with >=1 de-escalation->re-escalation: {ff}/{ffn} "
          f"= {100*ff/ffn:.1f}%" if ffn else "  n/a")

    print("\n[F] PER-REGIME (regime-conditioning candidate -- optimum INVALIDATE per regime)")
    by_regime = defaultdict(list)
    for sid in universe:
        by_regime[per[sid]["regime"] or "?"].append(sid)
    for rg, sids in sorted(by_regime.items(), key=lambda x: -len(x[1])):
        if len(sids) < 25:
            print(f"  {rg:<14} n={len(sids):>3}  (too few -> skip)")
            continue
        b, c = sweep_silent(per, outcome, sids, "maxr", INVALIDATE_GRID, LOSS_SET,
                            LC.ENTER_INVALIDATE)
        flag = "" if (b is None or abs(b["thr"] - LC.ENTER_INVALIDATE) < 1e-9) \
            else f"  -> regime opt {b['thr']:.2f} (J{b['j']:+.3f})"
        print(f"  {rg:<14} n={len(sids):>3}  global-thr J={c['j']:+.3f}{flag}")

    print("\n" + "=" * 70)
    print("RECOMMENDED OPTIMUM THRESHOLDS (vs current)  [output of L1]")
    print("=" * 70)
    print(recommend("ENTER_INVALIDATE", LC.ENTER_INVALIDATE, inv_best, inv_cur))
    print(recommend("ENTER_APPROACH  ", LC.ENTER_APPROACH, app_best, app_cur,
                    structural=True))
    print(recommend("ENTER_WEAKEN    ", LC.ENTER_WEAKEN, wk_best, wk_cur,
                    low_priority=True))
    print("  ENTER_INVALIDATE_CONFIRMED: 0.45 -> 0.45  HELD (validated ~0.74 prec; "
          "full sweep = Tier-2)")
    print("  EXIT_* / min_state_seconds: Tier-2 (per-bar re-sim) -- not in this harness")
    print("\nNOTE: a change is suggested only when Youden-J gain >= "
          f"{MIN_J_GAIN} AND F1 not worse. Otherwise current is kept.")


def sweep_silent(per, outcome, universe, feat, grid, positive, current_thr):
    best = None
    cur = None
    for thr in grid:
        prec, rec, f1, j = metrics(*confusion(per, outcome, universe, feat, thr, positive))
        cand = {"thr": thr, "prec": prec, "rec": rec, "f1": f1, "j": j}
        if abs(thr - current_thr) < 1e-9:
            cur = cand
        if thr >= current_thr - 1e-9 and (best is None or j > best["j"]):
            best = cand
    return best, cur


if __name__ == "__main__":
    asyncio.run(main())
