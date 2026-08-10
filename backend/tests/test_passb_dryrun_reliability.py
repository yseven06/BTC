"""CP-PASS-B-DRYRUN-RELIABILITY — a Pass B dry-run must terminate and be measurable.

WHAT WENT WRONG, AND WHY THE OBVIOUS FIX WOULD HAVE MISSED IT
-------------------------------------------------------------
A default dry-run sat for 59 minutes and was killed. The first diagnosis blamed
the Binance fetch, because `httpx.AsyncClient(timeout=10.0)` bounds each I/O
operation but httpx has no total-request bound. That diagnosis was WRONG, and the
run's own stdout proves it — all 180 bytes of it:

    mod: DRY-RUN (yazim YOK)
    pass A: 0 kalici degerlendirilemez satir emekli edilecekti (fetch yok)

The `aday: {len(rows)}` line sits between the batch SELECT and the fetch loop and
never printed. The loop never started; not one HTTP request was issued. The park
was on `await db.execute(select(...))` — the DATABASE path.

So this file guards BOTH bounds, and T3b exists specifically so a future edit
cannot delete the DB bound and still pass by virtue of the HTTP bound being
present.

THE SECOND DEFECT, WHICH NO TIMEOUT WOULD HAVE FIXED
----------------------------------------------------
`database.py:122` sets `idle_in_transaction_session_timeout = '180000'`. Pass B
autobegins a transaction on the batch SELECT and, in dry-run, issues no further
statement until the closing rollback. The session therefore sits idle-in-
transaction for the entire loop and Postgres terminates it after 180 s. The
25-row run survived on 128 s; any batch large enough to evidence Gate 8 would
not have. T16 pins the release.

GATE 8
------
The old metric could not see the failure that happened: `transient_fetch_error_retry`
increments only after a fetch RETURNS failed, so a call that never returns scored
zero. And 0/25 was reported as "0.0 %" when its 95 % upper bound is ~11 %. The
gate now reads terminal failures INCLUDING timeouts, and requires the one-sided
95 % upper bound — not the point estimate — to clear 5 %.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import pathlib
import re
import subprocess
import sys
from collections import Counter

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "p22a_shadow_eval.py"


def _load():
    """Import the script by path — it is not a package."""
    spec = importlib.util.spec_from_file_location("p22a_shadow_eval_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


P = _load()


class _Collector:
    """Stands in for BinanceCollector. Each behaviour is a deliberate failure mode."""

    def __init__(self, behaviour, ok_value="DF"):
        self.behaviour = behaviour
        self.ok_value = ok_value
        self.calls = 0

    async def fetch_ohlcv(self, symbol, timeframe, limit=100, end_time_ms=None):
        self.calls += 1
        b = self.behaviour(self.calls) if callable(self.behaviour) else self.behaviour
        if b == "ok":
            return self.ok_value
        if b == "hang":
            await asyncio.sleep(3600)        # never returns within any sane bound
            return self.ok_value
        if b == "connect_error":
            raise ConnectionError("connect refused")
        raise RuntimeError(f"unknown behaviour {b}")

    async def close(self):
        pass


BAR_TIME = __import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").timezone.utc)


async def _fetch(collector, stats, **kw):
    kw.setdefault("timeout", 0.05)
    kw.setdefault("retries", 0)
    return await P._fetch_bars(collector, "BTCUSDT", "1h", BAR_TIME, stats=stats, **kw)


# ── T1 · the success path is untouched ───────────────────────────────────────
@pytest.mark.asyncio
async def test_T1_success_path_unchanged():
    stats: Counter = Counter()
    df, limit, failed, kind = await _fetch(_Collector("ok"), stats, timeout=5.0)
    assert df == "DF" and failed is False and kind is None
    assert limit > 0
    assert stats["fetch_ok"] == 1 and stats["fetch_attempt"] == 1
    assert stats["fetch_timeout_attempt"] == 0 and stats["fetch_error_attempt"] == 0
    # A clean fetch must NOT be marked as retry-rescued.
    assert stats["fetch_row_recovered_by_retry"] == 0


# ── T2 · connect failure terminates and is classified as an error ────────────
@pytest.mark.asyncio
async def test_T2_connect_failure_terminates_within_bound():
    stats: Counter = Counter()
    df, _limit, failed, kind = await asyncio.wait_for(
        _fetch(_Collector("connect_error"), stats), timeout=5.0)
    assert df is None and failed is True
    assert kind == "error", "a connect refusal is an error, not a timeout"
    assert stats["fetch_error_attempt"] == 1 and stats["fetch_timeout_attempt"] == 0


# ── T3 · a socket stall terminates, and is classified AS A TIMEOUT ───────────
@pytest.mark.asyncio
async def test_T3_socket_stall_terminates_within_bound():
    stats: Counter = Counter()
    # The whole call is itself bounded by wait_for at 5s: if _fetch_bars did not
    # impose its own bound, this test would fail by TimeoutError here rather than
    # returning — which is exactly the regression being guarded.
    df, _limit, failed, kind = await asyncio.wait_for(
        _fetch(_Collector("hang"), stats, timeout=0.05), timeout=5.0)
    assert df is None and failed is True
    assert kind == "timeout", "a stall must be distinguishable from an error"
    assert stats["fetch_timeout_attempt"] == 1


@pytest.mark.asyncio
async def test_T3b_the_batch_SELECT_is_bounded_not_only_the_fetch():
    """The observed hang was on the SELECT, before any fetch. A patch that bounds
    only the HTTP call would leave the actual defect in place, so the DB bound is
    asserted structurally: `db.execute` for the batch must be inside a wait_for."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "evaluate")

    def _is_waitfor(node):
        f = node.func
        return (isinstance(f, ast.Attribute) and f.attr == "wait_for"
                and isinstance(f.value, ast.Name) and f.value.id == "asyncio")

    bounded = False
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call) and _is_waitfor(n)):
        wraps_execute = any(
            isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "execute"
            for inner in ast.walk(call))
        if not wraps_execute:
            continue
        # The wrapper alone proves nothing: `asyncio.wait_for(x, timeout=None)`
        # waits forever. The bound must be a real value, and it must come from a
        # variable so `--db-timeout` can reach it.
        tk = next((kw.value for kw in call.keywords if kw.arg == "timeout"), None)
        assert tk is not None, "wait_for around the batch SELECT needs a timeout"
        assert not (isinstance(tk, ast.Constant) and tk.value is None), (
            "timeout=None is an unbounded wait — the exact defect being fixed")
        assert isinstance(tk, (ast.Name, ast.Attribute)), (
            "the batch SELECT bound must be parameterised, not hard-coded")
        bounded = True
    assert bounded, (
        "evaluate() must wrap its batch db.execute in asyncio.wait_for — that is "
        "where the 59-minute park happened")


def test_T3c_the_fetch_bound_is_a_real_value_too():
    """Same trap on the HTTP side: the wrapper must carry a live bound."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_fetch_bars")
    checked = 0
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        f = call.func
        if not (isinstance(f, ast.Attribute) and f.attr == "wait_for"):
            continue
        tk = next((kw.value for kw in call.keywords if kw.arg == "timeout"), None)
        assert tk is not None and not (isinstance(tk, ast.Constant) and tk.value is None), (
            "the bar fetch must carry a real wall-clock bound")
        checked += 1
    assert checked == 1, f"expected exactly one bounded fetch, found {checked}"


# ── T4/T5 · retries are counted, and counted SEPARATELY ──────────────────────
@pytest.mark.asyncio
async def test_T4_retry_that_succeeds_is_counted_as_recovered():
    stats: Counter = Counter()
    col = _Collector(lambda n: "connect_error" if n == 1 else "ok")
    df, _l, failed, kind = await _fetch(col, stats, retries=2, timeout=5.0)
    assert df == "DF" and failed is False and kind is None
    assert col.calls == 2
    assert stats["fetch_row_recovered_by_retry"] == 1, "a rescued row must be visible"
    assert stats["fetch_error_attempt"] == 1
    # Recovered != failed. It must not land in the gate numerator.
    g = P.gate8(stats | Counter({"rows_attempted": 1}), 1)
    assert g["numerator_terminal_fetch_failures"] == 0
    assert g["rows_recovered_by_retry"] == 1


@pytest.mark.asyncio
async def test_T5_retries_exhausted_is_terminal_and_the_run_continues():
    stats: Counter = Counter()
    col = _Collector("connect_error")
    df, _l, failed, kind = await _fetch(col, stats, retries=2)
    assert col.calls == 3, "1 initial + 2 retries"
    assert df is None and failed is True and kind == "error"
    assert stats["fetch_attempt"] == 3 and stats["fetch_error_attempt"] == 3
    # Attempts and rows are NOT conflated: 3 attempts, but this is one row.
    assert stats["fetch_row_recovered_by_retry"] == 0


# ── T6 · a timeout can never read as success ─────────────────────────────────
def test_T6_a_timeout_cannot_produce_a_zero_numerator():
    stats = Counter({"fetch_row_terminal_timeout": 4, "rows_attempted": 100})
    g = P.gate8(stats, 100)
    assert g["numerator_terminal_fetch_failures"] == 4, (
        "timeouts MUST be in the numerator — the old metric's blindness to them "
        "is what let a hung run score 0.0 %")
    assert g["terminal_timeouts"] == 4
    assert g["rate"] == pytest.approx(0.04)
    assert g["verdict"] != "PASS", "4/100 cannot clear a 5% upper bound"


def test_T6b_a_stalled_run_is_INDETERMINATE_not_zero_percent():
    """The precise previous failure: a run that did not finish must not be
    scoreable at all. Zero failures among the rows it happened to reach is not
    evidence about the rows it never reached."""
    stats = Counter({"rows_attempted": 30, "run_deadline_exceeded": 1,
                     "rows_unattempted": 470})
    g = P.gate8(stats, 30)
    assert g["verdict"] == "INDETERMINATE"
    assert g["rate"] is None and g["upper_bound_95"] is None


# ── T7 · one bad symbol cannot hang the batch ────────────────────────────────
@pytest.mark.asyncio
async def test_T7_one_hanging_fetch_cannot_hang_the_whole_batch():
    stats: Counter = Counter()
    col = _Collector(lambda n: "hang" if n == 1 else "ok")
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    results = []
    for _ in range(4):
        results.append(await asyncio.wait_for(
            _fetch(col, stats, timeout=0.05, retries=0), timeout=5.0))
    elapsed = loop.time() - t0
    assert results[0][2] is True and results[0][3] == "timeout"
    assert [r[2] for r in results[1:]] == [False, False, False], "batch continued"
    assert elapsed < 3.0, f"a single stall dominated the batch ({elapsed:.2f}s)"


# ── T8/T9 · the write contract is untouched ──────────────────────────────────
def test_T8_dry_run_issues_no_write_statement():
    """AST, not substring: a comment mentioning UPDATE must not satisfy this, and
    a future edit that hoists the UPDATE out of `if not dry_run` must fail."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "evaluate")

    def _guarded_by_not_dry_run(node):
        for parent in ast.walk(fn):
            if isinstance(parent, ast.If):
                test = parent.test
                neg = (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                       and isinstance(test.operand, ast.Name)
                       and test.operand.id == "dry_run")
                if neg and any(node is d for d in ast.walk(parent)):
                    return True
        return False

    updates = [n for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "update"]
    assert updates, "expected the row UPDATE to still exist"
    for u in updates:
        assert _guarded_by_not_dry_run(u), (
            "every UPDATE in evaluate() must sit behind `if not dry_run`")


def test_T9_write_flag_semantics_are_unchanged():
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    # dry_run must still be derived as `not args.write` — not from --dry-run, and
    # not defaulted to False.
    found = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "dry_run" for t in node.targets):
            v = node.value
            found = (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not)
                     and isinstance(v.operand, ast.Attribute)
                     and v.operand.attr == "write")
    assert found, "dry_run must remain `not args.write`"
    assert P.DEFAULT_FETCH_RETRIES >= 0 and P.DEFAULT_FETCH_TIMEOUT > 0


def test_T9b_evaluate_still_defaults_to_dry_run():
    import inspect
    sig = inspect.signature(P.evaluate)
    assert sig.parameters["dry_run"].default is True


# ── T10/T11 · ordering is deterministic, and the biased mode cannot be silent ─
def test_T10_batch_ordering_is_deterministic_and_stable():
    a = str(P._batch_order(P.ORDER_HASH))
    b = str(P._batch_order(P.ORDER_HASH))
    assert a == b, "hash ordering must be reproducible"
    assert "md5" in a.lower()
    # Nothing non-deterministic may leak in.
    assert "random" not in a.lower()
    assert str(P._batch_order(P.ORDER_OLDEST)) != a


def test_T11_oldest_tail_cannot_silently_be_the_authoritative_gate8_mode():
    """`oldest` stays the default because it drains the backlog, but a Gate-8 PASS
    produced on it must be labelled at the point of production."""
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    # There must be a branch that tests the order against ORDER_OLDEST alongside
    # the gate verdict, and warns. Structural, so a stray comment cannot satisfy.
    guarded = False
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp):
            names = {n.attr for n in ast.walk(node.test) if isinstance(n, ast.Attribute)}
            consts = {n.value for n in ast.walk(node.test)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            if "ORDER_OLDEST" in names or "PASS" in consts:
                guarded = True
    assert guarded, "a PASS on the oldest-tail ordering must be flagged in the output"
    assert P.ORDER_HASH != P.ORDER_OLDEST


# ── T12/T13 · the gate boundary, and the n it demands ────────────────────────
@pytest.mark.parametrize("k,n,expected", [
    (0, 1000, "PASS"),            # clean and large
    (49, 1000, "NOT_EVIDENCED"),  # 4.9 % point estimate, but the bound is above 5 %
    (100, 1000, "FAIL"),          # 10 % — the point estimate itself breaches
    (0, 25, "NOT_EVIDENCED"),     # THE previous measurement
])
def test_T12_gate8_boundary(k, n, expected):
    stats = Counter({"fetch_row_terminal_error": k, "rows_attempted": n})
    assert P.gate8(stats, n)["verdict"] == expected


def test_T13_insufficient_n_is_never_COMPLETE():
    """0/25 was reported as 0.0 %. Its exact one-sided 95 % bound is ~11.3 %, so
    it cannot evidence a 5 % threshold and must not be a PASS."""
    g = P.gate8(Counter({"rows_attempted": 25}), 25)
    assert g["rate"] == 0.0
    assert g["upper_bound_95"] == pytest.approx(1 - 0.05 ** (1 / 25), rel=1e-9)
    assert g["upper_bound_95"] > 0.11
    assert g["verdict"] == "NOT_EVIDENCED"
    assert "too small" in g["reason"], "the reason must name sample size, not proximity"

    # A large n that merely sits close to the line gets the SAME verdict but a
    # different reason — conflating the two is what would let 49/1000 be read as
    # "just needs more rows".
    close = P.gate8(Counter({"fetch_row_terminal_error": 49, "rows_attempted": 1000}), 1000)
    assert close["verdict"] == "NOT_EVIDENCED" and "too close" in close["reason"]

    # And the smallest clean n that DOES clear it is > 58 — a property of the
    # bound, not a number anyone chose.
    assert P.gate8(Counter({"rows_attempted": 58}), 58)["verdict"] == "NOT_EVIDENCED"
    assert P.gate8(Counter({"rows_attempted": 59}), 59)["verdict"] == "PASS"


def test_the_threshold_itself_was_not_weakened():
    assert P.GATE8_MAX_RATE == 0.05
    assert P.GATE8_ALPHA == 0.05


def test_clopper_pearson_matches_the_closed_form_and_is_monotone():
    for n in (10, 59, 100, 1000):
        assert P.clopper_pearson_upper(0, n) == pytest.approx(1 - 0.05 ** (1 / n), rel=1e-9)
    # Monotone in k, and every bound is above the point estimate.
    prev = -1.0
    for k in range(0, 20):
        u = P.clopper_pearson_upper(k, 500)
        assert u > k / 500
        assert u > prev
        prev = u


# ── T14/T15 · nothing outside this script moved ──────────────────────────────
def test_T14_the_production_collector_is_untouched():
    """The bound is applied at the call site precisely so the collector shared
    with the live scheduler keeps its semantics."""
    base = subprocess.run(
        ["git", "diff", "--name-only", "main...HEAD"],
        cwd=BACKEND.parent, capture_output=True, text=True, check=True).stdout.split()
    assert "backend/app/collectors/binance_collector.py" not in base
    src = (BACKEND / "app" / "collectors" / "binance_collector.py").read_text(encoding="utf-8")
    assert "httpx.AsyncClient(timeout=10.0)" in src
    assert "wait_for" not in src


def test_T15_the_decision_path_is_untouched():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "main...HEAD"],
        cwd=BACKEND.parent, capture_output=True, text=True, check=True).stdout.split()
    forbidden = (
        "backend/app/services/shadow_eval.py",
        "backend/app/backtesting/resolution_core.py",
        "backend/app/backtesting/tracker.py",
        "backend/app/backtesting/lifecycle.py",
        "backend/app/services/scheduler.py",
        "backend/app/services/entry_activation.py",
        "backend/app/services/entry_flags.py",
        "backend/app/services/publication.py",
        "backend/app/services/lifecycle_log.py",
        "backend/app/models/decision_candidate.py",
        "backend/app/database.py",
    )
    for f in forbidden:
        assert f not in changed, f"{f} must not change in a reliability checkpoint"
    assert not [c for c in changed if c.startswith("frontend/")]
    # NO BLANKET MIGRATION CLAUSE HERE.
    #
    # This used to read `assert not [c for c in changed if "migrations/" in c]`.
    # The diff it inspects is `main...HEAD`, so once this checkpoint MERGED the
    # expression stopped describing this checkpoint at all and started
    # describing whatever branch happens to be checked out. CP-OHLCV-A1 adds a
    # migration legitimately, through its own gates, and this assertion failed —
    # not because a reliability checkpoint had grown a schema change, but
    # because a later, unrelated one had.
    #
    # The claim worth keeping is the LOCAL one, and it is asserted properly by
    # `test_this_checkpoint_adds_no_migration` below: the migration set this
    # checkpoint pinned is intact, and no migration added since performs DDL
    # against `signal_decision_candidates` — the table Pass B actually depends
    # on. That is strictly stronger than "the current diff mentions no
    # migration", because it keeps biting long after this branch is history.


# The migration set this checkpoint was written against, pinned by NAME.
#
# This guard used to read `[-1] == "0010_candidate_log_rls.sql"`. That proved a
# GLOBAL fact — that nothing has been added to the repo since — to support a
# LOCAL claim, that THIS checkpoint added no migration. scripts/migrate.py
# exists precisely to apply new files, so the old form had a guaranteed expiry
# date, and CP-OHLCV-A1's 0011 is that date arriving.
CHECKPOINT_MIGRATIONS = frozenset({
    "0001_consent_log.sql", "0002_stripe_subscription.sql",
    "0003_per_user_notifications.sql", "0004_signal_snapshot_extra.sql",
    "0005_notify_lifecycle.sql", "0006_enable_rls.sql",
    "0007_rls_revoke_data_api.sql", "0008_signal_performance_times.sql",
    "0009_resolution_provenance.sql", "0010_candidate_log_rls.sql",
})

# The tables THIS checkpoint's claims actually rest on. A migration added later
# by somebody else is not this test's business unless it moves one of these.
GUARDED_TABLES = frozenset({"signal_decision_candidates"})

_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_DDL_TABLE = re.compile(
    r"\b(?:create|alter|drop)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?"
    r'"?(?:public\.)?"?([a-z_][a-z0-9_]*)', re.I)


def _ddl_targets(sql: str) -> set:
    """Tables a migration CREATEs, ALTERs or DROPs.

    Comments are stripped first — 0001 carries the words "ALTER TABLE" inside a
    warning comment, and a guard that reads prose as DDL reports a schema move
    that never happened.
    """
    return {m.group(1).lower()
            for m in _DDL_TABLE.finditer(_SQL_COMMENT.sub(" ", sql))}


def test_this_checkpoint_adds_no_migration():
    mig = pathlib.Path(__file__).resolve().parent.parent / "migrations"
    present = {p.name for p in mig.glob("*.sql")}
    # Nothing this checkpoint was written against was removed, renamed, or had
    # a file renumbered into the middle of it.
    assert {n for n in present if n[:4] <= "0010"} == CHECKPOINT_MIGRATIONS, (
        f"the migration set this checkpoint pinned moved; found {sorted(present)}")
    # And no migration added SINCE touches the schema this checkpoint rests on.
    for p in sorted(mig.glob("*.sql")):
        if p.name in CHECKPOINT_MIGRATIONS:
            continue
        hit = _ddl_targets(p.read_text(encoding="utf-8")) & GUARDED_TABLES
        assert not hit, f"{p.name} moves {sorted(hit)}, which this checkpoint depends on"


# ── T17 · the run deadline actually exists in the loop ───────────────────────
def test_T17_the_fetch_loop_enforces_the_run_deadline():
    """T6b proves gate8 REPORTS a truncated run as INDETERMINATE. This proves the
    loop can actually produce that state — otherwise the deadline branch could be
    deleted and every gate-8 test would still pass on hand-built counters."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "evaluate")
    loop = next(n for n in ast.walk(fn) if isinstance(n, ast.For))

    def _sets(node, key):
        for n in ast.walk(node):
            if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store):
                sl = n.slice
                if isinstance(sl, ast.Constant) and sl.value == key:
                    return True
        return False

    ok = False
    for node in ast.walk(loop):
        if not isinstance(node, ast.If):
            continue
        names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(node.test) if isinstance(n, ast.Attribute)}
        if "run_deadline" not in names or "monotonic" not in attrs:
            continue
        if (_sets(node, "run_deadline_exceeded") and _sets(node, "rows_unattempted")
                and any(isinstance(n, ast.Break) for n in ast.walk(node))):
            ok = True
    assert ok, (
        "the fetch loop must compare time.monotonic() against run_deadline and, on "
        "breach, record run_deadline_exceeded + rows_unattempted and break — that "
        "is what forces gate 8 to INDETERMINATE instead of a clean partial rate")


# ── T16 · the 180s idle-in-transaction cliff ─────────────────────────────────
def test_T16_dry_run_releases_the_read_transaction_before_the_fetch_loop():
    """database.py sets idle_in_transaction_session_timeout=180000. A dry-run
    issues no SQL between the batch SELECT and the closing rollback, so holding
    that transaction across the loop gets the session killed at 180 s — which is
    why a 25-row (128 s) run survived and a gate-8-sized one would not."""
    db_src = (BACKEND / "app" / "database.py").read_text(encoding="utf-8")
    assert "idle_in_transaction_session_timeout" in db_src and "180000" in db_src, (
        "premise changed: re-derive this guard")

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "evaluate")
    loop = next(n for n in ast.walk(fn) if isinstance(n, ast.For))

    # Presence is not enough — the rollback must be REACHABLE in dry-run. An
    # earlier version of this guard only checked that a rollback call existed
    # before the loop, so rewriting `if dry_run:` to `if False:` left it passing.
    guarded_release = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or node.lineno >= loop.lineno:
            continue
        if not (isinstance(node.test, ast.Name) and node.test.id == "dry_run"):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "rollback"):
                guarded_release = True

    assert guarded_release, (
        "dry-run must end the read transaction BEFORE the fetch loop, under a real "
        "`if dry_run:` guard, or Postgres terminates the session mid-batch at 180s")
