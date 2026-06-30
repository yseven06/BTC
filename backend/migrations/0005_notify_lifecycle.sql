-- 0005: per-user opt-in for proactive lifecycle-transition notifications (P1.2).
-- Additive + idempotent. Default FALSE so existing users' behaviour is UNCHANGED
-- (no one receives lifecycle alerts until they explicitly opt in). One statement
-- per line (naive ';' splitter; no DO/$$ blocks).
-- Apply via: python scripts/run_migration.py migrations/0005_notify_lifecycle.sql
-- (restart backend first to clear idle-in-transaction sessions that lock ALTER.)

ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS notify_lifecycle BOOLEAN NOT NULL DEFAULT false;
