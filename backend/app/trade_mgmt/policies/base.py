"""
Policy interface for TM v2.

The replay engine talks ONLY to this abstraction. A new policy (Hard-BE,
Trailing, AdaptiveScaleout, ...) is added by subclassing `Policy` and
implementing `decide_tp1` — the replay core never changes.

Contract:
  • `decide_tp1` receives a `Tp1Context` (pre-decision only — no look-ahead) and
    returns a `ManagementDecision` (scale-out schedule + remainder handling).
  • Implementations MUST be PURE & DETERMINISTIC: same context → same decision,
    no time/random/IO. This keeps replay reproducible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.trade_mgmt.types import ManagementDecision, Tp1Context


class Policy(ABC):
    """A trade-management policy. Stateless & deterministic."""

    name: str = "policy"

    @abstractmethod
    def decide_tp1(self, ctx: Tp1Context) -> ManagementDecision:
        """Decide the scale-out + remainder handling at the TP1 juncture."""
        raise NotImplementedError
