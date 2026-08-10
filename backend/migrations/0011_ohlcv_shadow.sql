-- 0011: shadow OHLCV store — immutable CLOSED candles, research substrate only.
--
-- WHY
-- ---
-- Every signal pass fetches OHLCV for each symbol/timeframe and discards the
-- frame. `price_data` exists to hold that history and is EMPTY: nothing
-- constructs a PriceData(...) outside its own module and nothing reads it. The
-- consequence was measured in CP-SIGNAL-INTELLIGENCE-V2 — BTC/ETH beta, rolling
-- correlation, lead/lag, residual return, forward closed-bar labels and any
-- change-point work are all data-blocked, not idea-blocked.
--
-- `price_data` is NOT reused (see app/models/ohlcv_bar.py for the four reasons;
-- the load-bearing ones are its `asset_id` FK, which would force every reference
-- series into the tradeable-asset table, and its lack of `close_time`, without
-- which the closed-candle invariant cannot be expressed). It is left untouched.
--
-- WHAT READS THIS
-- ---------------
-- Offline research only. No decision path may read it: the moment a signal
-- depends on this table, a persistence outage becomes a signal outage. The
-- writer is fail-open for the same reason.
--
-- IMMUTABILITY
-- ------------
-- A closed bar is a historical fact, so ingestion upserts with DO NOTHING, not
-- DO UPDATE. A re-fetch is a no-op rather than a silent rewrite, and an exchange
-- correction surfaces as a row that disagrees with a fresh fetch — detectable —
-- instead of as data that changed underneath a finished analysis.
--
-- RAW MARKET DATA ONLY. No outcome, label or derived metric. Excursion paths,
-- MAE/MFE, give-back and trailing simulations are all COMPUTABLE from these
-- bars; keeping them out is what lets the same rows be recomputed under a new
-- definition later without a migration.
--
-- NOT APPLIED TO PRODUCTION BY THIS CHECKPOINT.

CREATE TABLE IF NOT EXISTS ohlcv_bars (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity. `symbol` is the exchange symbol, uppercase, no separator
    -- (BTCUSDT) — normalised by the writer so one market cannot become two
    -- series that join to nothing.
    symbol                  VARCHAR(32)  NOT NULL,
    timeframe               VARCHAR(8)   NOT NULL,
    source                  VARCHAR(16)  NOT NULL DEFAULT 'binance',

    -- Both bounds stored. open_time alone would force every reader to know the
    -- bar duration to answer "when did this close?", and that derivation is
    -- exactly where a lookahead creeps in.
    open_time               TIMESTAMPTZ  NOT NULL,
    close_time              TIMESTAMPTZ  NOT NULL,

    open                    NUMERIC(20,8) NOT NULL,
    high                    NUMERIC(20,8) NOT NULL,
    low                     NUMERIC(20,8) NOT NULL,
    close                   NUMERIC(20,8) NOT NULL,
    volume                  NUMERIC(30,8) NOT NULL,

    -- Kline fields 7/8/9/10 — same response, no extra API call. quote_volume
    -- gives notional size comparable across coins of very different unit price;
    -- trade_count separates one large print from many small ones; the taker-buy
    -- split is the only order-flow signal available without a paid feed.
    -- Nullable: a second source may not provide them.
    quote_volume            NUMERIC(30,8),
    trade_count             BIGINT,
    taker_buy_base_volume   NUMERIC(30,8),
    taker_buy_quote_volume  NUMERIC(30,8),

    -- Always TRUE for a persisted row — the writer refuses anything else. Kept
    -- as a column so research queries can carry `WHERE is_closed` explicitly:
    -- an invariant enforced only at write time is invisible at read time, and a
    -- reader who cannot see it cannot rely on it.
    is_closed               BOOLEAN      NOT NULL DEFAULT TRUE,
    ingested_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Structural guards. These are cheap and they make a malformed bar
    -- unrepresentable rather than merely unlikely: every excursion, beta and
    -- label computed downstream assumes low <= open/close <= high.
    CONSTRAINT ck_ohlcv_bars_bounds  CHECK (low <= high
                                            AND open  BETWEEN low AND high
                                            AND close BETWEEN low AND high),
    CONSTRAINT ck_ohlcv_bars_volume  CHECK (volume >= 0),
    CONSTRAINT ck_ohlcv_bars_window  CHECK (close_time > open_time),
    -- The table's name is its promise. A row that is not closed does not belong.
    CONSTRAINT ck_ohlcv_bars_closed  CHECK (is_closed)
);

-- IDEMPOTENCY. The natural key of a candle is (who said so, what, at what
-- granularity, starting when). open_time rather than close_time because it is
-- the exchange's own kline key and what pagination walks; given a fixed
-- timeframe the two are equivalent. This is what makes live ingestion and
-- historical backfill safe to overlap.
--
-- KNOWN, DELIBERATE OBJECT-TYPE DIFFERENCE. Under scripts/migrate.py this file
-- never builds the table: create_all runs first (migrate.py:94) and emits the
-- model's UNIQUE CONSTRAINT, after which the CREATE TABLE below is a no-op and
-- this statement is skipped as already-existing. Only the single-file path
-- (scripts/run_migration.py 0011_...sql) reaches this line, and it produces a
-- unique INDEX rather than a unique CONSTRAINT. The two are NOT
-- interchangeable for `ON CONFLICT ON CONSTRAINT <name>` — which is why the
-- writer infers its conflict target from the COLUMNS instead, a form both
-- objects satisfy. Making this an ALTER TABLE ... ADD CONSTRAINT would match
-- the object type but lose re-runnability: PostgreSQL has no ADD CONSTRAINT IF
-- NOT EXISTS, and this repo's line-based splitter forbids a DO/$$ guard.
-- Uniqueness enforcement and conflict inference are identical either way, and
-- tests/test_ohlcv_shadow.py pins both.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ohlcv_bars_natural
    ON ohlcv_bars (source, symbol, timeframe, open_time);

-- The query every research pass runs: one series, one timeframe, a date range,
-- in order.
CREATE INDEX IF NOT EXISTS ix_ohlcv_bars_symbol_tf_time
    ON ohlcv_bars (symbol, timeframe, open_time);

-- Cross-sectional: "every symbol's 15m bar that closed at T". This is the access
-- pattern BTC/ETH residualisation lives on — without it that join degenerates
-- into one scan per symbol.
CREATE INDEX IF NOT EXISTS ix_ohlcv_bars_tf_time
    ON ohlcv_bars (timeframe, open_time);

-- RLS: this table carries no user data, but every other table in this schema is
-- locked down (0006/0007/0010) and an unlocked one would be the exception that
-- gets forgotten. No policy is granted, so PostgREST/anon reaches nothing; the
-- backend connects as the owner and is unaffected.
ALTER TABLE ohlcv_bars ENABLE ROW LEVEL SECURITY;

-- DOWNGRADE
-- ---------
-- Safe and total: nothing references ohlcv_bars, no FK points at it, and no
-- decision path reads it. Dropping it loses only research substrate that can be
-- re-fetched from the exchange.
--
--   DROP TABLE IF EXISTS ohlcv_bars;
