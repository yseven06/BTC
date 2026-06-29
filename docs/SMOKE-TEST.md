# Production Smoke-Test Checklist

TradeMinds AI yayın-öncesi / deploy-sonrası duman testi. Her senaryo **PASS/FAIL**
olarak işaretlenir; kritik bir senaryo FAIL ise yayın yapılmaz. İlgili:
[SECURITY.md](./SECURITY.md), [DEPLOYMENT.md](./DEPLOYMENT.md), [OPERATIONS.md](./OPERATIONS.md).

## Nasıl çalıştırılır
- **Backend/API:** `curl` ile health/headers/rate-limit/404/public-vs-auth.
- **Frontend:** tarayıcıda her sayfa + konsol (hata/CSP) + network (analytics).
- **Logged-out senaryolar:** gizli (incognito) pencere veya yeni profil kullan.
- **Prod'da:** aynı adımları prod URL'lerinde + `DEBUG=false`/`docs kapalı` teyidiyle koştur.

> Politika notu: gerçek hesap oluşturma ve parola ile giriş, otomasyon tarafından
> yapılmaz; bu iki adımda **form/validasyon + API davranışı** doğrulanır, fiili
> kayıt/giriş insan tarafından yapılır.

---

## Yerel çalıştırma sonuçları — 2026-06-29 (dev: localhost:8000 / :3000)

| # | Senaryo | Yöntem | Sonuç |
|---|---------|--------|-------|
| 1 | Landing (logged-out) tam render | token geçici kaldır + reload + screenshot | ✅ PASS — hero + gerçek istatistikler (%35.91 başarı, 646 sinyal, −0.13% ort. getiri **dürüst/kırmızı**, %59.68 TP1) + 7b/7c trust bölümleri |
| 2 | Register akışı | SSR render + form alanları | ✅ PASS — email+parola+onay kutusu+kayıt butonu render (fiili kayıt: kullanıcı) |
| 3 | Login | SSR render + form alanları | ✅ PASS — email+parola+giriş render (fiili giriş: kullanıcı) |
| 4 | Dashboard | tarayıcı render + konsol | ✅ PASS — tam render, hata yok |
| 5 | Signal Detail | "Analiz" → drawer | ✅ PASS — giriş/SL/TP1-2-3, kalite 7/10, olasılık %67, **Motorlar(9)**, AI Açıklaması, PDF İndir |
| 6 | Pricing | tarayıcı render | ✅ PASS — planlar + aylık + disclaimer |
| 7 | Checkout modal | "Yükselt" → modal | ✅ PASS — otomatik yenileme + yenileme tarihi + iptal + periyot + **2 onay kutusu** (Madde 5i; gizli abonelik yok) |
| 8 | KVKK / Consent akışı | banner + footer "Çerez Ayarları" | ✅ PASS — 3 seçenek (Tümünü Kabul / Yalnızca Zorunlu / Tercihleri Yönet) |
| 9 | Rate limiting | POST /auth/login ×15 (geçerli şema) | ✅ PASS — 10×401 sonra **5×429** (10/dk) |
| 10 | Güvenlik header'ları | curl backend + frontend | ✅ PASS — XCTO/XFO/Referrer/HSTS/COOP (backend) + CSP/HSTS/XFO/XCTO (frontend) |
| 11 | Health endpoint | curl /health | ✅ PASS — 200, `{status:healthy, debug_mode}` |
| 12 | API endpoint'leri | curl public vs auth | ✅ PASS — /billing/plans 200; /consent/status & /notifications/settings **403** |
| 13 | Yasal sayfalar | curl /yasal + 4 slug | ✅ PASS — index + risk-bildirimi/kullanim-kosullari/cerez-politikasi/mesafeli-satis 200 |
| 14 | Footer | tarayıcı DOM | ✅ PASS — tek paylaşılan footer + yasal linkler |
| 15 | Cookie banner | consent temizle + reload | ✅ PASS — "Çerez Tercihleri" + 3 buton + Çerez Politikası linki |
| 16 | Analytics consent | localStorage `tm_cookie_consent` | ✅ PASS — `{necessary,analytics,version}` saklanıyor, gated |
| 17 | Sentry no-op | backend config + frontend DOM | ✅ PASS — backend SENTRY_DSN yok → no-op; frontend Sentry absent |
| 18 | PostHog consent'siz veri göndermez | analytics.ts + network | ✅ PASS — `opt_out_capturing_by_default:true` + `_consent` kapısı; network'te posthog/sentry isteği yok |
| 19 | CSP ihlali yok | konsol | ✅ PASS — "Refused to..." yok |
| 20 | Console hatası yok | konsol | ✅ PASS — yalnız zararsız dev LOG/INFO (React DevTools, Fast Refresh) |
| 21 | 404 / 500 | curl + kod | ✅ PASS — 404 (backend+frontend); 500 → global handler generic + `correlation_id` (Madde 6c) |

**Sonuç:** 21/21 PASS — kritik bug yok. Tespit edilen sorun olmadığı için düzeltme commit'i gerekmedi.

### Harness notları (app kusuru değil)
- React 19 delegated handler'ları sentetik `.click()` ile tetiklenmiyor; gerçek
  piksel tıklaması (computer) ile drawer/modal'lar düzgün açıldı.
- Landing logged-in'de `/dashboard`'a yönlenir; logged-out görünüm için auth
  token'ı localStorage'da geçici yeniden adlandırılıp test sonrası **birebir geri yüklendi**.
- Consent/banner testi sonrası `tm_cookie_consent` orijinal değere geri yüklendi
  (yeni ConsentLog satırı oluşturmadan).

---

## Deploy-sonrası (prod) ek teyitler
- [ ] **App başladı** = prod fail-fast validator geçti (kritik env'ler ayarlı: DEBUG=false, güçlü JWT_SECRET, prod DATABASE_URL/CORS). Boot loglarında RuntimeError yok.
- [ ] **Migration** deploy'da koştu: `python scripts/migrate.py status` → tüm migration'lar `APPLIED`, `PENDING (none)`. (İlk adoption'da `stamp` çalıştırıldı.)
- [ ] `GET /health` → 200 (artık `debug_mode` alanı yok — sızıntı kaldırıldı).
- [ ] `GET /docs`, `/redoc`, `/openapi.json` → 404 (prod'da kapalı, DEBUG-gated).
- [ ] Güvenlik header'ları + CSP prod URL'de canlı (`curl -I https://<api>` ve frontend).
- [ ] `CORS_ORIGINS` yalnız prod frontend domain'i; cross-origin isteği reddedilir.
- [ ] Rate limit + adaptif challenge **doğru per-IP** çalışıyor (uvicorn `--proxy-headers` aktif; farklı IP'ler ayrı sayılır, hepsi proxy IP'sine düşmüyor).
- [ ] Stripe yapılandırılmamışsa checkout **503** (mock bedava-upgrade yok); yapılandırılmışsa S7 e2e.
- [ ] Sentry DSN set → hata Sentry'ye düşüyor; PostHog consent sonrası event görünüyor.
- [ ] Stripe webhook imzası prod secret ile doğrulanıyor; ConsentLog yazımı prod DB'de kalıcı.
- [ ] Turnstile (anahtar varsa): soft/auth-fail bandında 428 → widget → çözüm → geçer; admin/internal bypass çalışır.
- [ ] UptimeRobot `/health` monitörü + `healthy` keyword alarmı kurulu.
- [ ] Landing/register/login gerçek logged-out tarayıcıda görsel + fiili kayıt/giriş.
