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
- **Config:** `backend/railway.json` — NIXPACKS build; **`preDeployCommand: python
  scripts/migrate.py`** (migrations run before the new release goes live); start
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers
  --forwarded-allow-ips=*`; healthcheck `/health`; `numReplicas: 1`. `backend/Procfile`
  carries `release:` (migrate) + `web:` (same start) as a fallback.
  - `--proxy-headers` is required so per-IP rate limiting / bot-challenge key on the
    real client IP (not Railway's proxy) — see `app/rate_limit.py`.
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
- **DB schema / migrations:** managed by `python scripts/migrate.py` (tracked via a
  `schema_migrations` table). Runs automatically each deploy (Railway `preDeployCommand`).
  On `apply` it first ensures the base schema (idempotent `create_all` — only creates
  missing tables, never drops/alters), then applies pending `migrations/000X_*.sql` in
  order, so **a fresh prod DB is built end-to-end**. App startup no longer creates the
  schema (decoupled from `DEBUG`).
  - **Adopting an EXISTING DB once:** `python scripts/migrate.py stamp` marks
    already-applied migrations without re-running them (some are destructive on re-run).
  - Migration `.sql` rules: one statement per line, idempotent (`IF NOT EXISTS`/guarded),
    no `DO/$$` blocks (line-based splitter). Status: `python scripts/migrate.py status`.

## 1.1 ⛳ Yayın için gerekli env değerleri (net liste)

> **Fail-fast guard (M2):** `ENVIRONMENT=production` iken `app/config.py` validator'ı
> aşağıdaki KRİTİK'lerden biri eksik/güvensizse (DEBUG=true · zayıf JWT_SECRET ·
> localhost DATABASE_URL/CORS) uygulamayı **başlatmaz** (RuntimeError). Yani kritikler
> ayarlanmadan prod açılmaz.

**Backend (Railway) — KRİTİK (bunlar olmadan prod güvensiz/kırık):**

| Env | Örnek / not |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `openssl rand -hex 48` (≥32 char, default değil) — token + challenge HMAC |
| `DATABASE_URL` | Supabase **pooler** asyncpg DSN (localhost değil) |
| `CORS_ORIGINS` | `["https://<vercel-domain>"]` (localhost değil; `*` değil) |
| `FRONTEND_BASE_URL` | `https://<vercel-domain>` (Stripe/OAuth redirect) |
| `RATE_LIMIT_ENABLED` | `true` |

**Backend — ÖZELLİK-BAĞIMLI (ilgili özellik açılacaksa):**

| Env | Ne zaman |
|---|---|
| `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` | ücretli abonelik (boşsa checkout 503 — tasarım gereği) |
| `TURNSTILE_SECRET_KEY` + `CHALLENGE_ENABLED=true` | bot-challenge (boşsa no-op) |
| `GOOGLE_CLIENT_ID/SECRET` + `GOOGLE_REDIRECT_URI=https://<api-domain>/api/v1/auth/google/callback` | Google login |
| `SUPABASE_URL/KEY/SERVICE_KEY`, `UPSTASH_REDIS_URL` (rediss:// TLS), `BINANCE_*`, `COINGECKO_API_KEY`, `FRED_API_KEY`, `FINNHUB_API_KEY` | veri/altyapı |
| `SENTRY_DSN` | hata izleme (önerilir) |

**Frontend (Vercel):**

| Env | Örnek / not |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<railway-api-domain>` (KRİTİK — CSP connect-src + API tabanı) |
| `NEXT_PUBLIC_SITE_URL` | `https://<vercel-domain>` (SEO/OG) |
| `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST` | izleme/analitik (önerilir; PostHog consent-gated) |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Turnstile (boşsa widget render olmaz) |

> Stripe (S7) ve Turnstile canlı E2E, gerçek anahtarlar girilince yapılır. Dev/CI için
> Cloudflare always-pass test anahtarları (`1x…AA`) ve Stripe test anahtarları kullanılabilir.

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

> 🧭 **Go-live sırası, migration ilk-çalıştırma kararı (apply vs stamp) ve ROLLBACK** için:
> **[RELEASE-RUNBOOK.md](./RELEASE-RUNBOOK.md)** (A4). Yıkıcı migration / veri-kaybı uyarıları orada.

## 4. Post-deploy checklist

- [ ] Backend `/health` returns 200 on the Railway domain.
- [ ] `CORS_ORIGINS` includes the exact Vercel domain (no trailing slash).
- [ ] Google OAuth: add `https://<api-domain>/api/v1/auth/google/callback` to the
      authorized redirect URIs in Google Cloud.
- [ ] `NEXT_PUBLIC_API_URL` on Vercel points to the Railway backend; reload and
      confirm live prices + signals load (no CORS errors in console).
- [ ] `DEBUG=false` confirmed (no SQL echo / no stack traces to clients).
- [ ] Smoke test: register → login → view signals → pricing → (test) checkout.

## 5. UptimeRobot (health alerting)

- HTTP(s) monitor on `https://<api-domain>/health` (expects 200), 1–5 min interval.
- Add a **keyword** check for `healthy` (catches a 200 with an unhealthy body).
- Alert contacts: email / Slack. (UptimeRobot = uptime; Sentry = errors — both env-gated/wired.)
- Optionally add a monitor for the Vercel frontend URL.

## 6. Wired since this guide was written

Sentry (backend+frontend, env-gated), PostHog analytics (consent-gated), rate limiting
(slowapi), legal pages + single-source disclaimer + KVKK, security headers + CSP, **tracked
migrations** (`migrate.py` + `schema_migrations`, auto-run on deploy), adaptive bot
challenge (Turnstile, env-gated), prod fail-fast config validator. See `docs/SECURITY.md`,
`docs/SMOKE-TEST.md`, `docs/PHASE2-ROADMAP.md`.

## 7. Still open (post-beta)

Horizontal scaling (extract scheduler to a worker + counters → Redis), CI/CD pipeline,
object storage for PDF reports, nonce-based CSP, GA4/Plausible.
