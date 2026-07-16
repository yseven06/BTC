"""CP-F1D-2 — resolution-provenance schema locks (migration 0009 + model).

Columns only; stamping starts in CP-F1D-3. Pins three facts:
  - SignalPerformance carries resolution_version / resolution_source with the
    right shape (nullable, SMALLINT / TEXT — matching migration 0009 exactly);
  - migration 0009 honors the runner's contract (IF NOT EXISTS idempotency,
    one statement per line for the line-based splitter, no DO/$$ blocks,
    additive-only, signal_performances only);
  - NOTHING in production writes or reads the new columns yet. CP-F1D-3 must
    consciously retire the no-WRITER half of that lock when the stamps land.

Note: `resolution_source` as a NAME already exists in the codebase — it is the
trade_path.extra JSON key (trade_path.py / tracker.py / tpsl_analytics.py).
That is deliberate reuse of the same concept and value family; the locks below
are therefore attribute-shaped (`<perf>.resolution_source`), not name-grep.
"""
from __future__ import annotations

import re
from pathlib import Path

import app
from app.models.signal import SignalPerformance
from sqlalchemy import SmallInteger, Text

APP_DIR = Path(app.__file__).resolve().parent
MIGRATION = APP_DIR.parent / "migrations" / "0009_resolution_provenance.sql"


# ── model shape ──────────────────────────────────────────────────────────────

def test_model_columns_exist_nullable_and_typed():
    cols = SignalPerformance.__table__.columns
    ver, src = cols["resolution_version"], cols["resolution_source"]
    assert ver.nullable and src.nullable            # NULL = pre-stamp era, by contract
    assert isinstance(ver.type, SmallInteger)       # matches SMALLINT in 0009
    assert isinstance(src.type, Text)               # matches TEXT in 0009
    assert ver.default is None and src.default is None      # no ORM-side default
    assert ver.server_default is None and src.server_default is None  # no DB default


# ── migration shape (runner contract) ────────────────────────────────────────

def test_migration_file_honors_runner_contract():
    sql = MIGRATION.read_text(encoding="utf-8")
    stmts = [ln.strip() for ln in sql.splitlines()
             if ln.strip() and not ln.strip().startswith("--")]
    # exactly the two additive ALTERs, nothing else
    assert len(stmts) == 2
    for st in stmts:
        assert st.startswith("ALTER TABLE signal_performances ADD COLUMN IF NOT EXISTS")
        assert st.endswith(";")                     # line-based splitter contract
    assert "resolution_version SMALLINT" in stmts[0]
    assert "resolution_source TEXT" in stmts[1]
    # destructive / non-splittable constructs are banned in the statements
    # (comments are free to mention them — scan the statement body only)
    body = " ".join(stmts).upper()
    for banned in ("DROP", "UPDATE", "DELETE", "DEFAULT", "NOT NULL", "$$", "DO "):
        assert banned not in body, f"0009 must stay additive/idempotent — found {banned!r}"


# ── no writer, no reader yet ─────────────────────────────────────────────────

def test_no_production_writer_or_reader_yet():
    """The columns are write-opened but untouched: no `<x>.resolution_version`
    or `<x>.resolution_source` attribute access anywhere under app/ (the
    trade_path extra KEY of the same name is dict access, not attribute
    access, and stays out of scope by construction). CP-F1D-3 retires the
    writer half of this lock on purpose — with per-path stamp tests."""
    offenders = []
    for py in APP_DIR.rglob("*.py"):
        rel = py.relative_to(APP_DIR).as_posix()
        if rel == "models/signal.py":               # the definition itself
            continue
        src = py.read_text(encoding="utf-8")
        if re.search(r"\.resolution_(version|source)\b", src):
            offenders.append(rel)
    assert offenders == [], f"yeni kolonlara erken dokunan dosyalar: {offenders}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} F1D-2 schema tests PASSED")
