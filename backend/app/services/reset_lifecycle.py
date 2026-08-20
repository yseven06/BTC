"""Reset lifecycle telemetry for opportunity lineages — CP-K.

WHAT IT ANSWERS. For one lineage: when it first became extended, when it first
genuinely reset, whether it then chased again, and how long each wait lasted — so
the eventual shadow question ("do not take an extended candidate; reconsider it
when the CURRENT chase episode genuinely resets") is answered from stored
evidence rather than guessed.

TWO ORTHOGONAL AXES, AND WHY. An earlier draft used a single chain
`not_extended -> extended -> reset -> settled` with `settled` absorbing. Walked
against a real path — extension, reset, re-extension, second reset — it reported
"has reset, therefore safe" while price was being chased again, and it could not
say when the current episode began. Reconstructing that from the row series does
not rescue it: rows genuinely go missing (a per-asset job_guard deadline writes
no candidate at all), and a reconstruction across the gap concludes "one episode,
no re-chase" — wrong in exactly the direction that matters. So:

    CURRENT STATE          recomputed every row, free to oscillate
    FIRST-RESET EVIDENCE   frozen once per lineage, never rewritten
    CURRENT EPISODE        updated per chase episode, never touching the above

THRESHOLD SEMANTICS, EXACTLY. `extension_value` is raw and
threshold-INDEPENDENT. Everything else — state, crossings, first-reset and
episode timestamps — is evaluated against X_ref = 2.0, a member of the
pre-registered family {0.5, 1.0, 1.5, 2.0, 3.0}, frozen as a SHADOW REFERENCE.
It is not a production gate and not a claim of universal optimum: CP-G/H returned
EXTENSION_REGIME_CONDITIONAL, with 4h/1d and tight-SL cells failing. A reset at
X = 2.0 is NOT automatically a reset at any other X; other thresholds must be
recomputed from the raw series and carry their own X.

BOUNDARIES ARE NOT RE-DERIVED HERE. Direction flip, neutral, terminal anchor and
the safety ceiling all reach this module as one `lineage_state='terminated'`,
because CP-J's lineage resolver already owns that decision and one owner is the
entire point.

PURE. No state, no I/O, no clock. Every timestamp comes from the caller's bar
time, so the same inputs always produce the same record — which is what makes
restart safety structural rather than hoped for.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

RESET_NAMESPACE = "reset_lifecycle_v1"
RESET_SCHEMA_VERSION = 1

# A frozen SHADOW REFERENCE, not a gate. Named as a constant so a test can prove
# no runtime file mentions it.
RESET_REFERENCE_THRESHOLD = 2.0

STATE_NOT_EXTENDED = "not_extended"
STATE_EXTENDED = "extended"
STATE_EXPIRED = "expired"        # lineage ended while extended, never reset
STATE_CLOSED = "closed"          # lineage ended without ever extending
STATE_UNRESOLVED = "unresolved"

_LINEAGE_TERMINATED = "terminated"
_LINEAGE_BEGIN = "begin"
_LINEAGE_UNRESOLVED = "unresolved"


def _iso(value: Any) -> Optional[str]:
    """The pinned representation: tz-aware UTC isoformat, `...T...+00:00`.

    Pinned because the repository already carries two spellings — exec_cost uses
    isoformat's `T`, shadow_observation uses str(Timestamp)'s space — and a third
    reader-visible variant would be one too many.
    """
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


def _blank() -> Dict[str, Any]:
    """Every key, always present. A missing key would read as 'this build
    predates the field', which is a different claim from 'the value is absent'."""
    return {
        "schema_version": RESET_SCHEMA_VERSION,
        "state": None,
        "extension_value": None,
        "extension_threshold": RESET_REFERENCE_THRESHOLD,
        "atr_source": None,
        "extension_detected_at": None,
        "first_reset_at": None,
        "first_reset_wait_bars": None,
        "bars_in_current_extension": 0,
        "current_extension_started_at": None,
        "last_reset_at": None,
        "threshold_crossings": 0,
        "unresolved_reason": None,
    }


def unresolved_reset_payload(reason: str) -> Dict[str, Any]:
    """The standalone sentinel, for a caller that could not even reach the
    decision. Explicitly not a bare None: an absent namespace means "historical
    row", and the ban on backfilling those is only checkable while the two cases
    stay distinguishable."""
    out = _blank()
    out["state"] = STATE_UNRESOLVED
    out["unresolved_reason"] = reason
    return out


def _carry(prev: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Inherit a predecessor's frozen evidence without inheriting its verdict."""
    out = _blank()
    if not prev:
        return out
    for key in ("extension_detected_at", "first_reset_at", "first_reset_wait_bars",
                "bars_in_current_extension", "current_extension_started_at",
                "last_reset_at", "threshold_crossings"):
        out[key] = prev.get(key, out[key])
    return out


def _unresolved(prev: Optional[Dict[str, Any]], reason: str,
                atr_source: Any) -> Dict[str, Any]:
    """Unresolved carries prior evidence forward. A momentary blip must not erase
    a first-reset timestamp that was correctly frozen bars ago."""
    out = _carry(prev)
    out["state"] = STATE_UNRESOLVED
    out["atr_source"] = atr_source
    out["unresolved_reason"] = reason
    return out


def decide_reset_lifecycle(*, extension_value: Any, bar_time: Any,
                           prev: Optional[Dict[str, Any]],
                           prev_bar_time: Any = None,
                           lineage_state: Any = None,
                           atr_source: Any = None,
                           atr_fallback_used: bool = False) -> Dict[str, Any]:
    """One row's reset-lifecycle record.

    `prev` is the predecessor row's namespace as read back off the table;
    `lineage_state` is CP-J's verdict for THIS row. Nothing here can see the
    future — outcomes, entries and expiries are not parameters, so they cannot
    leak in later without changing a signature a test pins.
    """
    # ── SAME-BAR REPLAY ────────────────────────────────────────────────────
    # The row is keyed on the bar with ON CONFLICT DO NOTHING, so a replay writes
    # nothing — but it must not COMPUTE a different episode that the conflict
    # then hides. Return what is already recorded.
    if prev and prev_bar_time is not None and bar_time is not None \
            and prev_bar_time == bar_time:
        return dict(prev)

    # ── LINEAGE ENDED ──────────────────────────────────────────────────────
    # Direction flip, neutral, terminal anchor and the safety ceiling all arrive
    # here identically. The reset window closes; whether that is a loss of
    # evidence depends only on whether it was mid-chase.
    if lineage_state == _LINEAGE_TERMINATED:
        out = _carry(prev)
        out["state"] = (STATE_EXPIRED
                        if prev and prev.get("state") == STATE_EXTENDED
                        else STATE_CLOSED)
        out["atr_source"] = atr_source
        out["current_extension_started_at"] = None
        out["bars_in_current_extension"] = 0
        return out

    # A new lineage starts empty. The predecessor row still carries a full
    # namespace, and inheriting it would recreate the 97.2% aliasing defect one
    # layer up from where CP-J removed it.
    if lineage_state == _LINEAGE_BEGIN:
        prev = None

    if lineage_state == _LINEAGE_UNRESOLVED:
        return _unresolved(prev, "lineage_unresolved", atr_source)

    # The risk engine substitutes a flat 2% when ATR is NaN. Dividing by a
    # substituted constant yields a number that LOOKS measured and is not, so the
    # normalised value is withheld entirely rather than published as evidence.
    if atr_fallback_used:
        return _unresolved(prev, "atr_substituted", atr_source)

    value = None
    try:
        if extension_value is not None:
            value = float(extension_value)
            if value != value:                      # NaN
                value = None
    except (TypeError, ValueError):
        value = None
    if value is None:
        return _unresolved(prev, "extension_unavailable", atr_source)

    # ── THE STATE MACHINE ──────────────────────────────────────────────────
    out = _carry(prev)
    out["extension_value"] = value
    out["atr_source"] = atr_source

    was_extended = bool(prev) and prev.get("state") == STATE_EXTENDED
    is_extended = value >= RESET_REFERENCE_THRESHOLD
    if is_extended != was_extended:
        out["threshold_crossings"] = (out["threshold_crossings"] or 0) + 1

    if is_extended:
        out["state"] = STATE_EXTENDED
        if was_extended:
            # same episode continuing
            out["bars_in_current_extension"] = (prev.get("bars_in_current_extension") or 0) + 1
        else:
            # FIRST extension of this lineage, or a RE-EXTENSION after a reset.
            # Either way a new episode begins; the first-extension timestamp is
            # written once and never moves.
            out["current_extension_started_at"] = _iso(bar_time)
            out["bars_in_current_extension"] = 1
            if out["extension_detected_at"] is None:
                out["extension_detected_at"] = _iso(bar_time)
        return out

    out["state"] = STATE_NOT_EXTENDED
    out["current_extension_started_at"] = None
    out["bars_in_current_extension"] = 0
    if was_extended:
        # A RESET. `last_reset_at` tracks the most recent one; the first-reset
        # evidence is frozen exactly once and is never rewritten by a later
        # crossing — that separation is what keeps "how long until it first
        # reset" answerable after the lineage has chased again.
        out["last_reset_at"] = _iso(bar_time)
        if out["first_reset_at"] is None:
            out["first_reset_at"] = _iso(bar_time)
            out["first_reset_wait_bars"] = prev.get("bars_in_current_extension") or 0
    return out
