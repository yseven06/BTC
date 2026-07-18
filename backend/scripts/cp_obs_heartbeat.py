"""CP-OBS-HEARTBEAT — scheduler / telemetry reliability diagnostic (READ-ONLY).

The forward strategy after CP-SQF is DATA ACCUMULATION (F1-a reopen needs weeks of
reliable ~100 resolutions/day). This script asks ONE question with the stored
telemetry only: is that accumulation actually flowing reliably, or are there
missed scheduler fires / telemetry gaps / silent stalls?

No dedicated cron-run log exists, so scheduler liveness is INFERRED from the
density and regularity of the telemetry the scheduler writes every pass. Crypto is
24/7, so there are NO market-hours gaps — any large silence is a downtime candidate.
Primary heartbeat proxy = signal_status_history (the tracker writes transitions/
resolutions almost every */2-min pass; ~1.5 events/min).

HARD CONTRACT: READ-ONLY (SELECT/WITH only; rollback; never commit); imports only
the read-only session factory; changes NO scheduler/behaviour; adds no cron/worker/
supervisor. Deterministic — the analysis is data-anchored and byte-identical across
runs; the SINGLE line tagged "[LIVE PROBE]" uses now() as a liveness read and varies
by design.

Run:  cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/cp_obs_heartbeat.py
"""
from __future__ import annotations

import asyncio
import logging

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


# --- live probe (the ONE non-deterministic line: staleness vs wall clock now()) ---
Q_FRESH = """
SELECT s.stream, s.tmax, round(extract(epoch FROM (now()-s.tmax))/60.0,1) AS stale_min
FROM (
  SELECT 'signals.generated_at' stream, max(generated_at) tmax FROM signals
  UNION ALL SELECT 'snapshots.created_at', max(created_at) FROM signal_snapshots
  UNION ALL SELECT 'status_history.created_at', max(created_at) FROM signal_status_history
  UNION ALL SELECT 'performances.closed_at', max(closed_at) FROM signal_performances
) s ORDER BY s.stream
"""

# --- deterministic: per-day density of the three cadence streams ---
Q_DAILY = """
WITH g AS (SELECT date_trunc('day',generated_at)::date d, count(*) n FROM signals GROUP BY 1),
     r AS (SELECT date_trunc('day',closed_at)::date d, count(*) n FROM signal_performances
           WHERE closed_at IS NOT NULL GROUP BY 1),
     s AS (SELECT date_trunc('day',created_at)::date d, count(*) n FROM signal_status_history GROUP BY 1),
     days AS (SELECT d FROM g UNION SELECT d FROM r UNION SELECT d FROM s)
SELECT days.d,
       coalesce(g.n,0) gen, coalesce(r.n,0) resolved, coalesce(s.n,0) status_ev
FROM days LEFT JOIN g ON g.d=days.d LEFT JOIN r ON r.d=days.d LEFT JOIN s ON s.d=days.d
ORDER BY days.d
"""

# --- deterministic: gap distribution in the heartbeat stream (status_history) ---
Q_GAP_STATS = """
WITH t AS (SELECT extract(epoch FROM (created_at - lag(created_at) OVER (ORDER BY created_at)))/60.0 g
           FROM signal_status_history)
SELECT count(*) FILTER (WHERE g IS NOT NULL) n_int,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY g)::numeric,3) med,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY g)::numeric,3) p90,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY g)::numeric,3) p99,
       round(max(g)::numeric,1) maxg,
       count(*) FILTER (WHERE g>15) gt15, count(*) FILTER (WHERE g>30) gt30,
       count(*) FILTER (WHERE g>60) gt60
FROM t
"""

# --- deterministic: every heartbeat gap > 15 min, chronological ---
Q_GAP_LIST = """
WITH t AS (SELECT created_at, lag(created_at) OVER (ORDER BY created_at) prev
           FROM signal_status_history)
SELECT to_char(prev,'YYYY-MM-DD HH24:MI') gstart, to_char(created_at,'YYYY-MM-DD HH24:MI') gend,
       round(extract(epoch FROM (created_at-prev))/60.0,1) gap_min
FROM t WHERE prev IS NOT NULL AND (created_at-prev) > interval '15 minutes'
ORDER BY created_at
"""

# --- deterministic: UNIFIED timeline gaps (whole-system silence across all streams) ---
Q_GAP_UNIFIED = """
WITH ev AS (
  SELECT generated_at ts FROM signals
  UNION ALL SELECT created_at FROM signal_snapshots
  UNION ALL SELECT created_at FROM signal_status_history
  UNION ALL SELECT closed_at FROM signal_performances WHERE closed_at IS NOT NULL
),
t AS (SELECT ts, lag(ts) OVER (ORDER BY ts) prev FROM ev)
SELECT to_char(prev,'YYYY-MM-DD HH24:MI') gstart, to_char(ts,'YYYY-MM-DD HH24:MI') gend,
       round(extract(epoch FROM (ts-prev))/60.0,1) gap_min
FROM t WHERE prev IS NOT NULL AND (ts-prev) > interval '20 minutes'
ORDER BY ts
"""

# --- deterministic: duplicate / overlap checks ---
Q_DUPES = """
SELECT
 (SELECT count(*) FROM (SELECT signal_id FROM signal_trade_path GROUP BY 1 HAVING count(*)>1) x) dup_tradepath,
 (SELECT count(*) FROM (SELECT signal_id,kind,created_at FROM signal_status_history
    GROUP BY 1,2,3 HAVING count(*)>1) y) dup_status_rows,
 (SELECT count(*) FROM (SELECT signal_id FROM signal_performances GROUP BY 1 HAVING count(*)>1) z) dup_perf
"""

# --- deterministic: 2-min-slot missed-fire proxy over the observation window ---
Q_SLOTS = """
WITH bounds AS (SELECT min(created_at) lo, max(created_at) hi FROM signal_status_history),
     slots AS (SELECT count(*) total FROM generate_series(
                 (SELECT date_trunc('minute',lo) FROM bounds),
                 (SELECT date_trunc('minute',hi) FROM bounds),
                 interval '2 minutes')),
     active AS (SELECT count(DISTINCT to_timestamp(floor(extract(epoch FROM created_at)/120)*120)) filled
                FROM signal_status_history)
SELECT (SELECT total FROM slots) total_slots, (SELECT filled FROM active) filled_slots
"""


async def run(db, sql):
    _assert_read_only(sql)
    return (await db.execute(text(sql))).mappings().all()


async def main():
    P = print
    async with async_session_factory() as db:
        fresh = await run(db, Q_FRESH)
        daily = await run(db, Q_DAILY)
        gstats = (await run(db, Q_GAP_STATS))[0]
        glist = await run(db, Q_GAP_LIST)
        guni = await run(db, Q_GAP_UNIFIED)
        dupes = (await run(db, Q_DUPES))[0]
        slots = (await run(db, Q_SLOTS))[0]
        await db.rollback()

    P("=" * 82)
    P("CP-OBS-HEARTBEAT · SCHEDULER/TELEMETRY RELIABILITY DIAGNOSTIC (READ-ONLY)")
    P("=" * 82)

    # A — live freshness (the only non-deterministic block)
    P("\n[A] LIVE FRESHNESS  [LIVE PROBE — uses now(), varies per run by design]")
    for r in fresh:
        P(f"    {r['stream']:<28} last={str(r['tmax'])[:19]}  stale={r['stale_min']} min")

    # B — daily density
    P("\n[B] DAILY DENSITY (deterministic)  gen / resolved / status-events per day")
    gens = [r["gen"] for r in daily if r["gen"] > 0]
    res = [r["resolved"] for r in daily if r["resolved"] > 0]
    for r in daily:
        P(f"    {str(r['d'])}  gen={r['gen']:>4}  resolved={r['resolved']:>4}  status={r['status_ev']:>5}")
    if gens:
        import statistics as st
        full_gen = [r["gen"] for r in daily[1:-1]]  # exclude partial first/last day
        P(f"    -> full-day gen: min={min(full_gen) if full_gen else None} "
          f"max={max(full_gen) if full_gen else None} "
          f"mean={round(st.mean(full_gen),1) if full_gen else None} "
          f"(partial first/last day excluded)")

    # C — heartbeat gap distribution + list
    P("\n[C] HEARTBEAT GAP ANALYSIS — signal_status_history (deterministic)")
    P(f"    intervals={gstats['n_int']}  median={gstats['med']}m  p90={gstats['p90']}m  "
      f"p99={gstats['p99']}m  MAX={gstats['maxg']}m")
    P(f"    gaps >15m: {gstats['gt15']}   >30m: {gstats['gt30']}   >60m: {gstats['gt60']}")
    P(f"    -- all heartbeat gaps > 15 min (chronological) --")
    if not glist:
        P(f"       (none)")
    for r in glist:
        P(f"       {r['gstart']} -> {r['gend']}   gap={r['gap_min']} min")

    # D — unified whole-system silence
    P("\n[D] UNIFIED-TIMELINE SILENCE (all streams; gap>20m = whole-system quiet/down)")
    if not guni:
        P(f"    (no unified gap > 20 min — system never went fully silent >20m)")
    for r in guni:
        P(f"    {r['gstart']} -> {r['gend']}   silence={r['gap_min']} min")

    # E — 2-min slot fill (missed-fire proxy)
    total_slots = slots["total_slots"] or 0
    filled = slots["filled_slots"] or 0
    empty = total_slots - filled
    P("\n[E] 2-MIN SLOT COVERAGE (missed-fire proxy over full window, deterministic)")
    P(f"    total 2-min slots={total_slots}  slots-with-status-activity={filled}  "
      f"empty={empty} ({round(100.0*empty/total_slots,1) if total_slots else 0}%)")
    P(f"    NOTE: an empty 2-min slot = no status CHANGE that pass (quiet), not proof of a "
      f"missed fire; only long CONSECUTIVE runs (see [C]/[D] max gap) indicate real downtime.")

    # F — duplicate / overlap
    P("\n[F] DUPLICATE / OVERLAP CHECKS (deterministic)")
    P(f"    signals with >1 trade_path row : {dupes['dup_tradepath']}  (single-flight/UNIQUE guard)")
    P(f"    duplicate status rows (sig,kind,ts) : {dupes['dup_status_rows']}")
    P(f"    signals with >1 performance row : {dupes['dup_perf']}")

    P("\n" + "=" * 82)
    P("END CP-OBS-HEARTBEAT · read-only · no DB writes · no scheduler/behaviour change")
    P("=" * 82)


if __name__ == "__main__":
    asyncio.run(main())
