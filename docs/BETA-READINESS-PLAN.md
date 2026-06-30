# Beta-Hazırlık Sertleştirme — ANALİZ & PLAN (kod YOK)

**Tarih:** 2026-06-30 · **Statü:** ANALİZ+PLAN. Davranış/prod etkili hiçbir değişiklik onaysız uygulanmaz.
**Kaynak:** 4-ajan kod-haritalama (deps · Legal · Stripe S7 · Turnstile/env/smoke/release) + birinci-el.
**Amaç:** Beta açılınca veri-gated zekâ-v2 (CM-M3/Similarity/Adaptive) kilidini hızlandıracak hazırlık;
**bağımsız yapılabilenleri** ayır, **anahtar/şirket-bilgisi bekleyenleri** netleştir.

## Genel bulgu (en önemli)
- **Majör dep migrasyonu YOK:** pydantic **zaten v2**, SQLAlchemy **zaten 2.x** (kod v1-kalıntısı=0).
  FastAPI/Starlette bump'ı minör → düşük risk. **numpy 1.26→2.0 tek YÜKSEK-SESSİZ risk** (NEP50/C-ABI
  → sinyal/backtest sayılarını sessizce değiştirebilir) → **ertelenir**.
- **Bump-gate hazır:** 12 standalone test (byte-identical equivalence en güçlü sayısal-gate) + SMOKE 21/21
  (HTTP/ASGI katmanı testle DEĞİL, smoke ile doğrulanır).
- **Legal:** 8 TR doküman özlü hazır; tek blokaj **şirket bilgisi** (tüzel-kişilik) → senin.
- **Stripe/Turnstile/prod-deploy:** anahtarlar + env değerleri → senin.

---

## A. BAĞIMSIZ İLERLETİLEBİLİR (anahtar/şirket-bilgisi gerekmez — onayınla)

> ✅ **A-BLOĞU TAMAM (2026-06-30):** A4 [a88e50e] · A5 [7319353] · A2a [3d2ab16] (A2b→B1) · A3 [d09e693]
> · A1 [a72466b] (dep bump; numpy/stripe SABİT; sıfır drift, tüm test PASS, geri-alma gerekmedi).
> **Beta için kalan = yalnız B-bloğu (kullanıcı).**

### A1 — Backend dependency bump (güvenli alt-küme) + lockfile
- **Kapsam:** fastapi 0.111→~0.115, starlette(transitive)→güncel, uvicorn 0.30→0.32, sqlalchemy
  2.0.30→2.0.3x, pydantic 2.7.4→2.9+, pydantic-settings, httpx 0.27→0.28, sentry-sdk. **Güvenlik:**
  python-jose 3.3.0 (CVE) + passlib/bcrypt uyarısı. **+ lockfile** (pip freeze snapshot) → deterministik
  before/after. **HARİÇ:** numpy 2.x (ertelendi), stripe (A3/S7 ile birlikte), pandas/ta/numpy ailesi.
- **Risk:** Düşük (v2 zaten yerinde). Tek friction: **slowapi==0.1.9 ↔ yeni Starlette** uyumu (middleware/
  exception-handler imza kayması). numpy ailesi dışlandığı için sayısal-drift riski yok.
- **Bağımlılık:** Yok (keyless). Python sürümü pinli değil (runtime.txt yok) → öneri: Python sürümünü de pinle.
- **Doğrulama:** bump ÖNCESİ+SONRASI **12 test scripti** (özellikle differential 8000 + backtest-equiv 9000
  byte-identical) + **SMOKE 21/21** (ASGI/middleware/rate-limit/headers). HERHANGİ bir equivalence farkı = **hard block**.
- **Efor:** **M** (1 gün; dikkatli regresyon). Ayrı küçük commit'ler (web-stack / security / lockfile).

### A2 — Legal best-practice metin iyileştirmesi (şirket-bilgisi GEREKMEZ) + hardcoded-iletişim uzlaştırma
- **Kapsam:** (a) `acik-riza`/`aydinlatma` yurt-dışı-aktarım (KVKK m.9) ifadesini standart-sözleşme diline
  sıkılaştır; (b) alt-işleyen listesini (Supabase/Vercel/Railway/Sentry/PostHog/Stripe/Cloudflare) "ör."
  → kesinleştir; (c) VERBİS-yükümlülük belirleme notu; (d) **`help/page.tsx` hardcoded `destek@trademinds.io`
  + Telegram** ↔ künye placeholder ÇELİŞKİSİNİ uzlaştır (tek kanonik kanal kararı senin). **HARİÇ:** şirket
  placeholder doldurma + v1.0 bump (B1).
- **Risk:** Düşük (metin; davranış yok). v0.9→v1.0 bump'ı BURADA YAPMA (global re-consent tetikler).
- **Bağımlılık:** Yok (best-practice); hardcoded-iletişim kararı senin tercihini ister.
- **Doğrulama:** `npm run legal:gen` + /yasal dev-route (tsc/dev, `next build` değil); placeholder grep'i
  hâlâ B1'i bekler (bu adım v1.0 yapmaz).
- **Efor:** **S-M** (yarım-1 gün).

### A3 — Stripe mock-gate sertleştirme (residüel kapatma) + S7 runbook
- **Kapsam:** mock free-upgrade kodda kapalı (DEBUG-gate+503) AMA 'staging' gibi non-production ENVIRONMENT
  + DEBUG=true + boş key residüeli var (gate yalnız DEBUG'a bakıyor). **Sertleştirme:** mock dalını
  `_stripe_configured()` VEYA `ENVIRONMENT=='development'` ile de kapı + prod'da boot-anı "STRIPE_SECRET_KEY
  boş" uyarısı. **+ S7 canlı-E2E runbook** dokümanı (stripe listen, test kartları, idempotency/cancel/
  payment-failed senaryoları).
- **Risk:** Düşük-orta (auth/billing yolu — dikkatli). Davranış: yalnız non-prod güvenlik sıkılaştırma.
- **Bağımlılık:** Sertleştirme keyless; **S7 E2E çalıştırma senin Stripe test anahtarların** (B2).
- **Doğrulama:** boş-key checkout → 503 (mock değil); DEBUG/ENVIRONMENT matriste mock erişilemez; smoke item-7/65.
- **Efor:** **S** (yarım gün).

### A4 — Release checklist + ROLLBACK runbook + migration ilk-çalıştırma kılavuzu
- **Kapsam:** **Rollback runbook YOK** → yaz (Railway redeploy-previous, frontend Vercel rollback, DB
  forward-only migration'ın geri-alınamazlığı + manuel telafi notu). **Migration ilk-çalıştırma kılavuzu:**
  fresh DB → `migrate.py apply`; mevcut DB → **bir kez `stamp`** (0003 re-run'da `DELETE FROM
  notification_settings` = veri kaybı). + single-replica/--workers 1 korunması uyarısı.
- **Risk:** Yok (doküman). Ama içeriği kritik (yanlış migration = veri kaybı).
- **Bağımlılık:** Yok.
- **Doğrulama:** Kılavuzu `migrate.py status/stamp/apply` davranışıyla çapraz-kontrol.
- **Efor:** **S** (yarım gün).

### A5 — Pre-beta smoke planı formalizasyon + prod-env checklist
- **Kapsam:** SMOKE-TEST.md post-deploy bölümü (işaretsiz) → **somut prod-URL smoke planı** (docs⇒404,
  prod headers/CORS, proxy-headers ile per-IP rate-limit/challenge, Stripe-unconfigured⇒503, webhook imza,
  Turnstile 428→widget, UptimeRobot). **+ prod-env checklist** (validator-zorunlu: ENVIRONMENT/DEBUG/
  JWT_SECRET/DATABASE_URL/CORS + feature: Stripe/Turnstile/Sentry/PostHog/OAuth).
- **Risk:** Yok (doküman/plan).
- **Bağımlılık:** Yok (çalıştırma prod deploy'a bağlı — B3).
- **Efor:** **S**.

## B. SENİN ANAHTAR/BİLGİNİ BEKLEYEN (bağımsız yapılamaz)

### A2 DURUM: **A2a TAMAM**, A2b → B1 ertelendi (kullanıcı kararı 2026-06-30)
- **A2a (TAMAM):** `frontend/src/lib/contact.ts` tek-kaynak (SUPPORT_EMAIL/TELEGRAM, B1'e kadar BOŞ);
  help page yalnız tanımlı kanalı gösterir, boşken uydurma değer YOK → `/yasal/iletisim-kunye`'ye
  yönlendirir. Hardcoded `destek@trademinds.io`/Telegram kaldırıldı. tsc temiz.
- **A2b (→ B1):** cross-border (KVKK m.9) + alt-işleyen listesi + VERBİS notu + EN-locale → **B1 Legal
  v1.0** sırasında gerçek tüzel-kişilik + aktarım mekanizması + avukat incelemesiyle. Şimdi metne dokunulmadı.

### B1 — Legal v1.0 (şirket-bilgisi + v1.0 bump)
- **Kapsam:** 11 placeholder ( unvan/MERSİS/vergi dairesi+no/adres/KEP/destek-eposta/KVKK-eposta/tüketici-
  eposta/VERBİS/yurt-dışı-mekanizma/telefon) doldur + 8 dokümanda taslak-banner kaldır + v0.9→**v1.0**
  (global re-consent tek release'te koordine).
- **Bağımlılık:** **Tüzel kişilik kuruluşu** (senin) — tek zorunlu launch blokajı (principle 5/6).
- **Efor:** Bilgi gelince **S** (mekanik doldur + bump + re-consent smoke).

### B2 — Stripe S7 canlı E2E · B3 — Turnstile E2E + prod env değerleri + ilk prod deploy
- **Bağımlılık:** B2 → Stripe test/whsec anahtarları + webhook endpoint kaydı. B3 → Cloudflare Turnstile
  anahtarları + prod env değerleri (JWT_SECRET/pooler-DATABASE_URL/CORS/FRONTEND_BASE_URL/NEXT_PUBLIC_*) +
  migration ilk-çalıştırma kararı.
- **Uyarı:** Turnstile anahtarları set EDİLMEZSE beta, login/register/checkout'ta bot-challenge **KAPALI**
  açılır (sessiz no-op). B3'te mutlaka set edilmeli.
- **Efor:** Anahtarlar gelince **M** (E2E + smoke + deploy).

---

## Önerilen sıra (bağımsız blok)
**A4 + A5 (dokümanlar, sıfır risk) → A3 (Stripe gate sertleştirme, S) → A2 (legal best-practice + iletişim
uzlaştırma) → A1 (dep bump, en substantif, güçlü regresyon-gate).** Her biri ayrı küçük commit + before/after
(A1 için byte-identical + smoke). B1/B2/B3 senin anahtar/bilgini bekler; A-bloğu beta'yı "anahtarlar gelince
anında aç" durumuna getirir.
