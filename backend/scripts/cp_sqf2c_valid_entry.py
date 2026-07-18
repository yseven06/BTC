"""CP-SQF-2C — Valid-entry / never-entered outcome forensic (READ-ONLY shadow).

Tests the feared hypothesis: are signals booked WIN/LOSS without the price ever
reaching the assumed entry (so the outcome isn't tradeable and distorts stats)?

Data source: the tracker already stores per-resolved-path entry telemetry at
SignalTradePath.extra["entry"] (entry_telemetry.py, "Reading A": entry_level =
entry-zone midpoint = the live tracker's fill reference). Fields:
  never_entered (bool), entry_reached (bool), data_available (bool),
  bars_to_entry (int), max_zone_penetration_pct (0..1).
This is a POST-birth observation of the OHLC the tracker fetched — it is the
DEFINITION of the entry segment, NOT a predictor of outcome (no leakage: outcome/
return are never used to classify entry, and no birth feature is derived from the
future). Coverage is partial (telemetry added forward) and reported explicitly.

Classes:
  valid_entered  : data_available & not never_entered   (price reached entry-mid)
  never_entered  : data_available & never_entered        (price never returned to mid)
  ambiguous_entry: telemetry missing OR data_available=false (undecidable)
  instant_invalid: born with SL < ~1 ATR away (birth geometry) — a separate flag

HARD CONTRACT (asserts in main): READ-ONLY (SELECT/WITH only; rollback; no commit);
NO leakage in the stop-proximity feature (birth-time only); deterministic; imports
only the read-only session factory.

Run:  cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/cp_sqf2c_valid_entry.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics as st
from collections import defaultdict

from sqlalchemy import text

from app.database import async_session_factory, engine as _engine

_engine.echo = False
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)


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
  (ss.extra->'birth')::text     AS birth,
  (tp.extra->'entry')::text     AS entry_tel,
  (tp.id IS NOT NULL)           AS has_tp,
  sp.outcome::text              AS outcome,
  sp.actual_return              AS actual_return,
  sp.hit_tp1 AS hit_tp1, sp.hit_tp2 AS hit_tp2, sp.hit_tp3 AS hit_tp3
FROM signals s
JOIN signal_performances sp ON sp.signal_id = s.id
LEFT JOIN signal_snapshots ss ON ss.signal_id = s.id
LEFT JOIN assets a ON a.id = s.asset_id
LEFT JOIN LATERAL (
  SELECT id, extra FROM signal_trade_path WHERE signal_id = s.id
  ORDER BY created_at DESC LIMIT 1
) tp ON TRUE
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
        et = {}
        if r.get("entry_tel"):
            try:
                et = json.loads(r["entry_tel"]) or {}
            except (TypeError, ValueError):
                et = {}
        sl_dist = _f(birth.get("sl_dist_pct"))
        atr = _f(birth.get("atr_pct"))
        sl_in_atr = (sl_dist / atr) if (sl_dist is not None and atr and atr > 0) else None

        has_tel = bool(et)
        data_avail = (et.get("data_available") is True)
        never = (et.get("never_entered") is True)
        reached = (et.get("entry_reached") is True)
        if has_tel and data_avail and never:
            cls = "never_entered"
        elif has_tel and data_avail and reached:
            cls = "valid_entered"
        else:
            cls = "ambiguous_entry"

        recs.append({
            "signal_id": r["signal_id"], "symbol": r.get("symbol") or "?",
            "direction": (r.get("direction") or "").lower(),
            "confidence": _f(r.get("confidence_score")),
            "composite": _f(r.get("composite_confidence")),
            "risk": _f(r.get("risk_score")),
            "week": iso_week(r["generated_at"]),
            "sl_in_atr": sl_in_atr, "sl_dist": sl_dist,
            "max_pen": _f(et.get("max_zone_penetration_pct")),
            "bars_to_entry": et.get("bars_to_entry"),
            "cls": cls,
            "instant_invalid": (sl_in_atr is not None and sl_in_atr < 1.0),
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
    nb = sum(1 for r in recs if r["outcome"] == "BREAKEVEN")
    pos = sum(x for x in rr if x > 0); neg = sum(x for x in rr if x < 0)
    return {
        "n": n,
        "stop": round(100.0 * nl / n, 1) if n else None,
        "win": round(100.0 * nw / n, 1) if n else None,
        "be": round(100.0 * nb / n, 1) if n else None,
        "tp1": round(100.0 * sum(1 for r in recs if r["tp1"]) / n, 1) if n else None,
        "avg": round(st.mean(rr), 3) if rr else None,
        "med": round(st.median(rr), 3) if rr else None,
        "pf": round(pos / abs(neg), 3) if neg < 0 else None,
    }


def fmt(e):
    return (f"n={e['n']:>4} stop={e['stop']}% win={e['win']}% be={e['be']}% "
            f"tp1={e['tp1']}% avgR={e['avg']} medR={e['med']} PF={e['pf']}")


def dist(recs, key):
    v = [r[key] for r in recs if r.get(key) is not None]
    return f"mean={round(st.mean(v),1)} med={round(st.median(v),1)}" if v else "n/a"


async def main():
    rows = await fetch_rows()
    recs = build(rows)
    ids = [r["signal_id"] for r in recs]
    assert len(ids) == len(set(ids)), "DUPLICATE signal_id"

    P = print
    P("=" * 80)
    P("CP-SQF-2C · VALID-ENTRY / NEVER-ENTERED FORENSIC (READ-ONLY, no behaviour change)")
    P("=" * 80)

    by_cls = defaultdict(list)
    for r in recs:
        by_cls[r["cls"]].append(r)

    # ---- A · coverage ----
    P(f"\n[A] COVERAGE / CLASSIFICATION")
    P(f"    closed signals            : {len(recs)}")
    for c in ("valid_entered", "never_entered", "ambiguous_entry"):
        g = by_cls.get(c, [])
        P(f"    {c:<16}: {len(g):>5}  ({round(100.0*len(g)/len(recs),1)}%)")
    measured = by_cls.get("valid_entered", []) + by_cls.get("never_entered", [])
    P(f"    -> entry-DECIDABLE subset : {len(measured)} ({round(100.0*len(measured)/len(recs),1)}%) "
      f"[the rest lack entry telemetry / post-birth bars]")
    P(f"    NOTE: entry telemetry is forward-only & partial; full-history backfill needs "
      f"OHLC re-fetch (price_data table empty) -> OUT OF SCOPE. never_entered rate is measured "
      f"on the decidable subset only.")

    # ---- B · never_entered x outcome (the crux) ----
    P(f"\n[B] NEVER-ENTERED x OUTCOME  (is entry-less LOSS being booked?)")
    for c in ("valid_entered", "never_entered"):
        g = by_cls.get(c, [])
        oc = defaultdict(int)
        for r in g:
            oc[r["outcome"]] += 1
        P(f"    {c:<16}: " + " ".join(f"{k}={v}" for k, v in sorted(oc.items(), key=lambda x: -x[1])))
    ne = by_cls.get("never_entered", [])
    ne_loss = sum(1 for r in ne if r["outcome"] == "LOSS")
    ne_win = sum(1 for r in ne if r["outcome"] == "WIN")
    P(f"    => entry-less LOSS booked : {ne_loss}  |  entry-less WIN (phantom) : {ne_win}")
    P(f"    (Reading A: SL sits BEYOND entry-mid, so a pullback that stops out MUST cross entry "
      f"first -> never_entered can essentially only be a run-away that books WIN.)")

    # ---- C · per-class performance ----
    P(f"\n[C] PER-CLASS PERFORMANCE")
    for c in ("valid_entered", "never_entered", "ambiguous_entry"):
        g = by_cls.get(c, [])
        if not g:
            continue
        nl = sum(1 for r in g if r["direction"] == "bullish")
        ns = sum(1 for r in g if r["direction"] == "bearish")
        P(f"    {c:<16}: {fmt(econ(g))}  L/S={nl}/{ns} conf({dist(g,'confidence')}) risk({dist(g,'risk')})")

    # ---- D · valid-entry FILTER shadow impact ----
    P(f"\n[D] VALID-ENTRY FILTER SHADOW IMPACT (does removing non-valid entries help?)")
    base = econ(recs)
    P(f"    baseline (all closed)          : {fmt(base)}")
    drop_never = [r for r in recs if r["cls"] != "never_entered"]
    P(f"    drop never_entered only        : {fmt(econ(drop_never))}  "
      f"[removes {len(recs)-len(drop_never)} phantom-wins]")
    valid_only = by_cls.get("valid_entered", [])
    P(f"    valid_entered ONLY (decidable) : {fmt(econ(valid_only))}  "
      f"[vs decidable-subset baseline below]")
    P(f"    decidable-subset baseline      : {fmt(econ(measured))}")
    P(f"    (if valid-only stop-rate >= baseline -> filter does NOT help; it strips wins, not losses)")

    # ---- E · phantom-win detail (entry-less TP) ----
    P(f"\n[E] PHANTOM WINS (never_entered -> booked WIN): tradeable at the assumed limit?")
    if ne_win:
        pw = [r for r in ne if r["outcome"] == "WIN"]
        by_sym = defaultdict(int)
        for r in pw:
            by_sym[r["symbol"]] += 1
        by_wk = defaultdict(int)
        for r in pw:
            by_wk[r["week"]] += 1
        pens = [r["max_pen"] for r in pw if r["max_pen"] is not None]
        P(f"    count={len(pw)}  avg_ret={round(st.mean([r['ret'] for r in pw if r['ret'] is not None]),3)}")
        P(f"    by symbol: {dict(sorted(by_sym.items(), key=lambda x:-x[1]))}")
        P(f"    by week  : {dict(sorted(by_wk.items()))}")
        P(f"    max_zone_penetration (0=only touched market edge,1=deep): "
          f"mean={round(st.mean(pens),3) if pens else None} "
          f"max={round(max(pens),3) if pens else None} (never reached midpoint=0.5 fill ref)")
        P(f"    => a LIMIT order at entry-mid would NOT fill -> these WINS are NON-tradeable at the")
        P(f"       assumed entry; they INFLATE win/PF stats (optimistic bias, not a loss problem).")

    # ---- F · stop-proximity at birth ----
    P(f"\n[F] STOP-PROXIMITY AT BIRTH (instant_invalid = SL < 1 ATR at generation)")
    withatr = [r for r in recs if r["sl_in_atr"] is not None]
    P(f"    signals with birth sl/atr known: {len(withatr)}")
    bands = [("1_<0.8", lambda x: x < 0.8), ("2_0.8-1.0", lambda x: 0.8 <= x < 1.0),
             ("3_1.0-1.2", lambda x: 1.0 <= x < 1.2), ("4_1.2-1.6", lambda x: 1.2 <= x < 1.6),
             ("5_>=1.6", lambda x: x >= 1.6)]
    for name, fn in bands:
        g = [r for r in withatr if fn(r["sl_in_atr"])]
        if not g:
            P(f"    {name:<10}: n=0")
            continue
        P(f"    {name:<10}: {fmt(econ(g))}")
    ii = sum(1 for r in recs if r["instant_invalid"])
    P(f"    => instant_invalid (SL<1 ATR at birth): {ii} ({round(100.0*ii/len(recs),1)}%)")

    P("\n" + "=" * 80)
    P("END CP-SQF-2C · read-only · no DB writes · no behaviour change")
    P("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
