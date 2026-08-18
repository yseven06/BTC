"""Pass B's payload must BIND to its columns — CP-MISSED-OPPORTUNITY-PASS-B.

THE DEFECT THIS EXISTS FOR. `--write` had never once succeeded. The first real
write attempt died on the UPDATE with:

    asyncpg.exceptions.DataError: invalid input for query argument $11:
    '2026-08-01T03:30:00' (expected a datetime.date or datetime.datetime
    instance, got 'str')

`build_entry_telemetry` returns `entry_reached_at` as an ISO STRING — that is its
documented contract (entry_telemetry.py:62) and the live path consumes it as a
string. `shadow_entry_reached_at` is a `DateTime(timezone=True)` column. The
evaluator handed one straight to the other.

WHY EVERY EXISTING GATE MISSED IT, INCLUDING A FULL DRY-RUN PARITY EXERCISE.
A dry-run computes exactly the same payload and then issues NO UPDATE — the
values are compared in Python and thrown away. Binding is the one step dry-run
by construction does not perform, so no amount of dry-running could ever reach
this. The parity run that compared 113 candidates field-by-field passed for the
same reason: it compared VALUES, and an ISO string compares fine against a
timestamp rendered as text.

WHAT IS ASSERTED HERE. Not "this one field is a datetime" — that would be a fix
pinned to the bug that was found. Instead the evaluator's payload is checked
against the ACTUAL SQLAlchemy column types for every key it may write, so a
sibling introduced later (another timestamp, a numeric handed over as a string)
fails here rather than in production on the first write of the day.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text

from app.models.decision_candidate import SignalDecisionCandidate
from app.services.shadow_eval import evaluate_candidate_shadow

UTC = timezone.utc
BAR = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

LONG = dict(direction="bullish", entry_zone_low=99.0, entry_zone_high=101.0,
            stop_loss=95.0, tp1=105.0, tp2=110.0, tp3=115.0)


def _frame(rows, start=BAR, freq="15min"):
    """Bars AFTER the decision bar, shaped like the collector's frame."""
    idx = pd.date_range(start + timedelta(minutes=15), periods=len(rows),
                        freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _column_types():
    cols = {}
    for c in SignalDecisionCandidate.__table__.columns:
        if c.name.startswith("shadow_"):
            cols[c.name] = c.type
    return cols


# The python types each SQLAlchemy column type will accept through asyncpg.
_ACCEPTS = {
    DateTime: (datetime,),
    Boolean: (bool,),
    Integer: (int,),
    Numeric: (int, float),
    String: (str,),
    Text: (str,),
}


def _acceptable(col_type):
    for sa_type, py_types in _ACCEPTS.items():
        if isinstance(col_type, sa_type):
            return py_types
    return None


def _payloads():
    """A spread of real evaluator outputs: a fill that resolves, and one that
    reaches the entry (which is what populates the timestamp that broke)."""
    walked = _frame([[100.0, 102.0, 99.5, 101.0],
                     [101.0, 106.0, 100.5, 105.5],
                     [105.0, 112.0, 104.0, 111.0]])
    never = _frame([[130.0, 131.0, 129.0, 130.0]] * 3)
    return [evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR, df=walked),
            evaluate_candidate_shadow(**LONG, timeframe="15m", bar_time=BAR, df=never)]


def test_every_shadow_value_binds_to_its_column_type():
    """THE RED TEST. On the broken bytes `shadow_entry_reached_at` is a str
    against a DateTime column, which is exactly the production DataError."""
    types = _column_types()
    problems = []
    for payload in _payloads():
        for key, value in payload.items():
            if key not in types or value is None:
                continue
            ok = _acceptable(types[key])
            if ok is None:
                continue
            # bool is a subclass of int; only reject the reverse direction.
            if isinstance(value, bool) and bool not in ok:
                problems.append(f"{key}={value!r} (bool) vs {types[key]}")
            elif not isinstance(value, ok):
                problems.append(f"{key}={value!r} ({type(value).__name__}) vs {types[key]}")
    assert not problems, "payload values that cannot bind: " + "; ".join(problems)


def test_the_entry_timestamp_is_a_timezone_aware_datetime():
    """Specifically pinned as well as generically covered: a naive datetime
    against `DateTime(timezone=True)` silently stores the wrong instant rather
    than failing, which is worse than the crash it replaces."""
    seen = 0
    for payload in _payloads():
        ts = payload.get("shadow_entry_reached_at")
        if ts is None:
            continue
        seen += 1
        assert isinstance(ts, datetime), f"expected datetime, got {type(ts).__name__}: {ts!r}"
        assert ts.tzinfo is not None and ts.utcoffset() is not None, \
            f"naive datetime would store the wrong instant: {ts!r}"
    assert seen, "no payload exercised the entry timestamp — the test proves nothing"


def test_the_evaluator_writes_only_permitted_columns():
    """A payload key that is not a column is silently dropped by the updater and
    would look like a field that 'never populates'."""
    columns = {c.name for c in SignalDecisionCandidate.__table__.columns}
    for payload in _payloads():
        stray = {k for k in payload if k.startswith("shadow_") and k not in columns}
        assert not stray, f"payload keys that are not columns: {sorted(stray)}"


@pytest.mark.parametrize("iso", ["2026-08-01T03:30:00", "2026-08-01T03:30:00+00:00"])
def test_a_naive_iso_string_is_still_normalised_to_an_aware_datetime(iso):
    """The frame's index is UTC, so a rendering that dropped the offset must be
    read back AS UTC rather than as local time. `_as_datetime` is the single
    place that decision is made."""
    from app.services.shadow_eval import _as_datetime

    out = _as_datetime(iso)
    assert isinstance(out, datetime)
    assert out.tzinfo is not None
    assert out.utcoffset() == timedelta(0)


def test_the_coercion_passes_through_none_and_real_datetimes_untouched():
    from app.services.shadow_eval import _as_datetime

    assert _as_datetime(None) is None
    already = datetime(2026, 8, 1, 3, 30, tzinfo=UTC)
    assert _as_datetime(already) is already
    assert _as_datetime("not a timestamp") is None

    # A NAIVE datetime — not a string — is the quiet case. asyncpg accepts it
    # against DateTime(timezone=True) and stores the wrong instant, so it must be
    # stamped here too. Testing only the aware input let a mutant that skips this
    # branch survive.
    naive = datetime(2026, 8, 1, 3, 30)
    out = _as_datetime(naive)
    assert out.tzinfo is not None and out.utcoffset() == timedelta(0), out
    assert out == already, "a naive timestamp from a UTC frame must read back as UTC"
