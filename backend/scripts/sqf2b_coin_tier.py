"""CP-SQF-2B — Coin / Symbol-tier outcome forensic (READ-ONLY shadow analysis).

Question: general scores don't separate outcome (CP-SQF-2A). Is there a per-COIN
edge — do some symbols persistently produce losses (an actionable blacklist), or is
the strong stop-rate dispersion just sample noise / a beta(volatility) confound?

Method rigor (the coin-identity overfit trap):
  * Per-coin stop-rate fit on the WHOLE history and judged on the WHOLE history is
    circular. The only actionable question is PERSISTENCE: rank coins as bad using
    EARLY weeks only, then measure the LATER book with vs without them (time-honest).
  * Rank-stability (Spearman) of per-coin stop-rate between the first and second
    half tells us whether coin-badness carries forward at all.
  * Beta/vol confound: if "bad coins" are just high-ATR coins, a blacklist only
    trims volatility exposure, not alpha.

HARD CONTRACT (asserts in main):
  * READ-ONLY. Only SELECT/WITH; never INSERT/UPDATE/DELETE/DDL; never commits;
    rollback after read. A guard rejects any non-SELECT statement.
  * NO leakage. The time-honest test defines "bad coin" from PAST weeks only and
    evaluates on strictly LATER weeks; outcome/return are labels, never predictors.
  * NO behaviour change. Imports only the read-only async session factory.
  * Deterministic. No randomness → re-running yields byte-identical output.

Run:  cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/sqf2b_coin_tier.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics as st
from collections import defaultdict

import numpy as np
from sqlalchemy import text

from app.database import async_session_factory, engine as _engine

_engine.echo = False
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

BINARY_UNIVERSE = {"WIN", "BREAKEVEN", "LOSS"}
LARGE_N, MED_N = 40, 20          # sample-size tiers
MIN_HALF_N = 10                  # min per-coin sample within a time-half to trust it
MIN_TRAIN_N = 15                 # min per-coin train sample to be eligible for blacklist


def _assert_read_only(sql: str) -> None:
    head = sql.lstrip().lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise RuntimeError(f"NON-READ-ONLY SQL BLOCKED: {sql[:60]!r}")
    low = f" {sql.lower()} "
    for b in (" insert ", " update ", " delete ", " drop ", " alter ",
              " create ", " truncate ", " grant ", " upsert ", "into "):
        if b in low:
            raise RuntimeError(f"NON-READ-ONLY TOKEN {b!r} BLOCKED")


_SQL = """
SELECT
  s.id::text                    AS signal_id,
  a.symbol                      AS symbol,
  s.direction::text             AS direction,
  s.timeframe::text             AS timeframe,
  s.confidence_score            AS confidence_score,
  s.risk_score                  AS risk_score,
  s.generated_at                AS generated_at,
  ss.composite_confidence       AS composite_confidence,
  ss.regime                     AS regime,
  ss.atr_pct                    AS atr_pct,
  (ss.extra->'birth')::text     AS birth,
  sp.outcome::text              AS outcome,
  sp.actual_return              AS actual_return,
  sp.hit_tp1 AS hit_tp1, sp.hit_tp2 AS hit_tp2, sp.hit_tp3 AS hit_tp3
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
        await db.rollback()
    return rows


def _f(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def iso_week(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def build(rows):
    recs = []
    for r in rows:
        birth = {}
        if r.get("birth"):
            try:
                birth = json.loads(r["birth"]) or {}
            except (TypeError, ValueError):
                birth = {}
        recs.append({
            "signal_id": r["signal_id"],
            "symbol": r.get("symbol") or "?",
            "direction": (r.get("direction") or "").lower(),
            "timeframe": (r.get("timeframe") or "").lower(),
            "regime": (r.get("regime") or None),
            "confidence": _f(r.get("confidence_score")),
            "composite": _f(r.get("composite_confidence")),
            "risk": _f(r.get("risk_score")),
            "atr_pct": _f(r.get("atr_pct")),
            "gen": r["generated_at"],
            "week": iso_week(r["generated_at"]),
            "planned_rr": _f(birth.get("planned_rr_tp1")),
            "sl_dist": _f(birth.get("sl_dist_pct")),
            "zone_w": _f(birth.get("entry_zone_width_pct")),
            # labels
            "outcome": (r.get("outcome") or "").upper(),
            "ret": _f(r.get("actual_return")),
            "tp1": bool(r.get("hit_tp1")), "tp2": bool(r.get("hit_tp2")), "tp3": bool(r.get("hit_tp3")),
        })
    return recs


def econ(recs):
    rr = [r["ret"] for r in recs if r["ret"] is not None]
    n = len(recs)
    nl = sum(1 for r in recs if r["outcome"] == "LOSS")
    nw = sum(1 for r in recs if r["outcome"] == "WIN")
    pos = sum(x for x in rr if x > 0)
    neg = sum(x for x in rr if x < 0)
    return {
        "n": n,
        "stop": round(100.0 * nl / n, 1) if n else None,
        "win": round(100.0 * nw / n, 1) if n else None,
        "tp1": round(100.0 * sum(1 for r in recs if r["tp1"]) / n, 1) if n else None,
        "tp2": round(100.0 * sum(1 for r in recs if r["tp2"]) / n, 1) if n else None,
        "tp3": round(100.0 * sum(1 for r in recs if r["tp3"]) / n, 1) if n else None,
        "avg": round(st.mean(rr), 3) if rr else None,
        "med": round(st.median(rr), 3) if rr else None,
        "pf": round(pos / abs(neg), 3) if neg < 0 else None,
    }


def pf_of(recs):
    rr = [r["ret"] for r in recs if r["ret"] is not None]
    pos = sum(x for x in rr if x > 0); neg = sum(x for x in rr if x < 0)
    return (pos / abs(neg)) if neg < 0 else None


def rank_avg(a):
    """Average ranks (1..n), ties get mean rank. Deterministic."""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sv = a[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = rank_avg(x), rank_avg(y)
    rx = rx - rx.mean(); ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return round(float((rx * ry).sum() / denom), 4) if denom > 0 else None


def dist(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return "n/a"
    return f"mean={round(st.mean(v),1)} med={round(st.median(v),1)}"


# ------------------------------------------------------------------ MAIN
async def main():
    rows = await fetch_rows()
    recs = build(rows)
    ids = [r["signal_id"] for r in recs]
    assert len(ids) == len(set(ids)), "DUPLICATE signal_id"

    P = print
    P("=" * 80)
    P("CP-SQF-2B · COIN/SYMBOL-TIER OUTCOME FORENSIC (READ-ONLY, no behaviour change)")
    P("=" * 80)

    by_coin = defaultdict(list)
    for r in recs:
        by_coin[r["symbol"]].append(r)
    weeks = sorted(set(r["week"] for r in recs))
    P(f"\n[A] UNIVERSE: closed={len(recs)}  coins={len(by_coin)}  weeks={weeks}")
    P(f"    BASELINE (all): {econ(recs)}")

    # ---------------- B · per-coin descriptive table (sorted worst->best) ----------------
    P(f"\n[B] PER-COIN TABLE (n>=10; sorted by stop-rate desc)  "
      f"[L/S=long/short counts · conf/comp/risk means · atr mean]")
    P(f"    {'symbol':<12} {'n':>4} {'stop%':>5} {'tp1%':>5} {'pf':>5} {'avg':>7} {'med':>7} "
      f"{'L':>3}/{'S':<3} {'conf':>5} {'comp':>5} {'risk':>4} {'atr%':>5}")
    coin_rows = []
    for sym, rs in by_coin.items():
        if len(rs) < 10:
            continue
        e = econ(rs)
        nl = sum(1 for r in rs if r["direction"] == "bullish")
        ns = sum(1 for r in rs if r["direction"] == "bearish")
        cf = [r["confidence"] for r in rs if r["confidence"] is not None]
        cp = [r["composite"] for r in rs if r["composite"] is not None]
        rk = [r["risk"] for r in rs if r["risk"] is not None]
        at = [r["atr_pct"] for r in rs if r["atr_pct"] is not None]
        coin_rows.append({
            "sym": sym, "n": e["n"], "stop": e["stop"], "tp1": e["tp1"], "pf": e["pf"],
            "avg": e["avg"], "med": e["med"], "L": nl, "S": ns,
            "conf": round(st.mean(cf), 1) if cf else None,
            "comp": round(st.mean(cp), 1) if cp else None,
            "risk": round(st.mean(rk), 1) if rk else None,
            "atr": round(st.mean(at), 2) if at else None,
        })
    coin_rows.sort(key=lambda x: (-(x["stop"] or 0), x["sym"]))
    for c in coin_rows:
        P(f"    {c['sym']:<12} {c['n']:>4} {str(c['stop']):>5} {str(c['tp1']):>5} {str(c['pf']):>5} "
          f"{str(c['avg']):>7} {str(c['med']):>7} {c['L']:>3}/{c['S']:<3} {str(c['conf']):>5} "
          f"{str(c['comp']):>5} {str(c['risk']):>4} {str(c['atr']):>5}")

    # ---------------- C · sample tiers + 4 categories ----------------
    P(f"\n[C] SAMPLE TIERS")
    large = [c for c in coin_rows if c["n"] >= LARGE_N]
    med = [c for c in coin_rows if MED_N <= c["n"] < LARGE_N]
    small = [c for c in coin_rows if c["n"] < MED_N]
    small_all = [sym for sym, rs in by_coin.items() if len(rs) < MED_N]
    P(f"    large (n>={LARGE_N}): {len(large)}  medium ({MED_N}-{LARGE_N-1}): {len(med)}  "
      f"small (<{MED_N}, shown n>=10): {len(small)}  (all coins <{MED_N}: {len(small_all)})")

    # Category rules (descriptive; persistence handled in [D]).
    harmful = [c for c in large if (c["stop"] or 0) >= 48 and (c["pf"] or 99) < 0.85]
    useful_lim = [c for c in coin_rows if (c["pf"] or 0) >= 1.15 and c["n"] < LARGE_N]
    neutral = [c for c in large if 0.88 <= (c["pf"] or 0) <= 1.12]
    P(f"\n[C1] clearly-harmful CANDIDATES (large n, stop>=48%, PF<0.85): "
      f"{[c['sym'] for c in harmful] or 'NONE'}")
    P(f"[C2] neutral/no-edge (large n, PF 0.88-1.12): {[c['sym'] for c in neutral] or 'NONE'}")
    P(f"[C3] potentially-useful but sample-limited (PF>=1.15, n<{LARGE_N}): "
      f"{[(c['sym'], c['n']) for c in useful_lim] or 'NONE'}")
    P(f"[C4] needs-more-data (n<{MED_N}): {len(small_all)} coins")

    # ---------------- D · PERSISTENCE: first half vs second half ----------------
    mid = weeks[len(weeks) // 2]
    P(f"\n[D] PERSISTENCE — split at week {mid}: early=weeks<{mid}, late=weeks>={mid}")

    def half(rs, late):
        return [r for r in rs if (r["week"] >= mid) == late]

    pairs = []  # (sym, early_stop, late_stop, early_pf, late_pf, n_e, n_l)
    for sym, rs in by_coin.items():
        e_rs, l_rs = half(rs, False), half(rs, True)
        if len(e_rs) >= MIN_HALF_N and len(l_rs) >= MIN_HALF_N:
            pairs.append((sym, econ(e_rs)["stop"], econ(l_rs)["stop"],
                          pf_of(e_rs), pf_of(l_rs), len(e_rs), len(l_rs)))
    P(f"    coins with >={MIN_HALF_N} in BOTH halves: {len(pairs)}")
    if len(pairs) >= 3:
        rho_stop = spearman([p[1] for p in pairs], [p[2] for p in pairs])
        e_pf = [p[3] for p in pairs if p[3] is not None and p[4] is not None]
        l_pf = [p[4] for p in pairs if p[3] is not None and p[4] is not None]
        rho_pf = spearman(e_pf, l_pf) if len(e_pf) >= 3 else None
        P(f"    Spearman rank-corr (early vs late) : stop-rate rho={rho_stop}  PF rho={rho_pf}")
        P(f"    (rho~0 => coin-badness does NOT persist = sample illusion; rho~1 => persists)")
        # flip flags
        flips = [p for p in pairs if (p[1] is not None and p[2] is not None
                 and ((p[1] >= 50) != (p[2] >= 50)))]
        P(f"    coins flipping across the 50% stop line early<->late: "
          f"{[(p[0], p[1], p[2]) for p in flips] or 'none'}")

    # ---------------- E · TIME-HONEST BLACKLIST OOS TEST ----------------
    P(f"\n[E] TIME-HONEST BLACKLIST OOS TEST (define bad coins on EARLY weeks, apply to LATE)")
    early = [r for r in recs if r["week"] < mid]
    late = [r for r in recs if r["week"] >= mid]
    P(f"    early n={len(early)}  late n={len(late)}   late baseline: {econ(late)}")
    early_by_coin = defaultdict(list)
    for r in early:
        early_by_coin[r["symbol"]].append(r)
    for T in (45.0, 50.0, 55.0):
        bad = {sym for sym, rs in early_by_coin.items()
               if len(rs) >= MIN_TRAIN_N and (econ(rs)["stop"] or 0) >= T}
        kept = [r for r in late if r["symbol"] not in bad]
        dropped = [r for r in late if r["symbol"] in bad]
        ek = econ(kept)
        retain = round(100.0 * len(kept) / len(late), 1) if late else 0.0
        base_pf = pf_of(late)
        dpf = None if (ek["pf"] is None or base_pf is None) else round(ek["pf"] - base_pf, 3)
        P(f"    bad = early stop>={T:.0f}% (n>={MIN_TRAIN_N}) -> {len(bad)} coins "
          f"{sorted(bad) if len(bad)<=12 else str(len(bad))+' coins'}")
        P(f"      LATE kept: n={ek['n']} stop={ek['stop']}% PF={ek['pf']} "
          f"[retain {retain}%  dPF vs late-baseline({base_pf and round(base_pf,3)})={dpf}] "
          f"| dropped n={len(dropped)} stop={econ(dropped)['stop'] if dropped else None}%")
    # also PF<1 definition
    badpf = {sym for sym, rs in early_by_coin.items()
             if len(rs) >= MIN_TRAIN_N and (pf_of(rs) is not None and pf_of(rs) < 0.9)}
    kept = [r for r in late if r["symbol"] not in badpf]
    ek = econ(kept); base_pf = pf_of(late)
    dpf = None if (ek["pf"] is None or base_pf is None) else round(ek["pf"] - base_pf, 3)
    P(f"    bad = early PF<0.9 (n>={MIN_TRAIN_N}) -> {len(badpf)} coins")
    P(f"      LATE kept: n={ek['n']} stop={ek['stop']}% PF={ek['pf']} "
      f"[retain {round(100.0*len(kept)/len(late),1)}%  dPF={dpf}]")

    # ---------------- F · BETA / VOL CONFOUND ----------------
    P(f"\n[F] BETA / VOLATILITY CONFOUND (is coin-badness just high ATR?)")
    cc = [c for c in coin_rows if c["atr"] is not None and c["stop"] is not None and c["n"] >= MED_N]
    if len(cc) >= 5:
        rho = spearman([c["atr"] for c in cc], [c["stop"] for c in cc])
        rho_pf = spearman([c["atr"] for c in cc], [c["pf"] or 0 for c in cc])
        P(f"    across {len(cc)} coins (n>={MED_N}): Spearman(atr_pct, stop-rate)={rho}  "
          f"Spearman(atr_pct, PF)={rho_pf}")
        P(f"    (+corr stop / -corr PF => 'bad coins' largely = high-volatility coins "
          f"=> tier ~ vol-exposure trim, not coin alpha)")
        hi = sorted(cc, key=lambda c: -(c["atr"] or 0))[:8]
        lo = sorted(cc, key=lambda c: (c["atr"] or 0))[:8]
        P(f"    highest-ATR coins: {[(c['sym'], c['atr'], c['stop']) for c in hi]}")
        P(f"    lowest-ATR coins : {[(c['sym'], c['atr'], c['stop']) for c in lo]}")

    P("\n" + "=" * 80)
    P("END CP-SQF-2B · read-only · no DB writes · no behaviour change")
    P("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
