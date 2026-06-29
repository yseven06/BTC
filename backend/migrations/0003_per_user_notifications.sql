-- 0003: per-user notification settings (remove the global singleton)
-- The old single global row is configuration-only (no per-user data worth keeping);
-- we drop all rows, add a per-user owner column, and let settings be recreated
-- per-user on demand. Idempotent (safe to re-run). One statement per line so the
-- migration runner's naive ';' splitter handles it (no DO/$$ blocks).
-- Apply via: python scripts/run_migration.py migrations/0003_per_user_notifications.sql
-- (restart backend first to clear idle-in-transaction sessions that lock ALTER.)

DELETE FROM notification_settings;
ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE notification_settings DROP CONSTRAINT IF EXISTS fk_notification_settings_user;
ALTER TABLE notification_settings ADD CONSTRAINT fk_notification_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_settings_user ON notification_settings (user_id);
ALTER TABLE notification_settings ALTER COLUMN user_id SET NOT NULL;
