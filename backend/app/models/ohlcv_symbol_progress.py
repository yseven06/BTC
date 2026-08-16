"""Per-symbol OHLCV attempt ledger — durable fairness in SYMBOL space.

WHY THIS TABLE EXISTS
---------------------
A3c already moved fairness off the wall clock and onto `run_seq` (see
ohlcv_progress.py). A3D then tried to make a run BOUNDED by partitioning the
universe, selecting K symbols per run from an index computed as
`run_seq mod ceil(N/K)`. Modelling killed it: with a universe oscillating
57/58/57/250, only ceil(N/K)/gcd(period, ceil(N/K)) blocks are ever reachable —
measured at K=5 as 25 of 50 blocks (95 of 250 symbols never selected) and at
K=6 as 21 of 42.

That is the SAME defect three earlier reviews already closed, with the universe
size playing the role the clock used to. The generalisation is what matters:
ANY selection that is a pure function of (run_seq, N) can be phase-locked when N
is itself periodic in run_seq. A different modulus, a prime, or a hash does not
help, because the lock is between run_seq's period and the modulus.

So the progression variable leaves index space. `Asset.symbol` is unique=True,
which makes it a stable total identity that no universe resize can renumber, and
fairness is carried per symbol here.

WHAT A ROW MEANS — EXACTLY
--------------------------
"This (source, symbol) was SELECTED for an attempted collection run whose
durable sequence was `last_attempt_run_seq`." Nothing more. It is NOT a claim
that the attempt fetched anything, persisted a bar, advanced a watermark, or
covered any history. A run that claims a partition and then dies has still
consumed it — deliberately, exactly as 0012's run_seq does, because that is what
stops a crash-looping run from replaying the same prefix forever.

NOT A COVERAGE OR COMPLETENESS SIGNAL. It cannot answer "which bars exist",
"where are the gaps" or "how far back does history reach". Those are A4's, and
inferring any of them from this column would be the category error the A3/A4
boundary exists to prevent.

THE create_all TRAP — WHY EVERY CONSTRAINT IS DECLARED HERE
-----------------------------------------------------------
`scripts/migrate.py` runs `Base.metadata.create_all` BEFORE applying pending
.sql files, so on a fresh database THIS MODEL creates the table and 0013's
`CREATE TABLE IF NOT EXISTS` is a silent no-op. Anything declared only in SQL
would never reach such a database while the ledger still recorded 0013 as
applied. String (VARCHAR) rather than Text, an UNNAMED primary key, and both
named CHECKs exist here for exactly that reason — 0012 measured a real
divergence (`character varying` vs `text`, and
`length(btrim((col)::text))` vs `length(btrim(col))`) that a constraint-NAME
comparison could not see.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, Index, String, text,
)

from app.database import Base


class OhlcvSymbolProgress(Base):
    """One row per (source, symbol). Four columns, one of them advisory."""

    __tablename__ = "ohlcv_symbol_progress"

    # Venue. Part of the key so a second venue can never advance binance's
    # fairness state. String -> VARCHAR, matching 0013 exactly.
    source = Column(String, primary_key=True, nullable=False)

    # The durable identity: Asset.symbol, which is unique=True and therefore a
    # total, stable ordering key. An index would not be, which is the entire
    # reason this table exists rather than a cursor into a list.
    symbol = Column(String, primary_key=True, nullable=False)

    # The fairness token: the run_seq of the run that last SELECTED this symbol.
    # Monotonic and durable because run_seq is. Deliberately NOT a timestamp —
    # a wall clock is the input whose phase-locking got the original rotation
    # rejected, and it would drift across restarts besides.
    last_attempt_run_seq = Column(BigInteger, nullable=False,
                                  server_default=text("0"))

    # Operator-facing only; no correctness path reads it. A shadow job is kept
    # out of the global /health `degraded` aggregate and its spec is
    # critical=False, so job_guard's staleness check short-circuits — this is
    # the only way to tell "advancing" from "stuck since last week".
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("last_attempt_run_seq >= 0",
                        name="ck_ohlcv_symbol_progress_seq"),
        CheckConstraint("length(btrim(symbol)) > 0",
                        name="ck_ohlcv_symbol_progress_symbol"),
        # Oldest-first read support: "the K active symbols with the smallest
        # last_attempt_run_seq for this source". Without it that read is a full
        # scan on every run. Declared here as well as in 0013 so create_all and
        # the migration produce the same catalogue.
        Index("ix_ohlcv_symbol_progress_source_seq",
              "source", "last_attempt_run_seq"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"<OhlcvSymbolProgress({self.source}/{self.symbol} "
                f"seq={self.last_attempt_run_seq})>")
