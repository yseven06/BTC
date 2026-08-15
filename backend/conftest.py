"""Test bootstrap — refuse to run against a production database.

WHY THIS FILE EXISTS
--------------------
The suite is pure unit tests today, but nothing structural stopped that from
changing. `backend/.env` carries a real DSN, `app.database` builds an engine from
it at import time, and any test that reached for a session would have opened a
connection to whatever that DSN pointed at. A single `await db.execute(...)` in a
future test is all it would take to mutate production rows from a laptop.

The guard runs in `pytest_configure`, i.e. before collection — so it fails the
run rather than failing a test, and nothing under test has imported a session by
then.

ALLOW-LIST, NOT DENY-LIST
-------------------------
A deny-list of known production hosts is only ever as good as its last update; a
host it has not heard of is silently treated as safe, which is the wrong default
for this. So the rule is inverted: a DSN is refused unless it is positively
recognised as local or as a test database.

NOTHING IS EVER PRINTED
-----------------------
No message here contains the DSN, the host, the database name, the user or the
password — only the name of the rule that fired. A guard that leaks the
credential it is protecting in its own error text would defeat itself, and CI
logs are frequently world-readable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit

import pytest

_ENV_FILE = Path(__file__).resolve().parent / ".env"

# Hosts that are unambiguously not production.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal", "db", "postgres"}

# Substrings that positively identify a throwaway database. A host or database
# name has to carry one of these to be accepted when it is not local.
_TEST_MARKERS = ("test", "_ci", "-ci", "ephemeral", "sandbox")

# Recognised managed-Postgres providers. Not the security boundary — the
# allow-list above is — but hitting one of these produces a clearer message than
# the generic "unrecognised host" rejection.
_MANAGED_MARKERS = ("supabase.co", "supabase.com", "rds.amazonaws.com",
                    "neon.tech", "azure.com", "cockroachlabs.cloud", "planetscale")


def _from_env_file(key: str) -> Optional[str]:
    """Read one key from backend/.env. Mirrors pydantic-settings' precedence:
    a real environment variable wins, the file is only the fallback."""
    try:
        if not _ENV_FILE.is_file():
            return None
        for line in _ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _setting(key: str) -> Optional[str]:
    return os.environ.get(key) or _from_env_file(key)


def classify_dsn(dsn: Optional[str], environment: Optional[str] = None) -> Tuple[bool, str]:
    """(is_safe, rule) for a DSN. Pure — takes no I/O and returns no DSN content.

    Split out from the hook so the policy itself is testable without mutating the
    process environment.
    """
    if (environment or "").strip().lower() == "production":
        return False, "ENVIRONMENT=production"

    if not dsn or not dsn.strip():
        # Nothing to connect to. The suite is unit tests; this is the normal case.
        return True, "dsn-yok"

    try:
        parts = urlsplit(dsn.strip())
    except ValueError:
        return False, "dsn-ayristirilamadi"

    host = (parts.hostname or "").lower()
    dbname = (parts.path or "").lstrip("/").lower()

    if host in _LOCAL_HOSTS:
        return True, "yerel-host"
    if any(m in host for m in _TEST_MARKERS) or any(m in dbname for m in _TEST_MARKERS):
        return True, "test-isaretli"
    if any(m in host for m in _MANAGED_MARKERS):
        return False, "yonetilen-veritabani-saglayicisi"
    return False, "taninmayan-uzak-host"


def _in_ci() -> bool:
    return any(os.environ.get(k) for k in ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE"))


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    # The OHLCV progression integration gate is opt-in and marked; registering
    # the marker here keeps the ordinary suite free of PytestUnknownMarkWarning
    # without adding a pytest.ini the repo does not otherwise have.
    # `config` was previously unused (hence the noqa), and three DSN-guard tests
    # call this hook with None to exercise the classification logic alone. Guard
    # the access rather than change those callers: the DSN rule below is the
    # safety-critical part of this hook and must stay reachable either way.
    if config is not None:
        config.addinivalue_line(
            "markers",
            "integration: needs a real PostgreSQL; runs only when OHLCV_TEST_DSN is set",
        )
    dsn = _setting("DATABASE_URL")
    safe, rule = classify_dsn(dsn, _setting("ENVIRONMENT"))

    if not safe:
        raise pytest.UsageError(
            "Testler production veritabanina karsi calistirilamaz.\n"
            f"  kural       : {rule}\n"
            "  cozum       : DATABASE_URL'i yerel bir test veritabanina yonlendir "
            "(ornegin postgresql+asyncpg://postgres:postgres@localhost:5432/zatetrade_test) "
            "veya testleri DATABASE_URL tanimsizken calistir.\n"
            "  not         : DSN, host, kullanici ve parola bilerek yazdirilmadi."
        )

    # In CI a throwaway database is mandatory: "no DSN" is fine on a laptop
    # running unit tests, but in CI it silently hides the day someone adds a
    # DB-backed test and it starts reaching for whatever the runner has.
    if _in_ci() and rule == "dsn-yok":
        raise pytest.UsageError(
            "CI'da DATABASE_URL zorunludur ve bir test veritabanini gostermelidir.\n"
            "  kural       : ci-test-veritabani-eksik\n"
            "  cozum       : is akisina bir postgres servisi ekle ve DATABASE_URL'i "
            "ona yonlendir (adi 'test' icermeli)."
        )
