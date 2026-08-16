-- 0013: per-symbol OHLCV attempt ledger — durable fairness in SYMBOL space.
--
-- WHY THIS EXISTS
-- ---------------
-- A3D tried to bound a collection run by partitioning the universe with an
-- index-space cursor derived from run_seq and the universe size N. Modelling
-- killed it: with a universe that oscillates 57/58/57/250, `run_seq mod
-- ceil(N/K)` reaches only ceil(N/K)/gcd(period, ceil(N/K)) distinct blocks —
-- measured at K=5 as 25 of 50 blocks, leaving 95 of 250 symbols unreachable,
-- and at K=6 as 21 of 42 blocks.
--
-- That is the SAME defect class three earlier reviews already closed for the
-- wall clock, re-entering through a different variable. The generalisation is
-- the point: ANY selection that is a pure function of (run_seq, N) can be
-- phase-locked when N is itself periodic in run_seq. Changing the modulus,
-- projecting through a prime, or hashing does not help — the lock is between
-- run_seq's period and the modulus, not between K and N.
--
-- So the progression variable moves out of index space entirely. Fairness is
-- now carried per SYMBOL, and `Asset.symbol` is `unique=True`, which makes it a
-- stable total identity that no universe resize can renumber.
--
-- WHAT A ROW MEANS — EXACTLY
-- --------------------------
-- "This (source, symbol) was SELECTED for an attempted collection run whose
-- durable sequence was `last_attempt_run_seq`." Nothing else. It is emphatically
-- NOT a claim that the attempt fetched anything, persisted a bar, advanced a
-- watermark, or covered any history. A run that claims a partition and then
-- dies has still consumed it — deliberately, exactly like 0012's run_seq, and
-- for the same reason: it is what stops a crash-looping run from replaying the
-- same prefix of the universe forever.
--
-- THIS IS NOT A COVERAGE OR COMPLETENESS SIGNAL. It cannot answer "which bars
-- exist", "where are the gaps", or "how far back does history reach". Those are
-- A4's, and reading last_attempt_run_seq to infer any of them would be a
-- category error the A3/A4 boundary exists to prevent.
--
-- ADDITIVE ONLY. Creates one table. Does not touch ohlcv_bars, does not alter
-- 0011 or 0012, and removes nothing. Rollback drops only the table created here;
-- the 0012 progression row and every collected bar survive untouched.
--
-- NOTE ON create_all: scripts/migrate.py runs Base.metadata.create_all BEFORE
-- the pending .sql files, so on a fresh database the MODEL creates this table
-- and the CREATE TABLE below is a no-op. Every constraint that carries
-- correctness is therefore declared in app/models/ohlcv_symbol_progress.py as
-- well, and the two paths are asserted to produce the same catalogue.

CREATE TABLE IF NOT EXISTS ohlcv_symbol_progress (
    -- Venue. Same value the watermark read and the bar write use, so a second
    -- venue can never advance binance's fairness state.
    --
    -- VARCHAR, NOT TEXT — the 0012 lesson, verbatim. create_all runs first and
    -- its Column(String) emits VARCHAR; declaring TEXT here produced a table
    -- whose catalog type depended on which path built it (`character varying`
    -- vs `text`, measured in PostgreSQL 17), and the CHECK then rendered as
    -- length(btrim((col)::text)) in one path and length(btrim(col)) in the
    -- other. Functionally equivalent, not the same catalog object, and
    -- invisible to any test comparing constraint NAMES.
    source                VARCHAR     NOT NULL,

    -- The durable identity. Asset.symbol is unique=True, so this is total and
    -- stable; an index would not be, which is the whole reason this table
    -- exists. Delisting sets Asset.is_active = false and KEEPS the symbol, so a
    -- row here simply stops being selected while the asset is inactive and
    -- resumes its place if it is reactivated.
    symbol                VARCHAR     NOT NULL,

    -- The fairness token: the run_seq of the run that last SELECTED this
    -- symbol. Monotonic and durable because run_seq is. Deliberately NOT a
    -- timestamp — a wall clock is exactly the input whose phase-locking got the
    -- original rotation rejected, and it would also drift with restarts.
    last_attempt_run_seq  BIGINT      NOT NULL DEFAULT 0,

    -- Operator-facing only. A shadow job is excluded from the global /health
    -- `degraded` aggregate and its spec is critical=False, so job_guard's
    -- staleness check short-circuits and can never surface a stalled ledger.
    -- This column is the only way to tell "advancing" from "stuck since last
    -- week". No correctness path reads it.
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- UNNAMED, so both construction paths emit PostgreSQL's default
    -- `ohlcv_symbol_progress_pkey`. Naming it here produced constraint names
    -- that DIFFERED by path in 0012 — measured, and invisible to a test that
    -- only checked a substring was present in both.
    PRIMARY KEY (source, symbol),
    CONSTRAINT ck_ohlcv_symbol_progress_seq CHECK (last_attempt_run_seq >= 0),
    CONSTRAINT ck_ohlcv_symbol_progress_symbol CHECK (length(btrim(symbol)) > 0)
);

-- Oldest-first read support. The selection is "the K active symbols with the
-- smallest last_attempt_run_seq for this source", so the index leads with
-- source and orders by the token. Without it that read degrades to a full scan
-- of the table on every run.
CREATE INDEX IF NOT EXISTS ix_ohlcv_symbol_progress_source_seq
    ON ohlcv_symbol_progress (source, last_attempt_run_seq);

-- ROLLBACK (manual, additive-only reversal — never run against production
-- without an explicit checkpoint; it removes ONLY this table and touches no
-- OHLCV bar and no 0012 state):
--
--   DROP TABLE IF EXISTS ohlcv_symbol_progress;
--
-- The A3F runtime falls back to no partitioning if the table is absent only in
-- the sense that it cannot run at all — the ACTIVATION checkpoint is what makes
-- this table a hard requirement, exactly as 0012 was for run_seq.
