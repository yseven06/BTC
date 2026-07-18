# CP-SQF-2A — Quality / Confidence Outcome Profiling (shadow, read-only)

**Tarih:** 2026-07-18 · **Statü:** shadow/offline karar-desteği (davranış değişikliği YOK)
**Script:** `backend/scripts/sqf2_score_profiling.py` (read-only; DB'ye yazmaz; deterministik — art arda koşularda byte-identical)
**Veri:** canlı DB · kapalı sinyaller (`outcome<>'ACTIVE' AND closed_at NOT NULL`) · generated_at 2026-06-20…07-18
**Kütüphane:** numpy/pandas (sklearn/scipy yok → AUC/PR-AUC/Brier/logistic-IRLS numpy ile elle; yeni bağımlılık eklenmedi)

---

## A. Executive conclusion

**Mevcut confidence/composite/probability/risk skorları outcome'u AYIRMIYOR** (AUC ≈ 0.50, hepsi). Ekrandaki **"7/10" = `Math.round(confidence_score/10)`** (SignalTable.tsx:30) — dar bir 65–80 bandına sıkışmış, outcome-korelasyonu ~0 olan **dekoratif** bir sayı. Birth-feature'lardan **yeniden-kalibre** edilmiş logistic model walk-forward'da yalnız **marjinal** ayrışma veriyor (pooled OOS AUC 0.531) ve **out-of-sample kitap ekonomisini iyileştirmiyor** (model "en iyi %25"i tut → PF 0.998, OOS-havuz baseline 1.007). Görünen tek edge olan **confidence≥76 bandı CONFOUNDED**: %81 bullish + trending_bull'a yığılmış, W26–W27'de pozitif ama **en yeni haftada (W29) tersine dönüyor** (≥76 stop %54.7, avgR −0.27).

**KARAR (5 seçenekten): → 4. OUT-OF-SAMPLE AYRIŞTIRICI EDGE YOK.**
Canlı yayın-barı / skor-gate **AÇILMAMALI**; veri birikmeye devam etmeli (gözlem-modu). Not: model OOS AUC hafta-hafta yükseliyor (0.516 → 0.548 → 0.562) — veri-birikimi sinyali olabilir; harness periyodik yeniden-koşulmalı (F1-a reopen tetikleyicisi).

---

## B. Dataset / coverage / join doğrulaması

- Kapalı sinyal (join'lenen): **2551** · binary evren (WIN/BE/LOSS): **2496** · hariç terminal (INVALIDATED 53 + EXPIRED 2): **55** · bilinmeyen outcome: **0**.
- Kapsam: confidence **%100** · composite_confidence **%93.3** · fear_greed %93.2 · regime %93.3 · planned_rr_tp1 / sl_dist_pct **%71** · engine_dir_agreement %93.3.
- Join **1:1** doğrulandı (signal_snapshots 0 duplicate; `signal_id` benzersizlik assert'i geçti). Row-order `ORDER BY generated_at, id` ile deterministik.
- **Baseline (tüm kapalı):** stop **%38.9** · win %36.7 · BE %22.3 · TP1 %55.2 · avgR −0.045 · medR +0.247 · **PF 0.93**. (CP-SQF-1 manuel forensic ile birebir.)
- Baseline (binary): stop %39.7 · PF 0.978.

## C. Outcome taxonomy → binary label

| outcome | n | → is_loss |
|---|---|---|
| LOSS | 992 | **1** |
| WIN | 935 | 0 |
| BREAKEVEN | 569 | 0 |
| INVALIDATED | 53 | binary-dışı (ayrı raporlandı) |
| EXPIRED | 2 | binary-dışı (ayrı raporlandı) |

BE/INVALIDATED/EXPIRED **loss'a otomatik sokulmadı**; is_loss yalnız outcome='LOSS'. İkincil sonuç = `actual_return` (kitap görüntüsüyle aynı % birimi) + hit_tp* + çok-sınıflı W/BE/L.

## D. Confidence score profili

- n=2551, unique=890, min 65.0 max 80.02 mean 71.66 median 71.95; **quantile(10/25/50/75/90) = 66.9 / 69.0 / 72.0 / 74.1 / 76.0** → dar band.
- **AUC(→loss) = 0.4954** · PR-AUC 0.3918 → **ayrıştırma yok** (0.5 = rastgele).
- Decile monotonluğu: skor arttıkça loss düşmeli; gerçekte adımların yalnız **%33'ü** monotonik → düzensiz. En üst decile (75.98–80.02) stop %37.2 / PF 1.41, en alt decile (65–66.9) stop %39.4 / PF 1.10 — fark küçük ve gürültülü.

## E. Composite confidence profili

- n=2379 (%93.3), **AUC(→loss) = 0.4969** · PR-AUC 0.3937 → confidence ile aynı, ayrıştırmıyor. Decile monotonluğu %56 (yine zayıf). En üst decile PF 1.451, ama alt decile de PF 1.20 → tutarsız.

## F. Probability & risk score profili

- **probability_score:** AUC 0.504 · composite_probability 0.5023 → ayrıştırmıyor. Decile'lar zikzak (dec3 PF 1.28, dec7 PF 0.72, dec9 PF 1.43, dec10 PF 0.83) — gürültü.
- **risk_score:** unique=**7**, median 5.0, quantile(10..90) hepsi **5.0** → fiilen **sabit** (crypto default). AUC 0.4997. **Ayrıştırıcı değil** — "risk MEDIUM default" hipotezi doğrulandı.

## G. Birth-feature model (recalibration) sonucu

27 birth/snapshot feature (confidence/probability/risk/composite×2/atr/vol×2/fear_greed/planned_rr/sl_dist/entry_zone_width/engine_agreement×3 + onehot direction/timeframe/regime) → logistic (IRLS, ridge, standardize). **Leakage whitelist assert'i geçti** (hiçbir post-birth alan feature değil). Walk-forward:

| fold (train → test) | n_train | n_test | OOS AUC | PR-AUC | Brier |
|---|---|---|---|---|---|
| W25–W26 → W27 | 616 | 635 | 0.5164 | 0.3829 | 0.2406 |
| W25–W27 → W28 | 1251 | 780 | 0.5475 | 0.4824 | 0.2641 |
| W25–W28 → W29 | 2031 | 465 | 0.5622 | 0.5350 | 0.2503 |
| **POOLED OOS** | | **1880** | **0.5313** | 0.447 | 0.2528 |

- Aynı havuzda ham confidence OOS AUC = 0.5173, composite_confidence 0.5173 → model marjinal iyileştirme (0.531 vs 0.517), ama **her ikisi de 0.5'e yakın**.
- Kalibrasyon: tahmin edilen loss-olasılığı ile gözlenen loss-oranı **monotonik değil** (örn. pred 0.26 → obs 0.36; pred 0.35 → obs 0.43; pred 0.62 → obs 0.33) → model olasılıkları güvenilir sıralama vermiyor.

## H. Walk-forward out-of-sample sonuç

Karar yalnız OOS'tan verildi. **Ekonomik test belirleyici:** model OOS "en iyi %25"i tut → **PF 0.998**, OOS-havuz baseline **1.007** → **iyileştirme YOK** (hafifçe daha kötü). Yani recalibration istatistiksel olarak marjinal ayrışsa da **kitap ekonomisini out-of-sample iyileştirmiyor**. (OOS AUC'nin haftalık yükselişi ayrı bir gözlem sinyali — bkz. N.)

## I. Decile ve kalibrasyon tabloları

Tam decile tabloları (5 skor × 10 decile) ve model kalibrasyon tablosu script stdout'unda. Özet: **hiçbir skorda temiz monoton loss-rate düşüşü yok**; en iyi durumda (composite) adımların %56'sı monotonik = şansa yakın. Model kalibrasyonu düz/gürültülü.

## J. Shadow yayın-bar karşılaştırması (naive P&L-removal)

| Varyant | n | retain% | stop% | TP1% | PF | avgR | dPF |
|---|---|---|---|---|---|---|---|
| baseline (tüm) | 2551 | 100 | 38.9 | 55.2 | 0.93 | −0.045 | — |
| raw conf≥65 (**mevcut canlı kapı**) | 2551 | **100.0** | 38.9 | 55.2 | 0.93 | −0.045 | 0.0 |
| raw conf≥76 | 246 | **9.6** | 37.0 | 57.7 | 1.346 | +0.187 | +0.416 |
| raw conf≥78 | 33 | **1.3** | 24.2 | 66.7 | 1.497 | +0.226 | +0.567 |
| composite top-quartile (≥74.2) | 597 | 23.4 | 38.0 | 56.8 | 1.055 | +0.033 | +0.125 |
| **model OOS keep-best-25%** | 471 | 25.1* | 40.6 | 55.0 | **0.998** | −0.001 | (OOS-havuz PF 1.007) |

\*OOS havuzunun %25'i. **Kritik okuma:** (a) mevcut conf≥65 kapısı **hiçbir şeyi elemiyor** (retain %100); (b) PF>1 veren tek ham bar **conf≥76/≥78 ama önemsiz hacim** (%9.6 / %1.3) ve confounded (bkz. K); (c) composite top-quartile marjinal (PF 1.055, %23 hacim); (d) recalibre model OOS'ta baseline'ı **yenmiyor**.

## K. LONG/SHORT, regime, timeframe ve confound kontrolleri

**≥76 confound decomposition (edge gerçek mi yoğunlaşmış mı):**
- Genel: ≥76 avgR +0.187 / stop %37.0 · <76 avgR −0.070 / stop %39.1.
- **Yön:** bullish dAvg **+0.366** (edge) · bearish dAvg **−0.04** (edge YOK). ≥76 bandı %81 bullish.
- **Regime:** trending_bull dAvg **+0.584** (çok yüksek) · diğerleri küçük. Edge trending_bull'a yığılmış.
- **Hafta:** W26 +0.492 · W27 +0.629 · W28 +0.132 · **W29 −0.118** (≥76 stop %54.7, avgR −0.274) → **en yeni haftada TERSİNE**.
- Konsantrasyon: ≥76 dağılımı bullish %81; hafta W28 %37 / W27 %25 / W29 %22.
→ **≥76 edge'i CONFOUNDED**: bullish + trending_bull + eski-hafta karışımı; en güncel dönemde ters. Genelleşmez.

**Segment sanity (filtre değil):** LONG stop %40.6 / PF 0.875 vs SHORT %36.1 / PF 1.05 (LONG daha kötü, 1.66× daha çok üretiliyor) · M15 hacmin %74'ü PF 0.919 · ranging regime en kötü (PF 0.76) · trending_bear en iyi (PF 1.134). Hepsi CP-SQF-1 forensic ile tutarlı.

## L. Leakage ve zaman-sızıntısı kontrolleri

- **Predictor whitelist** açık; runtime assert: hiçbir feature-adı leakage-substring (outcome/return/mfe/mae/gave_back/bars/hit_tp/realized/cur_/closed/…) içermiyor → geçti.
- Post-birth alanlar (actual_return, hit_tp*) yalnız **label** olarak record'da `_` önekli tutuldu; feature matrisine hiç girmedi.
- **Walk-forward zaman-ayrımı:** her fold'da train haftaları test haftasından önce (assert geçti); train n<150 fold (W26) atlandı, sahte sonuç üretilmedi.
- **Read-only:** `_assert_read_only` guard yalnız SELECT/WITH'e izin verir; her sorgu sonrası `rollback`; hiç `commit` yok; DB'ye yazma **0**.
- **Determinizm:** art arda iki koşu **byte-identical** (rastgelelik yok, IRLS zero-init, mergesort sıralama).

## M. Baseline karşılaştırması

Hiçbir shadow varyantı, anlamlı hacim koruyarak baseline PF 0.93'ü **out-of-sample güvenilir biçimde** aşmadı. conf≥76/≥78 PF>1 ama (i) hacim %10'un altında, (ii) confounded, (iii) W29'da tersine. Recalibre model OOS'ta baseline'ı yenmedi. → yayın-filtresi için **kanıtlanmış edge yok**.

## N. Net karar

**→ 4. OUT-OF-SAMPLE AYRIŞTIRICI EDGE YOK.**

Açık cevaplar:
- **confidence_score canlı yayın-barına aday mı?** — **HAYIR.** AUC 0.4954; band-farkları küçük; ≥76 confounded.
- **composite_confidence daha iyi mi?** — **HAYIR.** AUC 0.4969 (aynı); top-quartile PF 1.055 marjinal.
- **recalibrated model OOS daha iyi mi?** — **Marjinal (AUC 0.531) ama baseline'ı YENMİYOR** (keep-best-25% PF 0.998 < 1.007); kalibrasyon güvenilmez.
- **mevcut 7/10 güvenilir mi?** — **HAYIR.** `round(confidence_score/10)`; dar band; outcome-korelasyonu ~0; dekoratif.
- **≥76 sonucu confounded mı?** — **EVET.** bullish-only + trending_bull + eski-hafta; W29'da tersine.
- **Canlı davranış CP'si açılmalı mı?** — **HAYIR.** Veri birikmeye devam etsin (gözlem-modu; [[ai-master-roadmap]] ile tutarlı). Harness'i periyodik yeniden koş; **OOS AUC haftalık yükseliş trendi (0.516→0.562)** tek izlenmesi gereken pozitif işaret — F1-a reopen kapısı için ön-kayıtlı tetik olabilir.

**Sonuç:** CP-SQF-2A, "skoru düzeltirsek yayın-barı kurabiliriz" hipotezini **out-of-sample çürütür**: skor bozuk *ve* mevcut birth-feature seti out-of-sample kitap ekonomisini iyileştirecek edge taşımıyor → kısıt **skor değil, alpha**. Sıradaki değer CP-SQF-2B (coin-tier walk-forward) + veri-birikimi; canlı gate açılmaz.

---

## Ek — bağımsız doğrulama (adversarial SQL)

Script'in manşetleri, script'e güvenmeden **bağımsız read-only SQL** ile ayrı ayrı yeniden-türetildi (3 adversarial verifier). Hepsi **CONFIRM**:

| İddia | Bağımsız SQL sonucu | Verdict |
|---|---|---|
| confidence_score ayrıştırmıyor (AUC≈0.495) | İki yöntem (Mann-Whitney midrank + doğrudan konkordans): **0.49541** ve **0.49518** | CONFIRM |
| ≥76 edge'i confounded + W29'da tersine | W29 (07-13) ≥76: avgR **−0.274** / stop **%55.8** (<76: −0.156/%44.7); bullish-only (+0.366 vs bearish −0.040); trending_bull +0.516 | CONFIRM |
| Shadow bar: yalnız önemsiz-hacim PF>1 | ≥76→%9.64/PF **1.35**; ≥78→%1.29/PF **1.50**; ≥65→**%100** (min conf=65, hiçbir şey elemiyor), tam-set PF 0.93 | CONFIRM |

Nüans (verifier notu): erken haftaların *her biri* pozitif değil (kısmi ilk hafta −0.143; 07-06 −0.016) — manşet örüntüyü (edge eski-pozitif-haftalarda yoğun, güncelde ters) çürütmez. Verifier'lar canlı tabloda +1 sinyal drift'i gördü (2552 vs 2551) — ihmal edilebilir.

## Ek — çalıştırma

`cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/sqf2_score_profiling.py`
Read-only · DB'ye yazmaz · davranış değiştirmez · deterministik. Bağımsız SQL ile çapraz-doğrulama: confidence bandları + baseline stop-rate + ≥76 per-hafta dağılımı CP-SQF-1 manuel forensic sorgularıyla birebir eşleşiyor.
