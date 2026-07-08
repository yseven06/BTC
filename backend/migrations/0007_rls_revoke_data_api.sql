-- 0007_rls_revoke_data_api.sql
-- RLS Aşama-2 — Data API sertleştirme (defense-in-depth).
-- Aşama-1 (0006) 21 public tabloda RLS ENABLE + deny-all yaptı; anon/authenticated
-- RLS sayesinde 0 satır görüyor AMA tablo grant'ları hâlâ duruyor → RLS tek savunma
-- hattı. Bu migration anon + authenticated rollerinden TÜM ayrıcalıkları ve schema
-- USAGE'ı geri alır: RLS yanlışlıkla kapatılsa/izin-veren policy eklense bile
-- Data API "permission denied" döner (veri değil). USAGE revoke tek başına da
-- gelecekteki tablolara erişimi kapatır.
--
-- KAPSAM: yalnız anon + authenticated. postgres (owner, bypassrls) ve service_role
-- DOKUNULMAZ — backend asyncpg (postgres owner) ile bağlanır, etkilenmez. App Data
-- API'yi kullanmıyor (frontend supabase-js yok; backend supabase-client yok).
-- Idempotent (REVOKE no-op toleranslı) · satır-başı tek-statement (migrate.py splitter).
--
-- ROLLBACK (down) — gerekirse elle çalıştır:
--   GRANT USAGE ON SCHEMA public TO anon, authenticated;
--   GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
--   GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
--   GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM anon;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM authenticated;
REVOKE USAGE ON SCHEMA public FROM anon;
REVOKE USAGE ON SCHEMA public FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM authenticated;
