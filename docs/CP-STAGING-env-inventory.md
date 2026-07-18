# CP-STAGING-B — Env / Secrets Inventory (doc-only)

**Tarih:** 2026-07-18 · **Statü:** salt-karar dokümanı (kod/deploy/secret-taşıma YOK)
**Amaç:** Private staging'e geçmeden önce hangi env/secret'lar taşınmalı / taşınmamalı / local-only kalmalı sınıflandırması. **Bu doküman hiçbir gerçek değer içermez — yalnız key ADLARI, amaç, risk, gereklilik.** Kaynak: `backend/.env.example` (placeholder, tracked) + kod taraması. `backend/.env` (gerçek değerler) **okunmadı.**

> **Kapsam hatırlatması:** Staging = **backend-only private observation** (headless scheduler, public yüzey yok). Bu yüzden **hiçbir `NEXT_PUBLIC_*` (frontend/Vercel) key'i backend staging'e gitmez** ve **auth/payment/beta key'leri taşınmaz** (private-only sınırı).

## İki yapısal bulgu (envanteri etkiler)
1. **Telegram bot-token/chat_id GLOBAL ENV DEĞİL** — per-user, DB'de (`notification_settings.telegram_bot_token/telegram_chat_id`). ⇒ Staging'e Telegram env-key **gerekmez**; mevcut fan-out DB'den otomatik çalışır (davranış değişmez).
2. **`TURNSTILE_SECRET_KEY` `.env.example`'da yok** (frontend site-key var, backend secret'ı referanslı ama tanımsız) → henüz-bağlı-değil / beta-bekliyor. ⇒ Private observation için **gereksiz**.

---

## 1. Env/secret kategorileri
DB bağlantısı · Supabase · Binance/market-data · Scheduler/runtime config · Observability/alarm · Auth/payment/beta/legal · Frontend/public config · local-only dev config.

## 2. Key tablosu (yalnız adlar; değer YOK)

**Kısaltmalar:** Sınıf = Secret / Config · Stag = staging-observation'a gerekir mi · Prod = public-production'da gerekir mi · Risk = maruz-kalırsa etki.

### DB / Supabase
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `DATABASE_URL` | asyncpg DB bağlantısı (scheduler'ın DB'si) | **Secret** | **EVET (zorunlu)** | hayır | evet | **YÜKSEK** (yazma yetkili) | Tek en-kritik key. Aynı Supabase. Pool 8+2 korunur. |
| `SUPABASE_URL` | Supabase proje URL'i (supabase-py client varsa) | Config/low | verify | hayır | evet | Düşük | App-init'te gerekebilir → C dry-run'da doğrula. |
| `SUPABASE_KEY` (anon) | PostgREST anon | Secret-low | verify | hayır | evet | Orta | Muhtemelen scheduler'a gereksiz (DATABASE_URL yeterli). |
| `SUPABASE_SERVICE_KEY` | service-role (RLS-bypass) | **Secret** | verify | hayır | evet | **YÜKSEK** | Yalnız admin/PostgREST yolu kullanıyorsa; C'de doğrula. |

### Binance / market-data
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `BINANCE_BASE_URL` | Binance API kökü | Config | **EVET** | hayır | evet | Düşük | **Bölge-kritik** (host US-dışı olmalı) — C'de reach test. |
| `BINANCE_API_KEY` | Binance auth | Secret | **muhtemelen HAYIR** | hayır | belki | Orta | Public OHLC (klines) auth istemez; auto-trade yok → opsiyonel. C'de doğrula. |
| `BINANCE_API_SECRET` | Binance auth | **Secret** | **muhtemelen HAYIR** | hayır | belki | Orta | Yukarıdaki ile aynı; public-veri için gereksiz. |
| `COINGECKO_API_KEY` | CoinGecko (F&G/metadata) | Secret | opsiyonel | hayır | evet | Düşük | Free-tier keysiz çalışır ama rate-limit'li (kayıtlı sorun). |
| `COINGECKO_BASE_URL` | CoinGecko kökü | Config | opsiyonel | hayır | evet | Düşük | — |
| `FRED_API_KEY` | Makro (FED faiz) verisi | Secret | opsiyonel | hayır | evet | Düşük | Makro motoru koşuyorsa; yoksa motor sessiz-düşer. |

### Scheduler / runtime config
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `ENVIRONMENT` | ortam adı | Config | **EVET** | hayır | evet | Düşük | Staging'de `staging`/`production`; `development` DEĞİL. |
| `DEBUG` | debug modu | Config | **EVET** | hayır | evet | Düşük | Staging'de `false`. |
| `LOG_LEVEL` | log seviyesi | Config | evet | hayır | evet | Düşük | INFO. |
| `APP_NAME` / `APP_VERSION` / `API_PREFIX` | uygulama meta | Config | evet | hayır | evet | Düşük | — |

### Observability / alarm
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `CP_OBS_ALARM_PING_URL` | dead-man's-switch ping | **Secret** | **EVET (ayrı değer)** | hayır | evet | Orta | **Staging'de local'den FARKLI/ayrı ping URL** (plan §4). |
| `SENTRY_DSN` | hata izleme | Secret-low | opsiyonel | hayır | evet | Düşük | Boş = kapalı. İstenirse staging için ayrı proje. |
| `SENTRY_TRACES_SAMPLE_RATE` | trace örnekleme | Config | opsiyonel | hayır | evet | Düşük | — |

### Auth / payment / beta / legal — **PRIVATE STAGING'e TAŞINMAZ**
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `JWT_SECRET` (+`JWT_ALGORITHM`,`ACCESS_TOKEN_EXPIRE_MINUTES`,`REFRESH_TOKEN_EXPIRE_DAYS`) | kullanıcı auth | **Secret** | **HAYIR** | hayır | evet | **YÜKSEK** | Headless observation kullanıcı sunmaz → gereksiz. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | OAuth signup | **Secret** | **HAYIR** | hayır | evet | **YÜKSEK** | Signup=public/beta. |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | ödeme | **Secret** | **HAYIR (kesin)** | hayır | evet | **YÜKSEK** | Public beta'ya kadar ASLA taşınmaz. |
| `TURNSTILE_SECRET_KEY` (tanımsız/bekliyor) | bot-challenge | Secret | **HAYIR** | hayır | evet | Orta | Beta-bekliyor; observation'a gereksiz. |
| `FRONTEND_BASE_URL` / `CORS_ORIGINS` | OAuth/Stripe redirect + CORS | Config | **HAYIR** | hayır | evet | Düşük | Yalnız public HTTP API için. |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_LOGIN` / `RATE_LIMIT_REGISTER` / `RATE_LIMIT_REFRESH` / `RATE_LIMIT_CHECKOUT` | public-endpoint hız-sınırı | Config | **HAYIR** | hayır | evet | Düşük | Yalnız public auth/checkout route'ları için. |

### Diğer altyapı
| Key | Amaç | Sınıf | Stag | Local-only | Prod | Risk | Not |
|---|---|---|---|---|---|---|---|
| `UPSTASH_REDIS_URL` | Redis (rate-limit/cache) | **Secret** | **verify** | hayır | evet | Orta | Rate-limit public'e ait; scheduler-yolu Redis kullanıyorsa gerekir → C'de doğrula, aksi halde gereksiz. |

### Frontend / public (Vercel) — **backend staging'e HİÇ gitmez (N/A)**
`NEXT_PUBLIC_API_URL` · `NEXT_PUBLIC_SITE_URL` · `NEXT_PUBLIC_SENTRY_DSN` · `NEXT_PUBLIC_POSTHOG_KEY` · `NEXT_PUBLIC_POSTHOG_HOST` · `NEXT_PUBLIC_APP_VERSION` · `NEXT_PUBLIC_TURNSTILE_SITE_KEY` → **frontend-only**; private backend-observation staging'inde yeri yok.

### local-only dev
`DEBUG=true` · `ENVIRONMENT=development` · localhost URL'leri (`FRONTEND_BASE_URL`, `GOOGLE_REDIRECT_URI`, CORS localhost) → dev-varsayılanları; staging'de production-benzeri değerlerle **override edilir**, taşınmaz.

## 3. Güvenlik kuralları
- **Secret değerleri repo'ya YAZILMAZ**; bu doküman yalnız key-adı taşır.
- **`.env` commitlenmez** (zaten gitignore); **`.env.example` yalnız boş placeholder** içerir.
- Staging'de secret'lar **PaaS env-var UI / secret manager**'da tutulur (Railway service variables); repoda değil.
- **`CP_OBS_ALARM_PING_URL` staging'de AYRI değer** (local ping URL'inden farklı; iki ortam ayrı izlenir).
- **DB write yetkisi minimumda:** C dry-run **scheduler'ı BAŞLATMAZ** → yazma-yolu yapısal olarak kapalı (yalnız connectivity/Binance/env testi). İstenirse dry-run için **SELECT-only DB rolü** (belt-and-suspenders; DB-admin adımı, opsiyonel). Yazma yalnız D-cutover'da açılır.
- Şüpheli maruziyet → ilgili secret **rotate** (DATABASE_URL/Supabase/CP_OBS ping).

## 4. Staging-B verdict
- **Env inventory tamam mı?** **EVET** — `backend/.env.example` kanonik deploy-setidir; iki bulgu (Telegram=DB / Turnstile-secret=beta-pending) not edildi. Eksik key-TANIMI yok; C'de yalnız DEĞERLER taşınacak.
- **Staging-C dry-run için eksik key var mı?** **HAYIR** (tanım düzeyinde). Dry-run yalnız birkaç key'in DEĞERİNİ ister (aşağıda). `SUPABASE_*` / `BINANCE_API_*` / `UPSTASH_REDIS_URL` → "verify" (muhtemelen gereksiz; C'de kesinleşir).
- **Hangi key'ler olmadan dry-run YAPILAMAZ (zorunlu minimum):** `DATABASE_URL` (DB-connect) · `BINANCE_BASE_URL` (+host bölge reach) · `ENVIRONMENT`/`DEBUG`/`LOG_LEVEL` (app-init). Bunlar olmadan C başlamaz.
- **Public beta açılana kadar TAŞINMAZ:** `STRIPE_*` (kesin) · `GOOGLE_*` · `JWT_*` · `TURNSTILE_*` · `FRONTEND_BASE_URL`/`CORS_ORIGINS` · `RATE_LIMIT_*` · tüm `NEXT_PUBLIC_*`. Bunları taşımak private-only sınırını kırar (kullanıcı-yüzlü yetenek ima eder).

---

**Sonraki adım:** CP-STAGING-C (private worker dry-run) — bu envanterin **zorunlu minimum** setini PaaS'a girip **Binance-bölge reach + DB-connect + "üretir-ama-yazmaz"** doğrulaması (scheduler başlatılmadan). Ayrı onay. Bu doküman salt-karar; kod/deploy/secret-taşıma yok.
