"""CP-SQF-2A — Quality / Confidence Outcome Profiling (READ-ONLY shadow analysis).

Answers ONE question with the stored, birth-time telemetry only:
  "Does the current confidence / composite / probability score actually SEPARATE
   outcome — and if not, can a recalibrated birth-feature model do it out-of-sample?"

HARD CONTRACT (enforced by asserts in main):
  * READ-ONLY. Emits only SELECT/WITH statements; never INSERT/UPDATE/DELETE/DDL;
    never commits. A guard rejects any non-SELECT SQL before it is sent.
  * NO leakage. Predictors are a birth/snapshot-time WHITELIST; a blacklist assert
    guarantees no post-birth field (outcome/return/mfe/mae/gave_back/bars/hit_tp/
    realized/closed_at) ever enters the feature matrix.
  * NO behaviour change. Imports nothing from the live decision path (only the
    read-only async session factory). Changes no threshold/gate/scoring/publish.
  * Deterministic. No randomness anywhere (no shuffle, zero-init IRLS, fixed order)
    → re-running yields byte-identical numbers.
  * Walk-forward only for the model verdict: train weeks strictly precede test week.

Run:  cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/sqf2_score_profiling.py
No arguments. Prints a full report to stdout. Writes NOTHING to the DB or disk.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import statistics as st
import warnings
from collections import defaultdict

import numpy as np
from sqlalchemy import text

from app.database import async_session_factory, engine as _engine

# Read-only analysis: silence SQLAlchemy's SQL echo so stdout is a clean, byte-stable
# report. This toggles echo on THIS process's own engine instance only (the live
# uvicorn server is a separate process and is unaffected). No DB effect whatsoever.
_engine.echo = False
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

# ------------------------------------------------------------------ leakage sets
# Only these may ever be predictors (birth/snapshot-time, known at generation).
NUMERIC_PREDICTORS = [
    "confidence_score", "probability_score", "risk_score",
    "composite_confidence", "composite_probability",
    "atr_pct", "volatility_ratio", "volume_ratio", "fear_greed",
    "planned_rr_tp1", "planned_rr_tp3", "sl_dist_pct", "tp1_dist_pct",
    "entry_zone_width_pct",
    "engine_dir_agreement", "engine_score_std", "engine_bull_minus_bear",
    "engine_mean_conf",
]
CATEGORICAL_PREDICTORS = ["direction", "timeframe", "regime", "trend_direction", "risk_level"]

# Any predictor name containing one of these substrings is a leakage bug → abort.
LEAKAGE_SUBSTRINGS = [
    "outcome", "actual_return", "realized", "mfe", "mae", "gave_back",
    "bars_to", "bars_total", "hit_tp", "closed", "detail_label", "exit",
    "post_tp", "cur_", "sl_before", "resolved", "final_return", "captured",
]

# The model's compact, well-populated feature subset (kept small for IRLS stability).
MODEL_NUMERIC = [
    "confidence_score", "probability_score", "risk_score",
    "composite_confidence", "composite_probability",
    "atr_pct", "volatility_ratio", "volume_ratio", "fear_greed",
    "planned_rr_tp1", "sl_dist_pct", "entry_zone_width_pct",
    "engine_dir_agreement", "engine_score_std", "engine_mean_conf",
]
MODEL_CATEGORICAL = ["direction", "timeframe", "regime"]

WIN_THR = 0.5  # tracker's ±0.5 outcome thresholds (documented in fidelity.py)


# ------------------------------------------------------------------ read-only IO
def _assert_read_only(sql: str) -> None:
    head = sql.lstrip().lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise RuntimeError(f"NON-READ-ONLY SQL BLOCKED: {sql[:60]!r}")
    banned = (" insert ", " update ", " delete ", " drop ", " alter ",
              " create ", " truncate ", " grant ", " upsert ", "into ")
    low = f" {sql.lower()} "
    for b in banned:
        if b in low:
            raise RuntimeError(f"NON-READ-ONLY TOKEN {b!r} BLOCKED")


_SQL = """
SELECT
  s.id::text                              AS signal_id,
  a.symbol                                AS symbol,
  s.direction::text                       AS direction,
  s.timeframe::text                       AS timeframe,
  s.confidence_score                      AS confidence_score,
  s.probability_score                     AS probability_score,
  s.risk_score                            AS risk_score,
  s.risk_level::text                      AS risk_level,
  s.generated_at                          AS generated_at,
  ss.composite_confidence                 AS composite_confidence,
  ss.composite_probability                AS composite_probability,
  ss.regime                               AS regime,
  ss.atr_pct                              AS atr_pct,
  ss.volatility_ratio                     AS volatility_ratio,
  ss.volume_ratio                         AS volume_ratio,
  ss.trend_direction                      AS trend_direction,
  ss.fear_greed                           AS fear_greed,
  ss.engine_scores::text                  AS engine_scores,
  (ss.extra->'birth')::text               AS birth,
  sp.outcome::text                        AS outcome,
  sp.actual_return                        AS actual_return,
  sp.hit_tp1                              AS hit_tp1,
  sp.hit_tp2                              AS hit_tp2,
  sp.hit_tp3                              AS hit_tp3,
  sp.closed_at                            AS closed_at
FROM signals s
JOIN signal_performances sp ON sp.signal_id = s.id
LEFT JOIN signal_snapshots ss ON ss.signal_id = s.id
LEFT JOIN assets a ON a.id = s.asset_id
WHERE sp.outcome::text <> 'ACTIVE' AND sp.closed_at IS NOT NULL
ORDER BY s.generated_at, s.id
"""


async def fetch_rows():
    _assert_read_only(_SQL)
    async with async_session_factory() as db:
        res = await db.execute(text(_SQL))
        rows = [dict(r) for r in res.mappings().all()]
        await db.rollback()  # belt-and-suspenders: never leave a txn / never commit
    return rows


# ------------------------------------------------------------------ feature build
def _f(v):
    if v is None:
        return None
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def engine_features(engine_scores_json, direction):
    """Deterministic agreement features from the 9-engine {score,bias,confidence}.
    engine_dir_agreement = share of engines whose bias == signal direction.
    engine_bull_minus_bear = (n_bullish - n_bearish)/n.  engine_score_std = std of
    scores.  engine_mean_conf = mean of per-engine confidences. All birth-time."""
    out = {"engine_dir_agreement": None, "engine_score_std": None,
           "engine_bull_minus_bear": None, "engine_mean_conf": None}
    if not engine_scores_json:
        return out
    try:
        es = json.loads(engine_scores_json)
    except (TypeError, ValueError):
        return out
    if not isinstance(es, dict) or not es:
        return out
    scores, confs, biases = [], [], []
    for _, v in es.items():
        if not isinstance(v, dict):
            continue
        s = _f(v.get("score"))
        c = _f(v.get("confidence"))
        b = str(v.get("bias") or "").lower()
        if s is not None:
            scores.append(s)
        if c is not None:
            confs.append(c)
        if b:
            biases.append(b)
    n = len(biases)
    d = str(direction or "").lower()
    if n:
        out["engine_dir_agreement"] = round(sum(1 for b in biases if b == d) / n, 4)
        nb = sum(1 for b in biases if b == "bullish")
        ns = sum(1 for b in biases if b == "bearish")
        out["engine_bull_minus_bear"] = round((nb - ns) / n, 4)
    if len(scores) >= 2:
        out["engine_score_std"] = round(float(np.std(scores)), 4)
    if confs:
        out["engine_mean_conf"] = round(float(np.mean(confs)), 4)
    return out


def build_record(row):
    """Row -> flat record: whitelisted birth features + label fields (kept apart)."""
    rec = {"signal_id": row["signal_id"], "symbol": row.get("symbol"),
           "generated_at": row["generated_at"]}

    # --- base scores (100% populated on signals; composite_* on snapshot) ---
    for k in ("confidence_score", "probability_score", "risk_score",
              "composite_confidence", "composite_probability",
              "atr_pct", "volatility_ratio", "volume_ratio", "fear_greed"):
        rec[k] = _f(row.get(k))

    # --- categoricals ---
    for k in ("direction", "timeframe", "regime", "trend_direction", "risk_level"):
        v = row.get(k)
        rec[k] = str(v).lower() if v is not None else None

    # --- birth geometry (snapshot.extra->birth, ~76% coverage) ---
    birth = {}
    if row.get("birth"):
        try:
            birth = json.loads(row["birth"]) or {}
        except (TypeError, ValueError):
            birth = {}
    for k in ("planned_rr_tp1", "planned_rr_tp3", "sl_dist_pct",
              "tp1_dist_pct", "entry_zone_width_pct"):
        rec[k] = _f(birth.get(k))

    # --- engine agreement (birth-time) ---
    rec.update(engine_features(row.get("engine_scores"), rec["direction"]))

    # --- LABELS / outcomes (NEVER predictors) ---
    rec["_outcome"] = str(row.get("outcome") or "").upper()
    rec["_actual_return"] = _f(row.get("actual_return"))
    rec["_hit_tp1"] = bool(row.get("hit_tp1"))
    rec["_hit_tp2"] = bool(row.get("hit_tp2"))
    rec["_hit_tp3"] = bool(row.get("hit_tp3"))
    rec["_closed_at"] = row.get("closed_at")
    return rec


# ------------------------------------------------------------------ label mapping
# Primary binary universe = price-resolved outcomes; is_loss strictly = LOSS.
# INVALIDATED / EXPIRED are terminal but NOT stops -> excluded from the binary
# universe (reported separately), never auto-folded into loss.
BINARY_WIN = {"WIN"}
BINARY_ZERO = {"WIN", "BREAKEVEN"}          # not-loss side of the binary
BINARY_LOSS = {"LOSS"}
BINARY_UNIVERSE = {"WIN", "BREAKEVEN", "LOSS"}
NON_BINARY_TERMINAL = {"INVALIDATED", "EXPIRED"}


def label_mapping_table(recs):
    counts = defaultdict(int)
    for r in recs:
        counts[r["_outcome"]] += 1
    rows = []
    for oc in sorted(counts, key=lambda k: -counts[k]):
        if oc in BINARY_LOSS:
            binlab = "is_loss=1"
        elif oc in BINARY_ZERO:
            binlab = "is_loss=0"
        elif oc in NON_BINARY_TERMINAL:
            binlab = "EXCLUDED from binary (reported apart)"
        else:
            binlab = "UNKNOWN -> EXCLUDED (flagged)"
        rows.append((oc, counts[oc], binlab))
    return rows


# ------------------------------------------------------------------ metric maths
def roc_auc(y, s):
    """Rank-based AUC (Mann-Whitney). y in {0,1}, s = score (higher => more positive)."""
    y = np.asarray(y); s = np.asarray(s, dtype=float)
    pos = s[y == 1]; neg = s[y == 0]
    n1, n0 = len(pos), len(neg)
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    sv = s[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    sum_r_pos = ranks[y == 1].sum()
    auc = (sum_r_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    return round(float(auc), 4)


def pr_auc(y, s):
    """Average precision (area under precision-recall), higher score => positive."""
    y = np.asarray(y); s = np.asarray(s, dtype=float)
    if y.sum() == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1 - y)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / y.sum()
    ap = 0.0
    prev_r = 0.0
    for p, r in zip(precision, recall):
        ap += p * (r - prev_r)
        prev_r = r
    return round(float(ap), 4)


def brier(y, p):
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return None
    return round(float(np.mean((p - y) ** 2)), 4)


def calibration_table(y, p, bins=10):
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    out = []
    edges = np.linspace(0, 1, bins + 1)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if m.sum() == 0:
            continue
        out.append((round(lo, 2), round(hi, 2), int(m.sum()),
                    round(float(p[m].mean()), 4), round(float(y[m].mean()), 4)))
    return out


# ------------------------------------------------------------------ economics
def econ(recs):
    """Economic summary over a record list, using actual_return (stored % units)."""
    rr = [r["_actual_return"] for r in recs if r["_actual_return"] is not None]
    n = len(recs)
    n_ret = len(rr)
    n_loss = sum(1 for r in recs if r["_outcome"] == "LOSS")
    n_win = sum(1 for r in recs if r["_outcome"] == "WIN")
    n_be = sum(1 for r in recs if r["_outcome"] == "BREAKEVEN")
    n_tp1 = sum(1 for r in recs if r["_hit_tp1"])
    pos = sum(x for x in rr if x > 0)
    neg = sum(x for x in rr if x < 0)
    pf = round(pos / abs(neg), 3) if neg < 0 else None
    return {
        "n": n,
        "stop_rate": round(100.0 * n_loss / n, 1) if n else None,
        "win_rate": round(100.0 * n_win / n, 1) if n else None,
        "be_rate": round(100.0 * n_be / n, 1) if n else None,
        "tp1_rate": round(100.0 * n_tp1 / n, 1) if n else None,
        "avg_ret": round(st.mean(rr), 4) if rr else None,
        "med_ret": round(st.median(rr), 4) if rr else None,
        "pf": pf,
        "expectancy": round(st.mean(rr), 4) if rr else None,
        "n_ret": n_ret,
    }


def fmt_econ(e):
    return (f"n={e['n']:>4} stop={e['stop_rate']}% win={e['win_rate']}% "
            f"be={e['be_rate']}% tp1={e['tp1_rate']}% avgR={e['avg_ret']} "
            f"medR={e['med_ret']} PF={e['pf']} exp={e['expectancy']}")


# ------------------------------------------------------------------ logistic (IRLS)
def _standardize(X, mu=None, sd=None):
    # All-NaN columns (e.g. a birth feature absent in the earliest week) -> mu=0/sd=1
    # so the standardized column is a constant 0 (contributes nothing). errstate keeps
    # the reduction warning-free; the result is deterministic either way.
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN / DoF<=0 slices
        if mu is None:
            mu = np.nanmean(np.where(np.all(np.isnan(X), axis=0), 0.0, X), axis=0)
            mu = np.nan_to_num(mu, nan=0.0)
        if sd is None:
            sd = np.nanstd(X, axis=0)
            sd = np.nan_to_num(sd, nan=1.0)
            sd = np.where(sd < 1e-9, 1.0, sd)
        Xz = (X - mu) / sd
    Xz = np.nan_to_num(Xz, nan=0.0)  # impute standardized-missing -> mean (0)
    return Xz, mu, sd


def fit_logistic(X, y, l2=1.0, iters=30):
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        z = np.clip(Xb @ w, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        W = np.clip(p * (1 - p), 1e-6, None)
        reg = l2 * w.copy(); reg[0] = 0.0
        grad = Xb.T @ (p - y) + reg
        H = (Xb.T * W) @ Xb + l2 * np.eye(d + 1); H[0, 0] -= l2
        try:
            step = np.linalg.solve(H + 1e-8 * np.eye(d + 1), grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, grad, rcond=None)[0]
        w_new = w - step
        if np.max(np.abs(w_new - w)) < 1e-8:
            w = w_new; break
        w = w_new
    return w


def predict_logistic(w, X):
    Xb = np.hstack([np.ones((len(X), 1)), X])
    z = np.clip(Xb @ w, -30, 30)
    return 1.0 / (1.0 + np.exp(-z))


def build_matrix(recs, num_feats, cat_feats, cat_levels):
    """Design matrix from records. NaN kept for numerics (standardize imputes).
    Categoricals one-hot against provided levels (drops unseen)."""
    rows = []
    for r in recs:
        vec = [r.get(f) if r.get(f) is not None else np.nan for f in num_feats]
        for cf in cat_feats:
            val = r.get(cf)
            for lv in cat_levels[cf]:
                vec.append(1.0 if val == lv else 0.0)
        rows.append(vec)
    return np.asarray(rows, dtype=float)


def feature_names(num_feats, cat_feats, cat_levels):
    names = list(num_feats)
    for cf in cat_feats:
        names += [f"{cf}={lv}" for lv in cat_levels[cf]]
    return names


# ------------------------------------------------------------------ helpers
def iso_week(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def quantiles(vals):
    a = np.asarray(vals, dtype=float)
    return {q: round(float(np.quantile(a, q)), 3) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}


def score_profile(recs, key):
    vals = [r[key] for r in recs if r.get(key) is not None]
    binu = [r for r in recs if r["_outcome"] in BINARY_UNIVERSE]
    y = [1 if r["_outcome"] == "LOSS" else 0 for r in binu if r.get(key) is not None]
    s = [r[key] for r in binu if r.get(key) is not None]
    auc = roc_auc(y, s) if s else None
    prauc = pr_auc(y, s) if s else None
    cov = round(100.0 * len(vals) / len(recs), 1) if recs else 0.0
    return {
        "n": len(vals), "coverage": cov,
        "min": round(min(vals), 2) if vals else None,
        "max": round(max(vals), 2) if vals else None,
        "mean": round(st.mean(vals), 3) if vals else None,
        "median": round(st.median(vals), 3) if vals else None,
        "unique": len(set(round(v, 3) for v in vals)),
        "q": quantiles(vals) if vals else None,
        "auc_loss": auc, "prauc_loss": prauc, "n_binary": len(s),
    }


def decile_table(recs, key):
    binu = [r for r in recs if r["_outcome"] in BINARY_UNIVERSE and r.get(key) is not None]
    if len(binu) < 30:
        return None
    binu.sort(key=lambda r: r[key])
    vals = np.array([r[key] for r in binu])
    n = len(binu)
    out = []
    for d in range(10):
        lo = int(d * n / 10); hi = int((d + 1) * n / 10)
        chunk = binu[lo:hi]
        if not chunk:
            continue
        e = econ(chunk)
        out.append({
            "decile": d + 1, "lo": round(float(vals[lo]), 2),
            "hi": round(float(vals[min(hi, n) - 1]), 2), "n": e["n"],
            "vol_pct": round(100.0 * e["n"] / n, 1),
            "loss": e["stop_rate"], "tp1": e["tp1_rate"],
            "avg": e["avg_ret"], "med": e["med_ret"], "pf": e["pf"], "exp": e["expectancy"],
        })
    return out


def monotonic(decs, field, increasing):
    seq = [d[field] for d in decs if d[field] is not None]
    if len(seq) < 3:
        return None
    diffs = np.diff(seq)
    good = np.sum(diffs >= 0) if increasing else np.sum(diffs <= 0)
    return round(100.0 * good / len(diffs), 0)


# ------------------------------------------------------------------ MAIN
async def main():
    # ---- leakage guard (fail before any compute) ----
    all_pred = set(NUMERIC_PREDICTORS + CATEGORICAL_PREDICTORS
                   + MODEL_NUMERIC + MODEL_CATEGORICAL)
    for name in all_pred:
        for bad in LEAKAGE_SUBSTRINGS:
            assert bad not in name, f"LEAKAGE: predictor {name!r} matches {bad!r}"

    rows = await fetch_rows()
    recs = [build_record(r) for r in rows]

    # ---- integrity asserts ----
    ids = [r["signal_id"] for r in recs]
    assert len(ids) == len(set(ids)), "DUPLICATE signal_id in join"
    for r in recs:
        assert r["generated_at"] is not None, "null generated_at"

    P = print
    P("=" * 78)
    P("CP-SQF-2A · QUALITY/CONFIDENCE OUTCOME PROFILING (READ-ONLY, no behaviour change)")
    P("=" * 78)

    # ================= B · dataset / coverage =================
    binu = [r for r in recs if r["_outcome"] in BINARY_UNIVERSE]
    excl = [r for r in recs if r["_outcome"] in NON_BINARY_TERMINAL]
    unknown = [r for r in recs if r["_outcome"] not in (BINARY_UNIVERSE | NON_BINARY_TERMINAL)]
    P(f"\n[B] DATASET / COVERAGE")
    P(f"  closed signals joined : {len(recs)}")
    P(f"  binary universe (WIN/BE/LOSS) : {len(binu)}")
    P(f"  excluded terminal (INVALIDATED/EXPIRED) : {len(excl)}")
    P(f"  unknown outcome (excluded, flagged) : {len(unknown)}"
      + (f"  -> {sorted(set(r['_outcome'] for r in unknown))}" if unknown else ""))
    def cov(key):
        return round(100.0 * sum(1 for r in recs if r.get(key) is not None) / len(recs), 1)
    P(f"  coverage%%: confidence={cov('confidence_score')} composite_conf={cov('composite_confidence')} "
      f"fear_greed={cov('fear_greed')} regime={cov('regime')}")
    P(f"  coverage%%: planned_rr_tp1={cov('planned_rr_tp1')} sl_dist_pct={cov('sl_dist_pct')} "
      f"engine_dir_agreement={cov('engine_dir_agreement')}")
    P(f"  gen date range: {min(r['generated_at'] for r in recs).date()} .. "
      f"{max(r['generated_at'] for r in recs).date()}")

    # ================= C · label mapping =================
    P(f"\n[C] OUTCOME TAXONOMY -> BINARY LABEL (is_loss)")
    for oc, c, lab in label_mapping_table(recs):
        P(f"  {oc:<12} n={c:>4}  -> {lab}")
    base = econ(recs)
    baseb = econ(binu)
    P(f"  BASELINE (all closed) : {fmt_econ(base)}")
    P(f"  BASELINE (binary set) : {fmt_econ(baseb)}")

    # ================= D-F · per-score baseline profiles =================
    P(f"\n[D-F] PER-SCORE PROFILES  (auc_loss: higher score -> more LOSS; ~0.5 = no separation)")
    P(f"      NOTE score orientation: for confidence/composite a GOOD score would give "
      f"auc_loss<0.5 (high score -> fewer losses).")
    for key in ("confidence_score", "composite_confidence", "probability_score",
                "composite_probability", "risk_score"):
        pr = score_profile(recs, key)
        P(f"\n  == {key} ==")
        P(f"    n={pr['n']} cov={pr['coverage']}% unique={pr['unique']} "
          f"min={pr['min']} max={pr['max']} mean={pr['mean']} median={pr['median']}")
        P(f"    quantiles(10/25/50/75/90)={pr['q']}")
        P(f"    AUC(->loss)={pr['auc_loss']}  PR-AUC(->loss)={pr['prauc_loss']}  n_binary={pr['n_binary']}")
        decs = decile_table(recs, key)
        if decs:
            mono_loss = monotonic(decs, "loss", increasing=True)
            P(f"    decile table (asc score):  monotonic(loss-rate rises w/ score)={mono_loss}% of steps")
            P(f"      dec range          n   vol%  loss%  tp1%   avgR    medR   PF     exp")
            for d in decs:
                P(f"      {d['decile']:>2} [{d['lo']:>7},{d['hi']:>7}] {d['n']:>4} {d['vol_pct']:>5} "
                  f"{str(d['loss']):>5} {str(d['tp1']):>5} {str(d['avg']):>7} {str(d['med']):>7} "
                  f"{str(d['pf']):>5} {str(d['exp']):>6}")

    # confidence bands vs forensic
    P(f"\n  == confidence_score BANDS (forensic cross-check) ==")
    bands = [("<70", lambda v: v < 70), ("70-73", lambda v: 70 <= v < 73),
             ("73-76", lambda v: 73 <= v < 76), (">=76", lambda v: v >= 76)]
    for name, fn in bands:
        sub = [r for r in recs if r.get("confidence_score") is not None and fn(r["confidence_score"])]
        P(f"    {name:<6}: {fmt_econ(econ(sub))}")

    # ================= G · birth-feature recalibration model (walk-forward) =================
    P(f"\n[G/H] BIRTH-FEATURE MODEL — logistic (IRLS, numpy), WALK-FORWARD by ISO week")
    # cohort weeks by generated_at
    for r in recs:
        r["_week"] = iso_week(r["generated_at"])
    weeks = sorted(set(r["_week"] for r in recs))
    P(f"  weeks: {weeks}")
    # levels from full data (fixed, deterministic)
    cat_levels = {cf: sorted(set(r[cf] for r in recs if r.get(cf))) for cf in MODEL_CATEGORICAL}
    fnames = feature_names(MODEL_NUMERIC, MODEL_CATEGORICAL, cat_levels)
    # leakage assert on final model feature names
    for nm in fnames:
        base_nm = nm.split("=")[0]
        for bad in LEAKAGE_SUBSTRINGS:
            assert bad not in base_nm, f"LEAKAGE in model feature {nm!r}"
    P(f"  model features ({len(fnames)}): {MODEL_NUMERIC} + onehot{MODEL_CATEGORICAL}")

    def wk_binu(wk):
        return [r for r in recs if r["_week"] == wk and r["_outcome"] in BINARY_UNIVERSE]

    oos_pred = {}   # signal_id -> predicted loss prob (out-of-sample)
    MIN_TRAIN = 150
    for i in range(1, len(weeks)):
        train_weeks = weeks[:i]; test_week = weeks[i]
        train = [r for wk in train_weeks for r in wk_binu(wk)]
        test = wk_binu(test_week)
        if len(train) < MIN_TRAIN or len(test) < 20:
            P(f"  fold test={test_week}: SKIP (train={len(train)}, test={len(test)}; below min)")
            continue
        # time-leak assert: every train gen < every test gen
        tr_max = max(r["generated_at"] for r in train)
        te_min = min(r["generated_at"] for r in test)
        assert tr_max <= te_min or train_weeks[-1] < test_week, "TIME LEAK: train after test"
        Xtr = build_matrix(train, MODEL_NUMERIC, MODEL_CATEGORICAL, cat_levels)
        ytr = np.array([1.0 if r["_outcome"] == "LOSS" else 0.0 for r in train])
        Xte = build_matrix(test, MODEL_NUMERIC, MODEL_CATEGORICAL, cat_levels)
        yte = np.array([1.0 if r["_outcome"] == "LOSS" else 0.0 for r in test])
        Xtr_z, mu, sd = _standardize(Xtr)
        Xte_z, _, _ = _standardize(Xte, mu, sd)
        w = fit_logistic(Xtr_z, ytr, l2=1.0)
        p_te = predict_logistic(w, Xte_z)
        for r, p in zip(test, p_te):
            oos_pred[r["signal_id"]] = float(p)
        P(f"  fold train={train_weeks} (n={len(train)}) -> test={test_week} (n={len(test)}): "
          f"OOS AUC={roc_auc(yte, p_te)} PR-AUC={pr_auc(yte, p_te)} Brier={brier(yte, p_te)}")

    # pooled OOS
    pooled = [r for r in binu if r["signal_id"] in oos_pred]
    if pooled:
        yv = [1 if r["_outcome"] == "LOSS" else 0 for r in pooled]
        pv = [oos_pred[r["signal_id"]] for r in pooled]
        P(f"\n  POOLED OUT-OF-SAMPLE (model): n={len(pooled)} AUC={roc_auc(yv, pv)} "
          f"PR-AUC={pr_auc(yv, pv)} Brier={brier(yv, pv)}")
        # raw-confidence OOS baseline on the SAME pooled set (ranking, no fit needed)
        rc = [r["confidence_score"] for r in pooled]
        cc = [r["composite_confidence"] if r["composite_confidence"] is not None else np.nan for r in pooled]
        P(f"  POOLED (same set) raw confidence_score  AUC={roc_auc(yv, [-x for x in rc])} "
          f"(sign-flipped: higher conf should mean fewer losses)")
        if all(x == x for x in cc):
            P(f"  POOLED (same set) composite_confidence AUC={roc_auc(yv, [-x for x in cc])} (sign-flipped)")
        P(f"  CALIBRATION (model OOS, predicted loss-prob decile -> observed loss-rate):")
        for lo, hi, cnt, pm, ym in calibration_table(yv, pv):
            P(f"    [{lo:.1f},{hi:.1f}) n={cnt:>4} pred={pm} obs_loss={ym}")

    # ================= I · >=76 confound decomposition =================
    P(f"\n[I] >=76 CONFOUND DECOMPOSITION (is the top-band edge real or concentrated?)")
    hi76 = [r for r in recs if r.get("confidence_score") is not None and r["confidence_score"] >= 76]
    lo76 = [r for r in recs if r.get("confidence_score") is not None and r["confidence_score"] < 76]
    P(f"  overall  >=76: {fmt_econ(econ(hi76))}")
    P(f"  overall  <76 : {fmt_econ(econ(lo76))}")
    P(f"  -- stratified avg_ret (>=76 minus <76) within each segment; edge should persist if REAL --")
    def strat(dimfn, label):
        P(f"    by {label}:")
        keys = sorted(set(dimfn(r) for r in recs if dimfn(r) is not None))
        for k in keys:
            h = [r for r in hi76 if dimfn(r) == k]
            l = [r for r in lo76 if dimfn(r) == k]
            if len(h) < 15 or len(l) < 15:
                P(f"      {str(k):<16} n>=76={len(h):>3} n<76={len(l):>4}  (too few -> skip)")
                continue
            eh, el = econ(h), econ(l)
            P(f"      {str(k):<16} n>=76={len(h):>3} avgR={eh['avg_ret']:>7} stop={eh['stop_rate']}% "
              f"| n<76={len(l):>4} avgR={el['avg_ret']:>7} stop={el['stop_rate']}% "
              f"| dAvg={round((eh['avg_ret'] or 0)-(el['avg_ret'] or 0),3)}")
    strat(lambda r: r.get("direction"), "direction")
    strat(lambda r: r.get("regime"), "regime")
    strat(lambda r: r.get("_week"), "week")
    # concentration: where do >=76 signals live?
    P(f"  -- >=76 concentration (share of band) --")
    for label, dimfn in (("direction", lambda r: r.get("direction")),
                         ("week", lambda r: r.get("_week"))):
        dist = defaultdict(int)
        for r in hi76:
            dist[dimfn(r)] += 1
        tot = len(hi76)
        frag = ", ".join(f"{k}={round(100*v/tot)}%" for k, v in sorted(dist.items(), key=lambda x: -x[1]))
        P(f"    {label}: {frag}")

    # ================= J · shadow publish-bar simulation =================
    P(f"\n[J] SHADOW PUBLISH-BAR SIMULATION (offline; naive P&L-removal counterfactual)")
    P(f"  baseline (all closed)        : {fmt_econ(base)}  [retain 100%]")
    def variant(name, keep):
        sub = [r for r in recs if keep(r)]
        e = econ(sub)
        retain = round(100.0 * len(sub) / len(recs), 1)
        dpf = None if (e["pf"] is None or base["pf"] is None) else round(e["pf"] - base["pf"], 3)
        P(f"  {name:<28}: {fmt_econ(e)}  [retain {retain}%  dPF={dpf}]")
    variant("raw confidence>=65 (current)", lambda r: r.get("confidence_score") is not None and r["confidence_score"] >= 65)
    variant("raw confidence>=76", lambda r: r.get("confidence_score") is not None and r["confidence_score"] >= 76)
    variant("raw confidence>=78", lambda r: r.get("confidence_score") is not None and r["confidence_score"] >= 78)
    if recs and any(r.get("composite_confidence") is not None for r in recs):
        cc_all = [r["composite_confidence"] for r in recs if r.get("composite_confidence") is not None]
        q75 = float(np.quantile(cc_all, 0.75))
        variant(f"composite_conf top-quartile(>={round(q75,1)})",
                lambda r: r.get("composite_confidence") is not None and r["composite_confidence"] >= q75)
    # recalibrated model: keep lowest OOS loss-prob quartile (OOS only, no in-sample opt)
    if pooled:
        pv_sorted = sorted(oos_pred[r["signal_id"]] for r in pooled)
        thr_q = pv_sorted[int(0.25 * len(pv_sorted))]  # keep best 25% (lowest loss-prob)
        keepset = {r["signal_id"] for r in pooled if oos_pred[r["signal_id"]] <= thr_q}
        sub = [r for r in pooled if r["signal_id"] in keepset]
        e = econ(sub); ep = econ(pooled)
        P(f"  model OOS keep-best-25%%      : {fmt_econ(e)}  "
          f"[retain {round(100.0*len(sub)/len(pooled),1)}% of OOS pool; OOS-pool baseline PF={ep['pf']}]")

    # ================= K · segment sanity =================
    P(f"\n[K] SEGMENT SANITY (baseline stop-rate by segment; not a filter)")
    for label, dimfn, minn in (("direction", lambda r: r.get("direction"), 30),
                               ("timeframe", lambda r: r.get("timeframe"), 30),
                               ("regime", lambda r: r.get("regime"), 30)):
        P(f"  by {label}:")
        keys = sorted(set(dimfn(r) for r in recs if dimfn(r) is not None))
        for k in keys:
            sub = [r for r in recs if dimfn(r) == k]
            if len(sub) < minn:
                continue
            P(f"    {str(k):<16} {fmt_econ(econ(sub))}")

    P("\n" + "=" * 78)
    P("END CP-SQF-2A · read-only · no DB writes · no behaviour change")
    P("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
