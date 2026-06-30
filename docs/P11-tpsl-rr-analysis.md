# P1.1 — TP/SL & R:R İyileştirmesi — ANALİZ & TASARIM (kod YOK)

**Tarih:** 2026-06-30 · **Statü:** ANALİZ. Davranış-değiştiren → onay sonrası uygulama.
**Kaynak:** 4-ajan kod-haritalama (TP/SL üretimi · risk engine · SMC · R:R/filtre+zekâ-v2) + birinci-el okuma.

## 0. Kök neden (kanıtlanmış)
`signal_generator.py:282-344` actionable seviyeleri **sabit ATR çarpanlarıyla** üretir:
entry-kenarı 0.5×ATR · **SL 1.5×ATR · TP1 1.5×ATR** · TP2 3.0× · TP3 5.0×.
- **SL ve TP1 simetrik (1.5×/1.5×)** → SR-override öncesi planlı R:R ≈ **1.0**.
- **SR-override** (`nearest_res < tp2 → tp1 = nearest_res`, satır 305-308) TP1'i **içeri** çeker
  ve/veya SL'yi **dışarı** iter (`nearest_sup − 0.5×ATR`) → |TP1−entry| < |entry−SL| → **R:R < 1.0**.
- **Canlı kanıt: %79 sub-1-RR** (`tpsl_analytics.sub_1_rr_pct`).
- **R:R üretim anında HİÇ hesaplanmaz/filtrelenmez.** Risk engine `rr` hesaplar ama (a) seviyeler
  ÖNCESİ paralel çalışır (entry/sl/tp=None) → birth'te **hep None**; (b) yalnız risk_score'u iter,
  **bloklamaz**. Gerçek R:R = `birth_telemetry.planned_rr_tp1` (`trade_geometry.planned_rr`).
- **TP-ordering guard YOK** → SR-override sıralamayı bozabilir (tp1≷tp2).
- **SMC OB/FVG geometrisi** (`smc/engine.py:179-200` `unmitigated_*_ob`/`unfilled_*_fvg` {high,low,index})
  hazır ama entry/SL'de **kullanılmıyor** — yalnız SMC skoru HOLD oyuna girer.

## 1. Kapsam — kesin sınırlar
**DAHİL (veri-bağımsız, telemetri-önce + backtest-doğrulamalı):**
1. Backtest raporu zenginleştirme (TP1-RR + tp1/2/3 reach-rate + realized-R) — **ölçüm önkoşulu**.
2. **TP-ordering monotonluk guard** (saf bug fix).
3. **R:R telemetri-önce** (planlı R:R + "would-downgrade" bayrağı; eylem YOK) — etki ölç.
4. **R:R filtresi** (düşük-R:R BUY/SELL → HOLD) — **prensipli** eşikle (1.0; kalibre değil).
5. (Sonra) **SMC OB/FVG-çapalı entry/SL** — zon yoksa ATR/SR fallback.
6. (Sonra) **Adaptif-çarpan İSKELESİ** (vol_class'a göre yapı; değerler kalibre değil).

**HARİÇ (özellikle):**
- **min-TP1/SL mesafe FLOOR kalibrasyonu** (KEY2) + **optimal eşik/çarpan DEĞERLERİ** → **VERİ-GATED**
  (≥250-300 trade_path, `calibration_ready`). Şimdi yalnız dikiş haritalanır, sayı set edilmez.
- **HOLD fallback** (`346-369`, bilgi-amaçlı) — R:R filtresi buraya dokunmaz.
- **SMC yön-skorlaması** (engine score, smc>53/<47 gate) · `resolution_core.step_bar` (KEY1) ·
  `trade_geometry.planned_rr` tanımı · `BASE_ENGINE_WEIGHTS` · `safe_last_atr` (BUG-1) · risk_score 1-10 (D1).
- **Zekâ-v2'nin TP/SL'e BESLEMESİ** (CM/Similarity/Adaptive → çarpan/floor) → net-yeni + **veri-gated**.

## 2. Before / After (davranış)
| Senaryo | MEVCUT | P1.1 sonrası |
|---|---|---|
| TP1>TP2 sıralama bozulması (SR-override) | Yazılır (bozuk) | **Guard düzeltir** (monotonluk) |
| SR-override TP1'i çok yakına çeker (R:R 0.2) | BUY/SELL yayınlanır | **R:R<1.0 → HOLD'a indirir** (filtre) |
| Normal R:R≥1.0 sinyal | Aynı | **AYNI (byte-identical)** |
| Entry/SL yerleşimi | ATR/SR | (sonra) OB/FVG-çapalı, yoksa ATR/SR fallback (zon-yok bar'da AYNI) |
| ATR çarpanları | Sabit 1.5/3.0/5.0 | (sonra) vol_class-iskele; **değerler veri-gated** |

## 3. Sinyal kalitesi / risk / UX etkisi
- **Sinyal kalitesi:** kötü-R:R elenince yayınlanan setin beklentisi (expectancy) artar; sıralama
  düzelir. **Beta-öncesi yapılması, 4 zekâ-önceliğinin öğreneceği veriyi kalibre eder.**
- **Risk profili:** kullanıcı artık R:R<1 "tuzak" sinyalleri görmez (asimetrik risk düşer).
- **UX (DİKKAT):** %79 sub-1-RR → naif eşikle çoğu sinyal HOLD'a düşebilir → **actionable hacim ciddi
  azalır**. Bu yüzden **telemetri-önce + muhafazakâr eşik (1.0) + backtest** zorunlu; eşiği veriyle
  sonra sıkılaştır. (Alternatif: reshape — aşağıda riskli bulundu.)

## 4. Backtest etkisi & doğrulama metrikleri
KEY1 → backtest **geçerli BP2 gate** (canlı tracker + backtest tek `step_bar`, byte-identical).
**Eklenecek metrikler** (rapor şu an `average_rr`'yi **TP3-bazlı** veriyor → TP1 sorununu görmez):
- `planned_rr_tp1` ort/medyan + **sub_1_rr_pct** (üretim kalitesi).
- **tp1/tp2/tp3 reach-rate** + realized-R dağılımı + MFE/MAE.
- win_rate · profit_factor · expectancy · signal-count (HOLD vs actionable).
**Kabul kriteri:** filtre sonrası kalan setin **expectancy/profit_factor REGRESE OLMAMALI** (ideal:
artmalı); ordering-guard sonrası metrikler **≥ mevcut**; normal-R:R sinyaller **byte-identical**.
**Premise doğrulama:** "düşük-R:R sinyaller gerçekten mi kaybediyor?" → low-RR cohort'un realized-R'si
backtest'te ölçülür (filtreyi veriyle haklı çıkar).

## 5. Zekâ-v2 entegrasyon noktaları (harita; VALUES veri-gated)
- **Coin Memory v2:** `tm_stats` per-cell (avg_mfe_r/mae_r, tp1_rate, tight_sl, planned_rr) → per-coin
  çarpan/floor seçimi. **KEY2 floor'un veri-beslemesi** (`compute_coin_tm_summary`, MIN_TM_SAMPLES=10).
- **Adaptive v2:** `engine_weights` yolu (zaten threaded) ALONGSIDE bir "level-params" dönüşü → regime/
  per-cell adaptif çarpan; `adaptive_is_active` gibi gated. Bugün ağırlık yalnız skoru etkiler.
- **Similarity v2:** komşu-bazlı beklenen MFE/R → TP mesafesi bias (read-only, additive). Gate=8 eşleşme.
→ Üçü de **net-yeni TP/SL hook'u + veri-gated**; P1.1'in 3 çekirdek fix'i bunlardan bağımsız.

## 6. Mimari seçenekler (3) — R:R nasıl ele alınacak
**A — FİLTRE (düşük-R:R → HOLD):** planlı R:R<eşik ise BUY/SELL'i HOLD'a indir.
- ✅ En basit, dürüst (kötü sinyali gösterme), HOLD-gate'e additive, hedef manipülasyonu yok, geri-alınabilir.
- ❌ Actionable hacmi düşürür (%79 sub-1 → çok HOLD); eşik agresifse sinyal kıtlığı.
- 🔧 Risk: düşük (saf gate). Uzun vade: temiz set + kalibre beta verisi; hacim UX'i izlenmeli.

**B — RESHAPE (R:R'yi zorla):** R:R<eşik ise TP1'i dışarı it / SL'yi sıkılaştır.
- ✅ Hacmi korur.
- ❌ **Teknik gerekçesiz hedef üretir** (gerçek direncin ötesinde TP1 → gerçekçi değil, hit-rate düşer);
  TP1'in anlamını bozar; SL sıkılaştırma erken-stop riskini artırır.
- 🔧 Risk: **yüksek** (fabrikasyon seviyeler). Uzun vade: yanıltıcı; **önerilmez**.

**C — KÖK-NEDEN (ordering guard + SR-override disiplini + asimetrik default):** TP-ordering guard
(her zaman) + SR-override TP1'i floor-altı çekiyorsa override'ı KULLANMA (ATR-TP1'i koru) +
ops. TP1 default'unu hafif genişlet / SL default'unu sıkılaştır.
- ✅ Asıl nedeni düzeltir; hacmi korur; prensipli; ordering-guard saf-fix.
- ❌ Daha nüanslı; "yakın direnci TP1 yapma" kararı = TP1 bazen gerçek direncin ötesinde (daha az gerçekçi);
  default değişimi davranış-değiştiren (backtest şart).
- 🔧 Risk: orta. Uzun vade: dengeli ama default-tuning kısmı veriyle olgunlaşmalı.

**ÖNERİ: C(ordering-guard) + A(filtre), aşamalı; B reddedilir.**
1. Ordering-guard (saf bug fix, sıfır R:R-davranışı).
2. R:R telemetri-önce (ölç, eyleme geçme).
3. R:R filtre (A), **muhafazakâr eşik 1.0**, backtest before/after (premise + no-regression).
4. (Sonra) SMC entry + adaptif iskele. Floor/optimal-eşik/çarpan-değerleri → **veri-gated (KEY2)**.

## 7. Uygulama sırası (küçük commit'ler) + commit-başı doğrulama
- **P11-0 — Backtest rapor zenginleştirme** (additive: tp1-RR, tp1/2/3 reach-rate, realized-R). *Doğrulama:*
  mevcut backtest metrikleri **değişmez** (yalnız yeni alanlar eklenir); golden/diff/mapping/backtest 9000 PASS.
- **P11-1 — TP-ordering guard** (post-SR-override monotonluk + entry-tarafı kontrolü). *Doğrulama:*
  backtest before/after — düzelen sıralama dışında metrikler **≥ mevcut**; bozuk-ordering trade sayısı raporlanır;
  golden/diff/mapping/backtest PASS.
- **P11-2 — R:R telemetri-önce** (birth'e `planned_rr_tp1` zaten var + `low_rr_would_downgrade` bayrağı; eylem YOK).
  *Doğrulama:* davranış **byte-identical** (yalnız additive telemetri); canlı/backtest'te kaç sinyalin
  indirileceği + low-RR cohort realized-R **raporu**.
- **P11-3 — R:R filtre (A)** (düşük-R:R BUY/SELL→HOLD, eşik=1.0). **DAVRANIŞ-DEĞİŞTİREN → ayrı onay.**
  *Doğrulama:* backtest before/after (win_rate/profit_factor/expectancy **regresyonsuz**, sub_1_rr_pct düşer,
  signal-count etkisi); normal-R:R sinyaller byte-identical; fark→oto-fix yok, raporla.
- **P11-4 (ops., sonra) — SMC OB/FVG entry + adaptif çarpan iskelesi** (zon-yoksa fallback=AYNI; provenance
  telemetri-önce). *Doğrulama:* zon-yok bar'da byte-identical; zon-var delta backtest'le ölçülür.
- **DEFERRED (KEY2, veri-gated):** floor değerleri + optimal eşik + çarpan değerleri + per-cell/regime + zekâ-v2 besleme.

## 8. Onay noktası
Önerilen kapsam: **P11-0 → P11-1 → P11-2** (hepsi veri-bağımsız + byte-identical/saf-fix + telemetri-önce),
sonra **P11-3 ayrı onayla** (ilk gerçek davranış değişikliği). Mimari karar: **C+A (B reddedilir)**.
Onaylarsan **P11-0 (backtest rapor zenginleştirme)** ile başlarım — sıfır davranış değişikliği, ölçüm zemini.
