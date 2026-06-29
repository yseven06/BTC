-- 0004: additive birth-time telemetry escape hatch on signal_snapshots.
-- Holds extra["birth"] = generation-time provenance (atr_fallback, sr_override,
-- nearest S/R, entry geometry, risk inputs, volatility/confidence snapshot) for
-- backward analysis, Coin Memory v2, Similarity v2, Adaptive Learning and TP/SL
-- calibration. Pure telemetry — never read by the live decision path.
--
-- Idempotent + non-destructive: nullable JSON column, safe on re-run and a no-op
-- on a fresh DB where create_all already added it from the model.
ALTER TABLE signal_snapshots ADD COLUMN IF NOT EXISTS extra JSON;
