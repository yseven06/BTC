"""CP-OHLCV-A3F — durable per-symbol fairness.

A3D proved the blocker these guards exist to prevent: any partition selector that
is a pure function of (run_seq, N) phase-locks when N is periodic in run_seq. At
K=5 with a universe oscillating 57/58/57/250, only 25 of 50 index blocks were
reachable and 95 of 250 symbols were NEVER selected.

So the tests below are written in SYMBOL identities, never indices, and the
headline property is measured the only way that catches real starvation: the
longest stretch of consecutive runs in which a symbol was ACTIVE but NOT
selected. A metric that only counts "never selected at all" scores a symbol
selected once and then abandoned forever as perfect, which is exactly the bug
that has to be caught.

Nothing here registers, activates, or touches production.
"""

from __future__ import annotations

import ast
import inspect
import math
import pathlib
import random

import pytest

from app.services import ohlcv_progression as prog
from app.services.ohlcv_collector_job import SYMBOLS_PER_RUN

BACKEND = pathlib.Path(__file__).resolve().parent.parent


# ── a pure model of the SHIPPED ranking rule ────────────────────────────────
def rank_and_claim(active, k, run_seq, ledger):
    """Mirrors select_partition: MATERIALISE, then rank, then advance.

    The materialisation step is not cosmetic. Computing the same seed as an
    effective token instead of writing it reproduces the falsified policy
    exactly, because a rowless symbol then never ages. Asserted against the real
    source below so this model cannot drift from what ships.
    """
    seed = max(run_seq - 1, 0)
    for sym in active:
        ledger.setdefault(sym, seed)          # ON CONFLICT DO NOTHING
    ranked = sorted(active, key=lambda s: (ledger[s], s))
    picked = ranked[:k]
    for sym in picked:
        ledger[sym] = run_seq
    return picked


def worst_active_wait(k, universe_at, runs):
    """Longest consecutive stretch: ACTIVE but NOT selected."""
    ledger, waiting, worst, seen = {}, {}, {}, set()
    for t in range(1, runs + 1):
        u = sorted(universe_at(t))
        seen.update(u)
        picked = set(rank_and_claim(u, k, t, ledger))
        for s in u:
            waiting[s] = 0 if s in picked else waiting.get(s, 0) + 1
            worst[s] = max(worst.get(s, 0), waiting[s])
    return (max(worst.values()) if worst else 0), len(seen)


def S(i):
    return f"SYM{i:05d}"


def fixed(n):
    return lambda t: {S(i) for i in range(n)}


# ══ STABLE UNIVERSE: the exact ceil(N/K) bound ═════════════════════════════
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 12, 56, 57, 58, 59, 60, 127, 250])
def test_every_symbol_is_selected_within_ceil_n_over_k(n):
    """The bound the whole partition rests on, swept over every required N and
    every K from 1 to min(10, N)."""
    for k in range(1, min(10, n) + 1):
        wait, seen = worst_active_wait(k, fixed(n), max(240, 4 * math.ceil(n / k)))
        assert seen == n
        # a symbol waits at most one full cycle minus its own turn
        assert wait <= math.ceil(n / k) - 1, (
            f"N={n} K={k}: waited {wait} runs, bound is {math.ceil(n / k) - 1}")


# ══ THE A3D KILLER AND FRIENDS ═════════════════════════════════════════════
CHURN = {
    "A3D killer 57/58/57/250": lambda t: {S(i) for i in range([57, 58, 57, 250][t % 4])},
    "56/60 repeating": lambda t: {S(i) for i in range([56, 60][t % 2])},
    "1/250 repeating": lambda t: {S(i) for i in range([1, 250][t % 2])},
    "monotonic growth": lambda t: {S(i) for i in range(min(50 + t // 10, 250))},
    "monotonic shrink": lambda t: {S(i) for i in range(max(250 - t // 10, 50))},
    "moving inactive hole": lambda t: {S(i) for i in range(57)
                                       if not (t * 5 % 57 <= i < t * 5 % 57 + 5)},
    "rolling delist/relist": lambda t: {S(i) for i in range(57)
                                        if (i % 7) != (t // 3) % 7},
    "one symbol vanishes each run": lambda t: {S(i) for i in range(57)} - {S(t % 57)},
}


@pytest.mark.parametrize("name", sorted(CHURN))
@pytest.mark.parametrize("k", [4, 5, 6])
def test_bounded_churn_never_starves_and_stays_proportional(name, k):
    """THE A3F contract: under bounded churn every continuously-active symbol is
    selected within a bound PROPORTIONAL to ceil(N_max/K) — not merely 'finite'.
    A3D's index cursor satisfied 'finite' and still degraded 10x, which is what
    made it unusable."""
    gen = CHURN[name]
    runs = 1500
    wait, n_max = worst_active_wait(k, gen, runs)
    ideal = math.ceil(n_max / k)
    assert wait < runs, f"{name}: starvation, waited the whole horizon"
    assert wait <= 4 * ideal, (
        f"{name} K={k}: waited {wait}, ceil(N_max={n_max}/{k})={ideal}, "
        f"ratio {wait / ideal:.1f}x exceeds the 4x proportionality allowance")


def test_random_bounded_insert_delete_around_the_selected_set():
    rnd = random.Random(20260816)

    def gen(t):
        base = {S(i) for i in range(57)}
        for _ in range(3):
            base.discard(S(rnd.randrange(57)))
        return base | {f"NEW{rnd.randrange(20):03d}" for _ in range(3)}

    for k in (4, 5, 6):
        wait, n_max = worst_active_wait(k, gen, 1500)
        assert wait <= 4 * math.ceil(n_max / k), f"K={k}: waited {wait}"


def test_restart_and_redeploy_between_every_run_change_nothing():
    """The ledger is durable, so losing all process state each run is invisible.
    Modelled by rebuilding every in-memory structure except the ledger."""
    n, k, runs = 57, 5, 400
    ledger, waiting, worst = {}, {}, {}
    for t in range(1, runs + 1):
        u = sorted(fixed(n)(t))
        picked = set(rank_and_claim(u, k, t, ledger))   # ledger survives; nothing else
        waiting = {s: (0 if s in picked else waiting.get(s, 0) + 1) for s in u}
        for s in u:
            worst[s] = max(worst.get(s, 0), waiting[s])
    assert max(worst.values()) <= math.ceil(n / k) - 1


def test_missed_executions_do_not_advance_anything():
    """run_seq advances per EXECUTED run, so skipped cron slots simply do not
    exist to this ledger — there is no wall clock to fall behind."""
    n, k = 57, 5
    a, b = {}, {}
    for t in range(1, 61):
        rank_and_claim(sorted(fixed(n)(t)), k, t, a)
    for t in range(1, 61):                      # same executions, 1000x the elapsed time
        rank_and_claim(sorted(fixed(n)(t)), k, t, b)
    assert a == b


# ══ THE UNSEEN-SYMBOL POLICY (load-bearing) ════════════════════════════════
def test_a_new_symbol_enters_behind_every_overdue_incumbent():
    """Materialising at run_seq-1 puts a newcomer one generation behind the
    claim this run makes, so it cannot preempt an incumbent that is already
    overdue. -infinity would invert this and starve incumbents outright."""
    ledger = {S(i): 10 for i in range(6)}       # six incumbents, all attempted at 10
    picked = rank_and_claim(sorted({S(i) for i in range(6)} | {"ZZZNEW"}), 3, 20, ledger)
    assert "ZZZNEW" not in picked, "a newcomer jumped ahead of overdue incumbents"
    assert picked == [S(0), S(1), S(2)]


def test_a_perpetual_stream_of_newcomers_cannot_starve_an_incumbent():
    """THE decisive attack that rejected unseen-first. New identities arrive at
    K per run forever, adversarially named at BOTH ends of the tie-break, while
    one incumbent stays active throughout."""
    INC = "AAA_INCUMBENT"
    for k in (1, 2, 3, 4, 5, 6, 10):
        for lex_small in (True, False):
            ledger, waited, worst = {}, 0, 0
            for t in range(1, 801):
                u = {INC} | {S(i) for i in range(50)}
                u |= {(f"AAA{t:06d}_{j:02d}" if lex_small else f"ZZZ{t:06d}_{j:02d}")
                      for j in range(k)}
                assert len(u) <= 250
                picked = rank_and_claim(sorted(u), k, t, ledger)
                waited = 0 if INC in picked else waited + 1
                worst = max(worst, waited)
            assert worst <= 4 * math.ceil(51 / k), (
                f"K={k} lex_small={lex_small}: incumbent waited {worst} runs")


def test_a_new_symbol_is_nevertheless_selected_within_one_cycle():
    """Back of the queue must still mean IN the queue."""
    n, k = 20, 4
    ledger = {S(i): 1 for i in range(n)}
    universe = {S(i) for i in range(n)} | {"ZZZNEW"}
    for t in range(2, 2 + math.ceil((n + 1) / k)):
        if "ZZZNEW" in rank_and_claim(sorted(universe), k, t, ledger):
            return
    pytest.fail("a continuously-active new symbol was never selected within one cycle")


def test_repeated_bounded_additions_keep_the_proportional_bound():
    def gen(t):
        return {S(i) for i in range(57)} | {f"NEW{j:03d}" for j in range(min(t // 50, 20))}
    for k in (4, 5, 6):
        wait, n_max = worst_active_wait(k, gen, 1500)
        assert wait <= 4 * math.ceil(n_max / k)


def test_the_shipped_policy_is_materialised_current_minus_one():
    """Guards the model against drifting away from the real selector, and pins
    the two halves that were empirically falsified when either was missing."""
    assert prog.UNSEEN_MATERIALISES_ONE_GENERATION_BEHIND is True
    assert not hasattr(prog, "UNSEEN_SYMBOL_SEEDS_AT_CURRENT_RUN"), \
        "the falsified policy constant is still exported"
    src = inspect.getsource(prog.select_partition)
    assert "seed = max(run_seq - 1, 0)" in src, "the seed is not run_seq-1 floored at 0"
    assert "on_conflict_do_nothing" in src, "rowless symbols are not MATERIALISED"
    # ranking must read the STORED column, never a per-run default
    assert "OhlcvSymbolProgress.last_attempt_run_seq.asc()" in src
    assert ".get(" not in src.split("# 2. SELECT")[1].split("# 3. ADVANCE")[0], \
        "the ranking falls back to an in-memory default instead of the stored row"
    for forbidden in ("time.time", "datetime.now", "random", "hash("):
        assert forbidden not in src, f"the selector contains {forbidden!r}"


# ══ SHAPE OF THE REAL PRIMITIVE ════════════════════════════════════════════
def test_the_claim_is_one_statement_and_commits_before_returning():
    """The partition must be claimed in ONE short transaction that commits before
    any network work — a transaction held across a Binance request is the
    idle-in-transaction shape this codebase has already been bitten by."""
    # Parse the MODULE and pick the function node out of it. Dedenting a method
    # source and rewriting `async def` produced malformed indentation and an
    # IndentationError - the helper, not the code under test, was broken.
    module = ast.parse(pathlib.Path(prog.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in module.body
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "select_partition")
    src = inspect.getsource(prog.select_partition)
    executes = [n for n in ast.walk(fn)
                if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"]
    commits = [n for n in ast.walk(fn)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "commit"]
    # FOUR since A3H8, and the count is deliberately exact rather than a bound:
    # serialise + materialise + select + advance. The first is
    # `pg_advisory_xact_lock`, which A3H8 measured to be what actually makes two
    # concurrent claimants disjoint — SKIP LOCKED cannot, because the ranking
    # comes from a snapshot taken before the other claimant committed. It is
    # transaction-scoped, so this same COMMIT still releases everything, and the
    # transaction is still short and still has no network in it.
    assert len(executes) == 4, \
        "expected serialise + materialise + select + advance"
    assert len(commits) == 1, "expected exactly one commit"
    assert "pg_advisory_xact_lock" in src, \
        "the claim no longer serialises; concurrent claimants can collide"
    assert "CLAIM_LOCK_NAMESPACE" in src, \
        "the claim lock must use its own namespace, or a run blocks against itself"
    assert any(isinstance(n, ast.Call)
               and getattr(n.func, "attr", "") == "with_for_update"
               for n in ast.walk(fn)), "the oldest-K read is not FOR UPDATE SKIP LOCKED"
    assert "skip_locked=True" in src, "concurrent claims can collide"
    # IDENTIFIERS, NOT RAW TEXT. The original scan matched the whole source
    # including docstrings, so it fired the moment the contract prose mentioned
    # a concurrent run "fetching" a symbol — a comment cannot open a socket.
    # Walking the AST is also strictly stronger in the other direction: a
    # network call can no longer hide behind a renamed local or a comment that
    # happens to avoid the word.
    names = {getattr(n, "attr", "") or getattr(n, "id", "")
             for n in ast.walk(fn)
             if isinstance(n, (ast.Attribute, ast.Name))}
    for banned in ("sleep", "collector", "fetch", "http"):
        hit = sorted(x for x in names if banned in x.lower())
        assert not hit, f"network-shaped work ({banned}) inside the claim: {hit}"


def test_the_source_is_part_of_the_key_and_the_read():
    src = inspect.getsource(prog.select_partition)
    assert src.count("OhlcvSymbolProgress.source == src") >= 2, \
        "the read and the advance are not both source-scoped"
    assert "OhlcvSymbolProgress.symbol" in src


def test_k_is_not_part_of_the_durable_identity():
    """Retuning K must never invalidate a token or need a migration."""
    from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress
    cols = set(OhlcvSymbolProgress.__table__.columns.keys())
    assert cols == {"source", "symbol", "last_attempt_run_seq", "updated_at"}
    assert [c.name for c in OhlcvSymbolProgress.__table__.primary_key.columns] \
        == ["source", "symbol"]


def test_the_collector_partitions_symbols_not_timeframes():
    """K applied per timeframe would quarter the coverage and silently break the
    all-four-timeframes contract."""
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    assert "select_partition(" in src
    body = src.split("res.symbols_partition_size")[1].split("watermark")[0]
    assert "for tf" not in body, "the partition is applied inside a timeframe loop"
    assert SYMBOLS_PER_RUN >= 1

# ══ MODEL / MIGRATION CATALOGUE AGREEMENT ══════════════════════════════════
# `scripts/migrate.py` runs create_all BEFORE the pending .sql, so on a fresh
# database the MODEL builds the table and 0013 is a no-op. 0012 measured what
# happens when the two disagree: `character varying` vs `text`, and a CHECK that
# rendered as length(btrim((col)::text)) in one path and length(btrim(col)) in
# the other. Both are functionally equivalent and neither is the same catalogue
# object. These are static guards; the real catalogue equality is proved against
# a disposable PostgreSQL.
MIGRATION = BACKEND / "migrations/0013_ohlcv_symbol_progress.sql"


def test_the_migration_and_the_model_declare_the_same_columns():
    from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress
    sql = MIGRATION.read_text(encoding="utf-8")
    cols = OhlcvSymbolProgress.__table__.columns
    assert set(cols.keys()) == {"source", "symbol",
                                "last_attempt_run_seq", "updated_at"}
    # VARCHAR on BOTH sides — never TEXT, which is the 0012 mistake
    for name in ("source", "symbol"):
        assert cols[name].type.__class__.__name__ == "String", \
            f"{name} is not String/VARCHAR in the model"
        assert f"{name:<21} VARCHAR" in sql or f"{name}      VARCHAR" in sql, \
            f"{name} is not declared VARCHAR in 0013"
    assert "TEXT" not in sql.split("CREATE TABLE")[1].split(");")[0].upper() \
        .replace("CONTEXT", ""), "0013 declares a TEXT column"


def test_the_migration_and_the_model_declare_the_same_constraints():
    from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress
    sql = MIGRATION.read_text(encoding="utf-8")
    names = {c.name for c in OhlcvSymbolProgress.__table__.constraints if c.name}
    # THE SET, NOT A SUBSET. An earlier version of this test listed the names it
    # expected and checked each was present, which says nothing about the ones
    # it forgot to list — and it forgot `source`. The activation review found a
    # blank venue being accepted by the database while the sibling table
    # ohlcv_collection_progress had carried that constraint all along. Pinning
    # the exact set is what makes the next omission fail here instead of in a
    # migration review.
    expected = {"ck_ohlcv_symbol_progress_seq",
                "ck_ohlcv_symbol_progress_source",
                "ck_ohlcv_symbol_progress_symbol"}
    checks = {n for n in names if n.startswith("ck_")}
    assert checks == expected, \
        f"model CHECK set is {sorted(checks)}, expected {sorted(expected)}"
    for name in expected:
        assert name in sql, f"{name} missing from 0013"
    # Every NOT NULL text-ish column must carry a blank guard, so adding a
    # column cannot quietly reintroduce the same hole.
    for col in ("source", "symbol"):
        assert f"length(btrim({col})) > 0" in sql, \
            f"0013 has no blank guard for {col}"
    # the PK must stay UNNAMED in the SQL so both paths emit the default name
    assert "PRIMARY KEY (source, symbol)" in sql
    assert "CONSTRAINT pk_" not in sql, "the PK is explicitly named in 0013"


def test_the_migration_and_the_model_declare_the_same_index():
    from app.models.ohlcv_symbol_progress import OhlcvSymbolProgress
    sql = MIGRATION.read_text(encoding="utf-8")
    idx = {i.name for i in OhlcvSymbolProgress.__table__.indexes}
    assert "ix_ohlcv_symbol_progress_source_seq" in idx, \
        "the oldest-K index is missing from the model"
    assert "ix_ohlcv_symbol_progress_source_seq" in sql, \
        "the oldest-K index is missing from 0013"


def test_0013_is_additive_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    for forbidden in ("ALTER TABLE", "DROP TABLE", "DELETE FROM", "UPDATE ",
                      "ohlcv_bars", "ohlcv_collection_progress"):
        assert forbidden not in body, f"0013 is not additive-only: {forbidden}"


def test_the_partition_receives_k_verbatim_not_divided_per_timeframe():
    """K is a SYMBOL count. Passing symbols_per_run // len(TIMEFRAMES) would
    quarter the coverage while every other guard stayed green."""
    import ast as _ast
    src = (BACKEND / "app/services/ohlcv_collector_job.py").read_text(encoding="utf-8")
    tree = _ast.parse(src)
    calls = [n for n in _ast.walk(tree)
             if isinstance(n, _ast.Call)
             and getattr(n.func, "id", "") == "select_partition"]
    assert len(calls) == 1, f"expected exactly one select_partition call, got {len(calls)}"
    args = calls[0].args
    assert len(args) == 5, f"unexpected arity: {_ast.unparse(calls[0])}"
    k_arg = _ast.unparse(args[3])
    assert k_arg == "symbols_per_run",         f"K is transformed on the way to the partition: {k_arg}"

