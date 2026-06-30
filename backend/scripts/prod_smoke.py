"""Pre-beta / post-deploy SMOKE — SAFE automated backend checks (A5).

Runs the NON-destructive, read-only subset of docs/SMOKE-TEST.md against a deployed
backend URL and prints PASS/FAIL. stdlib-only (urllib) so it runs anywhere without the
venv. Side-effectful checks (rate-limit burst, register/login, checkout, webhook,
Turnstile widget) are intentionally NOT automated here — see SMOKE-TEST.md for the
manual steps.

Usage:  python scripts/prod_smoke.py https://<api-domain>
        API_BASE=https://<api-domain> python scripts/prod_smoke.py
"""
import os
import sys
import urllib.request
import urllib.error

PREFIX = "/api/v1"
SEC_HEADERS = ["x-content-type-options", "x-frame-options", "referrer-policy",
               "strict-transport-security"]


def _req(url, method="GET", headers=None, timeout=10):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, (e.read().decode("utf-8", "replace") if e.fp else "")
    except Exception as e:
        return None, {}, f"ERR {e}"


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_BASE", "")).rstrip("/")
    if not base:
        print("usage: python scripts/prod_smoke.py https://<api-domain>"); sys.exit(2)
    print(f"== SAFE prod smoke vs {base} ==")
    checks = []  # (name, ok, detail)

    st, hdr, body = _req(base + "/health")
    checks.append(("/health 200 + healthy", st == 200 and "healthy" in body.lower(), f"status={st}"))
    checks.append(("/health no debug_mode leak", "debug_mode" not in body, "debug_mode present!" if "debug_mode" in body else "clean"))
    checks.append(("security headers present", all(h in hdr for h in SEC_HEADERS),
                   "missing: " + ",".join(h for h in SEC_HEADERS if h not in hdr)))

    for path in ("/docs", "/redoc", "/openapi.json"):
        st, _, _ = _req(base + path)
        checks.append((f"{path} => 404 (prod-closed)", st == 404, f"status={st}"))

    st, _, _ = _req(base + PREFIX + "/billing/plans")
    checks.append((f"{PREFIX}/billing/plans 200 (public)", st == 200, f"status={st}"))

    st, _, _ = _req(base + PREFIX + "/notifications/settings")
    checks.append((f"{PREFIX}/notifications/settings 401/403 (auth-gated)", st in (401, 403), f"status={st}"))

    # CORS: a disallowed Origin must NOT be echoed back as allowed.
    st, hdr, _ = _req(base + "/health", headers={"Origin": "https://evil.example.com"})
    acao = hdr.get("access-control-allow-origin", "")
    checks.append(("CORS rejects unknown origin", acao not in ("*", "https://evil.example.com"),
                   f"ACAO={acao or '(none)'}"))

    print()
    passed = 0
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  ({detail})")
        passed += ok
    print(f"\n{passed}/{len(checks)} safe checks PASSED")
    print("Manual (side-effectful, see SMOKE-TEST.md): rate-limit 429 burst, register/login, "
          "checkout 503-or-S7, webhook signature, Turnstile 428 widget, UptimeRobot.")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
