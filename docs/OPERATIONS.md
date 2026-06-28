# Operasyon Rehberi (Runbook) — Deploy Sonrası

Production/beta ortamı ayağa kalktıktan sonra günlük operasyon ve olay
müdahalesi için pratik rehber. Kurulum için → [MONITORING.md](./MONITORING.md),
deploy adımları için → [DEPLOYMENT.md](./DEPLOYMENT.md).

> **EN KRİTİK KISIT — önce bunu oku.** Backend'in **scheduler'ı = TM v2 veri
> toplama sürecidir.** Sinyal üretimi, performans takibi ve sinyal yaşam döngüsü
> kaydı bu in-process scheduler'da döner. APScheduler süreç-içi çalıştığı için:
> - **Tek replica + `--workers 1`** zorunlu (`railway.json` zaten `numReplicas: 1`
>   ve `--workers 1` ile pinli). Yatay ölçeklemek **kopya iş** üretir
>   (çift sinyal, çift resolution).
> - Backend'i her yeniden başlatış **veri toplamayı geçici durdurur.** Mümkünse
>   düşük-volatilite/BIST-kapalı pencerede yeniden başlat. (Perf takibi 2 dakikada
>   bir döner; 15 dk'lık bir restart ~7-8 takip döngüsü kaçırır.)

---

## 1. Servis ayakta mı? (hızlı kontrol)

**Backend — `/health`:**
```bash
curl -s https://<railway-backend-domain>/health
# Beklenen:
# {"status":"healthy","service":"trademinds-backend","debug_mode":false}
```
- `debug_mode` production'da `false` olmalı (`true` ise `DEBUG` env yanlış set
  edilmiş → prod'da `init_db()` tetiklenir, istenmez).

**Frontend — anasayfa:** Tarayıcıda `https://<vercel-domain>` açılıyor, 200 dönüyor.

**Platform panelleri:**
- Railway → backend service → **Deployments**: son deploy "Success", durum "Active".
- Vercel → Project → **Deployments**: son deploy "Ready".

**BIST piyasa durumu (opsiyonel sağlık sinyali):**
```bash
curl -s https://<railway-backend-domain>/api/v1/prices/market-status
# {"bist_open": true/false}  — kapalıyken hisse fiyat polling'i otomatik durur
```

**Arka plan veri toplama gerçekten dönüyor mu?**
- Admin panel → **Sistem / Scheduler** ekranı: 6 işin `last_run_at` /
  `last_status` değerlerine bak (UI'daki "Şimdi Çalıştır" ile aynı veri kaynağı).
- API ile (admin JWT gerekir):
  ```bash
  curl -s https://<railway-backend-domain>/api/v1/admin/system/jobs \
    -H "Authorization: Bearer <admin_jwt>"
  ```
  Sağlıklı durumda tüm işler `last_status: ok` ve `last_run_at` beklenen
  aralıkta (taze).

---

## 2. Hangi loglara bakılır?

| Kaynak | Nerede | Ne için |
|---|---|---|
| Backend logları | Railway → service → **Logs** (canlı stream) | Scheduler, hata stack'leri, startup |
| Frontend logları | Vercel → Deployment → **Logs / Functions** | SSR/route hataları, build |
| Hata detayları | **Sentry** (backend + frontend projeleri) | Gruplanmış exception + stack trace |
| Erişilebilirlik | **UptimeRobot** | Up/Down geçmişi, kesinti süresi |

- Log seviyesi `LOG_LEVEL` env'i ile kontrol edilir (varsayılan `INFO`). Derin
  teşhis için geçici `LOG_LEVEL=DEBUG` → per-asset fetch/engine detayları görünür
  (çok ayrıntılı; teşhis sonrası geri al).
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.

**Railway loglarında aranacak sağlıklı başlangıç dizeleri:**
```
Starting TradeMinds AI Backend...
Background scheduler started.
[Scheduler] Started. Jobs: ...
Sentry monitoring enabled (environment=production)   # SENTRY_DSN set ise
```

**Periyodik (sağlıklı ritim) dizeleri:**
```
[Scheduler] ... sweep complete          # sinyal taraması bitti
[Scheduler] Performance sweep: {...}     # her 2 dakikada
[Scheduler] Price alerts: checked=X triggered=Y   # her dakika
```

### Scheduler işleri (6 + 1 startup) — beklenen ritim (UTC)
| İş | Aralık |
|---|---|
| 1h sinyaller | Her saat :01 |
| 4h sinyaller | 0/4/8/12/16/20 saatlerinde :02 |
| 15m sinyaller | :02/:17/:32/:47 |
| 1d sinyaller | 00:03 UTC |
| Performans takibi | Her 2 dakika |
| Fiyat alarmları | Her dakika |
| Startup tazelik kontrolü | Başlangıçta bir kez, hemen (date trigger) |

> Cron ifadelerinin ve iş etiketlerinin tek doğru kaynağı
> `backend/app/services/scheduler.py` ve Admin Scheduler ekranıdır.

---

## 3. UptimeRobot alarmı geldi — ilk müdahale adımları

Sırayla:

1. **Gerçek mi, false-positive mi?** `curl -s https://<backend>/health` — hâlâ
   düşük mü?
   - Cevap geliyorsa: geçici ağ/UptimeRobot tarafı hıçkırığı olabilir; geçmişe bak.
2. **Railway durumu:** service "Active" mi yoksa "Crashed/Restarting" mi?
   - **Deployments → Logs**'ta en son satırlar: traceback var mı?
3. **Son deploy:** Az önce bir deploy mu yapıldı? Hatalıysa Railway'de bir önceki
   başarılı deploy'a **Rollback**.
4. **Veritabanı:** Supabase panelinde proje up mı? "idle-in-transaction" /
   bağlantı tükenmesi belirtisi var mı? (Bilinen kök neden: bkz. proje hafızası
   "DB idle-in-transaction leak" — çözüm Supabase restart olabilir.)
5. **Healthcheck timeout:** `railway.json → healthcheckTimeout: 120`. Cold start
   uzunsa Railway yeniden deniyordur; loglarda "Starting..." dönüp duruyor mu?
6. **Restart kararı:** Gerekirse Railway'den restart et. **Ama** Bölüm 1'deki
   kısıtı hatırla — restart veri toplamayı durdurur; mümkünse kontrollü yap.
7. Çözüldükten sonra: `/health` Up, Admin Scheduler'da işler tekrar `ok`,
   loglar normal ritimde.

---

## 4. Sentry'de bir hata geldi — nasıl okunur?

1. Sentry → ilgili proje (backend mi frontend mi) → **Issues**.
2. Issue'ya gir:
   - **Stack trace / culprit:** hatanın atıldığı dosya:satır.
   - **Tags → environment:** `production` mı? (dev gürültüsünü ayıkla.)
   - **Breadcrumbs:** hatadan önceki adımlar (request, log).
   - **Events / frequency:** kaç kez, kaç kullanıcı, ilk/son görülme.
3. **Frontend stack'leri minified görünebilir** — source-map upload
   yapılandırılmadı (bkz. MONITORING.md §2). Satır eşlemesi için dosya/komponent
   adından gidin; gerekirse source-map upload'ı sonradan ekleyin.
4. PII kapalı (`send_default_pii=false`) → kullanıcı e-postası/IP görünmez;
   bağlamı breadcrumbs ve request meta'sından çıkarın.
5. Aksiyon: tekrar eden/yüksek frekanslı issue'ları önceliklendir; düzeltince
   Sentry'de **Resolve** işaretle (regresyonda tekrar açılır).

---

## 5. PostHog event'leri gerçekten akıyor mu? — doğrulama

**Ön koşul (ikisi birden):** `NEXT_PUBLIC_POSTHOG_KEY` set **ve** consent verildi
(`setAnalyticsConsent(true)`). Banner, Production Readiness Madde 5 (Legal/Consent)
ile geliyor — o gelene kadar event **akmaz**, bu normaldir (bkz. MONITORING.md §3).

**Canlı doğrulama:**
1. PostHog (EU Cloud) → **Activity** (veya Live Events).
2. Uygulamada bir akış yürüt: giriş yap, bir sinyal detayını aç, fiyatlandırma
   sayfasına git.
3. Beklenen event'ler düşmeli:
   - `$pageview` (her route)
   - `login_completed_v1` / `signup_completed_v1`
   - `signal_viewed_v1` (`symbol`, `market`, `timeframe` ile)
   - `pricing_viewed_v1`, `checkout_started_v1` (`tier`, `billing_cycle` ile)
4. Bir event'e tıklayıp **ortak property'leri** doğrula: `app_version`,
   `schema_version`, `user_tier`, `source=web`.

**Tarayıcıdan hızlı kontrol:** Network sekmesinde `eu.i.posthog.com`'a istek
gidiyor mu?
- Consent **verildiyse**: istek görünmeli.
- Consent **yoksa / key yoksa**: hiç istek olmamalı (no-op doğru çalışıyor).

**Akmıyorsa kontrol listesi:**
- Key gerçekten Vercel env'inde mi ve **yeni build** alındı mı? (NEXT_PUBLIC
  build-time gömülür.)
- Consent verildi mi? (`opt_out_capturing_by_default: true` — consent olmadan
  PostHog katmanı bloke eder.)
- Host doğru mu (`https://eu.i.posthog.com`)?
- Konsol/adblock event'i engelliyor olabilir (gerçek kullanıcıda da olur).

---

## 6. Railway (backend) deploy sonrası smoke-test

- [ ] Deploy "Success", service "Active".
- [ ] `curl /health` → `status: healthy`, `debug_mode: false`.
- [ ] Loglarda `Background scheduler started.` ve `[Scheduler] Started. Jobs: ...`.
- [ ] `SENTRY_DSN` set ise: `Sentry monitoring enabled (environment=production)`.
- [ ] `ENVIRONMENT=production`, `DEBUG=false`, `LOG_LEVEL=INFO` doğru.
- [ ] `DATABASE_URL` Supabase **Supavisor pooler** URL'i (asyncpg); bağlantı
      hatası yok.
- [ ] Admin Scheduler ekranında işler birkaç dakika içinde `last_status: ok`.
- [ ] `CORS_ORIGINS` prod frontend domain'ini içeriyor (trailing slash yok) →
      frontend API çağrıları CORS hatası vermiyor.
- [ ] Tek replica doğrulandı (`numReplicas: 1`); çift sinyal yok.

---

## 7. Vercel (frontend) deploy sonrası smoke-test

- [ ] Deploy "Ready".
- [ ] Anasayfa + dashboard + sinyaller + piyasalar render oluyor; konsol hatası
      yok (tarayıcı eklenti gürültüsü hariç).
- [ ] `NEXT_PUBLIC_API_URL` prod backend domain'ine işaret ediyor (login/sinyal
      verisi geliyor).
- [ ] `NEXT_PUBLIC_SITE_URL` prod domain (OpenGraph/SEO doğru).
- [ ] `NEXT_PUBLIC_SENTRY_DSN` set ise: bilinçli hata Sentry frontend projesine
      düşüyor.
- [ ] `NEXT_PUBLIC_POSTHOG_KEY` set ise: consent sonrası event'ler akıyor (§5).
- [ ] Login → dashboard akışı uçtan uca çalışıyor (auth token, refresh).
- [ ] Mobil/dar ekran temel kontrol (kritik sayfalar).

---

## 8. Hatırlatmalar (dokunma listesi)

- **TM v2 veri toplama / Trade Path / Coin Memory / Signal Generator / BIST**
  tarafına operasyon sırasında dokunulmaz; scheduler kesintisiz dönmeli.
- Yatay ölçekleme yok (scheduler süreç-içi). Ölçek gerekirse scheduler'ı ayrı
  worker'a çıkarmak **beta sonrası** roadmap'tedir.
- Production şeması Supabase'de mevcut; `init_db()` yalnız `DEBUG=true`'da çalışır.
  Şema değişikliği için Alembic migration (beta sonrası).
- Env değişkeni değiştirince backend **yeniden başlatılmalı** (`@lru_cache`'li
  ayarlar bir kez okunur); frontend NEXT_PUBLIC değişiklikleri **yeni build**
  gerektirir.
