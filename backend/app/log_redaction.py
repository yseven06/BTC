"""Central secret redaction for every log record. CP-MACRO-SHADOW-FETCH-SECRET-REDACTION.

WHY THIS EXISTS
    On 2026-07-31 the shadow FRED fetch ran for thirty minutes and put the API key
    into the container log four times. Nothing in our code logged it: httpx's own
    INFO line does, and the URL it prints carries `api_key=` in its query string
    (httpx/_client.py:1740). The same pattern is latent in the production
    MacroCollector, which builds an identical URL.

WHY LOWERING A LOG LEVEL IS NOT THE FIX
    There are THREE surfaces, and a level only closes one:

      1. `logging.getLogger("httpx")` INFO — the request line, full URL.
      2. `HTTPStatusError`'s message — httpx formats it as
         "... for url '{url}'" (httpx/_models.py:809-818). Any handler that
         prints an exception, or any traceback, carries the key at WARNING or
         ERROR, where a level cap does nothing.
      3. `httpcore.*` loggers — connection-level detail, DEBUG today, one
         config change away from being emitted.

    So the guarantee has to sit where every record passes regardless of origin or
    level: on the HANDLERS. A filter attached to a logger only sees records that
    logger created — child records propagate straight past it — which is exactly
    the mistake that would leave httpx unfiltered.

WHAT IT DOES
    Redacts sensitive query parameters out of `msg`, every element of `args`, the
    rendered traceback and `stack_info`, before the formatter ever runs. Levels
    are lowered for httpx/httpcore too, but only as defence in depth: the filter
    is what makes the claim true.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Any, Iterable, Tuple

REDACTED = "<redacted>"

# Names whose VALUE must never reach a log. Deliberately broader than the one
# parameter that leaked: a redaction boundary drawn around a single vendor is a
# boundary that the next vendor walks through.
SENSITIVE_QUERY_PARAMS: Tuple[str, ...] = (
    "access_token", "refresh_token", "client_secret", "private_key",
    "api_key", "apikey", "api-key", "auth_token", "authorization",
    "password", "passwd", "signature", "session", "secret", "token",
    "auth", "pwd", "sig", "key",
)

# Longest first. NOT load-bearing: a sabotage run proved reversing this changes
# nothing, because the lookbehind below already stops `token` from matching
# inside `access_token` — the character before it is `_`, which is excluded.
# Kept as belt-and-braces for the day someone loosens that lookbehind, and
# described accurately here rather than credited with a protection it does not
# provide.
_NAMES = "|".join(re.escape(p) for p in
                  sorted(SENSITIVE_QUERY_PARAMS, key=len, reverse=True))

# `(?<![\w-])` rather than `\b`: it keeps `cache_key=`, `sort_key=` and
# `series_key=` intact — an underscore is a word character, so a plain `\b` would
# not have protected them, and over-redacting ordinary telemetry hides the
# signal this exists to keep readable.
#
# The value stops at the first `&`, `;`, `#`, whitespace or closing quote/bracket,
# so a URL embedded in prose ("... for url 'https://x?api_key=abc'") is cut at
# the quote and the sentence survives. Percent-encoding inside the value is
# matched as-is and replaced wholesale, so encoding never splits a secret.
_SENSITIVE_RE = re.compile(
    r"(?i)(?<![\w-])(" + _NAMES + r")(\s*=\s*)([^&;#\s'\"<>\)\]]*)"
)


# `%s`, `%d`, `%(name)s`, `{}`, `{0}`, `{name}` — a value that is a FORMAT
# PLACEHOLDER, not a secret. Redacting one destroys the format string: logging
# then raises "not all arguments converted" and the whole record is LOST, which
# is a worse outcome than the leak this exists to prevent. The real value arrives
# through `args` and is redacted there.
_PLACEHOLDER_RE = re.compile(r"^(%[-#0-9. +]*[a-zA-Z]|%\([^)]*\)[-#0-9. +]*[a-zA-Z]|\{[^{}]*\})$")


def _sub(match: "re.Match[str]") -> str:
    name, sep, value = match.group(1), match.group(2), match.group(3)
    # An empty value carries no secret, and rewriting it to `<redacted>` would
    # make an absent credential look present — a false record in the other
    # direction. Left exactly as it was.
    if not value or _PLACEHOLDER_RE.match(value):
        return match.group(0)
    return f"{name}{sep}{REDACTED}"


def redact_text(value: str) -> str:
    """Every sensitive `name=value` in arbitrary text, masked. Never raises."""
    try:
        return _SENSITIVE_RE.sub(_sub, value)
    except Exception:  # noqa: BLE001 — redaction may never break logging
        return REDACTED


def redact_url(value: Any) -> str:
    """A URL with its sensitive query values masked.

    Works on the raw string rather than parse/re-encode: `parse_qsl` silently
    drops malformed segments and `urlencode` rewrites the encoding, so a
    round-trip would both lose information and change a log line that is meant to
    be a faithful record of what was requested. Duplicate parameters, their
    order, their encoding and any fragment all survive untouched.
    """
    return redact_text(str(value))


def _redact_arg(arg: Any) -> Any:
    """Redact one logging argument, leaving its TYPE alone unless it changed.

    `%d` positions hold ints, and `str(5)` never contains a sensitive pattern, so
    they are returned unchanged and the format string still works. Only an
    argument whose text actually carried a secret is replaced — and by then it
    must be a `%s` position, because nothing else could have held a URL.
    """
    if isinstance(arg, str):
        return redact_text(arg)
    if isinstance(arg, (int, float, bool, type(None))):
        return arg
    try:
        text = str(arg)
    except Exception:  # noqa: BLE001
        return arg
    cleaned = redact_text(text)
    return cleaned if cleaned != text else arg


class SecretRedactingFilter(logging.Filter):
    """Masks secrets on every record that reaches the handler it is attached to.

    Returns True always — this filters CONTENT, not records. Dropping a record
    would hide an error; the point is to keep the error and lose the secret.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            # Redact the RENDERED message, not `msg` and `args` separately.
            #
            # Two defects made that necessary, and both were found by driving
            # real records rather than by reading the code:
            #
            #   * `logger.info("token=%s", secret)` — the secret is a BARE value
            #     in `args` with no `name=` around it, and the `name=` in `msg`
            #     is attached to `%s`. Neither half is redactable alone; only
            #     `"token=<secret>"` after interpolation is.
            #   * redacting `msg` first ate the `%s`, so `msg % args` raised
            #     inside logging and the whole record was DROPPED — a worse
            #     outcome than the leak, since the line is lost either way.
            #
            # Rendering here costs nothing: a filter only runs on records that
            # already reached a handler, so the formatter was going to render it
            # anyway. `args` is cleared so the text is emitted literally and a
            # stray `%` in it cannot be reinterpreted.
            rendered = record.getMessage()
            cleaned = redact_text(rendered)
            if cleaned != rendered:
                record.msg = cleaned
                record.args = ()

            # Render and redact the traceback HERE. `Formatter.format` reuses
            # `exc_text` when it is already set, so this is the only point at
            # which the exception's own message — which httpx fills with the
            # request URL — can be masked before it is written.
            if record.exc_info and not record.exc_text:
                record.exc_text = redact_text(
                    "".join(traceback.format_exception(*record.exc_info)))
            elif record.exc_text:
                record.exc_text = redact_text(record.exc_text)

            if record.stack_info:
                record.stack_info = redact_text(record.stack_info)
        except Exception:  # noqa: BLE001 — a filter may never break logging
            pass
        return True


# Loggers whose request lines are noise once the application logs its own
# secret-free summary. Lowered as defence in depth ONLY: the filter above is
# what makes redaction a guarantee, and these still pass through it at WARNING
# and ERROR.
NOISY_HTTP_LOGGERS: Tuple[str, ...] = ("httpx", "httpcore")

_FILTER = SecretRedactingFilter()


def install(*, quiet_http_loggers: bool = True) -> None:
    """Attach the filter to every root handler. Idempotent; safe to call again.

    Handler-level, not logger-level: a filter on a logger only sees records that
    logger itself created, so records propagating up from `httpx` would sail past
    one attached to the root logger. Every record reaches a handler.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(_FILTER)
    # Also on the root logger, for anything logged directly through it.
    if not any(isinstance(f, SecretRedactingFilter) for f in root.filters):
        root.addFilter(_FILTER)

    if quiet_http_loggers:
        for name in NOISY_HTTP_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)


def is_installed() -> bool:
    root = logging.getLogger()
    if not root.handlers:
        return False
    return all(any(isinstance(f, SecretRedactingFilter) for f in h.filters)
               for h in root.handlers)
