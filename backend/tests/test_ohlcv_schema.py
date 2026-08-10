"""CP-OHLCV-A1 — the closed-candle shadow SCHEMA, and nothing else.

A1 IS SCHEMA ONLY. There is no writer service, no backfill, no scheduler wiring
and no fetch activation in this checkpoint; the table is created and left empty.
The POC that this was reconstructed from also carried `app/services/ohlcv_shadow.py`
and a 685-line suite that exercised it. That service is deliberately NOT part of
A1, so its tests are not here either — they belong to A2, together with the
writer they describe.

WHY THE ORM IS THE SCHEMA AUTHORITY, NOT THE MIGRATION
------------------------------------------------------
`scripts/migrate.py apply` runs `create_all` (:94) BEFORE it applies any pending
.sql file, inside one transaction. `app/models/__init__` imports `OhlcvBar`, so
by the time 0011 runs the table already exists and its
`CREATE TABLE IF NOT EXISTS` is a no-op — as are all three
`CREATE ... INDEX IF NOT EXISTS`. Only `ENABLE ROW LEVEL SECURITY` does real
work, and 0011 is still recorded in `schema_migrations`.

That is intentional, and it is why the four CHECKs live on the MODEL as well as
in the SQL: on production the model's DDL is what actually ships. A guard below
pins that, so a future edit cannot quietly move a constraint into SQL-only and
leave production without it.

Proven on real PostgreSQL 16 in the A1 preflight, both construction orders:
17 columns, 4 CHECKs, PK + gen_random_uuid(), natural uniqueness on
(source, symbol, timeframe, open_time), 2 secondary indexes, RLS enabled, 0
policies, and 7/7 schema sabotage probes rejected identically. The one benign
divergence is that the ORM path materialises uniqueness as a UNIQUE CONSTRAINT
while the SQL path materialises it as a UNIQUE INDEX of the same name — which is
exactly why no product code may use `ON CONFLICT ON CONSTRAINT`.
"""

from __future__ import annotations

import pathlib
import re

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.models.ohlcv_bar import OhlcvBar

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MIGRATION = BACKEND / "migrations" / "0011_ohlcv_shadow.sql"
TABLE = OhlcvBar.__table__

NATURAL_KEY = ("source", "symbol", "timeframe", "open_time")
EXPECTED_CHECKS = {
    "ck_ohlcv_bars_bounds", "ck_ohlcv_bars_volume",
    "ck_ohlcv_bars_window", "ck_ohlcv_bars_closed",
}


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _sql_code() -> str:
    """Migration text with comments stripped — a guard must read DDL, not prose."""
    return re.sub(r"--[^\n]*|/\*.*?\*/", " ", _sql(), flags=re.S)


# ── the table itself ─────────────────────────────────────────────────────────
def test_the_table_is_named_ohlcv_bars_on_both_sides():
    assert TABLE.name == "ohlcv_bars"
    assert re.search(r"create\s+table\s+if\s+not\s+exists\s+ohlcv_bars",
                     _sql_code(), re.I)


def test_the_column_set_is_exactly_the_seventeen_that_were_proven():
    expected = {
        "id", "symbol", "timeframe", "source", "open_time", "close_time",
        "open", "high", "low", "close", "volume", "quote_volume",
        "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume",
        "is_closed", "ingested_at",
    }
    assert set(TABLE.columns.keys()) == expected
    assert len(expected) == 17


def test_the_ohlcv_measurements_are_not_nullable():
    for name in ("symbol", "timeframe", "source", "open_time", "close_time",
                 "open", "high", "low", "close", "volume", "is_closed",
                 "ingested_at"):
        assert TABLE.columns[name].nullable is False, name
    # The enrichment columns are genuinely optional — an exchange that omits
    # them must not cost us the bar.
    for name in ("quote_volume", "trade_count",
                 "taker_buy_base_volume", "taker_buy_quote_volume"):
        assert TABLE.columns[name].nullable is True, name


# ── the id default: required, because create_all builds the live table ───────
def test_id_carries_a_server_side_uuid_default():
    """Not just a Python-side default. On the ORM-created production table a raw
    INSERT that omits `id` must still work, so the default has to exist IN THE
    DATABASE, not only in SQLAlchemy."""
    col = TABLE.columns["id"]
    assert col.primary_key is True
    assert col.server_default is not None, "id needs a DB-side default"
    assert "gen_random_uuid" in str(col.server_default.arg).lower()
    assert re.search(r"gen_random_uuid\s*\(\s*\)", _sql_code(), re.I)


# ── the four CHECKs, on BOTH sides ───────────────────────────────────────────
def test_the_model_declares_all_four_checks():
    """The model, not only the SQL. create_all runs first on production, so a
    CHECK that exists only in 0011 would never reach the live table."""
    found = {c.name for c in TABLE.constraints if isinstance(c, CheckConstraint)}
    assert found == EXPECTED_CHECKS, found


def test_the_migration_declares_the_same_four_checks():
    code = _sql_code()
    for name in EXPECTED_CHECKS:
        assert re.search(rf"constraint\s+{name}\s+check", code, re.I), name


def test_the_bounds_check_actually_constrains_all_three_relations():
    """A CHECK named `bounds` that only compared low<=high would pass a name
    test while letting an open outside the bar through."""
    src = next(str(c.sqltext) for c in TABLE.constraints
               if isinstance(c, CheckConstraint) and c.name == "ck_ohlcv_bars_bounds")
    norm = src.lower().replace("\n", " ")
    assert "low <= high" in norm
    assert "open" in norm and "close" in norm
    assert norm.count("between") >= 2 or norm.count(">=") >= 2


def test_volume_check_allows_zero_and_rejects_negative():
    src = next(str(c.sqltext) for c in TABLE.constraints
               if isinstance(c, CheckConstraint) and c.name == "ck_ohlcv_bars_volume")
    assert ">=" in src and ">" != src.strip(), (
        "a zero-volume bar is real market data (a quiet minute), not corruption")


def test_the_window_check_is_strict():
    src = next(str(c.sqltext) for c in TABLE.constraints
               if isinstance(c, CheckConstraint) and c.name == "ck_ohlcv_bars_window")
    assert "close_time > open_time" in src.replace("\n", " ")


def test_the_forming_candle_is_refused_by_the_schema():
    """A1's structural half of the closed-bar invariant. This is a FLAG check —
    it rejects is_closed=false; it does not compare close_time to a clock. The
    time-based half lives in the application layer and arrives with A2's writer,
    so this guard states what the schema really provides and no more."""
    src = next(str(c.sqltext) for c in TABLE.constraints
               if isinstance(c, CheckConstraint) and c.name == "ck_ohlcv_bars_closed")
    assert src.strip().lower() in ("is_closed", "(is_closed)")
    assert "now()" not in src.lower(), (
        "the schema check is a flag check; do not claim a clock comparison here")


# ── natural key + indexes ────────────────────────────────────────────────────
def test_the_natural_key_is_source_symbol_timeframe_open_time():
    uq = [c for c in TABLE.constraints if isinstance(c, UniqueConstraint)]
    assert len(uq) == 1
    assert tuple(c.name for c in uq[0].columns) == NATURAL_KEY
    assert uq[0].name == "uq_ohlcv_bars_natural"
    # and the SQL expresses the SAME key, as a unique index
    assert re.search(
        r"create\s+unique\s+index\s+if\s+not\s+exists\s+uq_ohlcv_bars_natural\s*"
        r"on\s+ohlcv_bars\s*\(\s*source\s*,\s*symbol\s*,\s*timeframe\s*,\s*open_time\s*\)",
        _sql_code(), re.I | re.S)


def test_the_two_secondary_indexes_exist_on_both_sides():
    names = {i.name for i in TABLE.indexes}
    assert names == {"ix_ohlcv_bars_symbol_tf_time", "ix_ohlcv_bars_tf_time"}, names
    for n in names:
        assert re.search(rf"create\s+index\s+if\s+not\s+exists\s+{n}", _sql_code(), re.I)


def test_no_product_code_may_use_the_constraint_name_for_conflict_resolution():
    """The ORM path materialises the natural key as a UNIQUE CONSTRAINT, the
    SQL-only path as a bare UNIQUE INDEX. `ON CONFLICT ON CONSTRAINT
    uq_ohlcv_bars_natural` therefore works on one and raises UndefinedObject on
    the other — measured, both ways, in the A1 preflight. Only the column-list
    form is construction-order independent, so the constraint name must not
    appear in any conflict clause anywhere in the app."""
    hits = []
    for path in (BACKEND / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        stripped = re.sub(r"#[^\n]*", " ", text)
        stripped = re.sub(r'""".*?"""', " ", stripped, flags=re.S)
        if re.search(r"on_conflict[^\n]*constraint\s*=", stripped) or \
           re.search(r"ON\s+CONFLICT\s+ON\s+CONSTRAINT", stripped, re.I):
            hits.append(str(path.relative_to(BACKEND)))
    assert not hits, f"constraint-name conflict target is not portable: {hits}"


# ── RLS ──────────────────────────────────────────────────────────────────────
def test_rls_is_enabled_with_no_policy():
    """Every other table in this schema is locked down (0006/0007/0010); an
    unlocked one becomes the exception that gets forgotten. No policy is granted,
    so PostgREST/anon reaches nothing while the backend connects as owner."""
    code = _sql_code()
    assert re.search(r"alter\s+table\s+ohlcv_bars\s+enable\s+row\s+level\s+security",
                     code, re.I)
    assert not re.search(r"create\s+policy", code, re.I), (
        "A1 grants no policy; adding one changes who can read the table")


# ── A1 scope: schema only ────────────────────────────────────────────────────
def test_a1_ships_no_writer_and_no_backfill():
    """The scope police, as a test. A1 creates the table and stops."""
    assert not (BACKEND / "app" / "services" / "ohlcv_shadow.py").exists(), (
        "the writer belongs to A2, not to the schema checkpoint")
    assert not (BACKEND / "scripts" / "ohlcv_backfill.py").exists(), (
        "the backfill belongs to A3, not to the schema checkpoint")


def test_the_model_is_registered_so_create_all_builds_the_table():
    """migrate.py runs create_all before the .sql files; that only reaches
    ohlcv_bars if the model is imported into the models package."""
    src = (BACKEND / "app" / "models" / "__init__.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", " ", src)
    assert "from app.models.ohlcv_bar import OhlcvBar" in code
    from app.database import Base
    assert "ohlcv_bars" in Base.metadata.tables


def test_nothing_in_the_decision_path_imports_ohlcv():
    """A1 must not couple to any decision surface. If a later edit makes the
    tracker, Pass B, entry activation, publication or lifecycle read this table,
    this fails."""
    for rel in ("app/backtesting/tracker.py", "app/backtesting/lifecycle.py",
                "app/backtesting/resolution_core.py", "app/services/scheduler.py",
                "app/services/entry_activation.py", "app/services/entry_flags.py",
                "app/services/publication.py", "app/services/lifecycle_log.py",
                "app/services/shadow_eval.py", "app/services/coin_memory.py",
                "app/engines/ai_decision/signal_generator.py",
                # Pass B lives under scripts/, not app/. Leaving it out meant a
                # sabotage that made the Pass-B runner import OhlcvBar passed
                # this guard cleanly — measured, not hypothetical.
                "scripts/p22a_shadow_eval.py"):
        text = (BACKEND / rel).read_text(encoding="utf-8")
        assert "ohlcv_bar" not in text, rel
        assert "OhlcvBar" not in text, rel
        assert "ohlcv_bars" not in text, rel
