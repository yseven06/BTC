"""Candidate decision log — every scored evaluation, published or not (P2.2-a).

WHY THIS TABLE EXISTS
---------------------
`signals` only ever contains ideas the platform decided to publish. Everything the
gates rejected — the HOLD downgrades, the sub-65% confidence demotions, the
reversal deferrals — evaluates, informs the active-signal checks, and is then
discarded at `scheduler.py:437-440` without leaving a trace. The P2.1 read-only
audit hit that wall directly: with no record of what was rejected, a looser
threshold cannot be simulated at all, and a tighter one can only be measured on
the survivors it would have kept. Every calibration question is unanswerable in
that state.

`SignalSnapshot` cannot fill the gap: its `signal_id` is `nullable=False,
unique=True` (intelligence.py:81-87), so it structurally requires a published
signal to hang off. This table is the same idea without that requirement.

CONTRACT
--------
  * PURELY OBSERVATIONAL. Nothing in the decision path reads a row back. Writing
    one cannot change a publish verdict, a signal count, a lifecycle transition
    or any user-visible output — the verdict is already final at every call site.
  * ADDITIVE. No existing table, column or row meaning changes.
  * IDEMPOTENT. `(asset_id, timeframe, evaluated_bar_time, policy_version,
    source)` is unique; a retry, an APScheduler misfire replay or an admin
    trigger_job_now that re-scores the same bar is suppressed by ON CONFLICT
    DO NOTHING rather than duplicating history. Wall-clock time is deliberately
    NOT part of the key — it differs between a run and its retry, so it cannot
    identify an evaluation.
  * FAIL-OPEN AT THE WRITER. The caller wraps the insert in try/except and a
    SAVEPOINT, so neither a bug here nor a constraint violation can abort the
    surrounding transaction. That transaction may hold a staged reversal close
    (scheduler.py:368-402); losing it to a telemetry error is the exact
    fail-open-becomes-fail-closed failure documented at tracker.py:44-52.

MEASUREMENT SEMANTICS THAT ARE EASY TO GET WRONG
------------------------------------------------
Two families of ambiguous names were deliberately NOT collapsed into one column,
because the competing definitions produce different numbers and silently mixing
them would corrupt every downstream comparison:

  atr_pct_regime      Wilder ATR / close * 100, from the regime detector. This is
                      the one `SignalSnapshot.atr_pct` already stores, so it is
                      the only one joinable to the existing 2 900-row history.
  atr_pct_geometry    atr_used / current_price * 100, the value the SL/TP levels
                      were actually built from (birth telemetry).
  volume_ratio_regime bar volume / 20-bar mean, from the regime detector.
  volume_ratio_geom.  the volume engine's own volume_trend_ratio.

`disagreement_count` is not a column at all: it has three plausible readings that
each yield a different integer. The three primitives are stored instead
(`conflict_min_count`, `bull_count`, `bear_count`) so any definition is derivable
after the fact, and none is baked in now.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

# Instrumentation contract version for these rows. Bump ONLY when the MEANING of
# an existing column changes. Adding a column is NOT a bump — consumers must read
# a missing/NULL column as "not measured". Same rule as TRADE_PATH_SCHEMA_VERSION
# (intelligence.py:42) and TRADE_PATH_EXTRA_VERSION (trade_path.py:61).
CANDIDATE_SCHEMA_VERSION = 1

# The PUBLISH-POLICY era in force when the row was written: the composite bands
# (68/54/46/32), the disagreement coefficient (4.0), the signal-quality consensus
# gate, the MTF penalty and demotion, MIN_ACTIONABLE_CONFIDENCE (65.0) and
# REVERSAL_MIN_CONFIDENCE (72.0), taken as ONE indivisible era.
#
# HAND-SET, never derived. Those thresholds are inline literals inside function
# bodies (signal_generator.py:120/129/132/135/138, scheduler.py:298/357), so a
# computed version would have to either parse source text or duplicate the
# literals into a second location that would silently drift. It would also
# over-claim: composite_score additionally depends on runtime-resolved adaptive
# engine weights, so an identical threshold tuple does not imply identical
# publishing behaviour. Bump this by hand whenever any of those change meaning.
CANDIDATE_POLICY_VERSION = 1

# `source` vocabulary — which code path produced the evaluation. Kept explicit
# rather than inferred, because the two paths do NOT share gate semantics and
# labelling them alike would make the population statistics dishonest.
SOURCE_SCHEDULER = "scheduler_cron"   # _generate_signal, the gated path
SOURCE_MANUAL_API = "manual_api"      # POST /signals/generate/{symbol}, ungated

# `verdict` vocabulary — the terminal fate of the evaluation.
VERDICT_PUBLISHED = "published"
VERDICT_DROPPED = "dropped"           # scored, then demoted to HOLD / not actionable
VERDICT_SKIPPED = "skipped"           # an active idea already holds this symbol

# `demotion_reason` vocabulary — WHY the verdict came out that way. These are
# assigned from locals at the exact sites that make each decision; they are never
# inferred, because the three demotion causes write identical variables and are
# otherwise indistinguishable after the fact.
REASON_PUBLISHED = "published"
REASON_CONFIDENCE_GATE = "confidence_gate"          # scheduler.py:299-302
REASON_REVERSAL_DEFER = "reversal_defer"            # scheduler.py:422-429
REASON_NOT_ACTIONABLE = "not_actionable"            # engine itself said HOLD
REASON_DUPLICATE_OR_EXISTING = "duplicate_or_existing"  # active idea already held

# `capture_status` — how complete this row's decision-time context is. A row from
# the ungated manual path cannot carry regime/weights/telemetry; saying so
# explicitly is the difference between a NULL that means "not measured" and a
# NULL that would otherwise be read as "measured as absent".
CAPTURE_FULL = "full"
CAPTURE_PARTIAL = "partial"

# `similarity_status` — the similarity engine needs the candidate's own persisted
# SignalSnapshot to compute a distance (similarity.py:147-157), which by
# definition does not exist for a rejected candidate. Rather than bolt a
# per-candidate DB round-trip onto a loop that runs ~90 assets x 4 timeframes,
# the column is left NULL and labelled, ready for offline enrichment later.
SIMILARITY_UNAVAILABLE = "unavailable_at_decision"

# Shadow terminal states. NO_FILL is deliberately NOT folded into `loss`: a setup
# whose entry was never reached did not lose a trade, it never took one, and
# P2.1 showed this distinction is exactly where the book's damage concentrates.
# It is excluded from default PF/expectancy/win-rate and reported as its own rate.
SHADOW_PENDING = "pending"
SHADOW_NO_FILL = "never_entered"
SHADOW_TP1 = "tp1"
SHADOW_TP2 = "tp2"
SHADOW_TP3 = "tp3"
SHADOW_STOP = "stop"
SHADOW_EXPIRY = "expiry"
SHADOW_INVALIDATED = "invalidated"
SHADOW_UNDECIDABLE = "undecidable"    # no post-bar data yet — never imputed as a result

# Why a row can NEVER be shadow-evaluated. These are properties of the stored row
# itself, not of the bars, so waiting cannot change them: a HOLD scan will not
# acquire a direction tomorrow.
SHADOW_REASON_NO_DIRECTION = "no_direction"
SHADOW_REASON_NO_GEOMETRY = "no_geometry"
SHADOW_PERMANENT_REASONS = frozenset({SHADOW_REASON_NO_DIRECTION, SHADOW_REASON_NO_GEOMETRY})

# The only directions a shadow trade can be walked from.
EVALUABLE_DIRECTIONS = ("bullish", "bearish")


def classify_birth_shadow(direction, entry_zone_low, entry_zone_high, stop_loss):
    """Why this candidate can never be shadow-evaluated — or None if it can.

    Everything this needs is known when the row is written, so a permanently
    unevaluable candidate can be stamped at birth instead of being inserted
    pending and retired by a later UPDATE. At ~6 500 such rows a day, that is the
    difference between a queue that means "waiting to be measured" and one that
    is 93 % rows which never can be.

    Direction is checked FIRST and wins outright. The offline retirement pass
    decides the same thing in SQL with a CASE whose first arm is the direction
    test, and the two must not disagree — a test walks a truth table across both.

    Lives on the model rather than in either caller: the runtime logger and the
    offline script both already import this module, so they share one definition
    without the runtime ever importing the script.
    """
    if direction is None or direction not in EVALUABLE_DIRECTIONS:
        return SHADOW_REASON_NO_DIRECTION
    if entry_zone_low is None or entry_zone_high is None or stop_loss is None:
        return SHADOW_REASON_NO_GEOMETRY
    return None


class SignalDecisionCandidate(Base):
    """One scored evaluation of one asset on one bar, whatever its verdict."""

    __tablename__ = "signal_decision_candidates"

    __table_args__ = (
        # The idempotency key. `evaluated_bar_time` is the last bar the engines
        # actually scored (df.index[-1]) — not wall clock, which differs between
        # a run and its retry. Each signals_* job fires exactly once per bar of
        # its own timeframe (cron registrations, scheduler.py:722-755), so within
        # one legitimate evaluation cycle this tuple is unique by construction and
        # any second insert carrying it is definitionally a duplicate.
        # `policy_version` is in the key so a policy bump re-evaluates rather than
        # colliding; `source` is in it so the gated and ungated paths never
        # overwrite each other.
        UniqueConstraint(
            "asset_id", "timeframe", "evaluated_bar_time", "policy_version", "source",
            name="uq_signal_decision_candidates_eval",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # --- identity -----------------------------------------------------------
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    # SET NULL, not CASCADE: scheduler.py:347 hard-deletes a NEUTRAL active
    # signal, and under CASCADE that would destroy the very row recording why it
    # was born. The candidate log must outlive its signal.
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    symbol = Column(String(32), nullable=True, index=True)   # denormalized for display
    timeframe = Column(String(8), nullable=False, index=True)

    # --- time (UTC throughout) ---------------------------------------------
    evaluated_bar_time = Column(DateTime(timezone=True), nullable=False, index=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)

    # --- provenance ---------------------------------------------------------
    source = Column(String(24), nullable=False, server_default=SOURCE_SCHEDULER, index=True)
    policy_version = Column(Integer, nullable=False,
                            default=CANDIDATE_POLICY_VERSION,
                            server_default=str(CANDIDATE_POLICY_VERSION))
    schema_version = Column(Integer, nullable=False,
                            default=CANDIDATE_SCHEMA_VERSION,
                            server_default=str(CANDIDATE_SCHEMA_VERSION))
    capture_status = Column(String(12), nullable=False,
                            default=CAPTURE_FULL, server_default=CAPTURE_FULL)

    # --- verdict ------------------------------------------------------------
    verdict = Column(String(16), nullable=False, index=True)
    demotion_reason = Column(String(32), nullable=True, index=True)
    # What the engines proposed, BEFORE the scheduler's own gates ran...
    engine_signal_type = Column(String(16), nullable=True)
    engine_direction = Column(String(16), nullable=True)
    # ...and what survived them.
    final_signal_type = Column(String(16), nullable=True)
    final_direction = Column(String(16), nullable=True)

    # --- decision-time scores ----------------------------------------------
    # POST-penalty and POST-clamp: when the max(50,...)/min(50,...) clamp at
    # signal_generator.py:124/126 bites, the pre-penalty value is unrecoverable.
    # Not a "raw" composite. NULL when birth telemetry failed to build — the
    # accompanying composite_score_source says which.
    composite_score = Column(Numeric(precision=6, scale=2), nullable=True)
    composite_score_source = Column(String(20), nullable=True)
    confidence_score = Column(Numeric(precision=6, scale=2), nullable=True)
    probability_score = Column(Numeric(precision=6, scale=2), nullable=True)
    risk_score = Column(Numeric(precision=6, scale=2), nullable=True)
    risk_level = Column(String(16), nullable=True)

    # --- consensus primitives (see module docstring: no `disagreement_count`) --
    conflict_min_count = Column(Integer, nullable=True)   # min(bull, bear) — drives the penalty
    bull_count = Column(Integer, nullable=True)
    bear_count = Column(Integer, nullable=True)
    disagreement_penalty = Column(Numeric(precision=6, scale=2), nullable=True)
    mtf_penalty = Column(Numeric(precision=6, scale=2), nullable=True)

    # --- market context: regime detector definitions ------------------------
    regime = Column(String(32), nullable=True, index=True)
    adx = Column(Numeric(precision=10, scale=4), nullable=True)
    atr_pct_regime = Column(Numeric(precision=10, scale=4), nullable=True)
    atr_pct_median = Column(Numeric(precision=10, scale=4), nullable=True)
    volume_ratio_regime = Column(Numeric(precision=10, scale=4), nullable=True)
    volatility_ratio = Column(Numeric(precision=10, scale=4), nullable=True)  # atr_pct/median
    trend_direction = Column(String(16), nullable=True)

    # --- market context: geometry / engine definitions ----------------------
    atr_pct_geometry = Column(Numeric(precision=10, scale=4), nullable=True)
    volume_ratio_geometry = Column(Numeric(precision=10, scale=4), nullable=True)
    fear_greed = Column(Integer, nullable=True)

    # --- the trade idea itself ---------------------------------------------
    last_close = Column(Numeric(precision=20, scale=8), nullable=True)
    entry_zone_low = Column(Numeric(precision=20, scale=8), nullable=True)
    entry_zone_high = Column(Numeric(precision=20, scale=8), nullable=True)
    stop_loss = Column(Numeric(precision=20, scale=8), nullable=True)
    tp1 = Column(Numeric(precision=20, scale=8), nullable=True)
    tp2 = Column(Numeric(precision=20, scale=8), nullable=True)
    tp3 = Column(Numeric(precision=20, scale=8), nullable=True)
    planned_rr_tp1 = Column(Numeric(precision=10, scale=4), nullable=True)
    sl_dist_pct = Column(Numeric(precision=10, scale=4), nullable=True)

    # --- similarity (deferred, see SIMILARITY_UNAVAILABLE) ------------------
    similarity_score = Column(Numeric(precision=10, scale=4), nullable=True)
    similarity_status = Column(String(32), nullable=True)

    # --- raw payloads -------------------------------------------------------
    engine_scores = Column(JSON, nullable=True)    # per-engine score/bias/confidence
    engine_weights = Column(JSON, nullable=True)   # RESOLVED weights (adaptive or base)
    mtf_trends = Column(JSON, nullable=True)
    adaptive_active = Column(Boolean, nullable=True)

    # --- shadow evaluation (all NULL at write time; filled offline) ---------
    # Structurally uncomputable at insert: `df` ends at the bar being scored, so
    # there are zero post-birth bars. This is the definition of the measurement,
    # not a gap to work around.
    shadow_evaluated_at = Column(DateTime(timezone=True), nullable=True, index=True)
    shadow_outcome = Column(String(16), nullable=True, index=True)
    shadow_detail_label = Column(Text, nullable=True)
    shadow_return_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    shadow_r_multiple = Column(Numeric(precision=10, scale=4), nullable=True)
    shadow_mfe_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    shadow_mae_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    shadow_bars_walked = Column(Integer, nullable=True)
    shadow_resolved_at = Column(DateTime(timezone=True), nullable=True)
    shadow_resolution_path = Column(String(16), nullable=True)   # bar_walk | expiry | no_fill
    shadow_resolution_reason = Column(Text, nullable=True)

    # --- entry validity (Reading A canonical + Reading B-lite, measurement only) --
    # Reading A (canonical, unchanged): entry = the entry-zone MIDPOINT, which is
    # the price the whole P&L machinery already pretends the trade filled at.
    # `shadow_entry_reached` answers "was that fill assumption ever physically
    # true", and nothing here alters lifecycle or outcome semantics.
    shadow_entry_reached = Column(Boolean, nullable=True)
    shadow_entry_reached_at = Column(DateTime(timezone=True), nullable=True)
    shadow_bars_to_entry = Column(Integer, nullable=True)
    shadow_never_entered = Column(Boolean, nullable=True)
    shadow_max_zone_penetration_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    # Reading B-lite: did price reach the FAR edge of the zone, not just the
    # midpoint. Under Reading A the stop sits beyond the midpoint, so price must
    # pass entry to reach SL and a midpoint-based "stopped before entry" flag
    # would be ~always False (entry_telemetry.py:12-18 documents exactly this).
    # The far-edge reading is the one that can actually discriminate.
    shadow_zone_far_edge_reached = Column(Boolean, nullable=True)
    shadow_stop_before_valid_entry = Column(Boolean, nullable=True)
    shadow_invalidated_before_entry = Column(Boolean, nullable=True)

    # Additive escape hatch — new keys here never need an ALTER.
    extra = Column(JSON, nullable=True, default=None)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return (f"<SignalDecisionCandidate(symbol={self.symbol}, tf={self.timeframe}, "
                f"verdict={self.verdict}, reason={self.demotion_reason})>")
