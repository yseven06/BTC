-- 0003: per-user notification settings (remove the global singleton)
-- The old single global row is configuration-only (no per-user data worth keeping);
-- we drop all rows, add a per-user owner column, and let settings be recreated
-- per-user on demand. Idempotent + guarded so it is safe to re-run.
-- Apply via: python scripts/run_migration.py migrations/0003_per_user_notifications.sql
-- (restart backend first to clear idle-in-transaction sessions that lock ALTER.)

-- 1) Clear the legacy global singleton row(s).
DELETE FROM notification_settings;

-- 2) Add the per-user owner column.
ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS user_id UUID;

-- 3) FK to users (guarded — Postgres has no IF NOT EXISTS for constraints).
DO $$ BEGIN
    ALTER TABLE notification_settings
        ADD CONSTRAINT fk_notification_settings_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4) One settings row per user.
DO $$ BEGIN
    ALTER TABLE notification_settings
        ADD CONSTRAINT uq_notification_settings_user UNIQUE (user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 5) Owner is mandatory (table is empty after step 1, so this is safe).
ALTER TABLE notification_settings ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_notification_settings_user_id ON notification_settings (user_id);
