"""BIST (Borsa İstanbul) market-hours helper.

Used to gate stock signal generation and stock price polling so the upstream
data source isn't hit (and egress isn't burned) while the exchange is closed.

Turkey is UTC+3 year-round (no DST since 2016). We use the Europe/Istanbul
zone when the tz database is available and fall back to a fixed +03:00 offset
otherwise (e.g. a Windows host without tzdata) — both resolve to the same wall
clock for Turkey.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Set

try:
    from zoneinfo import ZoneInfo
    _TR_TZ = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover — no tzdata; Turkey has no DST so +03:00 is exact
    _TR_TZ = timezone(timedelta(hours=3))

# BIST Equity Market continuous session: 10:00–18:00 Istanbul time, weekdays.
_OPEN = time(10, 0)
_CLOSE = time(18, 0)

# Manual TR public-holiday list (BIST fully closed on these dates). Kept empty
# for now — the gating architecture is ready for a real calendar. Religious
# holidays (Ramazan/Kurban Bayramı) shift yearly, so populate per-year or wire
# an external feed later.
# TODO: populate with the current year's official BIST holiday calendar.
BIST_HOLIDAYS: Set[date] = set()


def is_bist_open(now: Optional[datetime] = None) -> bool:
    """Return True if BIST is in its trading session right now (Istanbul time).

    Closed on weekends and on any date listed in BIST_HOLIDAYS. `now` may be
    passed (any tz-aware datetime) for testing; defaults to the current moment.
    """
    ist = now.astimezone(_TR_TZ) if now is not None else datetime.now(_TR_TZ)
    if ist.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    if ist.date() in BIST_HOLIDAYS:
        return False
    return _OPEN <= ist.time() <= _CLOSE
