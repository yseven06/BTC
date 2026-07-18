# CP-STAGING-A — Private Always-On Gözlem Ortamı: Mimari Plan (doc-only)

**Tarih:** 2026-07-18 · **Statü:** salt-karar dokümanı (deploy/kod/worker/secret-taşıma YOK; davranış BYTE-IDENTICAL)
**Amaç bağlamı:** CP-SQF kapandı (kısıt=alpha, veri-birikimi); CP-OBS-ALARM A/B/C tamamlandı (dead-man's-switch). Sıradaki yapısal karar: local-PC bağımlılığını azaltan **private, always-on, production-like gözlem** ortamı.

> **Bu doküman yalnız CP-STAGING-A'dır (mimari plan).** Hiçbir deploy/kod/worker/scheduler-göçü/secret-taşıma içermez. Uygulama alt-CP'leri B→F ayrı onaylarla.

---

## Bu mimariyi belirleyen üç load-bearing gerçek (TradeMinds'e özgü)

1. **Single-flight IN-PROCESS bir bellek-bool'udur** (F0-1E; `--workers 1`, tek-replika sabiti — DEPLOYMENT.md). İki scheduler (local + staging) aynı Supabase'e **paralel** koşarsa → **çift-işleme/yarış**; tek koruma `signal_trade_path.signal_id` UNIQUE ("kırılgan koruma"). ⇒ Göç = **CUTOVER (her an TEK yazıcı)**, "parallel run" DEĞİL.
2. **DB pool 8+2, Supavisor 15-cap altında** (db-idle-in-transaction-leak kaydı). İki instance = ~20 bağlantı > 15 → **bağlantı tükenmesi**. ⇒ Local pool kapanmadan staging pool açılmaz → temiz cutover zorunlu.
3. **Motor OHLC'yi runtime'da Binance API'den çeker.** ⇒ Host bölgesi **Binance-erişilebilir** olmalı (US-bölgeleri Binance'i bloklar). Local PC şu an erişiyor; staging host'unda **doğrulanmalı**.

---

## 1. Amaç
- Local PC uyku/kapanma/restart'ında **veri-birikimi durmasın** (HEARTBEAT: 26 günde 5 kesinti/~27sa, çoğu makine-kapalı).
- Scheduler/telemetry/signal-observation akışı **7/24** çalışsın; F1-a reopen'ın dayandığı çok-haftalık kesintisiz birikim güvenceye alınsın.
- **Public production açmadan** private observation-only ortam.

## 2. Kırmızı çizgiler
- Public deploy YOK · kullanıcıya-açık route YOK · payment/signup YOK.
- Production trading/gate/model/skor/sinyal-üretim davranışı **değişmez**.
- **Tek writer** korunur; **local ve staging aynı anda paralel scheduler ÇALIŞTIRMAZ.**
- Bu staging **beta launch DEĞİLDİR**; işletici-legal/Stripe/Turnstile kapıları açılmaz.

## 3. Host seçimi — karşılaştırma

| Seçenek | Avantaj | Risk | Maliyet | Güvenilirlik | env/secret riski | TradeMinds uygunluğu |
|---|---|---|---|---|---|---|
| **Local + alarm** (mevcut) | 0 kurulum, hazır | makine-kapalı kanıtlı; babysitting | $0 | Düşük-orta | mevcut = iyi | **Interim** |
| **Küçük VPS** (Hetzner/DO/Linode) | tam kontrol, systemd, sabit-fiyat | OS/patch/uptime **sen** yönetirsin | ~$4-6/ay | Yüksek (bakımlıysa) | SSH+env kendin sertleştirir | İyi ama ops-yükü |
| **Supabase edge / scheduled fn** | serverless, DB'ye yakın | **Deno/TS-only → Python motoru koşmaz (tam rewrite)** | Düşük | — (kapsam-dışı) | — | **HAYIR (over-build)** |
| **GitHub Actions cron** | ücretsiz, host yok | min 5dk + **zamanlama güvenilmez** (gecikir/atlar), 6h cap, kalıcı 2dk-scheduler için değil | ~$0 | Düşük (real-time) | secret'lar GH'de | **Zayıf** (app-scheduler için) |
| **Railway / Render / Fly (PaaS worker)** | managed always-on, env/log/rollback UI, auto-restart, repo **zaten Railway-yönelimli** | vendor-lite; **bölge/Binance erişimi doğrulanmalı**; free-tier'lar uyuyabilir (paid ~$5 gerekir) | ~$5/ay | **Yüksek** | env-UI şifreli, public-domain-siz private | **EN İYİ** |
| **Tam production deploy** | nihai hedef | beta-legal/ödeme/public kapılarını çeker (gözlem için gereksiz) | Yüksek | — | — | **Erken/OUT** |

**Seçim: Railway (birincil; Render/Fly denk-alternatif) — tek-instance private worker.** Gerekçe: repo zaten Railway-yönelimli (env.example/DEPLOYMENT.md), managed always-on, env/log/rollback yerleşik, ~$5/ay, private (public-domain-siz) kurulabilir. VPS eşit-güvenilir ama ops-yükü fazla; ikincil tercih.

## 4. Önerilen mimari
- **Tek private worker**, **autoscale KAPALI** (single-flight tek-replika şartı). İki şekil:
  - (a) *full-app, public-domain-siz* — kod-değişikliği yok; FastAPI API var ama dışa erişilemez.
  - (b) *headless scheduler-entrypoint* — **sıfır HTTP yüzeyi** (private-only için en temiz; küçük entrypoint gerektirir, gelecekte). **Tercih: uzun vadede (b); ilk cutover (a) ile kod-değişikliğisiz.**
- **Scheduler tek instance** — her an **tek yazıcı** (cutover, asla paralel).
- **DB aynı Supabase** — `DATABASE_URL` env'den, aynı postgres/service_role creds (RLS-bypass, local ile aynı güven düzeyi); **pool 8+2 korunur**; cutover'da 15-cap aşılmaz.
- **env/secrets PaaS üzerinde** — env-var UI (şifreli); `backend/.env` anahtarları oraya konur; **repo'ya değer girmez**; şüpheliyse DB/Telegram creds rotate.
- **CP_OBS_ALARM_PING_URL staging'e taşınır** — aynı URL staging env'ine; checker **PaaS-cron** (Railway/Render cron) 15dk'da koşar → dead-man's-switch artık **staging'i** izler; cutover'da local Windows-Task disable (ping-kaynağı staging'e geçer).
- **Healthcheck/dead-man's-switch staging'i izler** — iki katman: PaaS **auto-restart** (crash'te) + bağımsız **dead-man's-switch** (host tümden ölürse).
- **logs:** PaaS stdout capture + retention (scheduler zaten logluyor).

## 5. Cutover kuralı
- Local scheduler ve staging scheduler **paralel çalışmayacak** (§load-bearing #1/#2).
- Sıra: **(1)** staging **dry-run** (yazmayan gözlem; DB-connect + Binance-reach + "üretir-ama-yazmaz") → **(2)** kısa **cutover penceresi**: local scheduler **durdur** (pool kapansın) → staging scheduler **başlat** → status_history'nin yeni host'tan aktığını doğrula.
- **Rollback:** staging scheduler durdur → local scheduler + Windows-Task tekrar başlat. **Veri göçü YOK** (aynı DB); tek-yazıcı invariantı korunur; hızlı.

## 6. Legal / beta güvenlik
- **Private observation ONLY.** Public kullanıcı erişimi YOK · Stripe/Turnstile/signup KAPALI · custom-domain bağlanmaz, URL paylaşılmaz.
- Headless-worker (§4b) = sıfır HTTP yüzeyi (en güvenli). Full-app (§4a) seçilirse public-domain bağlanmaz.
- **Bu staging beta-launch DEĞİLDİR** — işletici-legal/ödeme/public kapıları tetiklenmez (hiçbir şey kullanıcı-yüzlü değil). Sınır doküman-kilitli.

## 7. Checkpoint serisi
- **CP-STAGING-A** · doc-only mimari plan *(bu doküman)*.
- **CP-STAGING-B** · env/secrets envanteri (`backend/.env` → secret/config sınıflaması; değer repo'ya girmez; PaaS'a nasıl konacağı; rotate gereği).
- **CP-STAGING-C** · private worker **dry-run**: host bölgesinden **Binance erişilebilirliği** + DB-connect + env-yükleme + "üretir-ama-**yazmaz**" doğrulaması. **Canlı DB'ye yazma YOK, çift-scheduler YOK.**
- **CP-STAGING-D** · scheduler **cutover** planı+uygulama (paralel DEĞİL; local-durdur → staging-başlat; tek yazıcı).
- **CP-STAGING-E** · heartbeat/alarm validasyonu (dead-man's-switch staging'i izliyor; PaaS auto-restart doğrulandı; test-kesinti → alarm geldi).
- **CP-STAGING-F** · local-PC bağımlılığını azaltma kararı (local = soğuk-yedek/emekli; kanonik runtime = staging; docs güncelle).

## 8. Geçiş kriterleri (D-cutover'dan ÖNCE hepsi)
- ✅ CP-OBS alarm **uçtan-uca** çalışmış (down-alert + recovery-alert alındı).
- ✅ Healthchecks/dead-man's-switch pingi **düzenli** (yeşil).
- ✅ **En az 1 gün** (öneri 5-7 gün) alarm **false-positive üretmeden** çalıştı.
- ✅ **env envanteri tamam** (CP-STAGING-B).
- ✅ Host bölgesinde **Binance erişimi doğrulandı** (CP-STAGING-C dry-run).
- ✅ DB-connect + no-write dry-run **yeşil**; **tek-yazıcı cutover penceresi** planlı + **rollback denendi**.
- ✅ **private-only** teyitli (public route/URL yok).

## 9. Net verdict
- **Hemen deploy ÖNERİLMİYOR.** Önce **CP-OBS-ALARM-C ops kurulumu uçtan-uca doğrulanmalı** (dead-man's-switch gerçekten alarm veriyor) ve **~5-7 gün local+alarm gözlem** yapılmalı → alarmı kanıtla + gözün açıkken gerçek local-downtime maliyetini ölç.
- **Kaç gün gözlem:** min **1 gün** false-positive'siz (sert-alt-sınır); öneri **5-7 gün** (alarma güven + "local yeterli mi" kararı).
- **Hangi koşulda staging'e geçilir:** §8 kriterlerinin tamamı sağlanınca — özellikle alarm-kanıtlı + dry-run-yeşil + Binance-bölge-OK + cutover/rollback-planlı. Alarm sık/pahalı kesinti gösterirse geçişi öne al; local çoğunlukla-iyi çıkarsa staging ertelenebilir (alarm + local-uyku-kapatma "yeterli" olabilir).
- **En düşük-riskli ilk uygulama adımı:** **CP-STAGING-B (env/secrets envanteri, doc-only)** — deploy değil, sıfır-risk doküman; cutover'dan önce hazır dursun. (Paralel: alarm-ops doğrulama + gözlem devam eder.)

**Genel sıra (kilit):** alarm-ops-doğrula → 5-7 gün gözlem → **B** (env doc) → **C** (dry-run: Binance+DB+no-write) → **D** (cutover) → **E** (alarm validasyon) → **F** (local bağımlılık kararı). Her biri ayrı onay; hiçbiri sinyal davranışını değiştirmez.

---

*Bu doküman salt mimari karardır; kod/deploy/DB/davranış değişikliği içermez. Uygulama B-F alt-CP'leriyle, ayrı onaylarla.*
