"""A3: the Stripe-unconfigured mock self-activation (grants a paid tier WITHOUT
payment) must run ONLY in genuine local development (DEBUG=true AND
ENVIRONMENT=='development'). Every other env must hard-fail 503."""
from app.api.routes.billing import _mock_activation_allowed


def test_mock_gate_matrix():
    # genuine local dev → mock ALLOWED
    assert _mock_activation_allowed(True, "development") is True
    # staging (DEBUG=true) → BLOCKED — this is the residual A3 closes
    assert _mock_activation_allowed(True, "staging") is False
    # production → BLOCKED (both the normal DEBUG=false and a misconfig DEBUG=true)
    assert _mock_activation_allowed(False, "production") is False
    assert _mock_activation_allowed(True, "production") is False
    # DEBUG off even in development → BLOCKED
    assert _mock_activation_allowed(False, "development") is False
    # any other non-'development' env value → BLOCKED (strict match per A3 decision)
    for env in ("dev", "local", "test", "preview", "prod", ""):
        assert _mock_activation_allowed(True, env) is False


if __name__ == "__main__":
    test_mock_gate_matrix()
    print("PASS A3 mock-gate matrix (mock allowed only in DEBUG+development)")
