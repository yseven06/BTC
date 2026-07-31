"""CP-MACRO-SHADOW-FETCH-SECRET-REDACTION — the key must not reach a log line.

On 2026-07-31 the shadow FRED fetch ran for thirty minutes and wrote a live API
key into the container log four times. Our code never logged it: `httpx` does,
at INFO, with the request's full URL — and the URL carries `api_key=`.

The centrepiece of this file is a PAIR. One test proves the hazard is real by
reproducing the leak with the redaction removed; the next proves it is closed
with the redaction in place. Either alone would be worthless: a passing
"no sentinel found" is equally consistent with a leak that was fixed and with a
test that never exercised the leaking code path at all.

Everything is asserted on CAPTURED, FORMATTED log output — the bytes a handler
would actually write — not on source text. Redaction that only satisfies a
source scan is not redaction.

No network: every request goes through a MockTransport. No real credential: the
key is an obvious sentinel and a test asserts it never appears anywhere.
"""
import asyncio
import io
import logging
import re

import httpx
import pytest

from app import log_redaction as lr
from app.collectors import macro_collector as mc
from app.services import macro_shadow as ms
from app.services import macro_shadow_fetch as msf

# Deliberately unmistakable, and long enough that a partial leak still trips.
SENTINEL = "SENTINEL-SECRET-VALUE-0123456789-DO-NOT-LOG"


class _Capture:
    """Captures FORMATTED output from the root logger — what a handler writes."""

    def __init__(self, *, redact: bool, level=logging.INFO):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        self.redact = redact
        self.level = level
        self._saved = None
        self._saved_levels = {}

    def __enter__(self):
        root = logging.getLogger()
        self._saved = (list(root.handlers), root.level, list(root.filters))
        for name in lr.NOISY_HTTP_LOGGERS:
            self._saved_levels[name] = logging.getLogger(name).level
            logging.getLogger(name).setLevel(self.level)
        root.handlers = [self.handler]
        root.filters = []
        root.setLevel(self.level)
        if self.redact:
            # Never `quiet_http_loggers`: the whole point is to prove the filter
            # holds while httpx is still shouting at INFO. Silencing it would
            # make the test pass for the wrong reason.
            lr.install(quiet_http_loggers=False)
        return self

    def __exit__(self, *exc):
        root = logging.getLogger()
        root.handlers, root.level, root.filters = self._saved
        for name, lvl in self._saved_levels.items():
            logging.getLogger(name).setLevel(lvl)
        return False

    @property
    def text(self) -> str:
        self.handler.flush()
        return self.stream.getvalue()


def _client(handler=None):
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [
            {"date": "2026-06-01", "value": "4.33"}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler or _h))


async def _do_request(url_params=None):
    async with _client() as c:
        r = await c.get("https://api.stlouisfed.org/fred/series/observations",
                        params=url_params or {"series_id": "FEDFUNDS",
                                              "api_key": SENTINEL})
        return r


# ══════════════════════════════════════════════════════════════════════════════
# 1 · THE PAIR — the hazard is real, and it is closed
# ══════════════════════════════════════════════════════════════════════════════
def test_the_leak_is_real_without_redaction():
    """Reproduces the 2026-07-31 incident.

    Without this, the test below proves nothing: "the sentinel is absent" is
    equally true of a working redaction and of a code path that never logged.
    """
    with _Capture(redact=False) as cap:
        asyncio.run(_do_request())
    assert "HTTP Request" in cap.text, "httpx did not log — the pair is meaningless"
    assert SENTINEL in cap.text, "the leak did not reproduce"


def test_the_leak_is_closed_with_redaction():
    """Same request, same httpx level, filter installed."""
    with _Capture(redact=True) as cap:
        asyncio.run(_do_request())
    assert "HTTP Request" in cap.text, "the request line must still be logged"
    assert SENTINEL not in cap.text
    assert "api_key=<redacted>" in cap.text
    # And the rest of the line survives — redaction, not deletion.
    assert "series_id=FEDFUNDS" in cap.text
    assert "200" in cap.text


# ══════════════════════════════════════════════════════════════════════════════
# 2 · EVERY LEVEL AND THE EXCEPTION PATH
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("level,emit", [
    (logging.INFO, "info"), (logging.WARNING, "warning"),
    (logging.ERROR, "error"), (logging.CRITICAL, "critical"),
])
def test_no_level_escapes_the_filter(level, emit):
    """Lowering a logger's level would close INFO and leave these wide open."""
    with _Capture(redact=True, level=logging.DEBUG) as cap:
        log = logging.getLogger("app.test")
        getattr(log, emit)("calling %s",
                           f"https://x.invalid/o?series_id=A&api_key={SENTINEL}")
    assert SENTINEL not in cap.text
    assert "<redacted>" in cap.text


def test_an_http_status_error_traceback_is_redacted():
    """httpx builds HTTPStatusError's message as "... for url '{url}'"
    (httpx/_models.py:809-818), so the exception itself carries the key —
    at ERROR, where no level cap helps."""
    def _fail(request):
        return httpx.Response(401, json={"error": "bad key"})

    async def _run():
        async with _client(_fail) as c:
            r = await c.get("https://api.stlouisfed.org/fred/series/observations",
                            params={"series_id": "FEDFUNDS", "api_key": SENTINEL})
            r.raise_for_status()

    with _Capture(redact=True) as cap:
        try:
            asyncio.run(_run())
        except httpx.HTTPStatusError:
            logging.getLogger("app.test").exception("fetch failed")
    assert SENTINEL not in cap.text
    assert "Traceback" in cap.text, "the traceback must survive, only masked"
    assert "401" in cap.text


def test_the_raw_exception_message_really_did_contain_the_key():
    """Pins the premise of the test above against httpx's own formatting, so a
    library change that stops embedding the URL turns this red rather than
    silently making the protection untested."""
    def _fail(request):
        return httpx.Response(403, json={})

    async def _run():
        async with _client(_fail) as c:
            r = await c.get("https://x.invalid/o",
                            params={"api_key": SENTINEL})
            r.raise_for_status()

    with pytest.raises(httpx.HTTPStatusError) as err:
        asyncio.run(_run())
    assert SENTINEL in str(err.value)
    assert SENTINEL not in lr.redact_text(str(err.value))


def test_stack_info_is_redacted():
    """The secret is placed IN `stack_info`, not in the message.

    An earlier version of this test logged the secret in the MESSAGE with
    `stack_info=True`. It passed with `stack_info` redaction deleted — the
    message path was doing all the work and the stack text, being a traceback of
    the test's own call site, never contained a credential. A sabotage run caught
    that; the record is built by hand here so the stack field is the only place
    the sentinel lives."""
    def _record():
        rec = logging.LogRecord("app.test", logging.WARNING, __file__, 1,
                                "harmless", (), None)
        rec.stack_info = (
            'Stack (most recent call last):\n'
            '  File "worker.py", line 8, in run\n'
            f'    client.get("https://x/?series_id=A&api_key={SENTINEL}")\n')
        return rec

    record = _record()
    assert lr.SecretRedactingFilter().filter(record) is True
    assert SENTINEL not in record.stack_info
    assert "api_key=<redacted>" in record.stack_info
    assert "series_id=A" in record.stack_info, "the stack must survive, only masked"

    # And end to end on a FRESH record, so the formatter — which appends
    # `stack_info` itself — cannot reintroduce what the check above masked.
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").handle(_record())
    assert SENTINEL not in cap.text


# ══════════════════════════════════════════════════════════════════════════════
# 3 · BOTH FRED PATHS
# ══════════════════════════════════════════════════════════════════════════════
def test_the_shadow_fetch_path_logs_no_secret(monkeypatch):
    class _S:
        MACRO_SHADOW_FETCH_ENABLED = True
        FRED_API_KEY = SENTINEL
        MACRO_FRED_FETCH_ENABLED = False
    monkeypatch.setattr(msf, "get_settings", lambda: _S())
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    msf.reset_cache_for_tests()
    real = httpx.AsyncClient
    monkeypatch.setattr(msf.httpx, "AsyncClient",
                        lambda *a, **k: real(transport=httpx.MockTransport(
                            lambda r: httpx.Response(200, json={"observations": [
                                {"date": "2026-06-01", "value": "4.33"}]}))))
    with _Capture(redact=True) as cap:
        snap = asyncio.run(msf.get_shadow_macro_snapshot())
    msf.reset_cache_for_tests()
    assert snap is not None and snap["fetch_status"] == "ok"
    assert SENTINEL not in cap.text
    # Our own line is present and carries host+path+status only.
    assert "[MacroShadowFetch] GET api.stlouisfed.org/fred/series/observations" in cap.text
    assert "api_key" not in cap.text.replace("api_key=<redacted>", "")


def test_the_shadow_fetch_arms_the_redaction_itself(monkeypatch):
    """The fetcher must not depend on `main.py` having run first.

    In the test above `_Capture(redact=True)` installs the filter, so deleting
    the fetcher's own `install()` call changed nothing and the sabotage went
    unnoticed. Here the capture starts with redaction OFF and the guard has to
    come from the code under test.

    The fetch also runs from the scheduler, from a worker process, and from
    admin generation — none of which is guaranteed to have imported `main`."""
    class _S:
        MACRO_SHADOW_FETCH_ENABLED = True
        FRED_API_KEY = SENTINEL
        MACRO_FRED_FETCH_ENABLED = False
    monkeypatch.setattr(msf, "get_settings", lambda: _S())
    monkeypatch.setattr(msf.job_guard, "remaining_budget", lambda job_id: None)
    msf.reset_cache_for_tests()
    real = httpx.AsyncClient
    monkeypatch.setattr(msf.httpx, "AsyncClient",
                        lambda *a, **k: real(transport=httpx.MockTransport(
                            lambda r: httpx.Response(200, json={"observations": [
                                {"date": "2026-06-01", "value": "4.33"}]}))))

    with _Capture(redact=False) as cap:
        assert not lr.is_installed(), "precondition failed: redaction was already on"
        snap = asyncio.run(msf.get_shadow_macro_snapshot())
        assert lr.is_installed(), "the shadow fetch did not arm the redaction"
        # Silence is not proof. httpx being muted would satisfy the assertion
        # below on its own, so a secret-bearing record is pushed through the
        # handler directly: only a filter the FETCH installed can mask it.
        logging.getLogger("app.test").error("u=https://x/?api_key=%s", SENTINEL)
    msf.reset_cache_for_tests()

    assert snap is not None and snap["fetch_status"] == "ok"
    assert SENTINEL not in cap.text
    assert "api_key=<redacted>" in cap.text, "the filter was not actually installed"


def test_the_production_collector_path_logs_no_secret(monkeypatch):
    """The same latent leak. This path has never been switched on, which is the
    only reason it has not leaked yet."""
    class _S:
        FRED_API_KEY = SENTINEL
        MACRO_FRED_FETCH_ENABLED = True
        MACRO_SHADOW_FETCH_ENABLED = False
    monkeypatch.setattr(mc, "get_settings", lambda: _S())
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()
    collector = mc.MacroCollector()
    assert collector._fred_key == SENTINEL, "the gate must be open for this test"
    collector.client = _client()
    # Pass 1 — production behaviour: the collector arms the guard, which also
    # quiets httpx, so the request line is not emitted at all.
    with _Capture(redact=True) as cap:
        value = asyncio.run(collector.fetch_fred_series("FEDFUNDS"))
        # Asserted INSIDE the block: the capture context restores logger levels
        # on exit, so checking afterwards would read the restored value and pass
        # regardless of what the collector did.
        assert logging.getLogger("httpx").level == logging.WARNING, \
            "the collector did not arm the guard"
    assert value == 4.33
    assert SENTINEL not in cap.text

    # Pass 2 — silence is not the proof. This test would pass just as well
    # against a collector that leaked but happened to be muted, so the same
    # request goes out through the collector's OWN client with httpx left at
    # INFO, and the redaction has to hold on its own.
    #
    # Issued directly rather than through `fetch_fred_series`, because that
    # method arms the guard itself and would re-mute httpx before the request —
    # the very silencing this pass is trying to remove.
    with _Capture(redact=True) as cap2:
        asyncio.run(collector.client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": "DGS10", "api_key": SENTINEL,
                    "file_type": "json"}))
    asyncio.run(collector.close())
    mc._MACRO_CACHE.clear()
    mc._MACRO_CACHE_EXPIRY.clear()
    assert "HTTP Request" in cap2.text, "httpx was still muted — nothing was proved"
    assert SENTINEL not in cap2.text
    assert "api_key=<redacted>" in cap2.text
    assert "series_id=DGS10" in cap2.text


# ══════════════════════════════════════════════════════════════════════════════
# 4 · URL SHAPES
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("raw,must_go,must_stay", [
    ("https://x/?api_key=SEC", "SEC", "https://x/"),
    ("https://x/?API_KEY=SEC", "SEC", "API_KEY"),
    ("https://x/?Api_Key=SEC", "SEC", "Api_Key"),
    ("https://x/?a=1&api_key=SEC&b=2", "SEC", "b=2"),
    ("https://x/?api_key=SEC&api_key=SEC2", "SEC2", "api_key"),
    ("https://x/?token=SEC&access_token=SEC2", "SEC2", "access_token"),
    ("https://x/?api_key=a%2Fb%3Dc", "a%2Fb%3Dc", "https://x/"),
    ("https://x/?api_key=SEC#frag", "SEC", "#frag"),
    ("https://x/?secret=SEC;key=SEC2", "SEC2", "secret"),
    ("not a url at all api_key=SEC trailing", "SEC", "trailing"),
    ("https://x/?apikey=SEC", "SEC", "apikey"),
    ("https://x/?client_secret=SEC", "SEC", "client_secret"),
])
def test_url_shapes_are_redacted_without_losing_the_rest(raw, must_go, must_stay):
    out = lr.redact_url(raw)
    assert must_go not in out, out
    assert must_stay in out, out
    assert lr.REDACTED in out


def test_every_occurrence_of_a_repeated_parameter_is_masked():
    out = lr.redact_url("https://x/?api_key=A1&b=2&api_key=A2&api_key=A3")
    assert "A1" not in out and "A2" not in out and "A3" not in out
    assert out.count(lr.REDACTED) == 3
    assert "b=2" in out


def test_parameter_order_is_preserved():
    out = lr.redact_url("https://x/?z=1&api_key=S&a=2&token=T&m=3")
    assert out.index("z=1") < out.index("api_key") < out.index("a=2") \
        < out.index("token") < out.index("m=3")


@pytest.mark.parametrize("safe", [
    # Underscore-joined: a word character, so `\b` would NOT have matched here.
    # These cases pass either way and prove nothing about the lookbehind.
    "https://x/?cache_key=abc", "https://x/?sort_key=name",
    "https://x/?series_key=FEDFUNDS", "https://x/?monkeypatch=1",
    "https://x/?series_id=FEDFUNDS&file_type=json",
    # Hyphen-joined: THIS is what the lookbehind is for. `-` IS a word boundary,
    # so `\b(key|...)` matches the tail of `sort-key` and redacts an ordinary
    # parameter. A sabotage run swapped the lookbehind for `\b` and every case
    # above still passed; these are the ones that catch it.
    "https://x/?sort-key=name",
    "https://x/?partition-key=abc&limit=10",
    "https://x/?idempotency-key=7f3a&x-request-id=9",
    "https://x/?public-token-count=3",
])
def test_ordinary_parameters_are_not_over_redacted(safe):
    """A redactor that hides ordinary telemetry destroys the signal it exists to
    keep readable, so the boundary has to be exact in BOTH directions.

    `(?<![\\w-])` excludes the hyphen as well as word characters: `api-key=`
    still matches as a whole (it is on the list), while `sort-key=` does not
    match at all."""
    assert lr.redact_url(safe) == safe


def test_an_empty_value_is_left_alone():
    """Rewriting `api_key=` to `<redacted>` would make an ABSENT credential look
    present — a false record pointing the other way."""
    assert lr.redact_url("https://x/?api_key=&b=1") == "https://x/?api_key=&b=1"


@pytest.mark.parametrize("bad", [
    "", "://///", "https://", "?api_key=", "%%%%", "https://x/?api_key",
    "http://[::1]:99999/?api_key=S", "\x00\x01api_key=S",
])
def test_malformed_input_never_raises(bad):
    out = lr.redact_url(bad)
    assert isinstance(out, str)
    assert "S" not in out or "api_key=<redacted>" in out or "api_key" not in out


def test_a_non_string_url_object_is_handled():
    url = httpx.URL(f"https://x/o?api_key={SENTINEL}&series_id=A")
    out = lr.redact_url(url)
    assert SENTINEL not in out
    assert "series_id=A" in out


# ══════════════════════════════════════════════════════════════════════════════
# 5 · FILTER MECHANICS
# ══════════════════════════════════════════════════════════════════════════════
def test_numeric_args_survive_so_format_specs_do_not_break():
    """httpx's line is `'HTTP Request: %s %s "%s %d %s"'` — replacing the `%d`
    argument with a string would raise inside logging and lose the record."""
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").info(
            'x %s "%s %d %s"', f"https://x/?api_key={SENTINEL}", "HTTP/1.1", 200, "OK")
    assert SENTINEL not in cap.text
    assert "200" in cap.text
    assert "OK" in cap.text


def test_dict_style_args_are_redacted():
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").info("%(u)s", {"u": f"?api_key={SENTINEL}"})
    assert SENTINEL not in cap.text


def test_a_preformatted_message_is_redacted():
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").info(f"url=https://x/?api_key={SENTINEL}")
    assert SENTINEL not in cap.text


def test_the_filter_never_drops_a_record():
    """It masks content; dropping would hide an error."""
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").error("boom %s", f"?api_key={SENTINEL}")
    assert "boom" in cap.text
    assert SENTINEL not in cap.text


def test_install_is_idempotent():
    with _Capture(redact=True) as cap:
        lr.install(quiet_http_loggers=False)
        lr.install(quiet_http_loggers=False)
        filters = [f for f in cap.handler.filters
                   if isinstance(f, lr.SecretRedactingFilter)]
        assert len(filters) == 1
        logging.getLogger("app.test").info("?api_key=%s", SENTINEL)
    assert cap.text.count(lr.REDACTED) == 1


def test_the_filter_is_attached_to_handlers_not_only_the_logger():
    """A filter on a LOGGER only sees records that logger created — records
    propagating up from `httpx` sail straight past it. Handlers see everything."""
    with _Capture(redact=True) as cap:
        assert any(isinstance(f, lr.SecretRedactingFilter)
                   for f in cap.handler.filters), "handler has no redaction filter"
        assert lr.is_installed()


def test_a_hostile_argument_does_not_make_the_filter_raise():
    """A `__str__` that raises is stdlib's problem — `logging` catches it in the
    formatter and reports a logging error. What must NOT happen is the FILTER
    raising, because a filter that raises takes down the caller."""
    class _Hostile:
        def __str__(self):
            raise RuntimeError("hostile __str__")

    record = logging.LogRecord("app.test", logging.INFO, __file__, 1,
                               "v=%s", (_Hostile(),), None)
    assert lr.SecretRedactingFilter().filter(record) is True


def test_a_format_string_whose_secret_is_a_placeholder_still_renders():
    """THE defect these tests found. `"token=%s"` redacted naively becomes
    `"token=<redacted>"` — the `%s` is gone, `msg % args` raises inside logging,
    and the ENTIRE record is dropped. Losing the line is a worse outcome than
    the leak: the secret still has to go, and the record still has to arrive."""
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").warning("u=https://x/?token=%s", SENTINEL)
    assert SENTINEL not in cap.text
    assert "u=https://x/?token=" in cap.text, "the record was dropped"
    assert lr.REDACTED in cap.text


def test_a_pathological_format_string_keeps_the_record():
    """Belt and braces beyond the placeholder rule: whatever the format string
    is, the line survives with its arguments redacted."""
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").error("%s api_key=%s%%", "ctx", SENTINEL)
    assert SENTINEL not in cap.text
    assert "ctx" in cap.text, "the record was dropped"


def test_production_install_also_quiets_the_http_loggers():
    """The names are written out LITERALLY here on purpose.

    The first version of this test looped over `lr.NOISY_HTTP_LOGGERS`, which is
    the very constant it was meant to police — deleting `httpcore` from that
    tuple shrank the loop to match and the test still passed. `httpcore` is the
    connection layer under httpx; it is at DEBUG today and one config change
    away from emitting URLs of its own."""
    required = {"httpx", "httpcore"}
    assert required <= set(lr.NOISY_HTTP_LOGGERS), \
        f"a noisy HTTP logger was dropped from the guard: {required - set(lr.NOISY_HTTP_LOGGERS)}"

    root = logging.getLogger()
    names = sorted(required | set(lr.NOISY_HTTP_LOGGERS))
    saved = {n: logging.getLogger(n).level for n in names}
    handlers, filters = list(root.handlers), list(root.filters)
    try:
        for n in names:
            logging.getLogger(n).setLevel(logging.INFO)
        lr.install()
        for n in names:
            assert logging.getLogger(n).level == logging.WARNING, n
    finally:
        for n, lvl in saved.items():
            logging.getLogger(n).setLevel(lvl)
        root.handlers, root.filters = handlers, filters


def test_redaction_fails_safe_when_the_regex_itself_raises(monkeypatch):
    """If the redactor breaks, it must break CLOSED.

    Nothing in these tests otherwise makes the regex raise, so a fallback that
    returned the raw text would have gone unnoticed — and it is precisely the
    branch that runs on the day something unexpected reaches it."""
    class _Exploding:
        def sub(self, *a, **k):
            raise RuntimeError("regex engine blew up")

    monkeypatch.setattr(lr, "_SENSITIVE_RE", _Exploding())

    out = lr.redact_text(f"url=https://x/?api_key={SENTINEL}")
    assert SENTINEL not in out, "redaction failed OPEN — it returned the raw text"
    assert out == lr.REDACTED

    # And the filter still neither raises nor leaks while the redactor is broken.
    with _Capture(redact=True) as cap:
        logging.getLogger("app.test").error("boom %s", f"?api_key={SENTINEL}")
    assert SENTINEL not in cap.text


def test_importing_the_application_arms_the_redaction():
    """`app/main.py` must call `install()` itself.

    Every other test in this file installs the filter through `_Capture`, so
    deleting the call in `main.py` left them all green while production shipped
    unprotected — a sabotage run found exactly that. This drives the real module
    against a root logger that starts WITHOUT redaction."""
    import importlib
    import app.main

    root = logging.getLogger()
    saved_handlers, saved_filters = list(root.handlers), list(root.filters)
    saved_levels = {n: logging.getLogger(n).level for n in lr.NOISY_HTTP_LOGGERS}
    original_app = app.main.app
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        root.handlers = [handler]
        root.filters = []
        assert not lr.is_installed(), "precondition failed: redaction was already on"

        importlib.reload(app.main)

        assert lr.is_installed(), "importing app.main did not arm the redaction"
        # Behavioural, not structural: a real record must come out masked.
        logging.getLogger("app.test").warning("u=https://x/?api_key=%s", SENTINEL)
        handler.flush()
        assert SENTINEL not in stream.getvalue()
        assert lr.REDACTED in stream.getvalue()
    finally:
        # Rebind the FastAPI instance the rest of the suite holds a reference to,
        # so the reload leaves nothing behind.
        app.main.app = original_app
        root.handlers, root.filters = saved_handlers, saved_filters
        for n, lvl in saved_levels.items():
            logging.getLogger(n).setLevel(lvl)


def test_the_sentinel_appears_in_no_source_file():
    """Belt and braces: the test's own key must not have been pasted anywhere."""
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    hits = []
    for path in (backend / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if SENTINEL in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    assert hits == [], hits


# ══════════════════════════════════════════════════════════════════════════════
# 6 · THE `internal_error` TELEMETRY FIX
# ══════════════════════════════════════════════════════════════════════════════
def _snapshot_with_both_series():
    return {"configured": True, "fetch_status": "ok", "series": {
        ms.SERIES_FEDFUNDS: {"value": 4.33, "observation_date": "2026-06-01",
                             "fetch_status": "ok"},
        ms.SERIES_DGS10: {"value": 4.10, "observation_date": "2026-07-29",
                          "fetch_status": "ok"}}}


def _built(snapshot):
    return ms.build_macro_shadow_from_snapshot(
        decision_time="2026-08-01T00:00:00+00:00", snapshot=snapshot,
        production_macro_score=50.0, production_macro_bias="neutral",
        production_macro_confidence=25.0, production_total_confidence=62.0,
        engine_count=9, publish_threshold=65.0, production_publish_verdict="dropped")


@pytest.mark.parametrize("sid", list(ms.UNSCORED_SERIES))
def test_an_unrequested_series_is_not_reported_as_an_internal_error(sid):
    """It said `requested=false`, `excluded_from_score_reason=not_read_by_engine`,
    `error_class=null` AND `fetch_status=internal_error` on 114 live rows. A row
    cannot both have not been asked and have failed internally."""
    entry = _built(_snapshot_with_both_series())["series"][sid]
    assert entry["fetch_status"] == "not_requested"
    assert entry["fetch_status"] != "internal_error"
    assert entry["requested"] is False
    assert entry["used_by_macro_score"] is False
    assert entry["excluded_from_score_reason"] == "not_read_by_engine"
    assert entry["error_class"] is None
    assert entry["value_present"] is False


@pytest.mark.parametrize("sid", list(ms.SCORED_SERIES))
def test_a_requested_series_still_reports_its_real_outcome(sid):
    entry = _built(_snapshot_with_both_series())["series"][sid]
    assert entry["fetch_status"] == "ok"
    assert entry["requested"] is True
    assert entry["used_by_macro_score"] is True


def test_a_genuine_internal_error_is_still_reported_as_one():
    """The fix must not swallow real failures: a SCORED series with an
    unrecognised status still lands on `internal_error`."""
    snap = _snapshot_with_both_series()
    snap["series"][ms.SERIES_DGS10] = {"value": None, "fetch_status": "nonsense"}
    entry = _built(snap)["series"][ms.SERIES_DGS10]
    assert entry["fetch_status"] == "internal_error"


def test_an_unconfigured_scored_series_is_not_configured_not_an_error():
    snap = {"configured": False, "series": {}}
    for sid in ms.SCORED_SERIES:
        assert _built(snap)["series"][sid]["fetch_status"] == "not_configured"
    for sid in ms.UNSCORED_SERIES:
        assert _built(snap)["series"][sid]["fetch_status"] == "not_requested"


def test_not_requested_is_a_known_status_but_never_the_payload_status():
    assert ms.NOT_REQUESTED == "not_requested"
    assert ms.NOT_REQUESTED in ms.FETCH_STATUSES
    p = _built(_snapshot_with_both_series())
    assert p["fetch_status"] != ms.NOT_REQUESTED
    assert ms.validate_macro_shadow(p) == []


def test_the_telemetry_fix_changes_no_scored_arithmetic():
    p = _built(_snapshot_with_both_series())
    assert p["components_expected"] == 2
    assert p["components_available"] == 2
    assert p["components_used"] == 2
    assert p["confidence_if_restored"] == 70.0
    assert p["delta_confidence"] == round((70.0 - 25.0) / 9, 6)
    assert p["fallback_reason"] is None
