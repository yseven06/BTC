"""The integration gate's OWN safety contract — runs in the ordinary suite.

The integration modules skip themselves when OHLCV_TEST_DSN is unset, which
means their safety logic is exactly the code least likely to be exercised. These
tests therefore run WITHOUT a database and assert the guard directly, so a future
refactor cannot quietly reconnect an "integration" test to production.

No database, no network, no marker — deliberately part of the normal suite.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
GATES = ("tests/test_ohlcv_progression_integration.py",
         "tests/test_ohlcv_symbol_ledger_integration.py")


def _mod(rel):
    return importlib.import_module(
        "tests." + pathlib.Path(rel).stem)


@pytest.mark.parametrize("rel", GATES)
def test_the_gate_skips_when_the_test_dsn_is_absent(rel, monkeypatch):
    monkeypatch.delenv("OHLCV_TEST_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://prod:pw@prod-host/prod")
    with pytest.raises(BaseException) as exc:
        _mod(rel)._dsn()
    assert exc.typename == "Skipped", f"expected a skip, got {exc.typename}"


@pytest.mark.parametrize("rel", GATES)
def test_the_gate_fails_closed_when_the_test_dsn_equals_production(rel, monkeypatch):
    """A SKIP here would read as a pass. It must be a failure, and it must happen
    before any connection is attempted."""
    same = "postgresql+asyncpg://prod:pw@prod-host/prod"
    monkeypatch.setenv("OHLCV_TEST_DSN", same)
    monkeypatch.setenv("DATABASE_URL", same)
    with pytest.raises(BaseException) as exc:
        _mod(rel)._dsn()
    assert exc.typename == "Failed", f"expected a hard failure, got {exc.typename}"


@pytest.mark.parametrize("rel", GATES)
def test_whitespace_does_not_defeat_the_equality_guard(rel, monkeypatch):
    monkeypatch.setenv("OHLCV_TEST_DSN", "  postgresql+asyncpg://p:pw@h/db  ")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://p:pw@h/db")
    with pytest.raises(BaseException) as exc:
        _mod(rel)._dsn()
    assert exc.typename == "Failed"


@pytest.mark.parametrize("rel", GATES)
def test_a_distinct_disposable_dsn_is_accepted(rel, monkeypatch):
    monkeypatch.setenv("OHLCV_TEST_DSN", "postgresql+asyncpg://t:pw@127.0.0.1:5999/throwaway")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://prod:pw@prod-host/prod")
    assert _mod(rel)._dsn().endswith("/throwaway")


@pytest.mark.parametrize("rel", GATES)
def test_database_url_is_never_a_fallback(rel):
    """Structural: the gate must read OHLCV_TEST_DSN and use DATABASE_URL only for
    the equality refusal. A `getenv("DATABASE_URL")` feeding the returned value
    would be the exact defect this guards."""
    src = (BACKEND / rel).read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "_dsn")
    returns = [ast.unparse(n.value) for n in ast.walk(fn)
               if isinstance(n, ast.Return) and n.value is not None]
    assert returns == ["dsn"], f"_dsn returns something other than the test DSN: {returns}"
    # ast.unparse normalises quoting, so compare against the normalised form
    body = ast.unparse(fn)
    assert "os.environ.get('OHLCV_TEST_DSN')" in body,         "the gate does not read OHLCV_TEST_DSN"
    assert "or os.environ" not in body, "a fallback expression is present"
    # DATABASE_URL may appear ONLY in the equality refusal, never in the value path
    dsn_assign = [ast.unparse(n) for n in ast.walk(fn)
                  if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", "") == "dsn" for t in n.targets)]
    assert all("DATABASE_URL" not in a for a in dsn_assign),         f"DATABASE_URL feeds the returned DSN: {dsn_assign}"


@pytest.mark.parametrize("rel", GATES)
def test_the_module_is_marked_integration_and_is_opt_in(rel):
    src = (BACKEND / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    marks = [ast.unparse(n.value) for n in tree.body
             if isinstance(n, ast.Assign)
             and any(getattr(t, "id", "") == "pytestmark" for t in n.targets)]
    assert marks == ["pytest.mark.integration"], f"module marker is {marks}"


def test_the_ordinary_suite_needs_no_database():
    """Every module carrying the integration marker must gate on the test DSN, so
    a plain `pytest` run never opens a connection."""
    missing = []
    for p in (BACKEND / "tests").glob("*.py"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "pytest.mark.integration" in src and "OHLCV_TEST_DSN" not in src:
            missing.append(p.name)
    assert missing == [], f"integration modules without a DSN gate: {missing}"
