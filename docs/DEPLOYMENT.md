# TradeMinds AI — Deployment Guide

Topology: **Backend → Railway** · **Frontend → Vercel** · **DB/Storage → Supabase**.
Secrets are never committed — set them as platform environment variables.

> ⚠️ Scheduler constraint: the backend runs APScheduler **in-process**. The web
> service MUST run as a **single replica** with **`--workers 1`** (already pinned
> in `railway.json`). Do NOT horizontally scale the web service, or signal/perf
> jobs will run on every replica (duplicate signals & resolutions). Horizontal
> scale requires extracting the scheduler to a dedicated worker (post-beta).

---

## 1. Backend — Railway

- **Root directory:** `backend` (set in the Railway service settings).
- **Config:** `backend/railway.json` (NIXPACKS build, start `uvicorn app.main:app
  --host 0.0.0.0 --port $PORT --workers 1`, healthcheck `/health`, `numReplicas: 1`).
  `backend/Procfile` carries the same start command as a fallback.
- **Environment variables** (from `backend/.env.example` — set each in Railway):
  - `DEBUG=false`, `ENVIRONMENT=production`
  - `DATABASE_URL` → Supabase **pooler** URL (asyncpg), `SUPABASE_URL/KEY/SERVICE_KEY`
  - `UPSTASH_REDIS_URL`
  - `JWT_SECRET` (strong, unique), `JWT_ALGORITHM=HS256`, token expiries
  - `GOOGLE_CLIENT_ID/SECRET`, `GOOGLE_REDIRECT_URI=https://<api-domain>/api/v1/auth/google/callback`
  - `BINANCE_*`, `COINGECKO_API_KEY`, `FRED_API_KEY`
  - `STRIPE_SECRET_KEY/PUBLISHABLE_KEY/WEBHOOK_SECRET`
  - `FRONTEND_BASE_URL=https://<frontend-domain>`
  - `CORS_ORIGINS=["https://<frontend-domain>"]`
- **Health check:** Railway hits `/health` (returns status + service). SSL/domain are platform-provided.
- **DB schema:** the production schema already lives in Supabase. `init_db()` runs
  ONLY when `DEBUG=true`, so production never auto-creates tables. **Future schema
  changes need a migration step** (Alembic — planned post-beta); until then apply
  changes via a reviewed SQL migration against Supabase.

## 2. Frontend — Vercel

- **Root directory:** `frontend`. `frontend/vercel.json` sets framework `nextjs`
  (build/output auto-detected). SSL/domain are platform-provided.
- **Environment variables** (from `frontend/.env.example`):
  - `NEXT_PUBLIC_API_URL=https://<railway-backend-domain>`
  - `NEXT_PUBLIC_SITE_URL=https://<vercel-domain>`
- The API base is read via `process.env.NEXT_PUBLIC_API_URL` (api.ts / useLivePrices /
  useBistStatus) — no hardcoded backend URL ships to production.

## 3. Supabase

- Use the **Supavisor pooler** connection string for `DATABASE_URL` (asyncpg).
- Pool is tuned to ≤10 connections (pool_size 8 + overflow 2) under the 15-connection
  pooler ceiling — see `backend/app/database.py`. Don't raise it without raising the
  pooler limit.
- Backups: rely on Supabase's managed backups (verify the plan's retention).

## 4. Post-deploy checklist

- [ ] Backend `/health` returns 200 on the Railway domain.
- [ ] `CORS_ORIGINS` includes the exact Vercel domain (no trailing slash).
- [ ] Google OAuth: add `https://<api-domain>/api/v1/auth/google/callback` to the
      authorized redirect URIs in Google Cloud.
- [ ] `NEXT_PUBLIC_API_URL` on Vercel points to the Railway backend; reload and
      confirm live prices + signals load (no CORS errors in console).
- [ ] `DEBUG=false` confirmed (no SQL echo / no stack traces to clients).
- [ ] Smoke test: register → login → view signals → pricing → (test) checkout.

## 5. Not yet wired (tracked in the Production Readiness roadmap)

Monitoring (Sentry/UptimeRobot), analytics (GA4/Plausible), rate limiting, legal
pages (Privacy/Terms/KVKK) + site-wide disclaimer, security headers, Alembic
migrations, CI/CD, object storage for PDF reports. See the roadmap.
