"""The ONE production call site for `macro_shadow_v1`. Stage 2 of the restore.

WHAT IT DOES
    Reads the already-final decision and returns the DISABLED shadow payload for
    one candidate row. It fetches nothing, computes no counterfactual and decides
    nothing; the payload it returns is additive telemetry that only
    `signal_decision_candidates.extra` ever sees.

WHY IT IS A SEPARATE MODULE
    `macro_shadow.py` is the frozen contract: pure arithmetic, an import set an AST
    test pins exactly, and no knowledge of what a "decision" is. Reading
    `decision["engine_results"]` is orchestration knowledge, so it lives here and
    the contract stays untouched by wiring.

THE ONE HARD GUARANTEE
    This module NEVER raises. A telemetry helper that can throw is a helper that
    can lose a candidate row: at every call site the return value is an argument
    to `record_candidate`, so an exception here would abort the write before it is
    attempted — and at the published site it would abort a transaction that
    already holds the new signal. Every failure therefore degrades to a payload
    that says it failed, and only as a last resort to `None`.

WHAT IT MUST NOT DO — enforced by tests, not by convention
    No HTTP client, no collector, no settings, no environment, no secret, no DB,
    no `EngineResult`, no mutation of `decision` or of `engine_results`. It is
    read-only over the decision and returns a fresh dict every call.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from app.services.macro_shadow import (
    COMPONENTS_EXPECTED_CRYPTO,
    EXCEPTION,
    MACRO_SHADOW_VERSION,
    NOT_CONFIGURED,
    build_disabled_macro_shadow,
)

logger = logging.getLogger(__name__)

# The engine whose absence this shadow is about. Matches MacroEngine.name
# (app/engines/macro/engine.py:36-37); a test asserts the two are equal so a
# rename cannot silently turn every payload into "macro engine not found".
MACRO_ENGINE_NAME = "macro_analysis"

# Why the production macro reading could not be read off the decision. Recorded
# rather than papered over with a plausible 50/neutral/25 — those are exactly the
# values a zero-component macro fallback produces, so inventing them would make a
# missing engine indistinguishable from a present one.
MACRO_ENGINE_MISSING = "macro_engine_missing"
DECISION_UNREADABLE = "decision_unreadable"


def _macro_reading(decision: Any) -> Optional[Mapping[str, Any]]:
    """The macro engine's entry in `decision["engine_results"]`, or None.

    READ-ONLY. `engine_results` is a list of `EngineResult.model_dump()` dicts
    (app/engines/ai_decision/engine.py:412); nothing here writes to the list or to
    any entry in it.
    """
    if not isinstance(decision, Mapping):
        return None
    results = decision.get("engine_results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        return None
    for entry in results:
        if isinstance(entry, Mapping) and entry.get("engine_name") == MACRO_ENGINE_NAME:
            return entry
    return None


def build_candidate_macro_shadow(
    *,
    decision: Any,
    decision_time: Any,
    verdict: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The disabled `macro_shadow_v1` payload for one candidate. Never raises.

    `decision` is read, never written. The production macro score/bias/confidence
    are taken from the decision's own engine result — the number that actually
    reached the composite — so the row records what production did, not what this
    module assumes it did.
    """
    try:
        reading = _macro_reading(decision)
        payload = build_disabled_macro_shadow(
            decision_time=decision_time,
            # Passed RAW. `build_disabled_macro_shadow` coerces each of the three
            # at its own boundary (`_finite` / `_text`), so there is exactly one
            # place that decides what a non-finite score or a non-string bias
            # becomes — not two rules that could drift apart.
            production_macro_score=(reading or {}).get("score"),
            production_macro_bias=(reading or {}).get("bias"),
            production_macro_confidence=(reading or {}).get("confidence"),
            production_publish_verdict=verdict,
            components_expected=COMPONENTS_EXPECTED_CRYPTO,
        )
        if reading is None:
            # The payload stays structurally valid and the three production fields
            # stay null; the reason goes in `errors` so a null is never mistaken
            # for "macro scored nothing".
            payload["errors"] = [{
                "error": MACRO_ENGINE_MISSING if isinstance(decision, Mapping)
                else DECISION_UNREADABLE,
                "engine_name": MACRO_ENGINE_NAME,
            }]
        return payload
    except Exception as exc:  # noqa: BLE001 — telemetry must never lose a candidate
        logger.warning("[MacroShadow] payload not built (fail-open, ignored): %s",
                       type(exc).__name__)
        return _last_resort(decision_time, verdict, type(exc).__name__)


def _last_resort(decision_time: Any, verdict: Optional[str],
                 error_class: str) -> Optional[Dict[str, Any]]:
    """A second, minimal attempt so a build failure still leaves a legible row.

    Only the exception CLASS name is carried — never a message, URL or response
    body, any of which could contain the api_key query parameter. If even this
    fails, the namespace is omitted rather than a half-built dict being written.
    """
    try:
        payload = build_disabled_macro_shadow(
            decision_time=decision_time,
            production_macro_score=None,
            production_macro_bias=None,
            production_macro_confidence=None,
            production_publish_verdict=verdict,
        )
        payload["fetch_status"] = NOT_CONFIGURED
        payload["errors"] = [{"error": EXCEPTION, "error_class": str(error_class)}]
        return payload
    except Exception:  # noqa: BLE001 — nothing left to fall back to
        logger.warning("[MacroShadow] namespace omitted for this candidate")
        return None


__all__ = ["MACRO_ENGINE_NAME", "MACRO_SHADOW_VERSION", "build_candidate_macro_shadow"]
