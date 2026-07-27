"""The test-safety guard itself (P2.2-a maintenance).

A guard nobody tests is a guard nobody can trust. These lock the policy — not
the plumbing — so that loosening it has to be deliberate.

The classifier is pure by design, so none of this touches os.environ, writes a
file, or opens a connection.
"""
import conftest
import pytest

PROD_LIKE = "postgresql+asyncpg://postgres.abcdefgh:pw@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
LOCAL = "postgresql+asyncpg://postgres:postgres@localhost:5432/zatetrade"
LOCAL_TEST = "postgresql+asyncpg://postgres:postgres@localhost:5432/zatetrade_test"
REMOTE_TEST = "postgresql+asyncpg://u:p@db-test.internal.example:5432/app"
UNKNOWN_REMOTE = "postgresql+asyncpg://u:p@10.20.30.40:5432/app"


# ── the production DSN must never pass ─────────────────────────────────────
def test_supabase_pooler_dsn_is_refused():
    safe, rule = conftest.classify_dsn(PROD_LIKE)
    assert safe is False
    assert rule == "yonetilen-veritabani-saglayicisi"


def test_production_environment_is_refused_even_with_a_local_dsn():
    """ENVIRONMENT=production alongside a local-looking DSN is a misconfiguration,
    not a safe combination — refuse it rather than trusting the DSN."""
    safe, rule = conftest.classify_dsn(LOCAL, environment="production")
    assert safe is False
    assert rule == "ENVIRONMENT=production"


def test_unknown_remote_host_is_refused_by_default():
    """The policy is an allow-list: a host the guard has never heard of is
    refused. A deny-list would silently wave through the next provider."""
    safe, rule = conftest.classify_dsn(UNKNOWN_REMOTE)
    assert safe is False
    assert rule == "taninmayan-uzak-host"


# ── legitimate targets must pass ───────────────────────────────────────────
@pytest.mark.parametrize("dsn,expected_rule", [
    (LOCAL, "yerel-host"),
    (LOCAL_TEST, "yerel-host"),
    (REMOTE_TEST, "test-isaretli"),
    (None, "dsn-yok"),
    ("", "dsn-yok"),
])
def test_safe_targets_are_allowed(dsn, expected_rule):
    safe, rule = conftest.classify_dsn(dsn)
    assert safe is True
    assert rule == expected_rule


def test_a_remote_host_needs_an_explicit_test_marker():
    assert conftest.classify_dsn("postgresql://u:p@ci-runner.example:5432/app_ci")[0] is True
    assert conftest.classify_dsn("postgresql://u:p@runner.example:5432/app_prod")[0] is False


# ── the guard must not leak what it is protecting ──────────────────────────
def test_refusal_reason_contains_no_dsn_no_host_no_password():
    _safe, rule = conftest.classify_dsn(PROD_LIKE)
    for secret in ("pw", "postgres.abcdefgh", "aws-1-us-east-1", "pooler.supabase.com",
                   "postgresql+asyncpg"):
        assert secret not in rule, f"the rule name leaked {secret!r}"


def test_the_hook_message_template_carries_no_dsn():
    """The rejection text a developer sees is assembled from the rule name only.
    A guard that prints the credential it is guarding defeats itself — and CI
    logs are routinely world-readable."""
    import inspect

    src = inspect.getsource(conftest.pytest_configure)
    # The message may reference the variable name, never interpolate the value.
    assert "{dsn}" not in src and "{host}" not in src
    assert "dsn" not in src.split("raise pytest.UsageError")[1].split(")")[0].replace("DSN", "")


# ── CI needs a real throwaway database, not "no DSN" ───────────────────────
def test_ci_requires_a_test_database(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(conftest, "_from_env_file", lambda key: None)

    with pytest.raises(pytest.UsageError) as err:
        conftest.pytest_configure(None)
    assert "ci-test-veritabani-eksik" in str(err.value)


def test_ci_accepts_a_marked_test_database(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", LOCAL_TEST)
    conftest.pytest_configure(None)   # must not raise


def test_ci_still_refuses_production(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", PROD_LIKE)
    with pytest.raises(pytest.UsageError) as err:
        conftest.pytest_configure(None)
    assert "yonetilen-veritabani-saglayicisi" in str(err.value)
    assert "pooler.supabase.com" not in str(err.value)
