# P2.5 — Lifecycle Kalibrasyonu: Analiz & Tasarım Raporu

> ## ✅ KAPANIŞ (2026-06-30) — L1 sonucu: MEVCUT EŞİKLER VERİYLE DOĞRULANDI, DAVRANIŞ DEĞİŞİKLİĞİ YOK
> L1 Calibration Harness (`backend/scripts/lifecycle_calibration.py`, salt-okur Tier-1) tam grid sweep +
> per-regime çalıştırıldı (569 resolved sinyal). **Sonuç — hiçbir lifecycle karar katmanı davranışı değişmez:**
> - **ENTER_INVALIDATE 0.60 → DEĞİŞMEZ.** J mevcut eşikte tepe (+0.637); yükseltmek recall'ı çökertir (0.81→0.56). confirmed-cluster 0.45 doğrulandı.
> - **ENTER_APPROACH 0.60 → DEĞİŞMEZ.** precision her eşikte düz ~0.49; eşik fayda vermiyor → **yapısal** (tasarım backlog, kalibrasyon değil).
> - **ENTER_WEAKEN 0.30 → DEĞİŞMEZ (şimdilik).** Otomatik kural 0.45'i işaretledi (J +0.073) AMA aksiyon-dışı: weakening **alarm üretmez (yalnız UI)** + sweep 3-tetikli OR-kuralının yalnız retrace-proxy'si + 0.45 confirmed-invalidate bandıyla çakışır → Tier-2 olmadan değiştirilmez.
> - **Regime-conditioning → UYGULANMAZ.** Hiçbir rejimin optimumu global 0.60'tan sapmadı.
> - **Lead-time:** invalidating 1.0h / approaching 1.5h medyan (makul). **Lead-time gözlemsel; karar katmanı değişmedi.**
> - **Flip-flop %39.4 (gözlenen):** ayrı **Tier-2 UX/telemetri backlog** (exit/hysteresis/min-duration churn) — TP/SL, resolution ve AI karar mekanizmasından **bağımsız** değerlendirilir; bu fazda DEĞİL.
>
> **Kapsam teyidi:** L1 salt-okur; üretim kodu (resolution / signal-gen / TP-SL / lifecycle karar) **değişmedi** →
> byte-identical/equivalence gate'i gereksiz (davranış değişimi yok). P2.5 bu kapsamla **TAMAMLANDI.**

**Tarih:** 2026-06-30 · **Statü:** KAPANDI (kalibrasyon teyit-edici, davranış değişikliği yok) · **Baseline:** `beta-ready-baseline` (afdb685)
**Kapsam kuralı:** Lifecycle yalnızca **gözlemsel/uyarı katmanı**dır. Kalibrasyon, **işlem-çözüm (TP/SL
resolution) ve sinyal-üretim katmanına DOKUNMAZ** → bu byte-identical kalmalı (kanıtlanacak). Eşik
değişimi = davranış değişimi → [[baseline-development-discipline]] before/after zorunlu.

---

## 0. Veri yeterliliği (bu faz neden data-ready)
history⋈performance birleşen sinyal: **600** · resolved kohort: ~562. Her durum için ENTER kalibrasyonuna
yeterli örnek: invalidating **240**, approaching_tp **379**, weakening **395**. history satırları
**P/R + momentum_dir + structure_event + regime + outcome**'u sakladığı için **ENTER eşik taraması salt
telemetriden** yapılabilir (tracker re-run yok). (Per-regime ince dilimde kuyruklar inceleşir → koarse kalibrasyon.)

## 1. Transition → outcome korelasyonları (mevcut eşiklerde, gerçek veri)
| Kohort (EVER reached) | n | win | breakeven | loss | Baseline'a karşı |
|---|---|---|---|---|---|
| **invalidating** | 240 | 16.2% | 11.7% | **72.1%** | loss **2.05×** (35.2%→72.1%) |
| **approaching_tp** | 379 | **49.9%** | 36.7% | 13.2% | win 1.44× (34.7%→49.9%) |
| **weakening** | 395 | 27.1% | 24.6% | 47.8% | loss 1.36× |
| **never-danger** (drama yok) | 180 | **52.2%** | 43.3% | **3.3%** | loss 0.09× (neredeyse hiç kayıp) |
| BASELINE (resolved+history) | 562 | 34.7% | 29.7% | 35.2% | — |

**Recall (kayıt yakalama):** invalidating tek başına ~**173/203 ≈ %85** kaybı yakalıyor; weakening+invalidating
neredeyse TÜM kayıpları kapsıyor (never-danger'da yalnız ~6 kayıp). → Durumlar gerçekten ayırt edici.

## 2. invalidating → gerçek loss oranı + derinlik duyarlılığı
**%72.1 loss/invalidated** (precision yüksek, recall ~%85). Derinlik kovasına göre **DÜZ**:
| retrace_to_sl | n | loss% | win% |
|---|---|---|---|
| 0.45–0.60 (yalnız confirmed-cluster) | 19 | **73.7%** | 26.3% |
| 0.60–0.75 | 174 | 70.7% | 17.2% |
| 0.75–0.90 | 38 | 73.7% | 7.9% |
| 0.90–1.05 | 9 | 88.9% | 11.1% |

→ **Bulgu:** confirmed-cluster (0.45–0.60 + yapı + momentum) = saf derin-retrace ile **AYNI precision (~%74)**.
v2 confirmed-cluster tasarımı **veriyle doğrulanıyor.** ENTER_INVALIDATE=0.60 + confirmed=0.45 **iyi kalibre.**
Saf-fiyat eşiğini 0.60 altına indirmek (confirmation'sız) bu veride desteklenmiyor. → **Kalibrasyon teyit-edici.**

## 3. approaching_tp → gerçek TP oranı (en zayıf uyarı)
**%49.9 win** — ama **never-danger %52.2 win**'den DAHA İYİ DEĞİL. progress kovasına göre monoton değil:
| progress_to_tp | n | win% | be% | loss% |
|---|---|---|---|---|
| 0.60–0.70 | 167 | 50.3% | 32.3% | 16.8% |
| 0.70–0.80 | 81 | **55.6%** | 33.3% | 11.1% |
| 0.80–0.90 | 43 | 44.2% | 46.5% | 9.3% |
| 0.90–1.00 | 19 | 63.2% | 21.1% | 15.8% |
| ≥1.00 | 69 | 42.0% | **49.3%** | 8.7% |

→ **Bulgu:** "TP'ye yaklaşma" win'i baseline'dan iyi tahmin ETMİYOR; yüksek **breakeven** (32–49%) **yapısal**
(SL'in breakeven'e çekilmesi + fiyatın geri gelmesi), eşik sorunu değil. ENTER_APPROACH 0.60→0.70 win'i
marjinal iyileştirir (50→56) ama lead-time/alert-hacmi kaybettirir ve ≥0.80'de tekrar düşer. → **Eşik tek
başına sınırlı fayda;** asıl iyileştirme tanım değişikliği (momentum-ile + henüz-geri-çekilmemiş) olur — bu
*kalibrasyon değil tasarım* (kapsam dışı, backlog).

## 4. weakening → sonraki outcome dağılımı
EVER-weakening: loss 47.8% / win 27.1% / be 24.6%. **weakening-ONLY (invalidating'e yükselmeyen, n=165):**
**win 42.4% · breakeven 41.8% · loss yalnız 14.5%.** → weakening'in tek başı **yüksek yanlış-alarm** (%85'i
kaybetmiyor; toparlıyor). **Ama:** P1.2 bildirim tetikleyicileri = yalnız `("approaching_tp","invalidating")`
— **weakening ALARM ÜRETMEZ** (yalnız UI). → weakening kalibrasyonu **kozmetik/düşük-öncelik** (churn azaltma),
bildirim kalitesini etkilemez.

## 5. Optimum eşiklerin nasıl hesaplanacağı (objective functions)
Her durum farklı amaç fonksiyonu ister:
- **INVALIDATING** (tehlike/çıkış uyarısı): precision tabanı (örn. ≥%65) altında **loss-recall maksimize**;
  veya Youden J = sensitivity+specificity−1. Mevcut (precision %72 + recall %85) **near-optimal** → grid ENTER∈{0.55,0.60,0.65}, confirmed∈{0.40,0.45,0.50} taranır, teyit beklenir.
- **APPROACHING_TP** (fırsat uyarısı): **P(win|approaching) maksimize**, win-coverage tabanı altında; lead-time
  cezası. Grid ENTER∈{0.60,0.65,0.70}. Beklenti: marjinal; yapısal breakeven nedeniyle büyük kazanım yok.
- **WEAKENING** (yumuşak ön-uyarı, alarmsız): yanlış-alarm tavanı altında **tehlikeye-lead-time**; veya churn
  (flip-flop) minimizasyonu. Grid ENTER_WEAKEN∈{0.30,0.40} + persist∈{1,2}.
- **Exit/hysteresis** (0.50/0.45/0.20) + **min_state_seconds**: amaç **flip-flop oranı** (zaten
  `flipflop_prevented_count` telemetrisi var) — re-simülasyonla ölçülür.

**Optimal seçim kuralı:** her grid noktası için (precision, recall, alert_volume, flipflop) hesapla; durum-bazlı
amaç fonksiyonunda **baseline'ı domine eden** nokta yoksa → **mevcut eşiği KORU** (değişiklik için kanıt eşiği:
precision/recall'da anlamlı + alert-hacmini kötüleştirmeyen iyileşme).

## 6. Hangi eşikler veriyle kalibre edilecek
| Eşik | Mevcut | Kalibrasyon yöntemi | Beklenti (veriye göre) |
|---|---|---|---|
| ENTER_INVALIDATE | 0.60 | Tier-1 retrospektif sweep | **Teyit** (düz precision) |
| ENTER_INVALIDATE_CONFIRMED | 0.45 | Tier-1 (confirmed kohort) | **Teyit** (~%74) |
| ENTER_APPROACH | 0.60 | Tier-1 (progress kovaları) | Marjinal; opsiyonel 0.65 |
| ENTER_WEAKEN + persist | 0.30 / 2 | Tier-1 + Tier-2 churn | Yanlış-alarm↓ (kozmetik) |
| EXIT_* (hysteresis) | .50/.45/.20 | **Tier-2 re-sim** (flip-flop) | Veri: per-bar replay gerekir |
| min_state_seconds | 300/tf-scaled | Tier-2 re-sim | Churn vs gecikme |
| (regime-conditioning) | yok | Tier-1 per-regime | **Aday** — n yeterliyse rejime özel eşik |

## 7. Telemetri & backtest doğrulama planı (iki katman)
- **Tier-1 — Retrospektif sweep (salt telemetri, kod yok, ŞİMDİ mümkün):** mevcut `signal_status_history`
  (P/R+momentum+structure+regime+outcome) üzerinden ENTER eşik grid'i → her durum için precision/recall/lift
  + per-regime kırılım. Bu rapor Tier-1'in ilk turu. **Yeni telemetri GEREKMİYOR** (history zaten yeterli).
- **Tier-2 — Backtest re-simülasyon (flip-flop/volume için):** lifecycle sınıflandırıcısını aday eşiklerle
  tarihsel OHLCV üzerinde **tek-kaynak `resolution_core.step_bar`** ile yeniden oynat → her-bar state dizisi,
  alert hacmi, flip-flop oranı, hysteresis etkisi. (ENTER eşikleri Tier-1'den; Tier-2 exit/min-duration'ı doğrular.)
- **Backtest-gate (BP2):** aday eşik seti, equivalence paketinde **işlem-çözümü/sonuçları DEĞİŞTİRMEMELİ**
  (lifecycle salt-gözlem) → golden/differential/mapping/backtest-equivalence **byte-identical PASS** zorunlu.
  Yalnız lifecycle state/alert metrikleri değişebilir (amaçlanan).

## 8. Before/after doğrulama metodolojisi
**İki ayrı doğrulama ekseni — karıştırma:**
1. **DEĞİŞMESİ beklenen (lifecycle/alert katmanı):** aynı tarihsel sinyal kümesinde **before vs after**:
   her durum precision/recall, alert hacmi (approaching+invalidating sayısı), flip-flop oranı, ortalama
   lead-time. Kabul: bildirim durumlarında (approaching/invalidating) **precision↑ veya recall↑ ve alert-hacmi
   kötüleşmesin**; weakening churn↓.
2. **DEĞİŞMEMESİ zorunlu (resolution/decision katmanı):** TP/SL resolution, trade outcome, sinyal üretimi
   **byte-identical** → equivalence paketi (golden 8 / diff 8000 / mapping 3000 / backtest 9000) PASS.
   *Bu, lifecycle eşiğinin yanlışlıkla karar katmanına sızmadığının kanıtıdır.*
- **Stash before/after tekniği:** eşik değişimi öncesi/sonrası aynı script ile metrikler; fark tablosu rapora.
- **Beklenmeyen fark** (resolution byte-identical değilse VEYA lifecycle metriği regresyon) → **oto-fix YOK**;
  neden+kapsam+etki raporu, birlikte karar ([[baseline-development-discipline]]).

---

## 9. Önerilen uygulama sırası (onay sonrası; her biri küçük, izole, doğrulanır)
1. **L1 — Kalibrasyon harness'i (analiz aracı, davranış değişmez):** Tier-1 grid sweep + per-regime'i
   tekrarlanabilir script (`scripts/lifecycle_calibration.py`) — eşik ÖNERİR, üretime DOKUNMAZ. Çıktı: optimal
   grid tablosu + öneri. (Salt-okur; byte-identical N/A.)
2. **L2 — (varsa) eşik güncellemesi:** L1 anlamlı+domine-eden nokta bulursa, **tek davranış değişikliği** olarak
   `lifecycle.py` sabitleri; before/after (§8) + equivalence byte-identical. Bulgu "teyit" ise **değişiklik YOK,
   teyit raporu**.
3. **L3 — (aday) regime-conditioning:** per-regime n yeterliyse rejime özel eşik; ayrı onay döngüsü.

> **Dürüst ön-sonuç:** Veri, durumların **zaten iyi kalibre** olduğunu gösteriyor (invalidating %72 precision /
> %85 recall, confirmed-cluster doğrulandı). En olası sonuç **küçük/teyit-edici** bir kalibrasyon + opsiyonel
> regime-conditioning adayı — büyük bir re-threshold değil. Asıl zayıf nokta (approaching'in win-gücü) **yapısal**
> ve kalibrasyon değil tasarım işidir (backlog). Karar, L1 tam sweep çıktısıyla birlikte verilecek.
