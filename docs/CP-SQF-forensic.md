# CP-SIGNAL-QUALITY-FORENSIC — Karar Dokümanı & Ölçüm-First Yol Haritası

**Tarih:** 2026-07-18 · **Statü:** KANONİK karar notu (salt-analiz; davranış değişikliği YOK)
**Kapsam:** CP-SQF-1 — forensic bulgularının kalıcılaştırılması + ölçüm-first plan.
**Veri:** canlı DB (2586 sinyal · 2549 kapalı · 1995 trade-path; 21 Haz – 18 Tem 2026).
**Bağlam:** Bu doküman bir **karar/ölçüm planıdır**; hiçbir gate/threshold/sinyal-davranışı uygulanmamıştır. Uygulama yalnız CP-SQF-3'te, shadow-pozitif + ön-kayıtlı + ayrı onayla. Roadmap AI-CORE gözlem-modu ([[ai-master-roadmap]]) ile tutarlı: bu ölçüm/shadow adımıdır, yeni davranış-CP'si değildir.

---

## 1. Kısa teşhis

- Son 250 sinyalde **stop ≈ %46**, **PF ≈ 0.63**, **medyan P/L ≈ −%0.53** → kitap son dönemde para kaybediyor (yaşam-boyu %38.9 / PF 0.93'ün belirgin altında).
- Problem **daha fazla sinyal değil; daha az ama daha doğru sinyal.**
- Kök-neden **SL/TP yönetimi değil**, yayınlanan sinyalin **edge zayıflığı**: ölçülebilir kaybedenlerin ~%69'u lehe hiç gitmeden (mfe ≈ 0.18R) stop oluyor.
- Çözüm **"daha çok gate" değil**; **ölçüm + shadow + kanıtlı yayın filtresi.** Yönetim/çıkış gate'i, edge'i olmayan bir girişi kurtaramaz — yalnız yayınlamama (filtre) çözer, o da ancak filtrenin gerçekten ayrıştırdığı **out-of-sample kanıtlanırsa**.

### Performans tablosu (referans)

| Pencere | n | Stop% | Win% | BE% | TP1% | Ort.P/L | Medyan | PF |
|---|---|---|---|---|---|---|---|---|
| Son 50 | 50 | 46.0 | 28.0 | 16.0 | 40.0 | −0.13% | −0.63% | 0.79 |
| Son 100 | 100 | 48.0 | 28.0 | 19.0 | 44.0 | −0.19% | −0.55% | 0.68 |
| Son 250 | 250 | 46.0 | 28.4 | 20.4 | 46.0 | −0.24% | −0.53% | 0.63 |
| Tüm | 2549 | 38.9 | 36.6 | 22.3 | 55.2 | −0.05% | +0.25% | 0.93 |

---

## 2. Kalıcı forensic bulguları

| # | Bulgu | Kanıt |
|---|---|---|
| 1 | **Quality/confidence skoru outcome'u ayrıştırmıyor.** | conf bandları <70 / 70–73 / 73–76 / ≥76 → stop %39 / 39 / 39 / **37**; yalnız ≥76 bandı (hacmin ~%10'u) +0.19% edge. Skor 65–81 dar bandda sıkışık. |
| 2 | **7/10 skoru dekoratif/default gibi.** | Görünen skorların çoğu 72–75 (ekranda "7/10"); `MIN_ACTIONABLE_CONFIDENCE=65` + confidence `[20,98]` clamp yayınlananları dar yüksek-banda topluyor. |
| 3 | **Risk level ayrıştırıcı değil.** | `risk_level` %96 MEDIUM (2451/2586). Crypto `base_risk=6.0` aslında HIGH'a meyilli; enum çoğunlukla MEDIUM'a düşüyor → sahte-çeşitlilik. |
| 4 | **Valid-entry / never_entered ölçümü dormant.** | Tracker outcome'u birth anından `entry=(zone_low+high)/2` varsayımıyla yürütüyor; `entry_telemetry` (`never_entered`/`entry_reached`/`bars_to_entry`) üretiliyor ama hiçbir karar/istatistik okumuyor ("read by NOTHING"). |
| 5 | **Entry almadan win/loss booking yapısal olarak mümkün** ama baskın problem değil. | Fill doğrulanmıyor; fiyat entry'ye geri çekilmeden fırlarsa yine midpoint'ten WIN yazılabiliyor. Önceki CP-2 shadow: entry ~anında geliyor (%92, medyan ~12dk) → entry-gate iptal. Baskın sorun yön edge'i, fill değil. |
| 6 | **Coin bazlı stop-rate dağılımı güçlü ama confounded olabilir.** | ≥20-sinyal coinlerde stop %2.3 (TRX) ↔ %56.5 (ALGO); majors düşük (BTC 16.2 · XRP 19.4 · ADA 24.0 · BCH 24.4 · AAVE 26.8), küçük-cap yüksek (ALGO 56.5 · LPT 55.8 · ICP 54.7 · AUDIO 53.8 · DYDX 52.9). Ama coin-alpha p=0.069 (underpowered), beta bireysel-varyansın ~%5'i → beta/regime confound riski. |
| 7 | **LONG aşırı-üretimi gözlemlenmeli, kör guard uygulanmamalı.** | LONG 1591 vs SHORT 958 (1.66×); LONG stop %40.5 / −0.087, SHORT %36.1 / +0.026. Not: doğum-anı exposure guard önceki forensicte negatif (≤0). Yalnız gözlem KPI'si. |
| 8 | **TP/SL geometrisi ana bozukluk değil.** | ATR-normalize (SL/TP1/TP2/TP3 = fiyat ± ATR×{1.5, 1.5, 3, 5}), TP-ordering guard var; Lever-1B SR-override'ın R:R'yi bozmasını çözdü (median R:R 0.41→1.0, sub-1 %82→%17). Bozukluk mesafede değil, hangi sinyalin yayınlandığında. |
| 9 | **Regime→yön hizalaması çalışıyor.** | bull'da %98 LONG, bear'da %11 LONG. Ama hizalıyken bile stop %41.5 → regime-mismatch değil, edge eksikliği. |
| 10 | **Kaybeden anatomisi = edge sorunu.** | Ölçülebilir kaybedenlerin %69'u mfe<0.5R; MAE 1.11R / MFE 0.36R. `correct_dir_tight_sl` (yön doğru/SL dar) = 150 kayıp (%18) ama KEY2 shadow floor'u ölçtü → PF kötüleşti. |

---

## 3. Standing KPI hedefleri

| KPI | Hedef | Durum |
|---|---|---|
| Valid-entered rolling stop-rate | **≤ %25** | ⚑ "valid-entered" tanımı entry-telemetri aktivasyonu gerektirir (henüz ölçülemiyor) |
| Profit factor | hedef **> 1.2**, minimum **> 1.0** | Ölçülüyor (şu an son-250 = 0.63) |
| Entry almadan loss booking | **= 0** | ⚑ `never_entered` join gerekiyor (henüz ölçülemiyor) |
| Stop'a yakın doğan sinyal | **= 0** | ⚑ "yakın" tanımı (birth fiyatı SL'e ≤X×ATR) + ölçüm gerekiyor |
| Quality-score ↔ outcome korelasyonu | **pozitif** | Şu an ≈0; rekalibrasyon hedefi |
| Coin-tier / cooldown deploy | **walk-forward pozitif olmadan YOK** | Karar kuralı |

**Not:** İlk üç KPI bugün **ölçülemiyor** — bu tam olarak CP-SQF-2'nin önce kurması gereken şeydir. Hedefler tanımlı, ama ölçüm hattı kurulmadan "geçti/kaldı" denemez.

---

## 4. Ölçüm-first yol haritası

1. **CP-SQF-1** (bu doküman) — forensic karar dokümanı / ölçüm planı.
2. **CP-SQF-2** — shadow harness: replay / walk-forward / coin-LOO / cluster-kontrolü. Salt-okur/offline; davranış değişmez.
3. **CP-SQF-3** — yalnız **tek** pozitif-çıkan kaldıraç (davranış değişikliği), ön-kayıtlı + baseline-karşılaştırmalı + ayrı onay.
4. **CP-SQF-4** — KPI panosu / rolling alarm (PF<0.9 / stop>%40) / F1-a reopen tetikleyici.

---

## 5. CP-SQF-2 shadow harness planı (kod yok — plan)

**Üç ölçüm hattı:**
- **Hat-1 · Quality/confidence outcome profiling** — birth telemetri (composite bileşenleri · engine-agreement · MTF · regime · coin-tier · planned_rr) ↔ outcome join. Soru: mevcut skor mu bozuk (rekalibrasyon işe yarar) yoksa hiçbir birth-özelliği out-of-sample ayrıştıramıyor mu (edge kısıtı)? → AUC + kalibrasyon eğrisi.
- **Hat-2 · Valid-entry / never_entered join ölçümü** — dormant `entry_telemetry` ↔ outcome. Soru: kaç WIN/LOSS dolmamış fill üzerine yazılıyor? + "stop'a yakın doğan sinyal" tanımı ve oranı.
- **Hat-3 · Coin-tier / cooldown shadow** — per-coin stop/PF + walk-forward + coin-LOO. Soru: "sürekli-kötü coin" alt-kümesi out-of-sample genelleşiyor mu yoksa beta/regime confound mu?

**Metodoloji:**
- **Veri:** `signal_trade_path` (mfe_r/mae_r/sl_dist/atr/cluster) + `signal_performances` (outcome/return) + `signal_snapshots` (birth skorları/regime/fear_greed) + `coin_memory`. Mevcut altyapı: `backend/app/trade_mgmt/` (path_reader, replay, scoring, **fidelity**, policies) + `backend/scripts/` (tm_replay_report, tm_fidelity_report, lifecycle_calibration, p11_rr_analysis).
- **Fidelity kapısı:** her replay önce `FixedCurrent ↔ gözlenen realized` eşleşmesini geçmeli (KEY2/TM-v2 disiplini); geçmeyen sinyal düşer.
- **Pencereler:** rolling son 50 / 100 / 250 / tüm dönem + haftalık kohort (bozulmanın nerede başladığını izole).
- **Walk-forward:** eşiği/filtreyi ilk N haftada fit et, sonraki haftada test et, yuvarla. Yalnız out-of-sample metrik karar verir.
- **Coin-LOO:** her coini sırayla dışarıda bırak, kalanlarda fit → dışarıdaki coinde test (coin-kimliğine ezber mi, genelleşen örüntü mü).
- **Cluster kontrolü:** her filtre "cluster-içi vs cluster-dışı" ayrı raporlanır (edge cluster-dışında yaşamalı — önceki forensic zorunluluğu).
- **Karar metrikleri:** out-of-sample **PF · stop-rate · expectancy (R) · korunan hacim%** ve Δ(filtreli − baseline).

---

## 6. İlk davranış değişikliği için karar kriteri

**İlk aday: Recalibrated quality/confidence publish bar.**
(Mevcut ham confidence üzerinde bar yükseltmek zayıf — skor zaten ayrıştırmıyor; yalnız ≥76 %10-hacim edge'i, muhtemelen confounded. Bu yüzden aday, mevcut eşik değil, **yeniden-kalibre edilmiş skor** üzerinde bar.)

**Yalnız şu şartlarla (hepsi geçmeli):**
1. Shadow testi **out-of-sample pozitif** olacak (skor outcome'u ayrıştırıyor: AUC anlamlı >0.5, kalibrasyon monotonik, walk-forward stabil).
2. Yayın-barı out-of-sample rolling **PF > 1.0 (ideal > 1.2)** sağlayacak.
3. İyileşme **coin/regime/cluster confounded olmayacak** (coin-LOO'da da geçerli).
4. Korunan hacim **"daha az ama daha doğru"** hedefiyle uyumlu (aşırı-kısma değil).
5. Ayrı **CP-SQF-3 onayı** alınacak (ön-kayıtlı + baseline-karşılaştırmalı).

**Eğer rekalibrasyon out-of-sample ayrıştıramazsa:** hiçbir skor-gate deploy edilmez; sonuç *"kısıt edge; veri biriktir"* olur (gözlem-modu / F1-a reopen ile tutarlı). Bu da geçerli ve dürüst bir çıktıdır.

---

## 7. Özellikle hemen uygulanmayacaklar (ölçülmeden deploy YOK)

Aşağıdakiler ya **önceki shadow/forensicte negatif/confounded** çıktı ya da **ölçülmeden kör uygulanmamalı.** Tekrar önerilmeden önce yeni ön-kayıtlı hipotez + walk-forward gerekir.

| Müdahale | İşaret | Gerekçe |
|---|---|---|
| **Min R/R gate** | ölçüldü → negatif/confounded | Hiçbir rr eşiği cluster-bağımsız negatif-EV taşımıyor; rr<1 kötülüğü = cluster confound (CP-P11-3R). TP1 scale-out gürültüyü kâra çeviriyor. |
| **TP/SL reshape** | reddedildi | Fabrikasyon hedef, hit-rate düşürür (P11 Lever-B). |
| **Stop genişletme (floor)** | ölçüldü → negatif | Shadow-eval: expectancy düz, PF kötüleşti 6.32→4.96 (KEY2). |
| **Erken çıkış / trailing exit** | ölçüldü → negatif/artefakt | invalidation-exit −32.7; weakening-exit +114 ama kitabın %69'unu keser (edge değil maruziyet-azaltma); hiçbir kural sağlam-pozitif (CP-REV0). |
| **Market regime hard filter** | ölçüldü → negatif | Doğum-anı BTC/market guard: mekanizma kanıtlı, öngörü çalışmıyor, temporal-kararsız (CP-MKT-0). |
| **M15 kesme** | ölçüldü → suçsuz | M15 cluster-dışında +141 kârlı; sorun timeframe değil cluster (CP-OBS-1B). |
| **Lifecycle threshold değişimi** | ölçüldü → değişiklik yok | P25 grid sweep: mevcut değerler optimal; eşik yükseltmek recall'ı çökertir. |
| **Coin blacklist** | ölçülmeden deploy YOK | Dağılım güçlü ama beta/regime confounded olabilir (p=0.069); walk-forward + coin-LOO şart. |
| **Opposite-direction invalidation** | zaten aktif | Reversal ≥72 conf eski sinyali kapatıyor; ek agresifleştirme ölçülmedi. |

---

## Ekler / bağlantılar

- İlişkili forensic mirası: KEY1c/d · KEY2 (shadow-eval) · P06 (TP/SL risk audit) · P07 (coin memory v2) · P08 (adaptive v2) · P11 (TP/SL & R:R + CLOSURE) · P25 (lifecycle calibration) · CP-REV0-MKT0-CLOSURE · TELEMETRY-TRADE-PATH.
- Backend gate durumu (2026-07-18 haritası): sert kalite kapısı YOK; tek gerçek kapı `MIN_ACTIONABLE_CONFIDENCE=65` + konsensüs/MTF HOLD-downgrade. Entry-zone / stop-proximity / min-R/R / exposure-cap / coin-blacklist kapıları YOK veya dormant. Regime + MTF karara dolaylı girer; Fear&Greed karara girmez. Opposite-direction invalidation + lifecycle-etiket AKTİF (lifecycle etiket outcome'a müdahale etmez).
- Tek cümlelik teşhis: *Sistem, ayrıştırıcı-olmayan bir 7/10 skoruyla neredeyse her şeyi yayınlıyor; son 250 sinyalde kitap PF 0.63 ile kaybediyor; kök-neden yönetim değil edge; çözüm daha çok gate değil, daha yüksek yayın-barı + ölçüm.*
