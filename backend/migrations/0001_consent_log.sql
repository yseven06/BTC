-- ============================================================================
-- 0001_consent_log.sql
-- Madde 5f — ConsentLog (append-only audit) + User consent current-state columns.
--
-- Idempotent: safe to run more than once. Apply to Supabase (prod + dev) since
-- init_db() only runs under DEBUG and create_all() never ALTERs existing tables.
--
-- ⚠️ ALTER TABLE acquires a lock. Per project history (idle-in-transaction leak),
-- run this when there are no idle-in-transaction sessions; if it hangs, restart
-- the Supabase project/pooler first, then re-run.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --- Append-only consent audit trail ---------------------------------------
CREATE TABLE IF NOT EXISTS consent_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE SET NULL,
    anonymous        BOOLEAN NOT NULL DEFAULT FALSE,
    consent_type     VARCHAR(50)  NOT NULL,
    action           VARCHAR(20)  NOT NULL,
    document_slug    VARCHAR(100),
    document_version VARCHAR(20),
    document_hash    VARCHAR(64),
    source           VARCHAR(30)  NOT NULL,
    locale           VARCHAR(10),
    ip_address       VARCHAR(64),
    user_agent       TEXT,
    checkbox_states  JSONB,
    details          JSONB,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_consent_logs_user_id      ON consent_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_consent_logs_consent_type ON consent_logs(consent_type);
CREATE INDEX IF NOT EXISTS ix_consent_logs_source       ON consent_logs(source);
CREATE INDEX IF NOT EXISTS ix_consent_logs_created_at   ON consent_logs(created_at);

-- --- User consent current-state mirror -------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_acked_at  TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_acked_at     TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_consent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS analytics_consent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_version     VARCHAR(20);
