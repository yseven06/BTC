-- 0002: Stripe subscription support
-- Idempotent + additive only (safe to run multiple times).
--  * stripe_events: webhook idempotency guard (processed event ids)
--  * payments.stripe_invoice_id: links recurring-renewal payments to the Stripe invoice
-- Apply via: python scripts/run_migration.py migrations/0002_stripe_subscription.sql
-- (restart backend first to clear idle-in-transaction sessions — see docs/known issue)

CREATE TABLE IF NOT EXISTS stripe_events (
    id          VARCHAR(255) PRIMARY KEY,
    type        VARCHAR(128) NOT NULL,
    received_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

ALTER TABLE payments ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS ix_payments_stripe_invoice_id ON payments (stripe_invoice_id);
