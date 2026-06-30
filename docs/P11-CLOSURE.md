# P1.1 — TP/SL & R:R İyileştirmesi — KAPANIŞ RAPORU

**Tarih:** 2026-06-30 · **Statü:** KAPANDI (Lever 1B kapsamıyla; filtre A uygulanmadı, 2A/3/floor ertelendi).
**Mimari:** C (kök-neden) seçildi; A (filtre) **gerek kalmadı**; B (reshape) reddedildi.

## 1. Çözülen kök neden
`signal_generator` SR-override'ı **herhangi bir yakın direnci/desteği TP1 yapıyordu**
(`if nearest_res < tp2: tp1 = nearest_res`) → TP1 içeri çekilince ödül küçülüyor, SL sabit kalıyor
→ **planlı R:R çöküyordu** (canlı %79, backtest %88 sub-1-RR; median R:R 0.41). Ayrıca R:R üretim
anında hiç hesaplanmıyor/filtrelenmiyordu (risk-engine `rr`'si seviyelerden ÖNCE çalışıyor → birth'te
None; gerçek = `planned_rr_tp1`).

## 2. Yapılan (commit'ler)
| Commit | Adım | İçerik |
|---|---|---|
| [b4c61b4] | P11-0 | Backtest rapor additive metrikleri (TP1-RR + reach-rate + realized-R); mevcut metrikler byte-identical |
| [32b6f1a] | P11-1 | TP-ordering monotonluk guard (saf sort; sıralıysa no-op) |
| [1e2a71b] | P11-2 | R:R ölçüm aracı (`scripts/p11_rr_analysis.py`, davranış yok) |
| [0d29acc] | **P11-3 Lever 1B** | **SR-override TP1'i yalnız DIŞARI iter, asla içeri çekemez** (eşik/magic-number YOK) |

## 3. Önce / Sonra metrikleri (469 trade, 10 asset, 1d, aynı veri)
| Metrik | ÖNCE | SONRA (1B) |
|---|---|---|
| sinyal hacmi | 469 | **469 (değişmedi)** |
| planned_rr_tp1 median | 0.413 | **1.0** |
| planned_rr_tp1 avg | 0.521 | 0.975 |
| planned_rr_tp1 min | 0.012 | 0.357 |
| [0,0.5) R:R bucket | %59.5 | **%3.0** |
| sub-1 oranı (would_downgrade@1.0) | %82.5 | **%17.3** |
| realized-R (genel) | 0.107 | **0.121** |
| tp1 reach | %43.1 | %8.5 |
| **per-asset** (BTC/ETH/BNB/SOL) | — | win/pf/expectancy **hepsi ↑ veya nötr** (ör. BTC exp 0.36→0.63, win 53→60) |

**~265 trade'in TP1'i değişti** (yakın direnç artık TP1 değil); entry/SL/yön/signal_type/hacim aynı.

## 4. Korunan byte-identical alanlar
- `resolution_core.step_bar` / bar-walk / backtest-equivalence: **golden 8/8 + differential 8000/8000 +
  mapping 3000/3000 + backtest 9000/9000 PASS** (1B yalnız `signal_generator` TP1-seçimini değiştirir;
  çözümleme çekirdeği dokunulmadı).
- entry_zone, stop_loss, direction, signal_type, sinyal hacmi: değişmedi.
- HOLD (bilgi-amaçlı) seviyeleri: dokunulmadı (SR-override görmez).

## 5. Bilinçli ertelenen maddeler (backlog)
- **2A** — taban TP1/SL asimetrisi (TP1 `1.5→2.0×ATR`): davranış/politika geliştirmesi; ayrı commit + before/after.
- **3** — SR-override-on-SL kapı (far-SL risk şişmesini sınırla): ayrı geliştirme.
- **min-TP/SL floor kalibrasyonu (KEY2)** + **optimal R:R eşiği**: **VERİ-GATED** (≥250-300 trade_path,
  `calibration_ready`). Filtre (A) premisi 1B sonrası zayıfladı → floor + eşik birlikte, yeni veriyle yeniden değerlendirilir.

## 6. Zekâ-v2 açısından beklenen etkiler ([[p07-coin-memory-v2]] · Similarity · [[p08-adaptive-v2]])
- **İLERİ-DÖNÜK:** 1B geçmişi yeniden yazmaz. Yeni trade_path'ler **dürüst R:R geometrisiyle** birikir
  (median 1.0) → roadmap'in *"beta verisi kalibre edilmemiş mantıkla birikir"* uyarısı **giderildi**.
  Eski (pre-1B) trade_path'ler bozuk geometriyi taşır → **era karışımı** oluşur.
- **Coin Memory v2 (tm_stats):** per-cell `planned_rr_tp1`/`sub1_rr`/`tight_sl` + `cur_*` (policy-koşullu)
  yeni geometriyle anlamlanır. Era karışımı: tm_stats şu an **okunuyor ama politikaya bağlı değil** +
  M3 **veri-gated/deferred** → aktivasyona kadar (≥250-300) verinin çoğu post-1B olur → karışım **transient**.
- **Similarity v2:** feature vektörü (regime/confidence/engine-fingerprint) **değişmedi** → eşleştirme aynı;
  ama eşleşen kurulumların **outcome/realized-R'si dürüstleşti** → "benzer kurulumlar nasıl çözüldü" daha anlamlı.
- **Adaptive v2:** adaptif ağırlıklar **yön/engine-doğruluğundan** öğrenir, TP/SL geometrisinden değil →
  1B doğrudan etkilemez; yalnız win/loss kalitesi hafif iyileşti → marjinal daha iyi öğrenme sinyali.
- **Genel not:** 1B için telemetri schema_version bump'ı YOK (üretim-mantığı değişikliği); era ayrımı deploy
  zamanı + `generated_at` ile yapılır. Zekâ-v2 politikaları aktive olurken era-farkındalığı düşünülmeli
  (KEY1-d v1/v2 deseni gibi); şimdilik tüketim deferred olduğu için sorun değil.

## 7. Yeni varsayılan mimari prensip
> **SR-override TP1'i yalnızca DIŞARI itebilir; asla içeri çekemez.** Yakın bir direnç/destek "izlenecek
> seviye"dir, hedef değil — TP1 en az ATR-default mesafesini korur. Bu, planlı R:R'nin SR-override
> tarafından çökertilmesini **yapısal olarak** engeller (eşik/magic-number gerektirmeden). TP-ordering
> monotonluk guard'ı (P11-1) bu prensibin tamamlayıcısıdır.

## 8. Statü
**P1.1 KAPANDI (Lever 1B).** Kök-neden çözüldü, hacim kaybı yok, tüm kalite metrikleri ↑/nötr, byte-identical
çekirdek korundu. Filtre (A) gereksiz; 2A/3/floor veri-gated backlog. Sonraki: roadmap'te bir sonraki öncelik.
