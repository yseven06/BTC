"""Canonical entry-validity surface — CP-ENTRY-VALIDITY-TELEMETRY-SURFACE.

The tracker has recorded PASSIVE entry-detection telemetry at
``SignalTradePath.extra["entry"]`` since 2026-07-11 (``entry_telemetry.py``),
and its own comment says it is "read by NOTHING". This module is the read side:
it turns that raw block into ONE canonical classification and aggregates
performance per cohort. It changes no decision, writes no row, and takes no
position on what should happen to a signal that never filled.

Three cohorts, and only three:

  reached      price provably touched the assumed entry level
  not_reached  price provably did NOT touch it within the observed window
  unknown      we cannot tell — no trade_path row, no telemetry block, no
               post-birth bars, absent flags, or CONTRADICTORY flags

Hard rules (they exist because breaking them silently inflates every metric):
  * ``None`` is never coerced to True or False. Absent is absent.
  * ``unknown`` is never folded into ``reached``. A missing measurement is not
    a positive measurement.
  * ``data_available=False`` means "no post-birth bars to observe" — the source
    module documents this explicitly (entry_telemetry.py:59). It is UNKNOWN,
    not "never entered".
  * Contradictory flags downgrade to ``unknown`` and record ``conflict_reason``.

Shape drift caveat (measured on production 2026-08-03, not assumed): 25 rows
written on 2026-07-11 carry a tenth key, ``invalidated_before_entry``, that no
longer exists anywhere in the repo — and they carry ``telemetry_version: 1``,
the SAME version as the 9-key shape. The version field is therefore NOT a
reliable shape discriminator, so every decision below is driven by key
PRESENCE, never by the version number. Unknown extra keys are ignored, not
trusted.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ENTRY_VALIDITY_VERSION = "entry_validity_v1"

# --- canonical statuses ------------------------------------------------------
STATUS_REACHED = "reached"
STATUS_NOT_REACHED = "not_reached"
STATUS_UNKNOWN = "unknown"
CANONICAL_STATUSES = (STATUS_REACHED, STATUS_NOT_REACHED, STATUS_UNKNOWN)

# --- provenance of the classification ---------------------------------------
SOURCE_TELEMETRY = "trade_path.extra.entry"
SOURCE_TELEMETRY_PARTIAL = "trade_path.extra.entry/partial_flags"
SOURCE_NO_TRADE_PATH = "absent/no_trade_path"
SOURCE_NO_ENTRY_BLOCK = "absent/no_entry_block"
SOURCE_MALFORMED = "absent/malformed_entry_block"

# --- why a row is unknown (non-conflict) ------------------------------------
UNKNOWN_NO_TRADE_PATH = "no_trade_path_row"
UNKNOWN_NO_ENTRY_BLOCK = "no_entry_telemetry_block"
UNKNOWN_MALFORMED = "entry_block_not_a_mapping"
UNKNOWN_NO_POST_BIRTH_BARS = "no_post_birth_bars"
UNKNOWN_FLAGS_ABSENT = "entry_flags_absent"

# --- why a row is unknown (contradiction) -----------------------------------
CONFLICT_BOTH_TRUE = "entry_reached_and_never_entered_both_true"
CONFLICT_BOTH_FALSE = "entry_reached_and_never_entered_both_false"
CONFLICT_REACHED_WITHOUT_DATA = "entry_reached_true_but_data_unavailable"
CONFLICT_NEVER_WITHOUT_DATA = "never_entered_true_but_data_unavailable"
CONFLICT_FLAG_NOT_BOOLEAN = "entry_flag_not_boolean"

# The CURRENT contract (entry_telemetry.py:56-66). Used for shape completeness
# only — an unrecognised extra key never contributes and never subtracts.
CANONICAL_ENTRY_KEYS: Tuple[str, ...] = (
    "telemetry_version",
    "entry_level",
    "data_available",
    "entry_reached",
    "entry_reached_at",
    "bars_to_entry",
    "wait_seconds",
    "max_zone_penetration_pct",
    "never_entered",
)

# Below this many TERMINAL rows a cohort's rate metrics are labelled unreliable
# rather than hidden — the number is still shown, but never without the flag.
MIN_RELIABLE_SAMPLE = 30

# --- report cohorts ----------------------------------------------------------
COHORT_RAW_ALL = "raw_all"
COHORT_VALID_ENTRY_ONLY = "valid_entry_only"
COHORT_NOT_REACHED = "not_reached"
COHORT_UNKNOWN = "unknown"

# The outcome arrives spelled two different ways depending on the path it came
# down: ``SignalOutcome.WIN.value`` is ``"win"``, while the stored column holds
# the member NAME, ``"WIN"``. Comparing against a single spelling silently
# reports zero of every outcome — no error, no empty result, just a plausible
# table of zeroes. Normalise once, here, and pin both spellings in the tests.
_TERMINAL_EXCLUDED = "ACTIVE"


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------
def _blank(
    *,
    status: str,
    source: str,
    unknown_reason: Optional[str] = None,
    conflict_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "version": ENTRY_VALIDITY_VERSION,
        "status": status,
        "source": source,
        "entry_reached": None,
        "entry_price": None,
        "entry_reached_at": None,
        "bars_to_entry": None,
        "wait_seconds": None,
        "max_zone_penetration_pct": None,
        "telemetry_version": None,
        "unknown_reason": unknown_reason,
        "conflict_reason": conflict_reason,
        "completeness": 0.0,
    }


def _as_bool(value: Any) -> Tuple[Optional[bool], bool]:
    """Return (bool_or_None, is_type_error).

    Only a real ``bool`` counts. ``None`` stays ``None`` — never coerced.
    A non-bool, non-None value (``"true"``, ``1``, ``[]``) is a TYPE ERROR, not
    a truthy value: silently accepting it is exactly how a corrupt row becomes
    a confident statistic.
    """
    if value is None:
        return None, False
    if isinstance(value, bool):
        return value, False
    return None, True


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _shape_completeness(block: Mapping[str, Any]) -> float:
    present = sum(1 for k in CANONICAL_ENTRY_KEYS if k in block)
    return round(present / len(CANONICAL_ENTRY_KEYS), 4)


def classify_entry_validity(
    entry_block: Any,
    *,
    has_trade_path: bool = True,
) -> Dict[str, Any]:
    """Reduce one raw ``extra["entry"]`` block to the canonical block.

    Pure: no DB, no clock, no config. ``has_trade_path=False`` distinguishes
    "the signal has no trade_path row at all" from "it has one but no entry
    telemetry" — both are unknown, for different and separately countable
    reasons.
    """
    if not has_trade_path:
        return _blank(
            status=STATUS_UNKNOWN,
            source=SOURCE_NO_TRADE_PATH,
            unknown_reason=UNKNOWN_NO_TRADE_PATH,
        )

    if entry_block is None:
        return _blank(
            status=STATUS_UNKNOWN,
            source=SOURCE_NO_ENTRY_BLOCK,
            unknown_reason=UNKNOWN_NO_ENTRY_BLOCK,
        )

    if not isinstance(entry_block, Mapping):
        return _blank(
            status=STATUS_UNKNOWN,
            source=SOURCE_MALFORMED,
            unknown_reason=UNKNOWN_MALFORMED,
        )

    reached, reached_bad = _as_bool(entry_block.get("entry_reached"))
    never, never_bad = _as_bool(entry_block.get("never_entered"))
    data_available, data_bad = _as_bool(entry_block.get("data_available"))

    out = _blank(status=STATUS_UNKNOWN, source=SOURCE_TELEMETRY)
    out["entry_price"] = _num(entry_block.get("entry_level"))
    out["telemetry_version"] = entry_block.get("telemetry_version")
    out["completeness"] = _shape_completeness(entry_block)

    # A corrupt flag poisons the whole row: refuse to classify it.
    if reached_bad or never_bad or data_bad:
        out["conflict_reason"] = CONFLICT_FLAG_NOT_BOOLEAN
        return out

    # --- contradictions (checked BEFORE any positive conclusion) ------------
    conflict: Optional[str] = None
    if reached is True and never is True:
        conflict = CONFLICT_BOTH_TRUE
    elif reached is False and never is False:
        conflict = CONFLICT_BOTH_FALSE
    elif reached is True and data_available is False:
        conflict = CONFLICT_REACHED_WITHOUT_DATA
    elif never is True and data_available is False:
        conflict = CONFLICT_NEVER_WITHOUT_DATA

    if conflict is not None:
        out["conflict_reason"] = conflict
        return out

    # --- no usable flags ----------------------------------------------------
    if reached is None and never is None:
        out["unknown_reason"] = (
            UNKNOWN_NO_POST_BIRTH_BARS if data_available is False else UNKNOWN_FLAGS_ABSENT
        )
        return out

    # --- positive classification -------------------------------------------
    if reached is None or never is None:
        # One flag missing is incomplete, not contradictory — the surviving
        # flag is unambiguous, so it decides; the provenance records the gap.
        out["source"] = SOURCE_TELEMETRY_PARTIAL

    if reached is True or never is False:
        out["status"] = STATUS_REACHED
        out["entry_reached"] = True
        out["entry_reached_at"] = entry_block.get("entry_reached_at")
        bars = entry_block.get("bars_to_entry")
        out["bars_to_entry"] = int(bars) if isinstance(bars, int) and not isinstance(bars, bool) else None
    else:
        out["status"] = STATUS_NOT_REACHED
        out["entry_reached"] = False

    out["wait_seconds"] = _num(entry_block.get("wait_seconds"))
    out["max_zone_penetration_pct"] = _num(entry_block.get("max_zone_penetration_pct"))
    return out


def select_trade_path_row(rows: Sequence[Any]) -> Optional[Any]:
    """Pick ONE trade_path row deterministically when a signal has several.

    Production currently has a unique index on ``signal_id`` (measured: 0
    duplicates), but a reader that silently depends on that is a reader that
    breaks the day it stops holding. Newest ``created_at`` wins; ties break on
    the stringified primary key. The result never depends on input order.
    """
    candidates = [r for r in rows if r is not None]
    if not candidates:
        return None

    def key(row: Any) -> Tuple[int, str, str]:
        created = getattr(row, "created_at", None)
        return (
            1 if created is not None else 0,
            created.isoformat() if created is not None else "",
            str(getattr(row, "id", "")),
        )

    return max(candidates, key=key)


# ---------------------------------------------------------------------------
# cohort metrics
# ---------------------------------------------------------------------------
def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 4)
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 4)


def _rate(hits: int, total: int) -> Optional[float]:
    return round(100.0 * hits / total, 2) if total else None


# CP-ENTRY-ACTIVATION-GATE: terminal labels that mean no position ever opened.
# The coarse outcome column still says EXPIRED / INVALIDATED for these rows, so
# a reader keying only off `outcome` would count invalidated_before_entry as a
# loss. The reporting surface has to exclude them explicitly — the fold guard
# in coin_memory covers the learning pool, not this.
NO_FILL_DETAIL_LABELS = frozenset({"expired_without_entry", "invalidated_before_entry"})


def is_no_fill_label(detail_label: Optional[str]) -> bool:
    """True when this DETAIL LABEL means the position never opened.

    The scalar form. Consumers that hold an ORM row or a dataclass — Similarity's
    candidate pool, for one — have the label itself, not a mapping, and building a
    throwaway dict per candidate just to ask this question is both wasteful and an
    invitation to inline the label list instead. One frozenset, two ergonomics.

    A NULL label is NOT a no-fill row. Legacy rows predate these labels entirely,
    and "we do not know" must never be silently promoted to "it never filled" —
    that is the same coercion this whole checkpoint exists to remove.
    """
    return str(detail_label or "") in NO_FILL_DETAIL_LABELS


def is_no_fill(record: Mapping[str, Any]) -> bool:
    """True when this row terminated without a proven entry."""
    return is_no_fill_label(record.get("detail_label"))


def _outcome(record: Mapping[str, Any]) -> Optional[str]:
    """The record's outcome as a canonical UPPERCASE token, or None.

    Accepts the enum member, its lowercase ``.value`` and the stored uppercase
    name interchangeably — see the note above ``_TERMINAL_EXCLUDED``. A record
    with no outcome is not resolved, so it is neither terminal nor an outcome.
    """
    raw = record.get("outcome")
    if raw is None:
        return None
    raw = getattr(raw, "value", raw)
    text = str(raw).strip()
    return text.upper() if text else None


def summarize_cohort(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate performance over one cohort of records.

    Safety properties that the tests pin:
      * ``win_rate`` denominator is WIN+LOSS only; zero denominator -> ``None``,
        never 0.0 and never 100.0.
      * ``profit_factor`` is ``None`` when there is no realised loss — a cohort
        with zero negative returns has an UNDEFINED profit factor, not an
        infinite one. The 141-signal phantom cohort is exactly this case.
      * every rate carries ``reliable``, false below ``MIN_RELIABLE_SAMPLE``.
    """
    n = len(records)
    terminal = [r for r in records if _outcome(r) not in (None, _TERMINAL_EXCLUDED)]
    n_term = len(terminal)

    def count(outcome: str) -> int:
        return sum(1 for r in terminal if _outcome(r) == outcome)

    wins, losses = count("WIN"), count("LOSS")
    returns = [v for v in (_num(r.get("return_pct")) for r in terminal) if v is not None]
    gross_profit = sum(v for v in returns if v > 0)
    gross_loss = abs(sum(v for v in returns if v < 0))

    tp_den = n_term
    mfe = [v for v in (_num(r.get("mfe_pct")) for r in terminal) if v is not None]
    mae = [v for v in (_num(r.get("mae_pct")) for r in terminal) if v is not None]

    return {
        "n": n,
        "n_terminal": n_term,
        "n_active": n - n_term,
        "reliable": n_term >= MIN_RELIABLE_SAMPLE,
        "min_reliable_sample": MIN_RELIABLE_SAMPLE,
        "outcomes": {
            "win": wins,
            "loss": losses,
            "breakeven": count("BREAKEVEN"),
            "expired": count("EXPIRED"),
            "invalidated": count("INVALIDATED"),
        },
        "win_rate": _rate(wins, wins + losses),
        "profit_factor": (round(gross_profit / gross_loss, 4) if gross_loss > 0 else None),
        "profit_factor_undefined_reason": (None if gross_loss > 0 else "no_realised_loss"),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
        "total_return_pct": round(sum(returns), 4) if returns else None,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "median_return_pct": _median(returns),
        "n_return_missing": n_term - len(returns),
        "tp1_rate": _rate(sum(1 for r in terminal if r.get("hit_tp1") is True), tp_den),
        "tp2_rate": _rate(sum(1 for r in terminal if r.get("hit_tp2") is True), tp_den),
        "tp3_rate": _rate(sum(1 for r in terminal if r.get("hit_tp3") is True), tp_den),
        "avg_mfe_pct": round(sum(mfe) / len(mfe), 4) if mfe else None,
        "avg_mae_pct": round(sum(mae) / len(mae), 4) if mae else None,
    }


def _confidence_band(value: Any) -> str:
    conf = _num(value)
    if conf is None:
        return "(bilinmiyor)"
    if conf < 55:
        return "1_<55"
    if conf < 60:
        return "2_55-59.99"
    if conf < 65:
        return "3_60-64.99"
    if conf < 70:
        return "4_65-69.99"
    if conf < 75:
        return "5_70-74.99"
    return "6_>=75"


_BREAKDOWNS: Tuple[Tuple[str, Any], ...] = (
    ("by_symbol", lambda r: r.get("symbol") or "(bilinmiyor)"),
    ("by_timeframe", lambda r: r.get("timeframe") or "(bilinmiyor)"),
    ("by_direction", lambda r: r.get("direction") or "(bilinmiyor)"),
    ("by_regime", lambda r: r.get("regime") or "(bilinmiyor)"),
    ("by_risk_level", lambda r: r.get("risk_level") or "(bilinmiyor)"),
    ("by_confidence_band", lambda r: _confidence_band(r.get("confidence"))),
)


def _breakdown(records: Sequence[Mapping[str, Any]], keyfn: Any) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, List[Mapping[str, Any]]] = {}
    for rec in records:
        buckets.setdefault(str(keyfn(rec)), []).append(rec)
    return {k: summarize_cohort(v) for k, v in sorted(buckets.items())}


# ---------------------------------------------------------------------------
# full report
# ---------------------------------------------------------------------------
def compute_entry_validity_report(
    records: Iterable[Mapping[str, Any]],
    *,
    top_symbols: int = 12,
) -> Dict[str, Any]:
    """Build the read-only report. ``records`` are plain dicts (see the route).

    Every record must already carry an ``entry_validity`` block produced by
    :func:`classify_entry_validity`.
    """
    rows = list(records)
    by_status: Dict[str, List[Mapping[str, Any]]] = {s: [] for s in CANONICAL_STATUSES}
    for rec in rows:
        status = (rec.get("entry_validity") or {}).get("status")
        by_status.setdefault(status if status in by_status else STATUS_UNKNOWN, []).append(rec)

    reached = by_status[STATUS_REACHED]
    not_reached = by_status[STATUS_NOT_REACHED]
    unknown = by_status[STATUS_UNKNOWN]

    reasons: Dict[str, int] = {}
    conflicts: Dict[str, int] = {}
    sources: Dict[str, int] = {}
    for rec in rows:
        ev = rec.get("entry_validity") or {}
        sources[str(ev.get("source"))] = sources.get(str(ev.get("source")), 0) + 1
        if ev.get("unknown_reason"):
            reasons[ev["unknown_reason"]] = reasons.get(ev["unknown_reason"], 0) + 1
        if ev.get("conflict_reason"):
            conflicts[ev["conflict_reason"]] = conflicts.get(ev["conflict_reason"], 0) + 1

    raw_all = summarize_cohort(rows)
    valid_only = summarize_cohort(reached)
    not_reached_stats = summarize_cohort(not_reached)
    unknown_stats = summarize_cohort(unknown)

    # Symbol breakdown is capped; say so out loud rather than truncating quietly.
    counts: Dict[str, int] = {}
    for rec in rows:
        counts[str(rec.get("symbol") or "(bilinmiyor)")] = counts.get(
            str(rec.get("symbol") or "(bilinmiyor)"), 0
        ) + 1
    keep = {s for s, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_symbols]}

    def breakdowns(subset: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, keyfn in _BREAKDOWNS:
            if name == "by_symbol":
                out[name] = _breakdown([r for r in subset if str(r.get("symbol")) in keep], keyfn)
            else:
                out[name] = _breakdown(subset, keyfn)
        return out

    total = len(rows)
    cohort_sum = len(reached) + len(not_reached) + len(unknown)

    return {
        "version": ENTRY_VALIDITY_VERSION,
        "read_only": True,
        "cohort_integrity": {
            "total_signals": total,
            "reached": len(reached),
            "not_reached": len(not_reached),
            "unknown": len(unknown),
            "sum": cohort_sum,
            "sum_matches_total": cohort_sum == total,
        },
        "status_provenance": {
            "by_source": dict(sorted(sources.items())),
            "unknown_reasons": dict(sorted(reasons.items())),
            "conflict_reasons": dict(sorted(conflicts.items())),
        },
        "cohorts": {
            COHORT_RAW_ALL: {
                "legacy_raw": True,
                "caveat": (
                    "Bugün production'ın raporladığı sayı. Entry gerçekleşmesini "
                    "VARSAYAR; not_reached ve unknown kayıtlar içindedir. "
                    "Karşılaştırma tabanı olarak korunur, düzeltilmiş metrik DEĞİLDİR."
                ),
                **raw_all,
            },
            COHORT_VALID_ENTRY_ONLY: {
                "legacy_raw": False,
                "caveat": (
                    "Yalnız entry'ye ulaştığı ÖLÇÜLEN sinyaller. unknown kohortu "
                    "dahil DEĞİL — ölçülmemiş olan, ulaşılmış sayılmaz."
                ),
                **valid_only,
            },
            COHORT_NOT_REACHED: {
                "legacy_raw": False,
                "caveat": (
                    "Entry'ye ulaşmadığı ÖLÇÜLEN sinyaller. Bunların outcome "
                    "kayıtları doldurulmuş bir pozisyon varsayar; hayali kohorttur."
                ),
                **not_reached_stats,
            },
            COHORT_UNKNOWN: {
                "legacy_raw": False,
                "caveat": (
                    "Entry durumu ÖLÇÜLEMEYEN sinyaller (telemetri öncesi, "
                    "trade_path yok, doğum sonrası bar yok veya çelişkili alan). "
                    "Bu kohorttan kalite sonucu ÇIKARILMAZ."
                ),
                **unknown_stats,
            },
        },
        "breakdowns": {
            COHORT_RAW_ALL: breakdowns(rows),
            COHORT_VALID_ENTRY_ONLY: breakdowns(reached),
            COHORT_NOT_REACHED: breakdowns(not_reached),
            COHORT_UNKNOWN: breakdowns(unknown),
        },
        "breakdown_limits": {
            "by_symbol": f"yalnız en çok işlem gören {top_symbols} sembol",
            "diğer": "sınır yok",
        },
        "learning_pool_contamination": _contamination(
            raw_all, valid_only, not_reached_stats, unknown_stats
        ),
    }


def _delta(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None:
        return None
    return round(new - old, 4)


def _contamination(
    raw: Mapping[str, Any],
    valid: Mapping[str, Any],
    not_reached: Mapping[str, Any],
    unknown: Mapping[str, Any],
) -> Dict[str, Any]:
    """How much of what the learners consume is not a measured fill.

    MEASUREMENT ONLY. This checkpoint deliberately does not change Coin Memory,
    Similarity or Adaptive Learning — it quantifies what they are currently fed
    so the decision to change them can be made on numbers.
    """
    den = raw.get("n_terminal") or 0
    contaminated = (not_reached.get("n_terminal") or 0) + (unknown.get("n_terminal") or 0)
    return {
        "measurement_only": True,
        "consumers": [
            "coin_memory (fold over resolved signals)",
            "similarity (find_similar_setups, HTTP route only)",
            "adaptive_weights (derived from coin_memory)",
        ],
        "terminal_pool": den,
        "not_reached_in_pool": not_reached.get("n_terminal") or 0,
        "unknown_in_pool": unknown.get("n_terminal") or 0,
        "contaminated_in_pool": contaminated,
        "contaminated_pct": _rate(contaminated, den),
        "effect_on_metrics": {
            "win_rate_delta": _delta(valid.get("win_rate"), raw.get("win_rate")),
            "avg_return_delta": _delta(valid.get("avg_return_pct"), raw.get("avg_return_pct")),
            "total_return_delta": _delta(valid.get("total_return_pct"), raw.get("total_return_pct")),
            "profit_factor_delta": _delta(valid.get("profit_factor"), raw.get("profit_factor")),
            "note": (
                "valid_entry_only eksi raw_all. profit_factor_delta=None ise "
                "kohortlardan en az birinde gerçekleşmiş zarar yoktur."
            ),
        },
    }
