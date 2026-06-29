# Güvenlik (Security) — Posizyon, Ops ve Checklist

TradeMinds AI güvenlik sertleştirmesi (Madde 6) özeti + operasyon rehberi.
İlgili: [DEPLOYMENT.md](./DEPLOYMENT.md), [OPERATIONS.md](./OPERATIONS.md),
[CAPTCHA-STRATEGY.md](./CAPTCHA-STRATEGY.md), [LEGAL-PACKAGE-PLAN.md](./LEGAL-PACKAGE-PLAN.md).

> İlke: **maksimum savunma.** Frontend bundle tarayıcıda görünür (gizlenemez) —
> ama içinde secret yok, prod source map yayınlanmaz, stack trace sızmaz.

---

## 1. Secret & kaynak ifşası
- **.env / secret:** `.gitignore` (21-23) `.env`, `.env.local`, `.env.*.local` kapsar; git'e commit edilmiş secret **yok** (doğrulandı). `.git`/`.env` prod'da HTTP'den servis edilmez (Vercel/Railway yalnız uygulamayı servis eder; Next yalnız `/public`).
- **Frontend secret:** yalnız `NEXT_PUBLIC_*` (tasarım gereği public: API URL, Sentry DSN, PostHog key, app version). Gerçek secret yok.
- **Prod source map:** Next varsayılanı kapalı (`next.config` `productionBrowserSourceMaps` açmıyor). Sentry'ye kontrollü upload ileride eklenebilir (CLI/Vercel entegrasyonu).
- **robots.txt:** `/public/robots.txt` — landing + `/yasal` crawlable; admin/api/app Disallow.

## 2. Güvenlik header'ları (Madde 6b)
- **Frontend** (`next.config.js` `headers()`, her route): HSTS(preload), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, **CSP** (default-src 'self'; frame-ancestors 'none'; object-src 'none'; img/font/style/script/connect/frame-src allowlist: API, PostHog EU, Sentry, Google Fonts, Turnstile).
- **Backend** (`SecurityHeadersMiddleware`, her yanıt): nosniff, XFO=DENY, Referrer-Policy=no-referrer, Permissions-Policy, COOP=same-origin, HSTS. (CSP backend'de yok — JSON API.)
- **Prod'da `/docs`, `/redoc`, `/openapi.json` kapalı** (DEBUG-gated) — API şeması dışarı açılmaz.

## 3. Kimlik doğrulama / yetkilendirme (Madde 6a)
- Tüm `/admin/*` → `require_admin`/`require_super_admin`; user-scoped CRUD → `get_current_user` + `user_id` filtreleme; `/consent/*` → auth.
- **6a düzeltmesi:** `/notifications/{settings,test}` artık auth zorunlu (eskiden anonim erişilebiliyordu — KRİTİK kapatıldı).
- **Bekleyen (takip işi):** notification settings global singleton → per-user'a taşınmalı (`task_0d92600b`).

## 4. Hata & log hijyeni (Madde 6c)
- Route'larda ham `str(e)`/`{exc}` istemciye sızmaz → generic mesaj + server-side `logger.error(exc_info=True)`.
- Global handler: exception sınıf adı yerine **correlation_id** (+ `X-Correlation-ID`) döndürür.
- **DEBUG=false** prod'da zorunlu (varsayılan False; FastAPI debug + SQL echo + init_db buna bağlı). Loglarda secret/token/DB-URL yok (denetimde teyit).

## 5. Girdi / upload / CORS / webhook (Madde 6d)
- **Body-size:** `MaxBodySizeMiddleware` — Content-Length > 3 MB → 413.
- **Avatar upload:** uzantı + content-type allowlist + **2 MB** sınırı + **magic-byte** sniff + uuid dosya adı (path traversal/overwrite yok).
- **CORS:** `CORS_ORIGINS` allowlist (prod'da yalnız Vercel domain'i; `*` değil).
- **Stripe webhook:** `stripe.Webhook.construct_event` ile imza doğrulamalı (`STRIPE_WEBHOOK_SECRET`).

## 6. Rate limit / brute-force / credential-stuffing
- **slowapi** (Madde 4): public auth/checkout endpoint'lerinde per-IP limit (login/register/google-login/refresh/checkout), XFF-aware, 429 JSON.
- **Adaptif CAPTCHA (Turnstile)** ADR hazır (`CAPTCHA-STRATEGY.md`): soft-limit/auth-failure tetikli challenge + bypass — Legal sonrası uygulanacak. Credential-stuffing için A3 auth-failure sayacı orada.

## 7. DDoS / edge koruması (öneri — ops)
Uygulama: FastAPI (Railway, tek replica) + Next.js (Vercel) + Supabase.
- **Cloudflare (önerilen, öne proxy):** DNS proxy (turuncu bulut) ile frontend domain'i (ve mümkünse Railway backend custom domain) Cloudflare arkasına alın. Kazanım: WAF, **rate-limiting kuralları**, bot mitigation, **"Under Attack" modu**, statik cache. Uygulama-içi slowapi + Turnstile ile katmanlı çalışır (Cloudflare hacmi keser, slowapi blast-radius'u sınırlar, Turnstile insan/bot ayırır).
- **Vercel:** otomatik DDoS mitigation + (Pro) Firewall — frontend için hazır gelir; ek WAF kuralları Pro/Enterprise'da.
- **Railway:** platform edge limitleri var; uygulama-içi rate limit + tek-replica ölçek sınırı nedeniyle backend'i Cloudflare arkasına almak en etkilisi.
- **Beta için minimum:** Cloudflare DNS proxy + temel rate-limit kuralı (örn. /api/v1/auth/* için IP başına dk limiti) + bot fight mode; saldırı anında "Under Attack". Custom domain + Cloudflare bağlanınca backend `client_ip` için `CF-Connecting-IP`'ye geçilebilir (slowapi key_func notu — CAPTCHA-STRATEGY §8).

## 8. Bağımlılık denetimi (Madde 6f — bekleyen bump'lar)
`npm audit` + `pip-audit` ile gerçek tarama yapıldı (2026-06 CVE DB). **Önerilen yükseltmeler** (ayrı commit + test ile):
| Paket | Mevcut | Hedef | Önem |
|---|---|---|---|
| next (frontend) | 15.3.3 | **15.5.19** | **KRİTİK** (React flight RCE GHSA-9qr9-h5gf-34mp + SSRF/DoS; non-major) |
| aiohttp | 3.9.5 | 3.14.1 | Yüksek (31 açık; outbound client) |
| python-multipart | 0.0.9 | 0.0.31 | Yüksek (multipart DoS) |
| python-jose | 3.3.0 | 3.4.0 | Orta (algoritma karışıklığı; allowlist mevcut) |
| python-dotenv | 1.0.1 | 1.2.2 | Düşük (kullanılmayan fonksiyon) |
| fastapi (→starlette) | 0.111.0 | güncel | Yüksek ama **regresyon riski** — izole/ayrı test |

**Rutin:** CI'a `npm audit --omit=dev --audit-level=high` + `pip-audit -r requirements.txt` ekleyin (haftalık cron + PR). `pip-audit` backend dev bağımlılığı olarak pinlenmeli (Dependabot/Renovate önerilir).

## 9. Yayın öncesi güvenlik checklist'i
- [ ] Prod env: `DEBUG=false`, `ENVIRONMENT=production` (Railway). `/health` → `debug_mode:false`.
- [ ] Prod secret'lar platform env'inde (Railway/Vercel); dev key'leri rotate edildi.
- [ ] `CORS_ORIGINS` = yalnız prod frontend domain'i (trailing slash yok).
- [ ] Güvenlik header'ları canlı (frontend + backend) — curl ile teyit.
- [ ] `/docs` prod'da kapalı (DEBUG=false → otomatik).
- [ ] Bağımlılık bump'ları (en az next 15.5.19 — kritik RCE) yapıldı + test edildi.
- [ ] Cloudflare/Vercel edge + temel rate-limit kuralları açık.
- [ ] Stripe webhook secret set + imza doğrulaması çalışıyor.
- [ ] ConsentLog migration uygulandı; Legal metinleri avukat onaylı (v1.0.0).
- [ ] (İleride) Turnstile + per-user notification settings.
