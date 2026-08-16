"""CP-OHLCV-A3F — BEHAVIOURAL guards for the real `select_partition`.

The fairness tests next door prove the ORDERING RULE against a pure model, and
the static tests prove the SHAPE of the code. Neither runs the real function, and
a sabotage pass proved that gap concretely: mutations that dropped the tie-break,
ranked inactive symbols, replaced symbol identity with a list index, or skipped
the durable advance all SURVIVED both. These tests drive the real
`select_partition` against a recording fake session and close it.

No database, no network, no activation.
"""

from __future__ import annotations

import pytest

from app.services.ohlcv_progression import select_partition


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        outer = self

        class _S:
            def all(self):
                return list(outer._rows)
        return _S()


class _Session:
    """Records every statement and serves the oldest-K read from `ledger`."""

    def __init__(self, ledger, recorder):
        self.ledger = ledger          # {symbol: token}
        self.rec = recorder
        self.active = set()           # filled by the materialise INSERT

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    async def execute(self, stmt, *a, **k):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
        self.rec.append(("sql", sql, stmt))
        if sql.startswith("insert"):
            # MATERIALISE — record the seeds actually written
            params = dict(stmt.compile().params)
            self.rec.append(("materialise", params))
            self.active = {v for k, v in params.items()
                           if isinstance(v, str) and k.startswith("symbol")}
            return _Result([])
        if sql.startswith("select"):
            # honour the ordering the statement ASKS for, so a mutated ORDER BY
            # produces a different answer here rather than being ignored
            asc_token = "last_attempt_run_seq asc" in sql or "order by" not in sql
            asc_sym = "symbol asc" in sql
            # HONOUR THE ACTIVE SET. Serving the whole ledger regardless of what
            # the statement asked for let a mutation that replaced symbol
            # identity with a list index survive: the fake handed back the real
            # symbols anyway. The materialise INSERT names the active symbols
            # explicitly, so use that - `IN (...)` compiles to an expanding
            # bindparam whose values are not in `compile().params`.
            items = [kv for kv in self.ledger.items()
                     if not self.active or kv[0] in self.active]
            items.sort(key=lambda kv: ((kv[1] if asc_token else -kv[1]),
                                       kv[0] if asc_sym else ""))
            limit = getattr(stmt, "_limit", None)
            picked = [s for s, _ in items][:limit or len(items)]
            self.rec.append(("select", picked))
            return _Result(picked)
        if sql.startswith("update"):
            self.rec.append(("advance", stmt.compile().params))
            return _Result([])
        return _Result([])

    async def commit(self):
        self.rec.append(("commit",))

    async def rollback(self):
        return None


def _sql(rec, prefix):
    """The first recorded statement of the given kind."""
    return next(r[1] for r in rec
                if r[0] == "sql" and r[1].startswith(prefix))


def _factory(ledger, rec):
    return lambda: _Session(ledger, rec)


@pytest.mark.asyncio
async def test_it_returns_the_caller_s_own_symbol_strings_not_indices():
    """M6: replacing identity with a list index must not survive."""
    rec = []
    ledger = {"AAAUSDT": 1, "BBBUSDT": 2, "CCCUSDT": 3}
    got = await select_partition(_factory(ledger, rec), "binance",
                                 ["AAAUSDT", "BBBUSDT", "CCCUSDT"], 2, 9)
    assert got == ["AAAUSDT", "BBBUSDT"], got
    assert all(isinstance(s, str) and s.endswith("USDT") for s in got)


@pytest.mark.asyncio
async def test_the_read_is_restricted_to_the_active_symbols():
    """M8: an inactive symbol keeps its row but must never be ranked."""
    rec = []
    await select_partition(_factory({"A": 1, "B": 2}, rec), "binance", ["A", "B"], 2, 9)
    sel = _sql(rec, "select")
    assert "symbol in" in sel or "symbol in (" in sel, \
        "the oldest-K read is not restricted to the active set"


@pytest.mark.asyncio
async def test_the_read_orders_by_token_then_symbol():
    """M1 and M10: newest-first, or a dropped tie-break, must not survive."""
    rec = []
    await select_partition(_factory({"A": 1}, rec), "binance", ["A"], 1, 9)
    sel = _sql(rec, "select")
    order = sel.split("order by")[1]
    assert "last_attempt_run_seq asc" in order, f"not oldest-first: {order}"
    assert "symbol asc" in order, f"tie-break missing: {order}"
    assert "desc" not in order, f"descending order: {order}"


@pytest.mark.asyncio
async def test_equal_tokens_resolve_by_symbol_deterministically():
    """M10 behaviourally: identical tokens must not resolve by insertion order."""
    rec = []
    ledger = {"ZZZ": 5, "AAA": 5, "MMM": 5}
    got = await select_partition(_factory(ledger, rec), "binance",
                                 ["ZZZ", "MMM", "AAA"], 2, 9)
    assert got == ["AAA", "MMM"], got


@pytest.mark.asyncio
async def test_the_selected_rows_are_durably_advanced_before_commit():
    """M3: selecting without advancing replays the same partition forever."""
    rec = []
    await select_partition(_factory({"A": 1, "B": 2, "C": 3}, rec), "binance",
                           ["A", "B", "C"], 2, 42)
    kinds = [r[0] for r in rec]
    assert "advance" in kinds, "the selected rows were never advanced"
    assert kinds.index("advance") < kinds.index("commit"), "advance after commit"
    params = next(r[1] for r in rec if r[0] == "advance")
    assert 42 in params.values(), f"the advance did not write run_seq: {params}"


@pytest.mark.asyncio
async def test_materialisation_seeds_one_generation_behind():
    """M4: seeding at the current run_seq is the falsified policy."""
    rec = []
    await select_partition(_factory({}, rec), "binance", ["A", "B"], 2, 7)
    seeds = next(r[1] for r in rec if r[0] == "materialise")
    assert 6 in seeds.values(), f"seed is not run_seq-1: {seeds}"
    assert 7 not in [v for k, v in seeds.items()
                     if "last_attempt" in k], "seeded at the current run_seq"


@pytest.mark.asyncio
async def test_the_first_run_floors_the_seed_at_zero():
    """CHECK (last_attempt_run_seq >= 0) must never be violated at run_seq=1."""
    rec = []
    await select_partition(_factory({}, rec), "binance", ["A"], 1, 1)
    seeds = next(r[1] for r in rec if r[0] == "materialise")
    assert all(v >= 0 for k, v in seeds.items() if "last_attempt" in k), seeds


@pytest.mark.asyncio
async def test_an_empty_active_set_claims_nothing_and_touches_no_session():
    rec = []
    assert await select_partition(_factory({}, rec), "binance", [], 5, 3) == []
    assert rec == [], "an empty universe still opened a transaction"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [dict(k=0), dict(k=-1), dict(run_seq=-1), dict(source="  ")])
async def test_invalid_inputs_are_refused(bad):
    kw = dict(source="binance", k=2, run_seq=5)
    kw.update(bad)
    with pytest.raises(ValueError):
        await select_partition(_factory({}, []), kw["source"], ["A"],
                               kw["k"], kw["run_seq"])
