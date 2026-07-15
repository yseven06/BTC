# CP-REV-0 + CP-MKT-0 — Kapanış (forensic, kod YOK, üretim değişmedi)

**Tarih:** 2026-07-15 · **Statü:** TAMAM → **CP-MKT-0 KAPANDI/UYGULANMAYACAK · CP-REV early-exit hattı KAPANDI/düşük öncelik · CP-OBS-1A telemetri KALIR (guard DEĞİL).**
**Kapsam:** salt-okuma. Mevcut DB (`signal_performances` × `signals` × `signal_snapshots`) + Binance BTC/ETH 15m klines; geçici analiz script'leri repo dışında (scratchpad), kalıcı dosya bırakılmadı. **Hiçbir production kodu/davranışı değişmedi.**

## 1. Test edilen varsayımlar
1. **(REV-0)** "Sistem aktif sinyalin tezini yeniden doğrulamıyor; `invalidating` anında çıksak zararı keseriz."
2. **(MKT-0)** "Korelasyonlu zarar cluster'ları BTC/ETH beta'sından doğuyor; doğum anında market context'i loglar (ve ileride kapılarsak) cluster'ı önleriz."

**Ortak zemin (CP-OBS-1B):** Kitabın **tüm edge'i cluster DIŞINDA** (1623 işlem, **+290.0**) ve **cluster İÇİNDE geri veriliyor** (629 işlem, **−278.3**) → net **+11.6**. Cluster = aynı yönde ≤20 dk aralıklı ≥4 stop. M15 suçlu değil: payı içeride ve dışarıda aynı (%75/%75) ve M15 cluster dışında kârlı (+141.4). Sorun **timeframe değil, cluster olayı**.

## 2. CP-REV-0 — yöntem ve sonuç
**Yöntem:** kapanmış her sinyalin bar-yürüyüşü üzerinde `compute_lifecycle_status` sinyalleri yeniden üretildi; "uyarı anında çık" karşı-olgusal getirisi ölçüldü.

**Öncül kısmen YANLIŞ çıktı:** revalidation ZATEN var (lifecycle v2 ucuz-ipuçlarıyla çalışıyor, `INVALIDATE_RETRACE_THRESHOLD=0.6`), ve **uyarı çalışıyor** — 17/17 cluster stop'unu ortalama **~185 dk önce** işaretledi (P2.5: %72 precision / %85 recall).

**Ekonomisi çalışmıyor:**
- `invalidating` anında çıkış → net **−32.7** (uyarı gerçek, ama fiyat sıklıkla geri dönüyor).
- `weakening` anında çıkış → +114.2 **ama artefakt**: kitabın **%69'unda** tetikleniyor ve **479 kazananı** kesiyor. Başabaş bir kitapta "çoğu işlemi kes" her zaman pozitif görünür; edge değil, maruziyet azaltmadır.
- Hiçbir kural bileşimi anlamlı/sağlam pozitif değil.

**Karar:** uyarı UI'da kalır (bilgi değerli), **aksiyona bağlanmaz**.

## 3. CP-MKT-0 — backfill-forensic yöntemi ve sonucu
**Yöntem:** BTC/ETH 15m klines → context feature'ları (`ret_15m/1h/4h/24h`, `dd_24h`, `atr_pct`), her sinyalin **doğum anına** nedensel `merge_asof` (yalnız kapanmış son bar). Kohort n=2264, net **+6.7** (≈ **+0.003/işlem** → kitap başabaş).

**Mekanizma KANITLANDI:** en zararlı **10 cluster'ın 9'u** BTC cluster yönüne **ters** hareket ederken başladı. Beta hipotezi doğru.

**Ama öngörü ÇALIŞMIYOR — BTC doğumdan SONRA dönüyor:**

| Doğum anında BTC yönü | n | net | win% | cluster payı |
|---|---|---|---|---|
| **Uyumlu** (`btc_aligned`) | 1565 | **+55.1** | 38.6 | **%29.9** |
| Ters | 699 | −48.4 | 37.2 | %24.0 |

Uyumlu doğanların cluster payı **daha YÜKSEK**. Yani doğum-anı BTC filtresi cluster'ı **önleyemez** — elemek istediğin olay, filtrenin "temiz" dediği tarafta doğuyor.

**En iyi görünen kural sağlam değil** — "BTC+ETH 1h ters" (+73.0, kitabın %24.9'unu eler):
- **Eşik taraması non-monoton:** 48.4 → 28.6 → 25.8 → **62.6** → 32.3 → 7.1 (gürültü imzası; gerçek edge monoton bozulur).
- **Temporal kararsız:** 1. yarı **+60.5** vs 2. yarı **+12.5** (~5×).
- **Win-rate anlamlı artmıyor:** 38.2 → 38.7.
- **Çoklu hipotez:** 16 kural tarandı, başabaş bir kitapta; +73.0 seçim yanlılığıyla açıklanabilir.

**Exposure kuralları da ödemiyor:** doğum-anı aynı-yön exposure rekonstrüksiyonu ort. **18.5**, maks **54** → yüksek tek-yönlü maruziyet **normal durum**. Tüm exposure kuralları **≤0**; `exposure≥15` tek başına **−18.7** ve kitabın **%52.5'ini** eler.

**Karar:** CP-MKT-0 **uygulanmayacak**. Market context ileride yalnız **factor/beta/model feature** bağlamında (F1) yeniden değerlendirilebilir — doğum-anı guard olarak değil.

## 4. CP-OBS-1A'nın nihai statüsü
`fb7be19` üretimde **kalır**: `extra.birth.exposure` additive telemetri, karar-yolu **byte-özdeş**, hiçbir karar geri okumuyor, fail-open. **Ama guard değildir** — bu forensic, CP-OBS-1A'nın arkasındaki exposure-guard hipotezini **zayıflattı** (§3). Telemetri yalnız **observability / forensic / gelecek-shadow zemini** olarak duruyor.

## 5. Kapanan yollar (yeniden önerilmeyecek)
Canlı early-close · invalidation-tetikli çıkış · weakening-exit · trailing çıkış · doğum-anı BTC/ETH market guard'ı · doğum-anı exposure guard'ı · CP-MKT-0 telemetri kodu · `extra.birth.market` alanı · exposure telemetrisinin bir karar tarafından geri okunması.

**Yeniden açma koşulu (hepsi birden):** yeni bir piyasa döngüsü verisi + **ön-kayıtlı** hipotez (post-hoc tarama değil) + kitabın başabaş olmaktan çıkmış olması + walk-forward/coin-LOO ile sağlamlık.

## 6. Roadmap'e etkisi
Roadmap **gövdesi değişmedi** (F0→F4 sırası, kapılar, iki yapısal borç aynen). Değişen: REV/MKT kısayolları aday listesinden düştü → **F0/F1 tek yol**. Bu, araştırma fazının tezini doğruluyor: **kısıt mimari değil, alpha**; ucuz guard'lar başabaş bir kitaptan edge üretmiyor. Cluster problemi beta'yı coin-karakterinden ayırmayı gerektiriyor → **F1 factor/beta katmanı**, onun önkoşulu **F0 temel**.

## 7. Sonraki doğru adım — **F0-1 · Outcome Recovery**
F0'ın diğer tüm kalemleri (Kappa tek-türetim, log↔model çizgisi, recency-decay, confidence-tier) **outcome etiketlerini okur**. Lokal çalışma nedeniyle makine kapalıyken etiketler bayatlıyor/geç çözülüyor — kaynak bozuksa üstüne kurulan her türetim bozukluğu miras alır. Ayrıca karar-yoluna **sıfır risk** taşır (yalnız zaten çözülmüş olması gereken sinyalleri çözer; mevcut tracker'a ince katman, yeni motor değil) ve tek F0 kalemi ki kullanıcı-görünür semptomu var (Signal Center'daki bayat ACTIVE'ler).

Sonra: F0-2 Kappa tek-türetim → F0-3 log↔model çizgisi → F0-4 recency-decay + confidence-tier → **F0 kapısı:** rebuild ≡ online byte-özdeş.

---
İlişkili: `docs/KEY2-shadow-eval.md` (aynı desen: çürütülen varsayım → deferred) · `docs/P25-lifecycle-calibration-analysis.md` (lifecycle eşikleri veriyle doğrulandı, davranış değişmedi) · `docs/TELEMETRY-TRADE-PATH.md`
