# Beta Launch Checklist — Tek Sayfa (Beta-Ready Baseline)

**Checkpoint:** 2026-06-30 · **Statü:** BETA-READY BASELINE. Bundan sonraki tüm geliştirmeler bu
baseline üzerinden ilerler. İşletim modeli = **gerçek kişi / bireysel işletici** ([OPERATING-MODEL.md](./OPERATING-MODEL.md)).
Ayrıntı: [RELEASE-RUNBOOK.md](./RELEASE-RUNBOOK.md) · [DEPLOYMENT.md](./DEPLOYMENT.md) · [SMOKE-TEST.md](./SMOKE-TEST.md).

## 1. Tamamlanan hazırlıklar
- **Beta-hazırlık A-bloğu (5/5):** A1 dep bump (numpy/stripe sabit) + lockfile · A2a iletişim tek-kaynak
  (`lib/contact.ts`) · A3 Stripe mock-gate (yalnız DEBUG+ENVIRONMENT=development) · A4 release-runbook+rollback
  +migration-kılavuzu · A5 çalıştırılabilir `prod_smoke.py`+env-checklist.
- **Şirket varsayımı KALDIRILDI** → gerçek kişi modeli; OPERATING-MODEL.md kanonik; 8 legal metin + tüm docs hizalı (version bump yok → re-consent yok).
- **Çekirdek (kod tarafı):** P0.6 KEY1 (tek-kaynak resolution, byte-identical) · P0.7 CM v2 M1+M2 · P0.8 A8-1 telemetri · P1.1 TP/SL&R:R (Lever 1B) · P1.2 Lifecycle proaktif bildirim (opt-in) · güvenlik/legal-kod/rate-limit/monitoring/smoke 21/21.
- **Doğrulama:** byte-identical/equivalence (golden 8 + diff 8000 + mapping 3000 + backtest 9000) + tüm test PASS; çalışma ağacı temiz; **kod davranışı değişmedi**.

## 2. Kullanıcıdan beklenenler (dış bağımlılık — tek kalan)
- **B1 — Operatör bilgileri ve faaliyet gösterilecek ülkeye göre gerekli hukuki/vergisel bilgiler:**
  gerçek kişi ad/işletme adı, vergi kimlik, adres, resmî iletişim → `lib/contact.ts` + künye + v0.9→v1.0.
  Gereklilikler **faaliyet gösterilecek ülkeye göre değişir** (şirket gerektirmez ≠ hiçbir hukuki bilgi
  gerekmez). MERSİS/KEP/VERBİS/aktarım = "varsa/uygulanmaz", **hukuki karar**.
- **B2 — Stripe S7:** `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` + webhook endpoint kaydı ([STRIPE-S7-RUNBOOK.md](./STRIPE-S7-RUNBOOK.md)). Bireysel hesap destekler.
- **B3 — Turnstile + prod env + ilk deploy:** Cloudflare anahtarları + prod env (ENVIRONMENT=production · DEBUG=false · güçlü JWT_SECRET · pooler DATABASE_URL · prod CORS · FRONTEND_BASE_URL · NEXT_PUBLIC_*).

## 3. Canlıya çıkış sırası
1. Prod env değerlerini ayarla (§2-B3). 2. **Migration kararı:** fresh DB → otomatik `migrate.py apply`;
mevcut DB → **bir kez `migrate.py stamp`** (0003 yıkıcı re-run = veri kaybı). 3. Backend deploy (Railway,
preDeploy migrate) → **migrate fail ise PROMOTE ETME**. 4. `/health` 200. 5. Frontend deploy (Vercel).
6. Doğrulama (§5). 7. UptimeRobot + Sentry. (Tek replika + `--workers 1` korunur.)

## 4. Rollback sırası
- **Uygulama (hızlı, varsayılan):** Backend → Railway önceki deployment'a Redeploy/Rollback; Frontend →
  Vercel önceki üretimi "Promote". Tetik: 5xx artışı / smoke fail / Sentry patlaması.
- **DB:** migration'lar **forward-only** (down yok) → bozuk migration için **ileri-telafi migration** yaz;
  yıkıcı migration yanlışlıkla çalıştıysa Supabase **backup restore**. Önce kod rollback (additive migration'lar uyumlu).
- **Env:** hatalı env düzelt → redeploy. `ENVIRONMENT=production` her zaman set olmalı.

## 5. Doğrulama adımları
- **Otomatik (güvenli):** `python scripts/prod_smoke.py https://<api>` (health/healthy/debug-sızıntı yok,
  /docs⇒404, güvenlik header, /billing/plans 200, auth-gate, CORS reddi).
- **Elle (yan-etkili):** rate-limit 429 burst, register/login, checkout (boş key⇒503 / S7), webhook imza,
  Turnstile 428→widget. ([SMOKE-TEST.md](./SMOKE-TEST.md) post-deploy.)

## 6. Go / No-Go kriterleri
**GO (hepsi sağlanmalı):** prod fail-fast validator geçti (kritik env) · `/health` 200 · migration status
APPLIED · `/docs`⇒404 · güvenlik header+CSP canlı · CORS yalnız prod domain · Stripe boşsa checkout 503
(mock free-upgrade YOK) · prod_smoke tüm güvenli kontrol PASS · işletici legal bilgileri (B1) doldu / v1.0
· Turnstile anahtarı set (yoksa bot-challenge KAPALI riski kabul edilmeli).
**NO-GO:** validator boot etmiyor · migration fail · mock free-upgrade erişilebilir · header/CORS açığı ·
Turnstile beklenip set edilmemiş.

## 7. Beta sonrası açılacak veri-gated fazlar (beta → veri → kilit açılır)
Eşik: ~250-300 trade_path (+ per-cell yoğunluk). Şu an ~200.
- **Coin Memory v2 — M3** (tm_stats → Similarity besleme + ince dilim).
- **Adaptive Learning v2 — politika** (regime-koşullu ağırlık + shadow/A-B fayda harness'i).
- **Similarity v2** (brute-force → ANN/feature-store ölçeklenme).
- **KEY2 — min-TP/SL floor + R:R eşik kalibrasyonu** + **P1.1 2A/3** (TP1 1.5→2.0×ATR, SR-on-SL kapı).
- **Sinyal eşik / Lifecycle kalibrasyonu.**
> Hepsi BP2 (telemetri-önce + backtest-gate) + ayrı analiz/onay döngüsüyle; KEY1 mimarisi bunu mümkün kılar.
