# Phase 2 Product Roadmap — TradeMinds AI

> ## 🏁 CHECKPOINT — BETA-READY BASELINE (2026-06-30)
> Beta-hazırlık **A-bloğu (A1-A5) TAMAM** · şirket varsayımı kaldırıldı → **gerçek kişi/bireysel
> işletici** modeli ([OPERATING-MODEL.md](./OPERATING-MODEL.md)) · dep güncellemeleri (numpy/stripe
> sabit) + byte-identical/equivalence PASS · çalışma ağacı temiz · **kod davranışı değişmedi.**
> **Kalan = yalnız dış bağımlılık (B1 operatör + faaliyet-ülkesine göre gerekli hukuki/vergisel bilgiler ·
> B2 Stripe anahtarları · B3 Turnstile+prod-env+deploy).**
> Tek-sayfa: **[BETA-LAUNCH-CHECKLIST.md](./BETA-LAUNCH-CHECKLIST.md)**. **Bundan sonraki tüm geliştirmeler
> bu baseline üzerinden ilerler.**

**Durum:** Production Readiness Sprint (Madde 1-8 + legal sertleştirme) **KAPANDI.** Bu belge,
Phase 2 ürün geliştirmesinin stratejik öncelik sıralamasıdır. Tüm Phase 2 işleri Phase 1'in
**güvenlik / hukuk / kalite** standartlarıyla yürütülür ([PRODUCT-LEGAL-PRINCIPLES.md](./PRODUCT-LEGAL-PRINCIPLES.md),
[SECURITY.md](./SECURITY.md)).

> Öncelik kriterleri: (K1) kullanıcı değeri, (K2) gelir/abonelik dönüşümü, (K3) AI sinyal
> kalitesi, (K4) rekabetçi ayrışma, (K5) teknik borç/mimari, (K6) yayına-çıkış kritikliği.
> Efor: S (<1 hafta) · M (1-2 hafta) · L (2-4 hafta) · XL (1 ay+).

---

## Yürütme ilkeleri ve onaylı sıra (2026-06-29, onaylı)

**Bağlayıcı Phase 2 ilkeleri:**
- **BP1 — Beta öncesi sıfır kritik açık:** Beta açılmadan önce hiçbir kritik güvenlik, ödeme
  veya kullanıcı-veri açığı kalmaz. **Stripe Subscription, Per-user Notifications, Turnstile ve
  Deploy production seviyesinde tamamlanır.**
- **BP2 — AI motoruna dokunurken: telemetri-önce, davranış-bozan-refactor-yok:** TP/SL, Risk
  Management, Coin Memory, Similarity, Adaptive Learning vb.'de mevcut çalışan mantığı bozacak
  refactor YAPILMAZ. Önce gerekli telemetry/veri toplama korunur/eklenir; sonra iyileştirmeler
  **geriye dönük analiz yapılabilir** biçimde eklenir. Gerçek-kullanıcı-verisini etkileyen veya
  AI-davranışını değiştiren hiçbir değişiklik **doğrulanmadan** uygulanmaz.

**Onaylı yürütme sırası:** 1) Stripe Subscription (gerçek recurring) → 2) Per-user Notification
Settings → 3) Cloudflare Turnstile (adaptive) → 4) Deploy + Production + Beta hazırlığı →
5) Mobil + PWA → 6) TP/SL & Risk Management → 7) Coin Memory v2 → 8) Adaptive Learning v2 →
9) Similarity v2 → 10) Landing dönüşüm. Her adım: **önce analiz → küçük commit → doğrulama → rapor.**

---

## 0. Mevcut durum anlık görüntüsü (kod-temelli, 2026-06-29)

| Alan | Olgunluk | Özet |
|---|---|---|
| AI Sinyal Çekirdeği (9 motor, orkestrasyon, ATR+S/R seviyeler, adaptif ağırlık) | **mature** | Projenin en olgun parçası; canlı + backtest'te çalışıyor |
| Lifecycle v2 (canlı durum takibi) | **mature** | Kurulu + entegre, **gözlem modunda** (kararı değiştirmiyor) |
| Zekâ modülleri (Coin Memory v1/adaptif, Similarity, Regime, Snapshot) | **partial-canlı** | Kod tam + karara bağlı; **veri eşikleriyle gated** (ana darboğaz: veri) |
| Billing / Abonelik | **partial** | Tier gating **mature**; ödeme tarafı **mock + tek-seferlik** (gerçek abonelik yok) |
| Bildirim & Alarm | **partial** | Telegram + PRICE alarm çalışıyor; **notification settings GLOBAL singleton (multi-tenant hatası)** |
| Frontend platform / mobil | **partial** | Landing iyi; **PWA yok, mobil kabuk kırık** (sabit sidebar) |
| Altyapı / Deploy / Veri | **partial** | Deploy **mature/prod-hazır**; Turnstile **yalnız ADR** (kod yok); BIST 5/38 hisse; Alembic dizini yok |
| İşlem Yürütme (Auto/Copy/Exchange/API Key) | **none** | **Greenfield** — yalnız disclaimer + planlı consent tipleri |

**Üç stratejik içgörü:**
1. **Beta açılışı keystone'dur.** Zekâ modüllerinin v2'si (Coin Memory/Similarity/Adaptive)
   **gerçek kullanıcı + gerçek çözülmüş sinyal verisine** bağlı (eşik-gated). Beta açılmadan
   v2 işine başlamak verimsiz → önce veri üreten beta, sonra veri-bağımlı zekâ.
2. **Gizli gelir kaçağı + güvenlik açığı var:** `STRIPE_SECRET_KEY` boşken `/checkout`
   aboneliği **ödeme almadan** aktive ediyor (`method='mock'`). Prod'da bu yol kapatılmazsa
   bedava Premium riski. → Stripe subscription işinin parçası, **acil**.
3. **İşlem yürütme (Auto/Copy Trade) en büyük regülasyon bahsidir.** Tüm hukuki duruşumuz
   "platform işlem yapmaz" üzerine kurulu; bu alan ayrı sözleşme + ayrı risk onayı + ağır
   güvenlik gerektirir. **Phase 3'e (ayrı legal track) ertelenir.**

---

## 1. Önceliklendirme (tier'lar)

| Tier | Tema | Maddeler |
|---|---|---|
| **P0** | Yayın & gelir & veri-kilidini-aç | Stripe Subscription · Per-user Notifications · Turnstile · Mobil+PWA · Prod Deploy+migration · **Beta açılışı** |
| **P1** | Sinyal kalitesi & ayrışma (veri-bağımsız) | TP/SL + R:R iyileştirme · Lifecycle aksiyon katmanı + proaktif bildirim |
| **P2** | Zekâ v2 (veri-gated, beta sonrası) | Sinyal eşik kalibrasyonu · Coin Memory v2 · Adaptive Learning v2 · Similarity v2 · Lifecycle kalibrasyon |
| **P3** | Büyüme & ölçek | Landing dönüşüm optimizasyonu · Performans/ölçeklenebilirlik · BIST tam açılış |
| **P4** | İşlem yürütme (mega-bahis, ayrı legal track) | API Key yönetimi · Exchange API · Auto Trade · Copy Trade |

---

## 2. P0 — Yayın Enablerleri (şimdi)

### P0.1 — Stripe Subscription (gerçek auto-renew) · efor **L** · K2,K6
- **Neden şimdi:** Gelir tahsilatının ön koşulu. Mevcut akış mock + `mode='payment'` (tek
  seferlik); Stripe'ta otomatik yenileme yok. Ayrıca mock-aktivasyon **bedava upgrade açığı**.
- **Kullanıcı etkisi:** Doğrudan düşük (UI benzer); **iş etkisi yüksek** (para akışı + kaçak kapanır).
- **Ertelenirse risk:** Gelir = 0; prod'da bedava Premium sızıntısı; mesafeli satış/oto-yenileme
  taahhütleri (legal) ile kod arasında uçurum.
- **Ön koşullar:** Stripe hesabı + anahtarlar (config hazır), recurring Price/Product, `requirements.txt`'e
  `stripe`, webhook olayları (invoice.paid / subscription.updated/deleted / payment_failed) + idempotency,
  `/cancel`'ı gerçek Stripe iptaline bağlama, **mock-aktivasyon prod'da kapatma**, iade + fatura akışı.
  (Mevcut: task_a410541a)

### P0.2 — Per-user Notification Settings · efor **L** · K1,K5,K6
- **Neden şimdi:** `NotificationSettings` **global singleton** — bir kullanıcının bot_token/chat_id'si
  tüm bildirimleri ele geçirir. Çok-kullanıcılı beta için **gerçek multi-tenant hatası** (Madde 6a auth
  ekledi ama izolasyon yok).
- **Kullanıcı etkisi:** Yüksek (her kullanıcı kendi Telegram/bildirim ayarı; doğru sinyal fan-out).
- **Ertelenirse risk:** Beta'da kullanıcılar birbirinin ayarını ezer → veri sızıntısı + bozuk bildirim.
- **Ön koşullar:** `user_id` FK + unique migration + veri taşıma; `get_or_create_settings(db, user)`;
  per-user fan-out; token şifreleme. (Mevcut: task_0d92600b)

### P0.3 — Cloudflare Turnstile (adaptif) · efor **L** · K6,K5
- **Neden şimdi:** Public beta'da auth/checkout bot/brute-force koruması. Yüksek kaliteli ADR hazır
  (CAPTCHA-STRATEGY.md) ama **tek satır kod yok**.
- **Kullanıcı etkisi:** Düşük-doğrudan (görünmez/managed widget), yüksek-koruma.
- **Ertelenirse risk:** Beta'da credential-stuffing / spam kayıt / abuse.
- **Ön koşullar:** Legal bitti (✓); backend `challenge.py` (env-gated) + A3 auth-failure sayacı;
  frontend invisible widget + 428 akışı; Turnstile env anahtarları.

### P0.4 — Mobil kullanılabilirlik + PWA · efor **L** · K1,K4,K6
- **Neden şimdi:** Oturum-içi uygulama **mobilde fiilen kullanılamıyor** (sabit genişlikli fixed
  sidebar, hamburger yok). Beta kullanıcılarının çoğu mobil → kötü ilk izlenim = churn.
- **Kullanıcı etkisi:** Çok yüksek (erişilebilirlik + retention). PWA = "ana ekrana ekle" + push temeli.
- **Ertelenirse risk:** Mobil beta kullanıcı kaybı; app-mağaza alternatifi gecikir.
- **Ön koşullar:** Responsive shell (hamburger + drawer + breakpoint padding); `manifest.json` + ikon
  seti + service worker (offline/cache) + layout Metadata. (Native = Phase 3.)

### P0.5 — Prod Deploy + Alembic migration disiplini + Beta açılış planı · efor **M** · K5,K6
- **Neden şimdi:** Deploy config olgun ama **çalıştırılmadı**; şema değişiklikleri elle SQL (Alembic
  `requirements`'te var ama `alembic.ini`/migrations dizini yok → riskli). Beta için go-live.
- **Kullanıcı etkisi:** Beta'nın varlık koşulu.
- **Ertelenirse risk:** Tüm P1/P2 (veri) bloke; manuel SQL şema kayması/hata riski.
- **Ön koşullar:** Alembic init + baseline + mevcut elle migration'ları içe alma; prod env
  (DEBUG=false, CORS, Sentry/PostHog DSN, Stripe, Turnstile); SMOKE-TEST.md deploy-sonrası checklist;
  işleticinin gerçek kimlik/iletişim bilgileri (gerçek kişi modeli — **şirket varsayılmaz**;
  bkz. OPERATING-MODEL.md) (legal v1.0 için — ayrı). UptimeRobot alarmı.

---

## 3. P1 — Sinyal Kalitesi & Ayrışma (veri-bağımsız, hemen değer)

### P1.1 — TP/SL & R:R iyileştirmesi · efor **M** · K3,K4
> **DURUM (2026-06-30): KAPANDI (Lever 1B).** Kök-neden çözüldü: SR-override artık TP1'i yalnız
> DIŞARI iter (asla içeri çekmez) → planlı R:R median 0.41→1.0, sub-1 %82.5→%17.3, **hacim aynı**,
> per-asset win/pf/expectancy ↑/nötr, byte-identical çekirdek korundu. Filtre (A) gereksiz çıktı.
> **Ertelenen (backlog):** 2A (TP1 1.5→2.0×ATR), 3 (SR-on-SL kapı), min-TP/SL floor + R:R eşiği
> (VERİ-GATED). Kanonik: docs/P11-CLOSURE.md + docs/P11-tpsl-rr-analysis.md.
- **Neden şimdi:** Çekirdek mature ama TP/SL **sabit ATR çarpanları** (1.5/3.0/5.0x); R:R açıkça
  hesaplanıp filtrelenmiyor; SMC OB/FVG entry'de kullanılmıyor; TP sıralaması bozulabilir. Bunlar
  **veri gerektirmeyen mantık iyileştirmeleri** → anında sinyal kalitesi + ayrışma.
- **Kullanıcı etkisi:** Yüksek (daha gerçekçi seviyeler, kötü R:R sinyallerin elenmesi).
- **Ertelenirse risk:** Sinyal güveni düşük kalır; beta verisi "kalibre edilmemiş" mantıkla birikir.
- **Ön koşullar:** Yok (mevcut motor + ATR + regime detector + SMC motoru hazır). Regresyon: backtest.

### P1.2 — Lifecycle aksiyon katmanı + proaktif bildirim · efor **M** · K1,K4
> **DURUM (2026-06-30): BACKEND FONKSİYONEL TAMAM** [P12-1 b311a28 · P12-2 ca50081 · P12-3 0df43a8].
> notify_lifecycle opt-in kolonu (default KAPALI) + format_lifecycle_message + notify_lifecycle fan-out
> (Pro+ gate, fail-open) + tracker hook (gerçek transition → {invalidating, approaching_tp}, commit
> sonrası fire-and-forget). Detection/resolution **byte-identical**; opt-in=0 → davranış değişmedi.
> **Kalan (ops.):** P12-4 frontend toggle + /lifecycle/metrics `lifecycle_alerts_sent` sayacı.
> Analiz: docs/P12-lifecycle-action-layer-analysis.md.
- **Neden şimdi:** Lifecycle v2 mature ama **gözlem-only**; WEAKENING/INVALIDATING tespit edince
  kullanıcıya **proaktif uyarı** vermiyor. Bu, güçlü bir ayrışma özelliği ("sinyalin bozuluyor").
- **Kullanıcı etkisi:** Yüksek (erken uyarı = güven + değer).
- **Ertelenirse risk:** Mature bir varlık atıl kalır; rakip "canlı sinyal sağlığı" ile ayrışır.
- **Ön koşullar:** **P0.2 (per-user notifications)** — bildirim hedefi için. Eşik kalibrasyonu P2'de
  iyileşir ama uyarı katmanı şimdi kurulabilir (muhafazakâr eşikle).

---

## 4. P2 — Zekâ v2 (VERİ-GATED — beta sonrası)

> Bu maddeler **gerçek kullanıcı + çözülmüş sinyal verisi** olmadan verimsizdir (eşikler:
> ~20 resolved/symbol+tf, ~8 similarity eşleşmesi, ~250-300 trade_path). **Ön koşul: P0 beta + veri birikimi.**

- **P2.1 — Sinyal eşik kalibrasyonu** (M, K3): 68/54/46 + 4-of-6 + disagreement/mtf katsayılarını
  gerçek win/loss ile kalibre et. Ön koşul: veri.
- **P2.2 — Coin Memory v2** (L, K3,K4): `tm_stats`'ı gözlemden **politikaya** bağla (coin-spesifik
  TP/SL/scale-out önerisi). Ön koşul: trade_path verisi + P1.1.
  - **DURUM (2026-06-30): M1+M2 TAMAM → veri-bağımsız altyapı KAPANDI** (fold-hardening + additive
    `tm_stats` + drop&rebuild + read-only reader + signals.py additive payload; docs/P07-coin-memory-v2-analysis.md).
    **M3 (politikaya/Similarity'ye bağlama) ⛔ DEFERRED → checkpoint-gated (≥250-300 trade_path);**
    şu an per-cell yalnız 1 hücre eşik üstü. tm_stats artık türetilebilir cache + okunabilir yüzey.
- **P2.3 — Adaptive Learning v2** (L, K3,K5): regime-koşullu adaptif ağırlık + outcome-label →
  karar; **shadow/A-B ölçüm harness'i** (adaptif vs base fayda ölçümü). Ön koşul: veri + ölçüm altyapısı.
  - **DURUM (2026-06-30): POLİTİKA ⛔ DEFERRED → checkpoint-gated** (130 hücreden 2 aktif, max 22 → erken).
    **A8-1 telemetri kancası TAMAM** [d98113c]: `extra.birth`'e additive `engine_weights_used`+
    `adaptive_active`+`regime` (byte-identical karar yolu) → ileride adaptif-vs-base ölçümü mümkün.
    Politika v2 + shadow/A-B harness veri checkpoint + ayrı onay bekliyor (docs/P08-adaptive-v2-analysis.md).
- **P2.4 — Similarity v2** (L, K3,K5): brute-force → feature-store/ANN indeks; ölçeklenme. Ön koşul:
  veri + perf.
- ✅ **P2.5 — Lifecycle kalibrasyon — TAMAM (2026-06-30):** L1 Calibration Harness (`scripts/lifecycle_calibration.py`,
  salt-okur Tier-1) ile 569 resolved sinyalde grid sweep + per-regime. **Sonuç: mevcut eşikler veriyle DOĞRULANDI,
  davranış değişikliği gerekmedi** (invalidating %72 prec/%85 recall, J 0.60'ta tepe; approaching yapısal; weakening
  UI-only; regime-conditioning gereksiz). Karar katmanı değişmedi. Kanonik: docs/P25-lifecycle-calibration-analysis.md.
  🔎 Backlog: flip-flop %39.4 churn → ayrı Tier-2 UX/telemetri (exit/hysteresis), TP/SL·resolution·AI-karardan bağımsız.
- **Ortak ön koşul (S):** Backfill/seed + **versiyonlu migration** (zekâ tabloları şu an create_all).

---

## 5. P3 — Büyüme & Ölçek (beta trafiği oluşunca)

- **P3.1 — Landing dönüşüm optimizasyonu** (M, K2): A/B test, conversion funnel (PostHog kurulu),
  JSON-LD/SEO. Ön koşul: beta trafiği (ölçülecek dönüşüm).
- **P3.2 — Performans & ölçeklenebilirlik** (L, K5): route/komponent code-splitting (ağır grafikler),
  SWR/React Query (merkezi cache/dedupe), **scheduler'ı ayrı worker'a çıkar** + sayaçları Upstash
  Redis'e taşı (yatay ölçek; şu an in-process → tek-replica zorunlu). Ön koşul: artan yük.
- **P3.3 — BIST tam açılış** (M, K1,K4): kalan ~33 hisse kademeli aktivasyon + BIST_HOLIDAYS takvimi.
  **Supabase Pro'ya geçildi** → egress kısıtı gevşedi; market-saatine-duyarlı polling + cache ile
  ayrı bir analizle ilerletilecek (kullanıcının istediği BIST karar raporu). Ön koşul: Pro plan (✓) +
  egress/polling analizi.

---

## 6. P4 — İşlem Yürütme (mega-bahis · Phase 3 · ayrı legal track)

> **Greenfield + en yüksek regülasyon riski.** Sıra zorunlu: API Key → Exchange (read-only önce) →
> Auto Trade (paper-trading önce) → Copy Trade. Her biri ayrı sözleşme + ayrı açık onay + ayrı risk
> bildirimi (legal mimari hazır) + ağır güvenlik gerektirir.

- **P4.1 — API Key yönetimi** (L, K5): şifreli saklama (KMS/at-rest), scope (read-only/trade), rotasyon,
  kullanıcı izolasyonu. **Diğer hepsinin ön koşulu.**
- **P4.2 — Exchange API entegrasyonu** (L-XL): ccxt/borsa SDK, order create/cancel/status, rate-limit,
  retry/circuit-breaker. Önce **read-only** (bakiye/pozisyon görüntüleme).
- **P4.3 — Auto Trade altyapısı** (XL, K4): emir state machine, risk/pozisyon limitleri, kill-switch,
  **paper-trading/sandbox önce**, idempotency, audit. Ayrı sözleşme + onay + 2FA + withdrawal-disabled key.
- **P4.4 — Copy Trade** (XL): lider/takipçi, oransal allocation, slippage/gecikme. Auto Trade üzerine kurulur.
- **Ertelenirse risk:** Düşük (ürün konumlandırması zaten "işlem yapmaz"); aksine **erken yapılırsa**
  regülasyon/itibar riski yüksek. Talep + lisans/uyum netliği oluşunca.

---

## 7. Önerilen ilk 3 (sıra)

1. **P0.1 Stripe Subscription** — gelir + bedava-upgrade açığını kapat (en yüksek iş etkisi).
2. **P0.2 Per-user Notifications** — multi-tenant hatasını kapat (beta ön koşulu) + P1.2'yi açar.
3. **P0.4 Mobil+PWA** — mobil beta kullanılabilirliği (retention).

Ardından P0.3 Turnstile + P0.5 Deploy → **Beta açılışı** → veri birikimi → P1 (sinyal kalitesi) →
P2 (zekâ v2). BIST tam açılış (P3.3) Pro plan sonrası ayrı egress analiziyle paralel yürütülebilir.

> **İlke:** Her madde küçük adım → ayrı commit → ayrı doğrulama (tsc/import + canlı/izole test) →
> ayrı rapor. TM v2 veri toplama / scheduler / çekirdek motorlar bozulmadan. Legal/güvenlik
> standartları her özellikte korunur.
