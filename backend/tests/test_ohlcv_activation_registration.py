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
import asyncio
import inspect
import pathlib

import pytest
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
    # DISABLED AFTER CALIBRATION. The first genuine run (22:58:02Z, run_seq=1)
    # was cancelled at 148.196 s against a 150 s budget, and the frozen gate is
    # T <= 150/1.9 = 78.947 s — so the registration was removed in the same
    # session. The invariant this guard carries is unchanged and is what still
    # matters: there is NEVER more than one OHLCV registration. It now reads
    # ZERO, and it will read one again only when a checkpoint re-activates on
    # a re-derived budget/slot.
    assert ids.count(JOB_ID) == 0, (
        f"{JOB_ID} is registered again — re-activation must come with a "
        f"re-derived budget, not a silent restore: {ids}")
    assert len(ids) == len(set(ids)), f"duplicate job ids: {ids}"
    assert len(ids) == 7, f"expected the 7 trading jobs, found {len(ids)}: {ids}"


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
    # AST rather than a substring match: the invariant is that the import is a
    # real statement INSIDE this function, which a string compare only
    # approximates — it also breaks on formatting, e.g. importing a second name
    # alongside it. Parsing states the property directly and is strictly
    # stronger, since a mention in a comment or docstring cannot satisfy it.
    fn = ast.parse(inspect.getsource(sched._job_ohlcv_collect)).body[0]
    imported = {alias.name
                for node in ast.walk(fn) if isinstance(node, ast.ImportFrom)
                if node.module == "app.services.ohlcv_collector_job"
                for alias in node.names}
    assert "run_collection_once" in imported, (
        f"the collector is not imported lazily inside the job: {imported}")


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


def test_no_cron_slot_is_claimed_while_disabled():
    """Was `test_the_cron_is_the_ratified_slot`, pinning minute='28,58'.

    The measured first run makes that slot unusable as it stands: 148.196 s
    reached only 13 of 57 symbols, so the full universe extrapolates to ~675 s
    against the 175 s the :58 window allows before signals_1h. Re-asserting
    '28,58' would pin a slot the evidence has already refuted, so this guard now
    holds the weaker true statement — no OHLCV trigger is claimed at all — and
    the slot must be re-derived by whichever checkpoint re-activates."""
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
    assert found is None, f"an OHLCV cron trigger is registered while disabled: {found}"


def test_the_retained_budget_would_still_fit_the_windows_it_was_sized_for():
    """The JobSpec is deliberately RETAINED after the disable, so this arithmetic
    still has to hold for it — otherwise a future re-activation could restore a
    registration on top of a spec that no longer fits anything.

    Note what this does NOT say: that 150 s is sufficient. The measured run
    proves it is not — it is a truncation point, not a completion budget."""
    from app.services.job_guard import CLEANUP_GRACE_SECONDS as G
    end = JOB_SPECS[JOB_ID].budget_seconds + G
    assert 28 * 60 + end < 32 * 60, "the :28 window would reach signals_15m at :32"
    assert 58 * 60 + end < 61 * 60, "the :58 window would reach signals_1h at :01"


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


# ══ THE ADMIN MANUAL TRIGGER IS FAIL-CLOSED ════════════════════════════════
# `trigger_job_now` is reachable from POST /admin/system/jobs/{job_id}/trigger.
# It does NOT consult the APScheduler registry — it dispatches through a literal
# `job_map`, and it fires `asyncio.create_task`, which (as tracker.py records) is
# NOT covered by APScheduler's max_instances=1. So an OHLCV entry in that map
# would be a SECOND execution path: admin-triggerable, off-slot, and able to run
# concurrently with the cron run — two progression claims and two sweeps at once.
#
# The map excludes it today. Nothing asserted that, and the sibling guard
# `test_no_second_execution_path_for_ohlcv` cannot: it skips scheduler.py by
# design, because scheduler.py is where the ONE legitimate call lives.
def test_the_admin_run_now_map_does_not_expose_ohlcv():
    """Read the literal, not the behaviour, so a dispatch refactor is visible."""
    tree = ast.parse((BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8"))
    maps = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.AnnAssign)
            and getattr(n.target, "id", None) == "job_map"
            and isinstance(n.value, ast.Dict)]
    assert len(maps) == 1, f"expected exactly one job_map literal, found {len(maps)}"
    keys = {k.value for k in maps[0].keys if isinstance(k, ast.Constant)}
    assert JOB_ID not in keys, \
        f"{JOB_ID} is admin-triggerable — that is a second, unbudgeted execution path"
    # Pinned positively too: emptying the map would satisfy the line above while
    # silently breaking every operator button.
    assert keys == {"signals_1h", "signals_4h", "signals_15m", "signals_1d",
                    "perf_tracking", "price_alerts", "startup_check"}, keys


@pytest.mark.asyncio
# `trigger_job_now` builds its map by CALLING the seven job coroutines, so a
# refused dispatch leaves seven un-awaited coroutine objects. That is the
# function's own pre-existing shape, not something this test introduces, and it
# is inert — the warning is silenced here rather than left to litter the suite.
@pytest.mark.filterwarnings("ignore::RuntimeWarning")
async def test_an_admin_run_now_request_for_ohlcv_fails_closed():
    """Behavioural half: call the real dispatcher. It must refuse BEFORE it
    spawns anything, so no task exists and the route answers 404."""
    before = len(asyncio.all_tasks())
    started = await sched.trigger_job_now(JOB_ID)
    assert started is False, "the admin trigger accepted an OHLCV run"
    assert len(asyncio.all_tasks()) == before, "a task was spawned despite refusal"
    # The route turns that False into 404 rather than reporting a started job.
    admin_src = (BACKEND / "app/api/routes/admin.py").read_text(encoding="utf-8")
    assert "if not started:" in admin_src and "404" in admin_src


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


# â•â• CANONICAL K â€” PLANNED K AND EXECUTED K ARE THE SAME VALUE â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# R1's second root cause. The reviewed activation configuration was K=5; the
# code path would have executed K=4, because `_job_ohlcv_collect` called
# `run_collection_once(async_session_factory)` with no `symbols_per_run`, so the
# value fell through to `collect_once`'s signature default. The K cost matrix
# modelled one configuration and production ran another, and no test noticed,
# because every existing K assertion is about the CONSTANT rather than about
# what the registered job actually binds.
#
# WHY AN IMPLICIT DEFAULT IS NOT ENOUGH EVEN WHEN THE NUMBER IS RIGHT: a default
# is bound at def-time and is invisible at the call site, so the value that will
# run cannot be read where the run is configured. Explicit binding is what makes
# planned K and executed K the same reviewable fact.
K_SENTINEL = 97          # a value no configuration would ever choose


class _NullCollector:
    async def fetch_ohlcv(self, *a, **k):            # pragma: no cover
        raise AssertionError("no item may be attempted with an empty partition")

    async def close(self):
        return None


class _NullFactory:
    """Session factory whose reads return nothing, so `collect_once` reaches the
    partition call and then has no work left to do."""

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    async def execute(self, *a, **k):
        class _R:
            rowcount = 0

            def all(self_):
                return []

            def scalars(self_):
                class _S:
                    def all(x):
                        return []
                return _S()
        return _R()

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _k_passed_to_run_collection_once(default_override=None):
    """What `_job_ohlcv_collect` actually hands to `run_collection_once`.

    The job imports `run_collection_once` LAZILY inside its own body, so
    patching the module attribute is picked up at call time exactly as the real
    lookup would be.
    """
    import app.services.ohlcv_collector_job as J

    seen = {}

    async def spy(session_factory, **kwargs):
        seen.update(kwargs)
        return J.CollectionResult()

    real_run = J.run_collection_once
    real_default = J.collect_once.__kwdefaults__["symbols_per_run"]
    J.run_collection_once = spy
    if default_override is not None:
        J.collect_once.__kwdefaults__["symbols_per_run"] = default_override
    try:
        await sched._job_ohlcv_collect()
    finally:
        J.run_collection_once = real_run
        J.collect_once.__kwdefaults__["symbols_per_run"] = real_default
    return seen


@pytest.mark.asyncio
async def test_the_registered_job_binds_K_explicitly():
    """The call site must SAY the K it runs. Without the kwarg, K is whatever
    the default happens to be â€” which is exactly how a reviewed K=5 became a
    running K=4."""
    import app.services.ohlcv_collector_job as J

    seen = await _k_passed_to_run_collection_once()
    assert "symbols_per_run" in seen, (
        "the registered OHLCV job does not bind K explicitly â€” it inherits "
        "collect_once's default, so reviewed K and executed K can differ")
    assert seen["symbols_per_run"] == J.SYMBOLS_PER_RUN, (
        f"registered K {seen['symbols_per_run']} != canonical {J.SYMBOLS_PER_RUN}")


@pytest.mark.asyncio
async def test_repointing_the_signature_default_cannot_move_the_registered_K():
    """THE DISCRIMINATING TEST. It applies Python's own resolution rule instead
    of asserting a shape: if the job omits the kwarg, the effective K IS the
    signature default, so repointing that default moves production's K silently.

    `collect_once`'s parameters are keyword-only, so the default lives in
    `__kwdefaults__` and was bound at def-time â€” patching the module constant
    would NOT move it, which is why this patches the real binding.
    """
    import app.services.ohlcv_collector_job as J

    seen = await _k_passed_to_run_collection_once(default_override=K_SENTINEL)
    effective = seen.get("symbols_per_run", K_SENTINEL)
    assert effective != K_SENTINEL, (
        "the registered job resolves K through collect_once's default, so "
        "changing that default silently changes production's K")
    assert effective == J.SYMBOLS_PER_RUN


def test_there_is_exactly_one_canonical_K_literal_in_the_runtime():
    """No second magic number. K is declared once, as a literal int, in the
    collector module; every other consumer must reference the NAME."""
    import app.services.ohlcv_collector_job as J

    assigns = []
    for p in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", "") == "SYMBOLS_PER_RUN" for t in node.targets):
                assert isinstance(node.value, ast.Constant), \
                    f"K is computed rather than declared in {p.name}"
                assigns.append((p.name, node.value.value))
    assert assigns == [("ohlcv_collector_job.py", J.SYMBOLS_PER_RUN)], \
        f"K must be declared exactly once, in the collector module: {assigns}"


def test_the_scheduler_passes_the_canonical_NAME_not_a_repeated_literal():
    """A literal at the call site would be a second source of truth: it could
    drift from the constant and nothing would notice."""
    tree = ast.parse((BACKEND / "app/services/scheduler.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_job_ohlcv_collect")
    bound = [kw for call in ast.walk(fn) if isinstance(call, ast.Call)
             for kw in call.keywords if kw.arg == "symbols_per_run"]
    assert bound, "_job_ohlcv_collect binds no symbols_per_run"
    for kw in bound:
        assert isinstance(kw.value, ast.Name), (
            "K is written as a literal at the call site â€” that is a second "
            "canonical value that can drift from the constant")
        assert kw.value.id == "SYMBOLS_PER_RUN", kw.value.id


@pytest.mark.asyncio
async def test_observability_reports_the_same_K_the_run_was_given():
    """`symbols_partition_size` is what the witness line reports. If it could
    differ from the K used to claim the partition, a run's own telemetry would
    misreport the configuration under review."""
    import app.services.ohlcv_collector_job as J

    seen = {}

    async def fake_partition(session_factory, source, selected, k, run_seq):
        seen["k"] = k
        return []

    real = J.select_partition
    J.select_partition = fake_partition
    try:
        res = await J.collect_once(_NullFactory(), _NullCollector(),
                                   timeframes=["15m"],
                                   symbols_per_run=J.SYMBOLS_PER_RUN, run_seq=1)
    finally:
        J.select_partition = real

    assert seen["k"] == J.SYMBOLS_PER_RUN, "a different K reached the partition"
    assert res.symbols_partition_size == J.SYMBOLS_PER_RUN, \
        "the reported K is not the K that was used"


@pytest.mark.asyncio
async def test_an_explicit_caller_still_overrides_K():
    """Direct and internal callers passing their own K must keep working â€” the
    canonical value is the DEFAULT CONFIGURATION, not a hard ceiling."""
    import app.services.ohlcv_collector_job as J

    seen = {}

    async def fake_partition(session_factory, source, selected, k, run_seq):
        seen["k"] = k
        return []

    real = J.select_partition
    J.select_partition = fake_partition
    try:
        res = await J.collect_once(_NullFactory(), _NullCollector(),
                                   timeframes=["15m"], symbols_per_run=2,
                                   run_seq=1)
    finally:
        J.select_partition = real

    assert seen["k"] == 2 and res.symbols_partition_size == 2


def test_the_canonical_K_is_the_reviewed_activation_value():
    """K is now an ACTIVATION DECISION, not a code-shape default, so the value
    is pinned by name. Changing it is a deliberate edit that lands here."""
    import app.services.ohlcv_collector_job as J

    assert J.SYMBOLS_PER_RUN == 5, (
        "the reviewed activation configuration is K=5; changing it requires a "
        "re-derived cost matrix, not a silent constant edit")
