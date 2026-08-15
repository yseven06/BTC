"""CP-OHLCV-A3c ACTIVATION — exactly one OHLCV execution path, and its contract.

This is the checkpoint where OHLCV stops being dormant, so these guards pin the
things that would be expensive to discover in production: that there is ONE
registration and not two, that the JobSpec is the ratified one, that the job is
shadow-scoped so a research store can never mark the trading service unhealthy,
and that importing the app still performs no OHLCV work.

The budget is deliberately asserted as an INITIAL value. job_guard derives
budgets from an observed healthy maximum (1.9x), and this job has never run, so
150 s is legal but uncalibrated — `test_the_budget_is_flagged_as_uncalibrated`
exists so that fact cannot quietly disappear.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

from apscheduler.triggers.cron import CronTrigger

from app.services import scheduler as sched
from app.services.job_guard import JOB_SPECS

BACKEND = pathlib.Path(__file__).resolve().parent.parent
JOB_ID = "ohlcv_collect"


# ══ EXACTLY ONE REGISTRATION ═══════════════════════════════════════════════
def test_exactly_one_ohlcv_add_job_exists():
    """Two registrations would mean two concurrent runs and two progression
    claims per cadence. Counted from the AST, so a string in a comment or
    docstring cannot satisfy it."""
    tree = ast.parse((BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8"))
    ids = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "add_job":
            continue
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                ids.append(kw.value.value)
    assert ids.count(JOB_ID) == 1, f"expected one {JOB_ID} registration, found {ids}"
    assert len(ids) == len(set(ids)), f"duplicate job ids: {ids}"
    assert len(ids) == 8, f"expected 7 existing + 1 OHLCV, found {len(ids)}: {ids}"


def test_no_second_execution_path_for_ohlcv():
    """No route, startup hook or background task may call the collector. The
    subsystem's own modules are excluded; everything else must be clean."""
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        if p.name in ("ohlcv_collector_job.py", "ohlcv_writer.py",
                      "ohlcv_progression.py", "scheduler.py"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if any(k in text for k in ("run_collection_once", "collect_once",
                                   "acquire_run_sequence", "collect_and_persist")):
            hits.append(str(p.relative_to(BACKEND)))
    assert hits == [], f"a second OHLCV execution path exists: {hits}"


def test_the_collector_is_imported_lazily_inside_the_job():
    """A module-level import would drag the collector into every process that
    imports the scheduler, and the dormancy guards assert that importing
    app.main performs no OHLCV work."""
    src = (BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8")
    module_level = [ln for ln in src.splitlines()
                    if ln.startswith("from app.services.ohlcv")
                    or ln.startswith("import app.services.ohlcv")]
    assert module_level == [], f"module-level OHLCV import: {module_level}"
    body = inspect.getsource(sched._job_ohlcv_collect)
    assert "from app.services.ohlcv_collector_job import run_collection_once" in body


def test_the_job_runs_through_run_tracked():
    """Outside _run_tracked there is no deadline, and an unbounded run is the
    exact failure job_guard exists to prevent."""
    body = inspect.getsource(sched._job_ohlcv_collect)
    assert "_run_tracked" in body
    assert f'"{JOB_ID}"' in body


# ══ THE RATIFIED SPEC ══════════════════════════════════════════════════════
def test_the_jobspec_is_exactly_the_ratified_contract():
    spec = JOB_SPECS[JOB_ID]
    assert spec.budget_seconds == 150.0
    assert spec.cadence_seconds == 1800.0
    assert spec.critical is False
    assert spec.shadow is True


def test_the_cron_is_the_ratified_slot():
    """minute='28,58' — both windows sit inside measured-free gaps between the
    signals sweeps. Any other minute reopens the slot analysis."""
    src = (BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", None) != "add_job":
            continue
        if not any(kw.arg == "id" and getattr(kw.value, "value", None) == JOB_ID
                   for kw in node.keywords):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "CronTrigger":
                found = {kw.arg: kw.value.value for kw in arg.keywords
                         if isinstance(kw.value, ast.Constant)}
    assert found == {"minute": "28,58"}, f"cron is not the ratified slot: {found}"


def test_the_slot_fits_between_the_signals_windows():
    """Arithmetic, not assertion-by-comment: budget + CLEANUP_GRACE must land
    before the next signals start in BOTH windows."""
    from app.services.job_guard import CLEANUP_GRACE_SECONDS as G
    end = JOB_SPECS[JOB_ID].budget_seconds + G
    assert 28 * 60 + end < 32 * 60, "the :28 run reaches signals_15m at :32"
    assert 58 * 60 + end < 61 * 60, "the :58 run reaches signals_1h at :01"


def test_the_budget_is_flagged_as_uncalibrated():
    """job_guard derives budgets from an observed healthy maximum (>=1.9x). This
    job has never run, so 150 s is legal but NOT calibrated, and the code must
    say so — otherwise the obligation to re-derive silently disappears."""
    spec_src = (BACKEND / "app/services/job_guard.py").read_text(encoding="utf-8")
    window = spec_src.split(f'"{JOB_ID}"')[0][-600:]
    assert "INITIAL" in window, "the uncalibrated status of 150 s is not recorded"
    assert JOB_SPECS[JOB_ID].budget_seconds < JOB_SPECS[JOB_ID].cadence_seconds


def test_the_label_exists_for_operators():
    assert sched._JOB_LABELS[JOB_ID]
    assert JOB_ID in sched.get_job_status()


# ══ SHADOW SCOPING ═════════════════════════════════════════════════════════
def test_the_job_is_shadow_and_cannot_degrade_the_trading_surface():
    """Collection health must never mark the trading service unhealthy. The
    shadow flag is what keeps it out of the global aggregate."""
    assert JOB_SPECS[JOB_ID].shadow is True
    assert JOB_SPECS[JOB_ID].critical is False
    for other, spec in JOB_SPECS.items():
        if other != JOB_ID:
            assert spec.shadow is False, f"{other} unexpectedly became shadow"


def test_the_seven_existing_specs_are_untouched():
    expected = {
        "signals_15m": (600.0, 900.0, True), "signals_1h": (900.0, 3600.0, True),
        "signals_4h": (900.0, 14400.0, False), "signals_1d": (900.0, 86400.0, False),
        "perf_tracking": (90.0, 120.0, True), "price_alerts": (30.0, 60.0, True),
        "startup_check": (900.0, None, False),
    }
    for job_id, (b, c, crit) in expected.items():
        spec = JOB_SPECS[job_id]
        assert (spec.budget_seconds, spec.cadence_seconds, spec.critical) == (b, c, crit), \
            f"{job_id} changed"
    assert set(JOB_SPECS) == set(expected) | {JOB_ID}
