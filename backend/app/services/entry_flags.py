"""Effective entry-gate flag resolution — CP-ENTRY-ACTIVATION-GATE §9.6.

Two of the three switches DEPEND on the first one. `ENTRY_WALK_START_ENABLED`
decides how the entry bar is walked, which is meaningless when no entry is being
detected; `ENTRY_PENDING_OCCUPANCY_ENABLED` is reserved for the successor
checkpoint and has no consumer here at all.

A dependent switch turned on without its parent is a CONFIGURATION MISTAKE, and
the only safe reading of a mistake is "do nothing". So:

  * the dependent switch resolves to False — never a partial behaviour,
  * production decisions are untouched,
  * the mistake is logged once as a structured ERROR,
  * `/health` shows `invalid_entry_flag_dependency` so it is visible without
    reading logs,
  * and the process still starts. Refusing to boot would trade a silent
    misconfiguration for an outage, which is a worse failure than the one it
    prevents.

EVERY consumer must read the ``effective_*`` values. Reading a raw flag is the
defect this module exists to prevent, and the sabotage tests assert exactly that.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.config import get_settings

logger = logging.getLogger(__name__)

# Surfaced verbatim on /health and asserted by tests — one spelling, one home.
INVALID_DEPENDENCY_KEY = "invalid_entry_flag_dependency"

_PARENT = "ENTRY_ACTIVATION_ENABLED"
_DEPENDENTS = ("ENTRY_WALK_START_ENABLED", "ENTRY_PENDING_OCCUPANCY_ENABLED")

# Log the misconfiguration once per process rather than on every candidate.
_warned: set = set()


def _raw(name: str) -> bool:
    return bool(getattr(get_settings(), name, False))


def entry_activation_enabled() -> bool:
    """The parent switch. It depends on nothing, so raw == effective."""
    return _raw(_PARENT)


def _effective_dependent(name: str) -> bool:
    parent = _raw(_PARENT)
    raw = _raw(name)
    if raw and not parent:
        if name not in _warned:
            _warned.add(name)
            logger.error(
                "[EntryFlags] %s: %s=true while %s=false — the dependent switch is "
                "being treated as FALSE and no entry-gate behaviour is applied. "
                "Set %s=true first, or set %s=false to clear this.",
                INVALID_DEPENDENCY_KEY, name, _PARENT, _PARENT, name,
            )
        return False
    return raw and parent


def effective_walk_start() -> bool:
    """Whether the entry BAR may be walked under the proved-exception rule."""
    return _effective_dependent("ENTRY_WALK_START_ENABLED")


def effective_pending_occupancy() -> bool:
    """RESERVED for CP-ENTRY-OCCUPANCY-SHADOW.

    Resolved for contract completeness and asserted by tests, but deliberately
    read by NO production code path in this checkpoint. Turning the raw switch on
    must not change the occupancy verdict, the publication volume, or the
    `skipped/duplicate_or_existing` count.
    """
    return _effective_dependent("ENTRY_PENDING_OCCUPANCY_ENABLED")


def invalid_dependencies() -> List[str]:
    """Names of dependent switches that are on while the parent is off."""
    if _raw(_PARENT):
        return []
    return [name for name in _DEPENDENTS if _raw(name)]


def flag_diagnostics() -> Dict[str, Any]:
    """Flag state for /health — raw next to effective, so a mismatch is visible."""
    invalid = invalid_dependencies()
    return {
        "raw": {
            _PARENT: _raw(_PARENT),
            "ENTRY_WALK_START_ENABLED": _raw("ENTRY_WALK_START_ENABLED"),
            "ENTRY_PENDING_OCCUPANCY_ENABLED": _raw("ENTRY_PENDING_OCCUPANCY_ENABLED"),
        },
        "effective": {
            _PARENT: entry_activation_enabled(),
            "ENTRY_WALK_START_ENABLED": effective_walk_start(),
            "ENTRY_PENDING_OCCUPANCY_ENABLED": effective_pending_occupancy(),
        },
        INVALID_DEPENDENCY_KEY: invalid,
    }
