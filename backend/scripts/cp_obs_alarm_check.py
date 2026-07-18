"""CP-OBS-ALARM-B — stateless read-only liveness checker (no behaviour change).

Makes the silent-stop risk proven in CP-OBS-HEARTBEAT VISIBLE: reads the freshness
of the telemetry the scheduler writes and emits OK / WARNING / CRITICAL + an exit
code, so an external runner (a human, or later an OS task in CP-OBS-ALARM-C) can
notice when the pipeline has silently stopped.

Design (see docs/CP-OBS-ALARM-plan.md):
  * Whole-system staleness = the FRESHEST of three streams (min staleness):
    signal_status_history.created_at · signals.generated_at · signal_snapshots.created_at.
    One fresh stream ⇒ OK. Only if ALL are stale does it alarm (kills the crypto-24/7
    single-stream-quiet false positive; a real outage silences all three at once).
  * Thresholds calibrated from HEARTBEAT: normal p99 gap ≈ 10 min; every real outage
    was ≥ 96 min ⇒ CRITICAL at 45 min catches all real outages with ~zero false alarms.
  * CP-OBS-ALARM-C dead-man's-switch: on OK ONLY, the checker GETs CP_OBS_ALARM_PING_URL
    (env). When pings STOP (app-down, machine-off, or the checker itself dying) the
    external cron-monitor alarms after its grace window — covering the machine-off/
    overnight failure mode HEARTBEAT proved that a local push could never catch.

HARD CONTRACT: READ-ONLY (SELECT only; rollback; never commit/INSERT/UPDATE/DELETE);
imports only the read-only session factory; touches NO scheduler/signal/model/gate
logic; adds NO OS task / cron / worker / new dependency / table. The ONLY outbound is
the optional dead-man's-switch GET to an env-configured URL (outbound-only, no inbound,
no open port, stdlib urllib); ping success/failure NEVER changes the liveness exit code.
Deterministic given (DB snapshot, now()): no randomness; the verdict is stable across
back-to-back runs — only the live staleness minutes + ping status vary with wall-clock/net.

Exit code: 0 = OK · 1 = WARNING · 2 = CRITICAL · 3 = check error (fail-loud).
Output: ONE parseable key=value line (+ a short human context line to stderr-free stdout).

Run:  cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/cp_obs_alarm_check.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import urllib.request
from urllib.parse import urlparse

from sqlalchemy import text

try:  # populate os.environ from backend/.env so PING_URL is readable (no override)
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.database import async_session_factory, engine as _engine

_engine.echo = False
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

# ---- config (thresholds, minutes) — calibrated from CP-OBS-HEARTBEAT ----
WARN_MIN = 20.0    # all streams stale > 20m  -> WARNING
CRIT_MIN = 45.0    # all streams stale > 45m  -> CRITICAL (real outages were >=96m)

# ---- CP-OBS-ALARM-C dead-man's-switch ping (env-only; no secret in code) ----
# Ping ONLY on OK. Not-OK / machine-off / checker-death => no ping => the external
# cron-monitor alarms after its grace window. The liveness exit code is NEVER changed
# by ping success/failure (a failed ping is itself a missed ping the monitor sees).
PING_URL = (os.environ.get("CP_OBS_ALARM_PING_URL", "") or "").strip() or None
PING_TIMEOUT_SEC = 5

OK, WARNING, CRITICAL, ERROR = "OK", "WARNING", "CRITICAL", "ERROR"
EXIT = {OK: 0, WARNING: 1, CRITICAL: 2, ERROR: 3}


def _assert_read_only(sql: str) -> None:
    head = sql.lstrip().lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise RuntimeError(f"NON-READ-ONLY SQL BLOCKED: {sql[:60]!r}")
    low = f" {sql.lower()} "
    for b in (" insert ", " update ", " delete ", " drop ", " alter ",
              " create ", " truncate ", " grant ", " upsert ", "into "):
        if b in low:
            raise RuntimeError(f"NON-READ-ONLY TOKEN {b!r} BLOCKED")


# staleness (minutes) of each stream's latest write vs the DB clock now()
Q_FRESH = """
SELECT
  extract(epoch FROM (now() - (SELECT max(created_at)   FROM signal_status_history)))/60.0 AS status_min,
  extract(epoch FROM (now() - (SELECT max(generated_at) FROM signals)))/60.0               AS gen_min,
  extract(epoch FROM (now() - (SELECT max(created_at)   FROM signal_snapshots)))/60.0       AS snap_min,
  (SELECT max(created_at)   FROM signal_status_history) AS status_max,
  (SELECT max(generated_at) FROM signals)               AS gen_max,
  (SELECT max(created_at)   FROM signal_snapshots)       AS snap_max
"""

# cheap overlap proxy: extra (duplicate) rows per one-per-signal table (single-flight guard)
Q_DUP = """
SELECT
  (SELECT count(*) - count(DISTINCT signal_id) FROM signal_trade_path)   AS dup_tradepath,
  (SELECT count(*) - count(DISTINCT signal_id) FROM signal_performances) AS dup_perf
"""


def verdict_for(stale_min: float) -> str:
    if stale_min > CRIT_MIN:
        return CRITICAL
    if stale_min > WARN_MIN:
        return WARNING
    return OK


def _mask_url(u: str) -> str:
    """Show scheme+host + a short path prefix; mask the secret tail. Never the full URL."""
    try:
        p = urlparse(u)
        if not p.netloc:
            return "***"
        shown = (p.path or "").lstrip("/")[:4]
        return f"{p.scheme}://{p.netloc}/{shown}***"
    except Exception:
        return "***"


def _send_ping(url: str) -> str:
    """Dead-man's-switch ping: stdlib GET, short timeout. Returns a status WORD.
    NEVER raises and NEVER changes the liveness verdict/exit-code — a failed ping is
    simply a missed ping that the external cron-monitor will alarm on."""
    try:
        req = urllib.request.Request(
            url, method="GET", headers={"User-Agent": "cp-obs-alarm/1"})
        with urllib.request.urlopen(req, timeout=PING_TIMEOUT_SEC) as resp:
            return f"sent(http{resp.getcode()})"
    except Exception as e:
        return f"failed({type(e).__name__})"


async def main() -> int:
    try:
        _assert_read_only(Q_FRESH)
        _assert_read_only(Q_DUP)
        async with async_session_factory() as db:
            f = (await db.execute(text(Q_FRESH))).mappings().one()
            d = (await db.execute(text(Q_DUP))).mappings().one()
            await db.rollback()
    except Exception as e:  # fail-loud: a broken checker must not read as "OK"
        print(f"verdict=ERROR reason={type(e).__name__}:{str(e)[:80]!r} ping=skipped_error")
        return EXIT[ERROR]

    streams = {
        "status_history": float(f["status_min"]) if f["status_min"] is not None else None,
        "generated": float(f["gen_min"]) if f["gen_min"] is not None else None,
        "snapshots": float(f["snap_min"]) if f["snap_min"] is not None else None,
    }
    present = [v for v in streams.values() if v is not None]
    if not present:
        print("verdict=ERROR reason='no telemetry timestamps' ping=skipped_error")
        return EXIT[ERROR]

    # whole-system staleness = freshest stream (one fresh stream => system alive)
    whole = min(present)
    v = verdict_for(whole)
    dup_tp = int(d["dup_tradepath"] or 0)
    dup_perf = int(d["dup_perf"] or 0)

    def r(x):
        return None if x is None else round(x, 1)

    # --- dead-man's-switch ping: ONLY on OK; never changes the liveness exit code ---
    if v != OK:
        ping_status = "skipped_not_ok"
    elif PING_URL is None:
        ping_status = "disabled_no_env"
    else:
        ping_status = _send_ping(PING_URL)

    # ONE parseable key=value line (primary contract)
    print(
        f"verdict={v} whole_stale_min={round(whole,1)} warn={WARN_MIN} crit={CRIT_MIN} "
        f"status_history_min={r(streams['status_history'])} "
        f"generated_min={r(streams['generated'])} snapshots_min={r(streams['snapshots'])} "
        f"dup_tradepath={dup_tp} dup_perf={dup_perf} ping={ping_status}"
    )
    # short human context (does not change the parse contract above)
    ping_ctx = (f"ping {ping_status} -> {_mask_url(PING_URL)}" if PING_URL
                else "ping disabled (no CP_OBS_ALARM_PING_URL in env; console-only)")
    print(
        f"# CP-OBS-ALARM liveness: system is {v} "
        f"(freshest telemetry {round(whole,1)}m old; OK<= {WARN_MIN}m, WARN> {WARN_MIN}m, CRIT> {CRIT_MIN}m). "
        f"{ping_ctx}. latest: status_history={str(f['status_max'])[:19]} generated={str(f['gen_max'])[:19]}",
        file=sys.stdout,
    )
    return EXIT[v]


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
