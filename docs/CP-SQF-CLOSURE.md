# CP-SQF-CLOSURE — Signal-Quality Forensic Serisi Kapanış Kararı

**Tarih:** 2026-07-18 · **Statü:** KANONİK kapanış kararı (davranış değişikliği YOK)
**Kapsam:** CP-SQF ölçüm serisini (2A/2B/2C) yeni edge-avına uzatmadan kapatmak.
**Bağlam:** Tüm seri salt-okuma/shadow; hiçbir canlı sinyal/gate/threshold/scoring/scheduler/API/frontend/DB davranışı değişmedi. [[ai-master-roadmap]] AI-CORE gözlem-modu ile tutarlı.

**Seri commit zinciri (doğrulandı):**
| CP | Konu | Script | Rapor | Commit |
|---|---|---|---|---|
| CP-SQF-1 | forensic karar + ölçüm planı | — | `docs/CP-SQF-forensic.md` | `e05c026` |
| CP-SQF-2A | quality/confidence skor-profilleme | `backend/scripts/sqf2_score_profiling.py` | `docs/CP-SQF2A-report.md` | `9614f60` |
| CP-SQF-2B | coin/symbol-tier forensic | `backend/scripts/sqf2b_coin_tier.py` | `docs/CP-SQF2B-report.md` | `8b7f1d0` |
| CP-SQF-2C | valid-entry / never-entered | `backend/scripts/cp_sqf2c_valid_entry.py` | `docs/CP-SQF2C-report.md` | `e93a189` |

---

## 1. Executive summary

CP-SQF serisi, "son dönemde stop oranı çok yüksek" gözlemini (son-250 stop %46 / PF 0.63, CP-SQF-1) üç somut kaldıraç açısından ölçtü: **skor kalitesi (2A)**, **coin kimliği (2B)**, **entry geçerliliği (2C)**. Üçü de **negatif** çıktı; her manşet en az iki bağımsız SQL yöntemiyle adversarial doğrulandı. **Sonuç: şu an hiçbir canlı davranış değişikliği yapılmaz** — yeni model/gate/blacklist/recalibration açılmaz. Ana bulgu: **mevcut skor sistemi edge üretmiyor; coin ve valid-entry hipotezleri de canlı değişiklik için yetersiz.** Kısıt mimari/gate değil, **alpha (sinyal edge'i)**. Tek gerçek açık konu **phantom-WIN ölçümü** — zarar-azaltan bir gate değil, raporlama/istatistik-doğruluğu meselesi.

## 2. CP-SQF-2A / 2B / 2C karar tablosu

| CP | Ana bulgu (doğrulanmış) | Canlı değişiklik |
|---|---|---|
| **2A skor** | confidence_score AUC(→loss) **0.4954**, composite_confidence 0.4969, probability 0.504, risk_score 0.4997 (7 benzersiz değer, %90 = 5.0) → **hiçbiri ayrıştırmıyor**. "7/10" = `round(confidence_score/10)` = **dekoratif/dar-band**. Rekalibre model pooled OOS AUC 0.531 ama "en iyi %25 tut" **PF 0.998 < baseline 1.007** → OOS iyileştirmiyor. Görünen tek edge (≥76) **confounded** (bullish+trending_bull, en yeni haftada tersine). | **YOK** (yayın-barı/recalibration açılmaz) |
| **2B coin** | In-sample dispersion güçlü (TRX %2.3 ↔ ALGO %56.5) ama **kalıcı değil** (Spearman erken↔geç stop ρ=**0.21**, PF ρ=0.37; birçok coin flip, ör. ARB %9→%52). Zaman-dürüst blacklist OOS'ta en iyi **+0.036 PF** (0.971→1.007, breakeven'ı ancak, −%18 hacim). Kısmi vol-confound (Spearman atr↔stop 0.26). DYDX yalnız **WATCH** adayı. | **YOK** (blacklist/cooldown/threshold açılmaz) |
| **2C entry** | never_entered 43 sinyalin hepsi WIN/BE → **entry-less LOSS = 0** (hipotez çürüdü). 41 **phantom-WIN** (fiyat entry-mid'e hiç ulaşmadan TP'ye kaçmış → limit dolmaz). Valid-entry filtresi kitabı **kötüleştiriyor** (PF 0.933→**0.894**, stop %38.8→39.4). **instant_invalid (SL<1.2 ATR doğumda) = 0**. | **YOK** (valid-entry gate açılmaz; ayrıca post-hoc → gate feature'ı olamaz) |

## 3. Canlı davranış değişikliği neden yapılmıyor?

1. **Skor ayrıştırmıyor (2A):** ham skorlar AUC≈0.50; rekalibrasyon OOS'ta kitap ekonomisini iyileştirmiyor (PF 0.998 < 1.007). Yayın-barı yükseltilecek güvenilir bir ayrıştırıcı yok.
2. **Coin edge'i kalıcı/sömürülebilir değil (2B):** dispersion büyük ölçüde örneklem-yanılsaması + kısmi vol-confound; OOS blacklist marjinal, tek-bölme, walk-forward-sağlam değil.
3. **Entry-fill baskın sorun değil (2C):** entry-less loss sıfır; valid-entry filtresi zarar azaltmıyor, apparent-performansı kötüleştiriyor; never_entered zaten publish-anında bilinmez.
4. **Confound-mezarlığı geniş:** bu üç negatif, önceki ölçülmüş-negatif müdahalelere (min-R/R, TP/SL floor, erken-çıkış, market-guard, exposure-guard, M15-kesme, lifecycle-eşik — bkz. `docs/CP-SQF-forensic.md` §7) ekleniyor. Kör deploy, ölçülmüş-negatif bir yolu tekrar açmak demek.
5. **Kısıt = alpha:** başabaşa yakın bir kitaptan ucuz gate/filtre edge üretmiyor; ileri yol veri-birikimi + ön-kayıtlı hipotez ([[ai-master-roadmap]] F1-a reopen).

## 4. Hangi hipotezler kapandı?

- **"Yayın-barını (skor eşiği) yükseltmek stop'u düşürür"** → KAPANDI (skor ayrıştırmıyor; rekalibrasyon OOS-nötr).
- **"Kalite skoru rekalibre edilirse edge çıkar"** → KAPANDI (pooled OOS AUC 0.531, ekonomik OOS iyileşme yok).
- **"Bazı coinler kalıcı zararlı → blacklist edge verir"** → KAPANDI (persistence zayıf; OOS marjinal; vol-confound).
- **"Entry gerçekleşmeden loss yazılıyor, valid-entry gate zararı keser"** → KAPANDI (entry-less loss = 0; filtre kitabı kötüleştiriyor).
- **"Sinyaller stop'a çok yakın doğuyor"** → KAPANDI (SL<1.2 ATR doğum = 0).

## 5. Hangi konu açık kaldı?

**Tek açık konu: phantom-WIN ölçümü (istatistik-doğruluğu).** never_entered→WIN sinyalleri (ölçülen 709'da 41, W28-29'da yoğun) varsayılan entry-mid limit'inde dolmazdı → win/PF istatistiklerini hafifçe **optimistik** şişiriyor. Bu **zarar-azaltan bir gate DEĞİL**; Reading-A (midpoint-fill) varsayımının bir etiketleme tutarsızlığı. İki opsiyon (ikisi de düşük-öncelik, davranış değil):
- **Raporlama netleştirmesi:** outcome'da `never_entered_win` ayrı işareti (telemetri zaten `extra->entry`'de var; küçük iş).
- **Tam-tarih ölçümü:** entry-telemetri kapsamı %27.7; tam ölçüm OHLC re-fetch gerektirir (`price_data` boş) → maliyetli, düşük değer, opsiyonel.

## 6. Reopen trigger kriterleri (yalnız dokümante; canlı alarm/panel YAPILMAZ)

SQF yeniden ancak **ölçülebilir bir alarm** oluşursa açılır. Aşağıdakiler kayıt altındadır; şu an canlı alarm sistemi veya frontend paneli **kurulmaz** (yalnız periyodik manuel harness-koşusu ile izlenir):

- **rolling PF < 0.8** (son-N kapalı sinyal; şu an son-250 ≈ 0.63 → zaten düşük, ama tek başına yeni davranış açmaz — aşağıdaki ek-koşullarla birlikte değerlendirilir).
- **rolling stop-rate > %40** (son-N).
- **phantom-WIN oranı anlamlı seviyeye çıkarsa** (decidable alt-kümede belirgin artış → istatistik-güveni bozulur).
- **yeni veriyle OOS AUC / PF belirgin değişirse** — özellikle 2A'nın haftalık yükselen OOS AUC trendi (0.516→0.548→0.562) eşiği geçerse (ör. pooled OOS AUC ≥ ~0.58 walk-forward-stabil) → **ön-kayıtlı** yeni hipotezle 2A rekalibrasyonu yeniden değerlendirilir.

**Reopen disiplini:** yeniden-açma = yeni piyasa döngüsü VEYA yukarıdaki alarmlardan biri + **ön-kayıtlı hipotez** (post-hoc tarama değil) + walk-forward/coin-LOO sağlamlık. Bu, [[ai-master-roadmap]] F1-a reopen kapısıyla aynı çizgidedir.

## 7. Sonraki önerilen güvenli takip başlığı

**Yeni edge-avı BAŞLATILMAZ.** Önerilen güvenli yol:
1. **Veri-birikimi + periyodik harness re-run:** üç SQF script'i read-only ve deterministik; veri büyüdükçe (haftalık) yeniden koşulup reopen-tetikleri kontrol edilir. Özellikle 2A OOS-AUC trendi izlenir.
2. **(Opsiyonel, düşük-öncelik) phantom-WIN raporlama netleştirmesi** — yalnız istenirse; davranış değil, etiketleme/istatistik doğruluğu.
3. **Canlı alarm/panel şimdi kurulmaz** (kullanıcı kararı); reopen-tetikleri yalnız bu dokümanda kayıtlıdır.

**Kapanış:** CP-SQF serisi hedefine ulaştı — "daha az ama daha doğru sinyal" için skor/coin/entry kaldıraçlarının hiçbiri şu veriyle canlı-değişikliği hak etmiyor; kısıt **alpha**, çözüm **veri-birikimi + ön-kayıtlı reopen**. Seri **KAPALI**.

---

*Tüm sayılar ilgili CP raporlarından (yukarıdaki commit'ler) alınmış ve adversarial bağımsız SQL ile doğrulanmıştır. Bu doküman salt karar kaydıdır; hiçbir kod/DB/davranış değişikliği içermez.*
