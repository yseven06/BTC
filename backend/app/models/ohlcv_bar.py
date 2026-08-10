"""Shadow OHLCV store — immutable CLOSED candles only.

WHY A NEW TABLE AND NOT `price_data`
------------------------------------
`price_data` already models OHLCV, and it is empty: nothing constructs a
`PriceData(...)` anywhere outside its own module and nothing reads it. It was
never wired up. Resurrecting it was considered and rejected on four grounds,
each of which would have cost more than a new table:

  1. Its key is `asset_id` -> a FK into `assets`. A reference series only needs
     to EXIST, not to be tradeable: BTC/ETH anchors, and later peer/sector
     symbols, would each have to be forced into the tradeable-asset table to be
     storable. Keying on the exchange symbol removes that coupling entirely.
  2. It has no `close_time`. The closed-candle invariant this module exists for
     cannot be expressed without the exchange's own answer to "did this bar
     finish?" — deriving it from `timestamp + duration` is exactly the guess
     `candle_window.py` was written to avoid.
  3. It has no `source`. Two providers disagreeing about the same bar has to be
     representable, not silently merged.
  4. `Asset.price_data` is a live relationship with `cascade="all, delete-orphan"`
     in the ORM registry the decision path imports. Changing that model's shape
     is a change inside the blast radius of signal generation; adding a table
     beside it is not.

So `price_data` is left exactly as it is — dead, but untouched.

WHAT THIS TABLE IS FOR
----------------------
Research substrate, and nothing else. It is written by a fail-open shadow path
and read by offline analysis (BTC/ETH beta, rolling correlation, lead/lag,
residual return, relative strength, closed-bar forward labels, change-point and
regime-transition work). No decision path reads it and none may: the moment a
signal depends on it, a persistence outage becomes a signal outage.

RAW MARKET DATA ONLY
--------------------
No outcome, label, or derived metric belongs here. Excursion paths, give-back,
MAE/MFE and trailing simulations are all COMPUTABLE from these bars, and keeping
them out is what lets the same rows be recomputed under a new definition later
without a migration. Market data and outcome data stay separate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

# The only provider today. Stored per row rather than assumed, so a second
# source can coexist and be compared instead of overwriting.
SOURCE_BINANCE = "binance"

# Canonical timeframe strings — the SAME literals the collector accepts
# (binance_collector.py:48-51) and candle_window.TIMEFRAME_DURATIONS keys on.
# One spelling, repo-wide: "15m" never also appears as "15min", "M15" or "900".
CANONICAL_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")

# What production actually generates signals on (scheduler jobs). The shadow
# store is not limited to these, but a backfill with no explicit list uses them.
PRODUCTION_TIMEFRAMES = ("15m", "1h", "4h", "1d")


class OhlcvBar(Base):
    """One CLOSED candle from one source.

    Immutable by contract: a closed bar's OHLCV is a historical fact. The writer
    upserts with DO NOTHING rather than DO UPDATE, so a re-fetch of an already
    stored bar is a no-op instead of a silent rewrite. An exchange correction —
    rare, but real — therefore shows up as a row that does NOT match a fresh
    fetch, which is a detectable condition, rather than as data that quietly
    changed underneath a completed analysis. Reconciling such a row is a
    deliberate, separate operation; it is not something ingestion does on its own.
    """

    __tablename__ = "ohlcv_bars"

    # A SERVER default as well as the Python one. `migrate.py` builds a fresh
    # database with create_all (from THIS model) and only afterwards applies the
    # .sql files, so anything the model omits is simply absent — including for a
    # plain SQL INSERT that supplies no id. Without the server default, the two
    # construction paths disagree: 0011's table accepts such an INSERT and
    # create_all's rejects it with a NOT NULL violation.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default=text("gen_random_uuid()"))

    # ── Identity ────────────────────────────────────────────────────────────
    # Exchange symbol, uppercase, no separator (BTCUSDT). Normalised by the
    # writer, never by the caller, so "btc/usdt" and "BTCUSDT" cannot become two
    # different series.
    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(8), nullable=False)
    source = Column(String(16), nullable=False, server_default=text(f"'{SOURCE_BINANCE}'"))

    # ── Time ────────────────────────────────────────────────────────────────
    # Both bounds are stored. open_time alone would force every reader to know
    # the bar duration to answer "when did this close?", and that derivation is
    # precisely where a lookahead creeps in.
    open_time = Column(DateTime(timezone=True), nullable=False)
    close_time = Column(DateTime(timezone=True), nullable=False)

    # ── OHLCV ───────────────────────────────────────────────────────────────
    # Same precision as price_data (20,8 / 30,8): enough for both sub-cent alts
    # and BTC-scale notional volume, and it keeps the two tables comparable if
    # they are ever joined for a sanity check.
    open = Column(Numeric(precision=20, scale=8), nullable=False)
    high = Column(Numeric(precision=20, scale=8), nullable=False)
    low = Column(Numeric(precision=20, scale=8), nullable=False)
    close = Column(Numeric(precision=20, scale=8), nullable=False)
    volume = Column(Numeric(precision=30, scale=8), nullable=False)

    # ── Free-from-Binance extras ────────────────────────────────────────────
    # Kline fields 7/8/9/10 arrive in the SAME response as OHLCV — storing them
    # costs one more column each and no extra API call, and they answer
    # questions OHLCV cannot: quote_volume gives notional size comparable across
    # coins of wildly different unit price, trade_count separates "one large
    # print" from "many small ones", and the taker-buy split is the only
    # order-flow signal available without a paid feed. Nullable because a second
    # source may not provide them.
    quote_volume = Column(Numeric(precision=30, scale=8), nullable=True)
    trade_count = Column(BigInteger, nullable=True)
    taker_buy_base_volume = Column(Numeric(precision=30, scale=8), nullable=True)
    taker_buy_quote_volume = Column(Numeric(precision=30, scale=8), nullable=True)

    # ── Provenance ──────────────────────────────────────────────────────────
    # Always TRUE for a persisted row — the writer refuses anything else. Kept
    # as a column anyway so every research query can carry `WHERE is_closed`
    # explicitly: an invariant that is only enforced at write time is invisible
    # at read time, and a reader who cannot see it cannot rely on it.
    is_closed = Column(Boolean, nullable=False, server_default=text("true"))
    ingested_at = Column(DateTime(timezone=True), nullable=False,
                         server_default=text("now()"))

    __table_args__ = (
        # ── STRUCTURAL GUARDS ───────────────────────────────────────────────
        # These live HERE, not only in 0011_ohlcv_shadow.sql, because the model
        # — not the .sql — is what actually builds the table on a fresh
        # database. scripts/migrate.py:94 runs `Base.metadata.create_all`
        # BEFORE it applies any pending migration, so create_all creates
        # ohlcv_bars first and 0011's `CREATE TABLE IF NOT EXISTS` is then a
        # silent no-op. Measured on PostgreSQL 16 with these constraints absent
        # from the model: the table came up with ZERO check constraints and
        # accepted a forming candle, a high-below-low bar, a negative volume and
        # an inverted window — while `schema_migrations` recorded 0011 as
        # applied and a test that reads the .sql TEXT stayed green.
        #
        # The predicates are written to match 0011 character-for-character in
        # intent so both construction paths normalise to the same
        # pg_get_constraintdef; the parity is asserted against a real database,
        # not by comparing strings.
        CheckConstraint("low <= high AND open BETWEEN low AND high "
                        "AND close BETWEEN low AND high",
                        name="ck_ohlcv_bars_bounds"),
        CheckConstraint("volume >= 0", name="ck_ohlcv_bars_volume"),
        CheckConstraint("close_time > open_time", name="ck_ohlcv_bars_window"),
        # The table's name is its promise. A row that is not closed does not
        # belong, and the writer's refusal is not enough on its own: a backfill,
        # a repair script or a second ingester would each have to re-earn it.
        CheckConstraint("is_closed", name="ck_ohlcv_bars_closed"),
        # IDEMPOTENCY. The natural key of a candle is (who said so, what, at what
        # granularity, starting when). `open_time` rather than `close_time`
        # because it is the exchange's own kline key and is what pagination
        # walks; the two are equivalent given a fixed timeframe.
        UniqueConstraint("source", "symbol", "timeframe", "open_time",
                         name="uq_ohlcv_bars_natural"),
        # The query every research pass runs: one series, one timeframe, a date
        # range, in order. Leading with the constraint's own columns would make
        # this index redundant with it; leading with symbol+timeframe and
        # ordering by open_time is what a range scan wants.
        Index("ix_ohlcv_bars_symbol_tf_time", "symbol", "timeframe", "open_time"),
        # Cross-sectional: "every symbol's 15m bar that closed at T". This is the
        # access pattern BTC/ETH residualisation lives on — without it that join
        # degenerates into a scan per symbol.
        Index("ix_ohlcv_bars_tf_time", "timeframe", "open_time"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (f"<OhlcvBar({self.source}:{self.symbol} {self.timeframe} "
                f"open={self.open_time} close={self.close})>")
