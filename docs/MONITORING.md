# Monitoring & Analytics — Kurulum ve Doğrulama

TradeMinds AI'ın izleme (Sentry), ürün analitiği (PostHog) ve dış erişilebilirlik
takibi (UptimeRobot) katmanlarının kurulum rehberi.

> **Tasarım ilkesi — env-gated / no-op:** Bu katmanların *tamamı* environment
> değişkeni olmadan **hiçbir şey yapmaz** (no-op). DSN/key girilmemiş bir ortamda
> kod çalışır ama dışarıya tek bir istek bile gitmez. Bu sayede lokal/dev ve
> arka plandaki **TM v2 veri toplama** süreci hiçbir şekilde etkilenmez.
> İzleme yalnızca production/beta ortamında, platform env değişkenleri set
> edilince devreye girer.

İlgili belge: deploy adımları için [DEPLOYMENT.md](./DEPLOYMENT.md), deploy
sonrası operasyon için [OPERATIONS.md](./OPERATIONS.md).

---

## 0. Mimari özet

| Katman | Kapsam | Sağlayıcı | Gate (devreye girme koşulu) |
|---|---|---|---|
| Hata izleme — backend | FastAPI exception + performance trace | Sentry | `SENTRY_DSN` set |
| Hata izleme — frontend | Next.js client/server/edge hataları | Sentry | `NEXT_PUBLIC_SENTRY_DSN` set |
| Ürün analitiği | Funnel event'leri (frontend-only) | PostHog (EU Cloud) | `NEXT_PUBLIC_POSTHOG_KEY` set **ve** kullanıcı consent verdi |
| Erişilebilirlik | `/health` dış ping + alarm | UptimeRobot | Monitor oluşturuldu |

- **Backend yalnızca Sentry** kullanır; PostHog backend'de yoktur.
- **PostHog yalnızca frontend**tedir ve **provider-agnostik bir facade**
  (`frontend/src/lib/analytics.ts`) arkasındadır — uygulamanın hiçbir yeri
  doğrudan `posthog`'u import etmez.
- Tüm DSN/key'ler **secret değildir** anlamına gelmez: `NEXT_PUBLIC_*` değerleri
  tarayıcıya açılır (DSN/PostHog key bunun için tasarlanmıştır), ama
  `SENTRY_DSN` (backend) ve diğer gizli anahtarlar yalnızca platform env'inde
  tutulur.

---

## 1. Sentry — Backend (FastAPI)

**Kod:** `backend/app/main.py` (init), `backend/app/config.py` (ayarlar).

Init yalnızca `settings.SENTRY_DSN` dolu ise çalışır:

```python
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    logger.info("Sentry monitoring enabled (environment=%s).", settings.ENVIRONMENT)
```

### Env değişkenleri
| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `SENTRY_DSN` | `""` (boş = kapalı) | Sentry proje DSN'i. Boşsa `sentry_sdk.init()` hiç çağrılmaz. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Performance trace örnekleme oranı (0.0–1.0). |
| `ENVIRONMENT` | `development` | Sentry'de ortam etiketi (`production`/`beta`/…). |

### Kurulum
1. [sentry.io](https://sentry.io) → yeni **Python / FastAPI** projesi oluştur.
   Veri bölgesi olarak **EU**'yu seç (frontend ile tutarlı olsun).
2. Proje DSN'ini kopyala.
3. Railway → backend service → **Variables**:
   - `SENTRY_DSN = https://...ingest.de.sentry.io/...`
   - `ENVIRONMENT = production` (veya `beta`)
   - (opsiyonel) `SENTRY_TRACES_SAMPLE_RATE = 0.1`
4. Deploy → loglarda `Sentry monitoring enabled (environment=production).` satırını gör.

### Davranış / notlar
- `send_default_pii=False`: kullanıcı e-postası/IP gibi PII **gönderilmez**.
- DSN yoksa tamamen no-op — dev'de Sentry sessizdir.
- `@lru_cache()` nedeniyle `settings` process başında bir kez okunur; env
  değişkenini değiştirince **yeniden başlatma** gerekir.

---

## 2. Sentry — Frontend (Next.js)

**Kod:** `frontend/instrumentation.ts`, `frontend/instrumentation-client.ts`,
`frontend/sentry.server.config.ts`, `frontend/sentry.edge.config.ts`.

Üç runtime (client/server/edge) için ayrı config; her biri DSN yoksa no-op:

```ts
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}
```

Dışa verilen kancalar: `onRequestError` (server component hataları),
`onRouterTransitionStart` (client navigasyon trace'i).

### Env değişkenleri
| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | `""` (boş = kapalı) | Frontend Sentry DSN'i. Boşsa üç runtime de no-op. |

### Kurulum
1. Sentry'de ikinci bir proje aç: **Next.js** (yine **EU** bölgesi).
2. DSN'i kopyala.
3. Vercel → Project → **Settings → Environment Variables**:
   - `NEXT_PUBLIC_SENTRY_DSN = https://...ingest.de.sentry.io/...`
   - (zaten set:) `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_API_URL`
4. Yeniden deploy (NEXT_PUBLIC değişkenleri **build-time** gömülür — yeni
   değişken için yeni build şart).

### Davranış / notlar
- `next.config.js` **`withSentryConfig` ile sarılmadı** (dev/build riskini
  önlemek için bilinçli karar). Runtime hata yakalama Next-native instrumentation
  dosyalarıyla çalışır.
- **Source-map upload yapılandırılmadı.** Dolayısıyla production stack trace'leri
  minified görünür. Okunabilir stack için sonradan Sentry CLI / Vercel Sentry
  entegrasyonu eklenebilir (beta sonrası). Hata yakalama bundan etkilenmez,
  yalnızca satır eşleme okunabilirliği etkilenir.
- `tracesSampleRate: 0.1` → trace'lerin %10'u gönderilir (maliyet kontrolü).

---

## 3. PostHog — Ürün analitiği (frontend-only)

**Kod:** `frontend/src/lib/analytics.ts` (facade — `posthog`'u import eden **tek**
dosya), `frontend/src/lib/analytics-events.ts` (event taksonomisi),
`frontend/src/components/AnalyticsProvider.tsx` (yaşam döngüsü bağlama).

### Env değişkenleri
| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `NEXT_PUBLIC_POSTHOG_KEY` | `""` (boş = kapalı) | PostHog proje API key'i. Boşsa analitik tamamen no-op. |
| `NEXT_PUBLIC_POSTHOG_HOST` | `https://eu.i.posthog.com` | **EU Cloud** varsayılan. |
| `NEXT_PUBLIC_APP_VERSION` | kod `0.0.0`, `.env.example` `1.0.0` | Her event'e `app_version` olarak eklenir. |

### Consent akışı — KRİTİK: iki koşul birden
Event'ler ancak **HER İKİSİ** sağlanınca gönderilir:

1. `NEXT_PUBLIC_POSTHOG_KEY` set (init olur), **ve**
2. `setAnalyticsConsent(true)` çağrıldı (kullanıcı çerez izni verdi).

PostHog `opt_out_capturing_by_default: true` ile başlatılır; `track()` çağrıları
bile consent gelene kadar PostHog katmanında bloke edilir. Facade içindeki
`active()` koşulu: `_initialized && _consent && isBrowser`. Üçünden biri eksikse
tüm `track/identify/reset/pageview` sessizce hiçbir şey yapmaz.

> **Operasyon notu:** Çerez izni banner'ı henüz yok (Production Readiness
> **Madde 5 — Legal/Consent**'te gelecek). Banner gelene kadar `setAnalyticsConsent(true)`
> çağıran bir yer **olmadığından**, PostHog key girilse bile event akmaz. Yani
> analitiğin tam aktif olması için: key set **+** consent banner devrede.

### Facade API (uygulama yalnızca bunları çağırır)
`initAnalytics()`, `setAnalyticsConsent(granted)`, `setUserTier(tier)`,
`track(event, props)`, `identify(userId, traits)`, `reset()`, `pageview(path)`.
Sağlayıcı değişirse **yalnızca `analytics.ts` değişir**; çağrı noktaları aynı kalır.

### Init seçenekleri
`autocapture: false` (otomatik tık takibi yok), `capture_pageview: false`
(pageview'lar manuel — `AnalyticsProvider` her route değişiminde `pageview()`
çağırır), `capture_pageleave: true`, `persistence: 'localStorage+cookie'`,
`person_profiles: 'identified_only'` (profil yalnız login'de `identify()` ile).

### Ortak property seti (her event'te otomatik)
`app_version`, `schema_version` (= `1`; taksonomi değişince
`ANALYTICS_SCHEMA_VERSION` artırılır), `user_tier` (`useTierLimits` ile senkron),
`source` (`'web'`). Çağıran taraf üstüne `symbol`, `timeframe`, `regime`, `tier`
gibi alanlar ekler.

### Event taksonomisi (versiyonlu)
13 event tanımlı (`analytics-events.ts`), **5'i** şu an bağlı (Madde 2e):

| Event sabiti | Gönderilen ad | Tetiklendiği yer | Ek property |
|---|---|---|---|
| `signup_completed` | `signup_completed_v1` | `auth-context` register | `method` |
| `login_completed` | `login_completed_v1` | `auth-context` login + googleLogin | `method` |
| `signal_viewed` | `signal_viewed_v1` | `SignalDetailSection` mount | `signal_id, symbol, market, timeframe` |
| `pricing_viewed` | `pricing_viewed_v1` | `pricing` sayfası mount | — |
| `checkout_started` | `checkout_started_v1` | `pricing` `subscribe()` | `tier, billing_cycle` |

Tanımlı ama henüz **bağlı olmayan 8 event** (gerektiğinde eklenir):
`landing_cta_clicked`, `signup_started`, `signal_generation_clicked`,
`subscription_activated`, `watchlist_created`, `alert_created`,
`portfolio_created`, `pdf_downloaded`.

### Kurulum
1. [posthog.com](https://posthog.com) → **EU Cloud** workspace → proje oluştur.
2. Project API Key'i kopyala (`phc_...`).
3. Vercel env:
   - `NEXT_PUBLIC_POSTHOG_KEY = phc_...`
   - `NEXT_PUBLIC_POSTHOG_HOST = https://eu.i.posthog.com`
   - `NEXT_PUBLIC_APP_VERSION = 1.0.0`
4. Yeniden deploy.
5. Consent banner'ı (Madde 5) devreye girince `setAnalyticsConsent(true)` akışı
   tamamlanır → event'ler akmaya başlar.

---

## 4. UptimeRobot — Erişilebilirlik takibi

Backend `/health` endpoint'i dış dünyadan periyodik ping'lenir; düşerse alarm.

`/health` cevabı:
```json
{ "status": "healthy", "service": "trademinds-backend", "debug_mode": false }
```

### Kurulum
1. [uptimerobot.com](https://uptimerobot.com) → ücretsiz hesap.
2. **Add New Monitor**:
   - **Monitor Type:** HTTP(s)
   - **Friendly Name:** `TradeMinds Backend /health`
   - **URL:** `https://<railway-backend-domain>/health`
   - **Monitoring Interval:** 5 dakika (ücretsiz planın en sıkı aralığı)
3. (Önerilir) **Keyword** monitörü olarak da kur: response içinde `healthy`
   kelimesini ara — böylece 200 dönen ama bozuk bir cevap da yakalanır.
4. (Opsiyonel) İkinci monitor: frontend `https://<vercel-domain>` (anasayfa 200).
5. **Alert Contacts:** e-posta (ve istenirse Telegram/Slack) ekle, monitöre bağla.

### Notlar
- Healthcheck `/health`'tir; Railway de aynı path'i kullanır
  (`railway.json → healthcheckPath: /health`).
- `/health` DB'ye dokunmaz; "process ayakta mı" sinyalidir. Daha derin sağlık
  için bkz. [OPERATIONS.md](./OPERATIONS.md) (scheduler/job durumu).
- **Alarm zamanlaması:** UptimeRobot, monitörü "Down" olarak **teyit ettikten**
  sonra alarm yollar (ilk başarısız kontrolde hemen değil — kısa süre içinde
  tekrar dener). 5 dk aralıkta tipik bildirim gecikmesi birkaç dakikadır. Daha
  kısa tepki istiyorsan ücretli planla aralığı düşür.

---

## 5. Tüm monitoring env değişkenleri — özet

**Backend (Railway):**
```
SENTRY_DSN=                      # boş = Sentry kapalı
SENTRY_TRACES_SAMPLE_RATE=0.1
ENVIRONMENT=production           # Sentry ortam etiketi
LOG_LEVEL=INFO                   # DEBUG/INFO/WARNING/ERROR/CRITICAL
```

**Frontend (Vercel):**
```
NEXT_PUBLIC_SENTRY_DSN=                              # boş = frontend Sentry kapalı
NEXT_PUBLIC_POSTHOG_KEY=                             # boş = analitik kapalı
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
NEXT_PUBLIC_APP_VERSION=1.0.0
```

Tam env envanteri için `backend/.env.example` ve `frontend/.env.example`.

---

## 6. Production / Beta kurulum sırası

1. **Sentry projeleri** (2 adet: backend Python, frontend Next.js — ikisi de EU).
2. **PostHog** projesi (EU Cloud).
3. **UptimeRobot** hesabı + `/health` monitörü + alert contact.
4. Railway env'e backend değişkenlerini gir (`SENTRY_DSN`, `ENVIRONMENT=production`,
   `LOG_LEVEL=INFO`).
5. Vercel env'e frontend değişkenlerini gir (`NEXT_PUBLIC_SENTRY_DSN`,
   `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`, `NEXT_PUBLIC_APP_VERSION`).
6. Her iki tarafı da **yeniden deploy** et (NEXT_PUBLIC build-time gömülür).
7. Aşağıdaki doğrulama checklist'ini çalıştır.
8. Consent banner (Production Readiness Madde 5 — Legal/Consent) sonrası PostHog
   event akışını tekrar doğrula.

---

## 7. Doğrulama checklist'i

**Backend Sentry**
- [ ] Railway loglarında `Sentry monitoring enabled (environment=production).` var.
- [ ] Sentry → proje → Issues'a bir test hatası düşüyor (geçici test route'u veya
      `sentry_sdk.capture_message("test")` ile; sonra kaldır).
- [ ] `ENVIRONMENT` etiketi `production` görünüyor.

**Frontend Sentry**
- [ ] Vercel build loglarında Sentry instrumentation yükleniyor (hata yok).
- [ ] Tarayıcıda bilerek bir hata ürettiğinde Sentry frontend projesine düşüyor.
- [ ] `environment` etiketi `production`.

**PostHog**
- [ ] `frontend/.env`/Vercel'de `NEXT_PUBLIC_POSTHOG_KEY` set.
- [ ] Host `https://eu.i.posthog.com` (EU veri ikametgâhı).
- [ ] Consent verildikten sonra PostHog → **Activity / Live events**'te
      `$pageview`, `signal_viewed_v1` vb. görünüyor.
- [ ] Event'lerde ortak property'ler var: `app_version`, `schema_version`,
      `user_tier`, `source=web`.
- [ ] Consent verilmeden **hiçbir** event akmıyor (network sekmesinde
      `eu.i.posthog.com`'a istek yok).

**UptimeRobot**
- [ ] Monitor **Up** durumunda, son kontrol 5 dk içinde.
- [ ] `/health` keyword kontrolü `healthy` buluyor.
- [ ] Test: backend kısa süre durdurulduğunda alarm e-postası geliyor.

> Event akışını gerçek zamanlı doğrulama ve alarm sonrası ilk müdahale adımları
> için → [OPERATIONS.md](./OPERATIONS.md).
