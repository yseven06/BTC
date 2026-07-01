# KEY2 Shadow Evaluation — min TP/SL floor "ne olurdu?" (kod YOK, üretim değişmedi)

**Tarih:** 2026-07-02 · **Statü:** TAMAM → **KEY2 DEFERRED / YENİDEN DEĞERLENDİRİLECEK.**
**Kapsam:** salt-okunur. Etkilenen (sıkı-SL) trade_path'ler, üretimin AYNI `resolution_core.resolve_trade_path`'ı
ile floored seviyelerle **yeniden çözümlendi**. Hiçbir production kodu/davranışı değişmedi.

## 0. Test edilen varsayım
> **Dar (gürültü-bandı) TP/SL seviyeleri sistematik olarak zararlıdır** (erken stop / sahte TP / whipsaw).
Çözüm önerisi: hibrit floor `max(k×ATR, min_pct×fiyat)` — seviyeleri minimum bir mesafeye genişlet.

## 1. Yöntem + güvence (fidelity gate)
- Etkilenen küme = `|entry−SL|/entry < floor`. Her biri için tarihsel bar'lar çekildi, `resolve_trade_path`
  ile (a) OLD seviyelerle [fidelity kontrolü] (b) FLOORED seviyelerle yeniden çözüldü.
- **Fidelity:** OLD yeniden-çözüm saklı sonucu üretiyor mu → %0.5 floor'da **28/32 (%88)**, %0.3'te 9/12 (%75).
  Yalnız fidelity-geçen kayıtlar raporlandı → floored sayılar güvenilir.

## 2. Sonuç — floor beklenen faydayı ÜRETMEDİ
**Floor = %0.5 (28 işlem):**
| Metrik | OLD | FLOORED | Δ |
|---|---|---|---|
| stop-rate | 86% | 75% | −11pp |
| TP1-reach | 79% | 71% | −8pp |
| win-rate | 79% | 71% | −8pp |
| **expectancy** | **0.483%** | **0.495%** | **+0.012pp (≈düz)** |
| **profit-factor** | **6.32** | **4.96** | **−1.36 (kötüleşti)** |

**Floor = %0.3 (extreme tail, 9 işlem):** stop 100→100% · TP1 100→100% · expectancy 1.312→1.318% → **SIFIR etki.**

**Rejim (%0.5):** bull 100→100% (exp 1.60→1.58, düz) · **bear 71→57% (exp 0.15→0.20 ✅)** · **ranging 67→33% (0.40→0.45 ✅, n=3)** · low-vol 92→85% (0.25→0.25, düz).

## 3. Neden — dürüst yorum
1. Floor bir **takas**: daha az stop ↔ stop olunca **daha büyük kayıp** (geniş SL) + **daha az gürültü-kazancı**. Net expectancy ~sıfır, PF düşer.
2. Sıkı-seviyeli işlemler aslında **net-pozitif** — **TP1 scale-out** gürültü-hareketini kâra çeviriyor. "Dar = zararlı" premise'i **zayıf**.
3. Extreme tail (%0.3) floor'a **duyarsız**.
4. Fayda yalnız **bear + ranging**'de → blanket floor gereksiz; olsa olsa **rejim-koşullu** — ama o da veri-ince.

## 4. Karar & bulgular (kullanıcı onayı, 2026-07-02)
- ✅ **Varsayım mevcut veriyle doğrulanmadı.**
- ✅ **Kod değişikliği YAPILMADI.**
- ✅ **Production davranışı DEĞİŞMEDİ.**
- 🔁 **KEY2 production listesinden çıkarılmadı** → **DEFERRED / yeniden değerlendirilecek.**
- 🔮 **Yeniden değerlendirme koşulu:** daha fazla veri — özellikle **v2 trade_path** (P1.1 sonrası geometri) +
  **bear/ranging** yoğunluğu artınca (shadow'un tek fayda gösterdiği rejimler). Örneklem şu an küçük (28/9), v1/v2 karışık.

## 5. Metodoloji notu (gelecek için)
Shadow eval altyapısı (fidelity-gated re-resolution) **tekrar kullanılabilir**: veri büyüyünce aynı script
rejim-koşullu floor'u yeniden ölçer. Bu, "veriyle doğrulamadan üretime dokunma" disiplininin (BP2) somut aracıdır.
