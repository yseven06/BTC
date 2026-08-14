"""The durable OHLCV fairness progression primitive. NOTHING calls this yet.

It lives in its own module on purpose. `ohlcv_collector_job` carries an A3/A4
boundary guard asserting the collector never grows an upsert — that guard is
about BAR writes (revising history is A4's job, not A3's) and it is correct, so
the progression upsert is kept out of that module rather than the guard loosened
to accommodate it.
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.ohlcv_progress import OhlcvCollectionProgress

log = logging.getLogger(__name__)


async def acquire_run_sequence(session_factory, source: str) -> int:
    """Durably claim the next run sequence for `source`. ONE statement, ONE commit.

    MEANING. The returned value says "a collection run for this source has
    STARTED" — never that it succeeded, completed, attempted every symbol or
    persisted a bar. A run that claims a sequence and dies immediately has still
    consumed it, and that is deliberate: it is what stops a crash-looping run from
    replaying the same prefix of the universe forever. Measured on the previous
    architecture, advancing only on completion left a run that always died after
    two symbols reaching 2 of 57 symbols across 200 runs; advancing at the start
    reached 57 of 57.

    WHY A SINGLE STATEMENT AND NOT read-modify-write. A SELECT followed by an
    UPDATE is a lost-update race the moment two runs overlap, and the collector
    must not depend on `max_instances=1` for its own correctness. `INSERT ...
    ON CONFLICT (source) DO UPDATE SET run_seq = <table>.run_seq + 1 RETURNING`
    performs the read, the increment and the write inside one statement: the
    conflicting row is locked for the duration, so concurrent callers serialise and
    every caller receives a distinct value.

    WHY ITS OWN SHORT-LIVED SESSION. The transaction must commit BEFORE the first
    item and must never be open across a Binance request — the pool ceiling is 10
    and a transaction held across the network is exactly the idle-in-transaction
    shape this codebase has been bitten by before.

    FAILURE IS NOT SWALLOWED. If this cannot commit, the caller must not pretend
    fairness progression happened; the exception propagates and the run does not
    start.
    """
    src = (source or "").strip()
    if not src:
        # An empty source would key progression under a namespace that no watermark
        # read or row write could ever match.
        raise ValueError("source must be a non-empty string")

    stmt = (pg_insert(OhlcvCollectionProgress)
            .values(source=src, run_seq=1)
            .on_conflict_do_update(
                index_elements=[OhlcvCollectionProgress.source],
                set_={"run_seq": OhlcvCollectionProgress.run_seq + 1,
                      "updated_at": func.now()})
            .returning(OhlcvCollectionProgress.run_seq))

    async with session_factory() as db:
        result = await db.execute(stmt)
        seq = result.scalar_one()
        await db.commit()
    return int(seq)
