# Release Runbook — Go-Live, Migration Kararı & Rollback (A4)

DEPLOYMENT.md'yi **tamamlar**: yayın sırası + migration ilk-çalıştırma kararı + **rollback** +
olay müdahale. Topoloji: Backend→Railway · Frontend→Vercel · DB→Supabase. **Tek replika + `--workers 1`
zorunlu** (in-process APScheduler; yatay ölçek = çift sinyal/çözüm). Migration runner: `scripts/migrate.py`
(+ `schema_migrations` tablosu, `lock_timeout=5s`, `statement_timeout=60s`).

---

## 1. Yayın-öncesi checklist (her deploy)
**Kritik env (yoksa prod BAŞLAMAZ — config.py fail-fast validator):**
`ENVIRONMENT=production` · `DEBUG=false` · `JWT_SECRET` (≥32, default değil) · `DATABASE_URL` (pooler,
localhost değil) · `CORS_ORIGINS` (prod domain, `*` değil) · `FRONTEND_BASE_URL` · `RATE_LIMIT_ENABLED=true`.
**Özellik env:** Stripe (boşsa checkout 503), Turnstile (boşsa challenge **no-op** — bot koruması KAPALI),
Google OAuth, Sentry/PostHog. **Frontend:** `NEXT_PUBLIC_API_URL` (kritik), `NEXT_PUBLIC_SITE_URL`,
`NEXT_PUBLIC_TURNSTILE_SITE_KEY`.
**Kod/şema:** `git` temiz + tag; `migrate.py status` beklenen PENDING'leri gösteriyor; single-replica
(`railway.json numReplicas:1`) korunuyor.

## 2. ⚠️ Migration ilk-çalıştırma KARARI (geri-alınamaz — dikkat)
`preDeployCommand: python scripts/migrate.py` her deploy'da **release canlıya geçmeden önce** çalışır.
**İLK prod deploy'da hedef DB'nin durumuna göre KARAR ver:**

```
Hedef DB tamamen BOŞ/yeni mi?
 ├─ EVET → otomatik `migrate.py` (apply): create_all (eksik tablolar) + tüm 000X_*.sql sırayla.
 │         (Railway preDeployCommand bunu zaten yapar; ekstra işlem yok.)
 └─ HAYIR (tablolar/veri zaten var — mevcut Supabase) →
        İLK DEPLOY'DAN ÖNCE BİR KEZ:  python scripts/migrate.py stamp
        (uygulanmış migration'ları ÇALIŞTIRMADAN işaretler.)
        ⛔ stamp ATLANIRSA: apply, 0003'ü yeniden çalıştırır → `DELETE FROM notification_settings`
           = VERİ KAYBI. Migration'lar forward-only; geri-alma scripti YOK.
```
**Doğrulama:** `migrate.py status` → tüm beklenenler `APPLIED`. **Yeni migration eklerken:** tek-satır
ifadeler, idempotent (`IF NOT EXISTS`), `DO/$$` blok YOK (satır-bazlı splitter). **Önce bir branch/staging
DB'de dene.**

## 3. Go-live sırası
1. Env'leri ayarla (§1). 2. Migration kararını ver (§2). 3. Backend deploy (Railway) → preDeploy migrate
çalışır; **migrate başarısızsa release'i PROMOTE ETME** (logları incele; idle-in-transaction kilidi
`lock_timeout` ile migrate'i düşürebilir — bkz. [[db-idle-in-transaction-leak]], gerekiyorsa Supabase restart).
4. `/health` 200. 5. Frontend deploy (Vercel). 6. Post-deploy smoke (§4). 7. UptimeRobot + Sentry doğrula.

## 4. Post-deploy smoke (prod URL — özet; tam plan A5/SMOKE-TEST.md)
`/health` 200 (debug_mode sızmıyor) · `/docs`+`/redoc`+`/openapi.json` ⇒ 404 · güvenlik başlıkları + CSP
canlı · CORS yalnız prod domain · per-IP rate-limit/challenge (`--proxy-headers`) · Stripe boşsa
checkout ⇒ 503 (mock free-upgrade YOK) · webhook imza (prod secret) · Turnstile 428→widget→pass ·
gerçek tarayıcı register/login.

## 5. ROLLBACK runbook
> **İlke:** Uygulama rollback'i HIZLI + güvenli (platform redeploy-previous). **DB rollback DEĞİL**
> (migration'lar forward-only, down-script yok) → DB için **ileri-telafi** (yeni idempotent migration) gerekir.

**A) Uygulama (kod) rollback — varsayılan, hızlı:**
- **Backend (Railway):** önceki başarılı deployment'a **Redeploy/Rollback** (Railway dashboard → Deployments
  → önceki → Redeploy). Healthcheck `/health` 200'ü bekle. Tek-replika korunur.
- **Frontend (Vercel):** Deployments → önceki üretim deployment'ı → **Promote to Production** (anında).
- **Ne zaman:** davranış regresyonu, 5xx artışı, smoke başarısız, Sentry hata patlaması.

**B) Migration / DB rollback — DİKKAT (otomatik geri-alma YOK):**
- Migration'lar **forward-only idempotent SQL**; `down` yok. Bir migration sorunluysa:
  1. Önce **kod rollback** (A) ile uygulamayı önceki sürüme al (şema yeni kolonları görmezden gelebilir —
     additive migration'larda genelde güvenli).
  2. DB'yi düzeltmek gerekiyorsa **YENİ bir ileri-telafi migration** yaz (ör. yanlış eklenen kolonu
     `DROP COLUMN IF EXISTS` ile geri al) — manuel `DELETE`/`DROP` prod'da **elle çalıştırma**, migration olarak
     versiyonla + `schema_migrations`'a kaydet.
  3. **0003 gibi yıkıcı migration yanlışlıkla apply edildiyse** (notification_settings silindi): veri kaybı;
     Supabase **managed backup**'tan point-in-time restore tek telafi (retention'ı önceden doğrula).
- **Altın kural:** additive migration'lar (ADD COLUMN IF NOT EXISTS) kod-rollback ile uyumludur; yıkıcı/
  şema-bozan migration'ları **asla** doğrulanmamış prod'a gönderme.

**C) Konfig/env rollback:** Hatalı env (ör. yanlış CORS) → platform env'i düzelt → redeploy. `ENVIRONMENT`
default 'development'a düşerse validator atlanır + DEBUG default'u mock-free-upgrade'i açabilir → **prod'da
ENVIRONMENT=production mutlaka set**.

## 6. Olay hızlı-referans
| Belirti | İlk aksiyon |
|---|---|
| Prod boot etmiyor (RuntimeError) | Validator: DEBUG/JWT_SECRET/DATABASE_URL/CORS kritiğini düzelt |
| preDeploy migrate fail | Logları gör; idle-in-transaction → Supabase restart; release'i promote etme |
| 5xx / regresyon | Kod rollback (A) → Sentry'de kök-neden |
| Checkout free-upgrade şüphesi | `ENVIRONMENT=production` + `DEBUG=false` doğrula; boş-key ⇒ 503 olmalı |
| Bot spam / brute-force | Turnstile anahtarları set mi? `CHALLENGE_ENABLED=true`? slowapi 429 aktif mi? |
| Çift sinyal/çözüm | Yatay ölçek kazası → `numReplicas:1` + `--workers 1` geri al |

## 7. Sınırlar (post-beta)
CI/CD yok (deploy manuel) · scheduler ayrı worker'a çıkarılmadı (tek-replika zorunlu) · migration down-script
yok (ileri-telafi modeli) · object storage / nonce-CSP açık. Bunlar bilinçli post-beta.
