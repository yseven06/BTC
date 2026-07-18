# CP-SQF-2C — Valid-entry / Never-entered Outcome Forensic (shadow, read-only)

**Tarih:** 2026-07-18 · **Statü:** shadow/offline karar-desteği (davranış değişikliği YOK)
**Script:** `backend/scripts/cp_sqf2c_valid_entry.py` (read-only; DB'ye yazmaz; deterministik)
**Veri:** canlı DB · kapalı sinyaller · 2559 sinyal

---

## Executive conclusion

Korkulan "entry gerçekleşmeden loss yazılıyor" hipotezi **kesin ÇÜRÜDÜ.** Entry-telemetrisi olan alt-kümede (709 sinyal, %27.7 kapsam) `never_entered=true` olan **43 sinyalin 41'i WIN, 2'si BREAKEVEN — SIFIRI LOSS.** Yani entry-less LOSS booking = **0**. Bulunan gerçek olgu bunun **TERSİ**: fiyat entry-mid'e (limit fill referansı) hiç geri çekilmeden TP'ye kaçtığı için **41 phantom-WIN** var — bunlar bir limit-emirle dolmazdı, dolayısıyla non-tradeable ve istatistikleri **hafifçe ŞİŞİRİYOR** (optimistik bias). Sonuç: valid-entry filtresi performansı **iyileştirmez, kötüleştirir** (43 WIN'i eler, 0 LOSS eler → PF 0.933→0.894, stop %38.8→39.4). Ayrıca hiçbir sinyal stop'a anormal yakın doğmuyor (SL<1 ATR = **0**).

**KARAR: Valid-entry shadow gate ÖNERİLMİYOR; canlı davranış değişikliği YOK.** Entry-fill baskın bir sorun değil; tek gerçek gözlem 41 phantom-win'in optimistik-bias'ı (bir etiketleme netleştirmesi, zarar-gate'i değil). Bu, SQF ölçüm serisinin (2A skor + 2B coin + 2C entry) üçüncü ve son negatifidir → **kısıt = alpha** teyit edilir.

---

## A. Kapsam / sınıflandırma

| Sınıf | n | pay |
|---|---|---|
| valid_entered (fiyat entry-mid'e ulaştı) | 666 | %26.0 |
| never_entered (hiç ulaşmadı) | 43 | %1.7 |
| ambiguous_entry (telemetri yok / post-birth bar yok) | 1850 | %72.3 |
| **entry-DECIDABLE alt-küme** | **709** | **%27.7** |

**Kapsam uyarısı:** entry-telemetri (`signal_trade_path.extra->entry`) ileriye-dönük ve kısmi (%27.7); tam-tarih backfill OHLC re-fetch gerektirir (`price_data` tablosu boş) → **kapsam-dışı**. never_entered oranı yalnız decidable alt-kümede ölçüldü.

## B. Never-entered × outcome (KRUX)

| Sınıf | outcome dağılımı |
|---|---|
| valid_entered | LOSS 295 · WIN 192 · BREAKEVEN 179 |
| never_entered | **WIN 41 · BREAKEVEN 2 · LOSS 0** |

→ **Entry-less LOSS booked = 0** · entry-less WIN (phantom) = 41. (Reading A: SL, entry-mid'in ÖTESİNDE; stop olan bir pullback yapısal olarak önce entry'yi geçer → never_entered ancak fiyatın kaçıp WIN yazdığı durumdur.)

## C. Sınıf-bazlı performans

| Sınıf | n | stop% | win% | tp1% | avgR | PF |
|---|---|---|---|---|---|---|
| valid_entered | 666 | **44.3** | 28.8 | 49.5 | −0.167 | **0.705** |
| never_entered | 43 | **0.0** | 95.3 | 100.0 | +1.511 | — (loss yok) |
| ambiguous_entry | 1850 | 37.7 | 38.2 | 56.3 | −0.034 | 0.95 |

→ valid_entered kitabın en kötü dilimi (stop %44.3, PF 0.705); never_entered ise phantom (stop %0). Skor per-sınıf de ayrışmıyor (conf ~72 hepsinde).

## D. Valid-entry filtresi shadow etkisi (KARAR verici)

| Senaryo | n | stop% | PF | not |
|---|---|---|---|---|
| baseline (tüm kapalı) | 2559 | 38.8 | **0.933** | — |
| never_entered'ı çıkar | 2516 | 39.4 | **0.894** | 43 phantom-win silinir → PF DÜŞER |
| valid_entered ONLY (decidable) | 666 | 44.3 | 0.705 | — |
| decidable-subset baseline | 709 | 41.6 | 0.877 | valid-only bundan da kötü |

→ Valid-entry'e filtrelemek stop-rate'i **artırır**, PF'i **düşürür**. Filtre WIN'leri eliyor, LOSS'ları değil. **Fayda YOK.** (Ayrıca never_entered post-hoc'tur — publish anında bilinmez → canlı gate feature'ı olamaz zaten.)

## E. Phantom-win detayı (entry-less TP)

- 41 sinyal, ort. getiri **+1.566**; 31 farklı sembole yayılmış (BTC 3, ETH 3 dahil).
- **max_zone_penetration ort 0.066 / max 0.479** → fiyat entry-mid'e (0.5 fill-ref) **hiç ulaşmadı**, zon'un yalnız piyasa-kenarına dokunup kaçtı → limit-emir **dolmazdı**.
- Hafta: W28=14, W29=27 (telemetri yalnız bu haftalarda dolu → kapsam artefaktı; eski haftalarda ölçülemiyor).
- → Bu WIN'ler varsayılan entry'de **trade-edilemez**; win/PF'i şişiriyor (optimistik bias, zarar sorunu değil).

## F. Doğum anı stop-yakınlığı

| sl_in_atr bandı | n | stop% |
|---|---|---|
| <0.8 · 0.8-1.0 · 1.0-1.2 | **0** | — |
| 1.2-1.6 | 443 | 40.6 |
| ≥1.6 | 1376 | 40.8 |

→ **instant_invalid (SL<1 ATR) = 0 (%0).** Hiçbir sinyal stop'a anormal yakın doğmuyor (min ~1.2 ATR). SL-mesafesi stop-rate'i öngörmüyor (40.6% vs 40.8%).

## Net verdict (7 soru)

1. **Never-entered problemi var mı?** — Var ama KÜÇÜK (%1.7 tümünde / %5.8 decidable'da) ve **korkulanın TERSİ** (hepsi WIN/BE).
2. **Kaç sinyal trade-edilebilir değil?** — Decidable 709'da **43** (%5.8); entry-mid limit'e göre dolmazdı. Tam-tarih için kapsam %27.7 → backfill gerekir (OHLC yok).
3. **Entry gerçekleşmeden loss yazılan var mı?** — **SIFIR (0).** Hipotez kesin çürüdü.
4. **Valid-entered daha mı iyi?** — **HAYIR, DAHA KÖTÜ** (stop %44.3, PF 0.705 vs kitap %38.8/0.933). never_entered'lar phantom-WIN olduğu için "iyi" görünüyor.
5. **Valid-entry shadow gate öneriliyor mu?** — **HAYIR.** Filtre WIN eler (43, 0 loss) → stop ARTAR, PF DÜŞER; ayrıca post-hoc olduğundan canlı gate feature'ı olamaz.
6. **Canlı davranış değişikliği?** — **HAYIR.** Tek gerçek olgu 41 phantom-win optimistik-bias'ı — bir **etiketleme netleştirmesi** (Reading A midpoint-fill varsayımının tutarsızlığı; telemetri zaten var, istenirse outcome'da ayrı `never_entered_win` etiketi = küçük raporlama işi), zarar-azaltan gate değil.
7. **CP-SQF-2D için sıradaki başlık:** SQF üç somut açıyı da negatif kapattı (2A skor · 2B coin · 2C entry) → **kısıt=alpha teyit.** Öneri: **2D forensic AÇMA; SQF serisini KAPAT** → `CP-SQF-CLOSURE` (seri-verdict + KPI panosu / rolling-alarm PF<0.9 & stop>%40 + F1-a reopen ön-kayıtlı tetik = orijinal CP-SQF-4). Tek kalan gerçek forensic açığı phantom-win'in tam-tarih ölçümü (entry backfill) ama düşük değer + OHLC re-fetch maliyeti → opsiyonel.

---

## Ek — bağımsız doğrulama (adversarial SQL, ≥2 yöntem)

Script'e güvenmeden her manşet ≥2 bağımsız SQL yöntemiyle yeniden-türetildi (3 verifier agent). Hepsi **CONFIRM**:

| İddia | Yöntem 1 | Yöntem 2 | Verdict |
|---|---|---|---|
| entry-less LOSS = 0 | never_entered=true çapraz-tablo: WIN=**41**, BE=**2**, LOSS=**0** (n=43) | FILTER sayımı: ne_loss=**0**, ne_win_be=43; + 3. geçiş (LEFT JOIN, dup-check) 0 orphan/dup | **CONFIRM** |
| valid-entry filtresi kitabı kötüleştiriyor | tüm-kitap PF **0.9335→0.8940**, stop **%38.77→39.43** (her iki kitapta 992 loss) | elenen 43'ün hepsi pozitif-getiri, 0-loss → mekanik olarak PF'i düşürür | **CONFIRM** |
| doğumda stop-yakınlığı yok (SL<1.2 ATR = 0) | 1819 hesaplanabilir, count(<1.2)=**0**, count(<1.0)=**0**, min=**1.3669** | band stop-rate: 1.2-1.6 = **%40.63** vs ≥1.6 = **%40.84** (0.21pp, öngörücü değil) | **CONFIRM** |

Kapsam notu (verifier): 740 kapalı sinyal birth-snapshot'suz (sl_in_atr hesaplanamaz); iddia birth-verisi olan popülasyona kapsamlı — o popülasyonda birebir tutuyor.

## Ek — çalıştırma

`cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/cp_sqf2c_valid_entry.py`
Read-only · DB'ye yazmaz · davranış değiştirmez · deterministik. Leakage-güvenli: entry-sınıflandırması outcome/return kullanmaz (segment tanımı, predictor değil); stop-proximity yalnız birth-geometri.
