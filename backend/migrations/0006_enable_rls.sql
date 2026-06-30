-- 0006: enable Row-Level Security on every public table (security hardening,
-- Phase 1). Closes the Supabase `rls_disabled_in_public` CRITICAL advisory:
-- with RLS off + Supabase default grants, the anon/authenticated roles could
-- read/insert/update/delete every table via the PostgREST Data API.
--
-- Scope of THIS migration (deliberately minimal — Phase 1 only):
--   * ENABLE (not FORCE) RLS on all 21 public tables.
--   * NO policies   → with RLS on + no policy, anon/authenticated get deny-all.
--   * NO REVOKE     → Phase 2 (defense-in-depth), separate analysis/approval.
--   * NO FORCE      → owner is never subjected to RLS.
--
-- App impact: NONE. The backend connects as `postgres`, which is the OWNER of
-- every table AND has rolbypassrls=true → it bypasses RLS entirely. The app
-- does not use the anon/authenticated roles. So this blocks the public REST
-- exposure without changing any backend behaviour.
--
-- Idempotent: ENABLE ROW LEVEL SECURITY is a no-op if already enabled; IF EXISTS
-- guards a missing table. One statement per line (naive ';' splitter; no DO/$$).
-- Rollback: ALTER TABLE <t> DISABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.stripe_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.consent_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.notification_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.admin_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.portfolio_holdings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_performances ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_trade_path ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.coin_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.analysis_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.price_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.schema_migrations ENABLE ROW LEVEL SECURITY;
