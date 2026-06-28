"""
TM v2 Phase 1 — PathReader.

DB-READ ONLY. Maps `signal_trade_path` rows to `PathRecord` and derives the
policy-independent quantities (tp1_r, tp1_atr, sl_before_tp, confidence flags).
No writes, no ORM-model import, no live coupling. Per-row fail-open: a bad row
is skipped + logged, never aborts the load.

`sl_before_tp` is DERIVED here (the locked decision: not a stored column):
  intrabar_ambiguous            → None  (same-bar SL+TP; order unknowable)
  cur_reached_tp1 == True        → False (TP1 reached strictly before any SL)
  not reached_tp1 & outcome=loss → True  (clean stop, no TP first)
  otherwise (expired / win w/o SL) → None
"""

from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional

from sqlalchemy import text

from app.trade_mgmt.types import PathRecord

logger = logging.getLogger(__name__)

_COLUMNS = """
    signal_id, asset_id, symbol, timeframe, direction, regime, outcome,
    detail_label, resolved_at, schema_version, source,
    entry_price, sl_price, tp1_price, tp2_price, tp3_price,
    mfe_r, mae_r, mfe_atr, mae_atr, mfe_pct, mae_pct,
    bars_total, mfe_bar_idx, mae_bar_idx, sl_dist_pct, atr_pct_at_signal,
    cur_reached_tp1, cur_reached_tp2, cur_reached_tp3, cur_bars_to_tp1,
    cur_post_tp1_mfe_r, cur_post_tp1_mae_r, cur_gave_back_after_tp1, cur_realized_return,
    intrabar_ambiguous, still_forming_resolution
"""


def _f(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def _i(v: Any) -> Optional[int]:
    return None if v is None else int(v)


def _derive_sl_before_tp(reached_tp1: Any, outcome: Any, intrabar_ambiguous: bool) -> Optional[bool]:
    """Ordering of SL vs first TP from existing fields (see module docstring)."""
    if intrabar_ambiguous:
        return None
    if reached_tp1:
        return False
    if (outcome or "").lower() == "loss":
        return True
    return None


def to_path_record(row: Mapping[str, Any]) -> PathRecord:
    """Pure mapping: a DB row mapping → PathRecord (with derived fields).
    Unit-testable without a database."""
    entry = _f(row.get("entry_price"))
    sl = _f(row.get("sl_price"))
    tp1 = _f(row.get("tp1_price"))
    atr = _f(row.get("atr_pct_at_signal"))

    tp1_r: Optional[float] = None
    if entry is not None and sl is not None and tp1 is not None and entry != sl:
        tp1_r = round(abs(tp1 - entry) / abs(entry - sl), 4)

    tp1_atr: Optional[float] = None
    if entry is not None and tp1 is not None and atr:
        tp1_atr = round(abs(tp1 - entry) / (atr / 100.0 * entry), 4)

    intrabar = bool(row.get("intrabar_ambiguous"))
    still = bool(row.get("still_forming_resolution"))
    reached_tp1 = row.get("cur_reached_tp1")
    outcome = row.get("outcome")
    sbt = _derive_sl_before_tp(reached_tp1, outcome, intrabar)

    flags: List[str] = []
    if still:
        flags.append("still_forming")
    if intrabar:
        flags.append("intrabar_ambiguous")
    if row.get("mfe_r") is None:
        flags.append("no_mfe")
    if row.get("tp2_price") is None:
        flags.append("no_tp2_price")
    if row.get("tp3_price") is None:
        flags.append("no_tp3_price")
    if sbt is None:
        flags.append("ordering_unknown")

    return PathRecord(
        signal_id=str(row.get("signal_id")),
        asset_id=(str(row["asset_id"]) if row.get("asset_id") is not None else None),
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        direction=row.get("direction"),
        regime=row.get("regime"),
        outcome=outcome,
        detail_label=row.get("detail_label"),
        resolved_at=row.get("resolved_at"),
        schema_version=_i(row.get("schema_version")),
        source=row.get("source"),
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=_f(row.get("tp2_price")),
        tp3=_f(row.get("tp3_price")),
        mfe_r=_f(row.get("mfe_r")),
        mae_r=_f(row.get("mae_r")),
        mfe_atr=_f(row.get("mfe_atr")),
        mae_atr=_f(row.get("mae_atr")),
        mfe_pct=_f(row.get("mfe_pct")),
        mae_pct=_f(row.get("mae_pct")),
        bars_total=_i(row.get("bars_total")),
        mfe_bar_idx=_i(row.get("mfe_bar_idx")),
        mae_bar_idx=_i(row.get("mae_bar_idx")),
        sl_dist_pct=_f(row.get("sl_dist_pct")),
        atr_pct_at_signal=atr,
        cur_reached_tp1=reached_tp1,
        cur_reached_tp2=row.get("cur_reached_tp2"),
        cur_reached_tp3=row.get("cur_reached_tp3"),
        cur_bars_to_tp1=_i(row.get("cur_bars_to_tp1")),
        cur_post_tp1_mfe_r=_f(row.get("cur_post_tp1_mfe_r")),
        cur_post_tp1_mae_r=_f(row.get("cur_post_tp1_mae_r")),
        cur_gave_back_after_tp1=row.get("cur_gave_back_after_tp1"),
        cur_realized_return=_f(row.get("cur_realized_return")),
        intrabar_ambiguous=intrabar,
        still_forming_resolution=still,
        tp1_r=tp1_r,
        tp1_atr=tp1_atr,
        sl_before_tp=sbt,
        confidence_flags=tuple(flags),
    )


async def load_paths(db, *, source: str = "live", schema_version: Optional[int] = None) -> List[PathRecord]:
    """Read signal_trade_path (READ ONLY) → list[PathRecord], oldest first.
    Per-row fail-open. `db` is an AsyncSession provided by the caller."""
    where = "WHERE source = :source"
    params: dict = {"source": source}
    if schema_version is not None:
        where += " AND schema_version = :sv"
        params["sv"] = schema_version
    q = f"SELECT {_COLUMNS} FROM signal_trade_path {where} ORDER BY resolved_at"

    rows = (await db.execute(text(q), params)).mappings().all()
    out: List[PathRecord] = []
    for r in rows:
        try:
            out.append(to_path_record(r))
        except Exception as e:  # fail-open per row — never abort the whole load
            logger.warning("PathReader: skipped row signal_id=%s: %s", r.get("signal_id"), e)
    return out
