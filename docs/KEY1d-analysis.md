# KEY1-d (D4) Analiz Raporu — Canlı-SL kısayolunu scale-out'a saygılı hale getirme

**Statü:** ANALİZ — uygulanmadı. Onay bekleniyor. Bu faz **CANLI resolution davranışını**
değiştirir (ileri-dönük). Onay vermeden implementasyona geçilmeyecek.

## 0. Hata (BUG-6/7/8) — kanıt
Tracker'ın **Pass-1 canlı-SL kısayolu** (`tracker.py` L292-337) mum kapanışını beklemeden
anlık SL kırılmasını yakalar. Ama:
- `sl = signal.stop_loss` (**ORİJİNAL stop**) + **tam notional** (remaining=1.0) kullanır,
- `perf.hit_tp1/hit_tp2/hit_tp3`'ü **hiç kontrol etmez** — oysa bar-walk bunları **aktif
  trade'lerde kalıcılaştırıyor** (`tracker.py` L592 "partial target hits").

Sonuç: TP1'i almış (50% kârı bankalamış, stop'u breakeven'a çekmiş) bir sinyal, sonra anlık
fiyat orijinal stop'a değerse → **tam-boyut, orijinal-stop kaybı** olarak kaydedilir; TP1 kârı
ve breakeven-stop mantığı **silinir**. `_write_trade_path_live_sl_failopen` ise `reached_tp1=
perf.hit_tp1` (True olabilir) kopyalar ama `realized_return=tam-kayıp` + `gave_back=None` yazar
→ **çelişkili öğrenme satırı**.

## 1. Mevcut davranış ↔ Yeni davranış

| Durum (canlı-SL anında) | MEVCUT | KEY1-d sonrası |
|---|---|---|
| TP1 **alınmamış**, fiyat orijinal stop'u kırar | Tam-boyut orijinal-stop kaybı | **AYNI (byte-identical)** |
| TP1 **alınmış** (BE stop), fiyat ≤ BE'ye düşer | Tam-boyut **orijinal-stop** kaybı (yanlış) | Bankalanan TP1 (0.5·ret_tp1) + kalan 50% **BE'de** (≈0) → küçük kâr/breakeven |
| TP1+TP2 alınmış, fiyat ≤ BE | Tam-boyut orijinal-stop kaybı (yanlış) | 0.5·ret_tp1 + 0.3·ret_tp2 + kalan 20% BE'de |

## 2. TP1/TP2/TP3 scale-out sonrası canlı stop mantığı değişimi
- **Tespit (`_check_live_sl_hit`):** Etkin stop = `entry (BE)` **eğer perf.hit_tp1** ise, değilse
  `signal.stop_loss`. (Şu an her zaman orijinal stop kontrol edilir.) Böylece TP1-bankalı bir
  trade'in BE-kırılması da anlık yakalanır.
- **Muhasebe (Pass-1 çözüm):** `realized = bankalanan TP portları + kalan×(etkin-stop getirisi)`.
  TP1 alınmışsa etkin stop = BE (entry) → kalan ≈0. TP3 zaten tam-kapanış (aktif değil → canlı-SL
  tetiklenmez). Scale-out portları step_bar ile **AYNI** (50/30/kalan) — tek-kaynak korunur.
- **Tek-kaynak notu:** Canlı-SL tek-nokta bir çözümdür (bar-walk değil). Scale-out port/getiri
  tanımı `resolution_core` ile hizalı kalacak (gerekirse küçük ortak yardımcı; portlar 0.50/
  0.30/kalan + BE — step_bar ile aynı).

## 3. Etkilenen senaryolar
- **YALNIZCA** "TP1 (veya TP1+TP2) alınmış + canlı-SL kısayolu BE/orijinal-stop'u yakaladı" alt
  kümesi. (TP1 alınmamış canlı-SL → değişmez; bar-walk Pass-2 zaten BE'yi doğru işliyor → değişmez.)
- Bu, canlı-SL çözümlerinin küçük bir alt kümesidir (yalnız mid-candle hızlı düşüşte TP1-bankalı).

## 4. Geçmiş veriye etki
- **YOK (ileri-dönük).** Mevcut `signal_performance` + `signal_trade_path` satırları **yeniden
  yazılmaz**. Yalnız deploy sonrası YENİ canlı-SL çözümleri düzeltilmiş mantığı kullanır.
- Eski/yeni ayrımı: yeni satırlarda `SignalTradePath.schema_version = 2` (eskiler v1 kalır).
  Çelişkili eski v1 canlı-SL satırları olduğu gibi durur; öğrenme katmanları v1/v2 ile ayırabilir.

## 5. Coin Memory / Similarity / Lifecycle / Adaptive etkisi
- Bu katmanlar **canlı telemetriyi** (`perf` + `trade_path`) tüketir. D4 ileri-dönük → **eski
  veri değişmez**; yeni satırlar **doğru** (TP1-bankalı düzgün). 
- Öneri: öğrenme katmanları **v1 canlı-SL** (resolution_source=live_sl, schema_version=1)
  satırlarını filtrele/aşağı-ağırlıkla (çelişkili realized). v2 satırları güvenilir.
- **Lifecycle:** canlı-SL çözüm olayı + outcome (loss→win/BE bazı durumlarda) ileri-dönük düzelir.
- Doğrudan zarar yok; veri kalitesi **artar**.

## 6. Risk analizi
- **Canlı başarı metrikleri değişir:** bazı "kayıp" canlı-SL çözümleri win/BE'ye yeniden
  sınıflanır (gerçekte TP1 kârı + BE kapanışıydı). Bu bir **düzeltme**dir ama win_rate'i etkiler
  → iletişim gerekir.
- Edge: TP2-ama-TP1-yok imkânsız (TP2, TP1 gerektirir). TP3 → tam kapanış (canlı-SL tetiklemez).
  Yalnız {TP1} veya {TP1,TP2} kalır → fix bunları ele alır.
- Tespit fix'i (BE kontrolü) eklenmezse TP1-bankalı BE-kırılması mid-candle yakalanmaz (bir
  sonraki bar-walk pass'inde doğru kapanır) → yalnız zamanlama; muhasebe doğruluğu RESOLUTION
  fix'iyle gelir.
- Fail-open korunur (telemetri çözümü bloklamaz).

## 7. Rollback planı
- D4 yalnız `tracker.py` canlı-SL kısayolu (+ `_check_live_sl_hit` + `_write_trade_path_live_sl_
  failopen`) + `schema_version` bump. **Migration YOK** (schema_version kolon mevcut).
- **Rollback = `git revert`.** İleri-dönük olduğu için: revert sonrası yeni çözümler eski mantığa
  döner; **revert öncesi yazılmış v2 satırları DB'de kalır** (zarar yok — doğru veriler). Geçmiş
  yeniden yazılmadığı için geri-alma güvenli; veri tutarsızlığı oluşmaz.

## 8. Before/After doğrulama planı
1. **Birim test (yeni live-SL resolution yardımcısı):** senaryolar — (a) TP1-yok → tam orijinal-
   stop kaybı **byte-identical (eski==yeni)**; (b) TP1-bankalı → 0.5·ret_tp1 + kalan BE; (c) TP1+
   TP2 → 0.5·ret_tp1+0.3·ret_tp2 + kalan BE. Beklenen değerler el-ile hesaplı.
2. **Differential:** TP1-yok dalı eski canlı-SL ile **birebir**; TP1 dalı yeni doğru değer.
3. **Regresyon (DEĞİŞMEMELİ):** bar-walk yolu golden 8/8 + differential 8000/8000 + mapping
   3000/3000 + backtest-equivalence 9000/9000 **yeniden PASS** (D4 yalnız live-SL kısayoluna
   dokunur; bar-walk + backtest değişmez).
4. **Canlı smoke:** sonraki TP1-bankalı canlı-SL çözümünde perf + trade_path tutarlı
   (reached_tp1=True + realized=bankalı + gave_back set + schema_version=2).
5. Fark/anomali → oto-fix YOK; neden+kapsam+etki + alternatifler raporlanır.

## 9. Başarı & kabul (acceptance) kriterleri
- ✅ TP1-yok canlı-SL: **byte-identical** (tam orijinal-stop kaybı, eski==yeni).
- ✅ TP1-bankalı canlı-SL: realized = bankalanan TP1(+TP2) + kalan-BE (tam kayıp DEĞİL); outcome
  doğru sınıflanır; trade_path satırı **tutarlı** (reached_tp1=True ↔ realized ↔ gave_back).
- ✅ Yeni canlı-SL satırları `schema_version=2`; eski v1 satırları **dokunulmamış**.
- ✅ Bar-walk + backtest yolları **regresyonsuz** (tüm mevcut testler PASS).
- ✅ Scale-out port tanımı `resolution_core` ile **tek-kaynak** (50/30/kalan + BE).
- ✅ Beklenmeyen anomali yok; tüm farklar D4 ile açıklanabilir.

## 10. Kapsam / uygulama notu (onay sonrası)
- Dokunulan: `tracker.py` Pass-1 canlı-SL bloğu + `_check_live_sl_hit` (etkin-stop) +
  `_write_trade_path_live_sl_failopen` (bankalı realized + gave_back + schema_version=2).
- **Dokunulmayan:** bar-walk (Pass-2), `resolution_core.step_bar`, backtest. Küçük/izole commit +
  before/after + birim test; mevcut tüm testler yeniden PASS olmadan merge yok.

## 11. UYGULAMA SONUCU (KEY1-d uygulandı + doğrulandı)
**Commit'ler:** d-1a [2247817] `live_sl_realized` helper + test (wire yok). d-1b-1 [1d984e9]
canlı wiring (`_check_live_sl_hit` etkin-stop + Pass-1 `live_sl_realized` + writer gave_back +
`TRADE_PATH_SCHEMA_VERSION=2`). d-1b-2 v1-handling (predicate + analytics + bu doküman).

**Before/After (trade-bazlı):** TP1-not-hit `−4.0 → −4.0` (LOSS, gave_back None) = **byte-identical**;
TP1-bankalı `−4.0 → +1.5` (WIN, gave_back True); TP1+TP2 `−4.0 → +3.3` (WIN). trade_path
**tutarlı** (reached_tp1 ↔ realized ↔ gave_back ↔ schema_version=2).

**Doğrulama (hepsi PASS):** live_sl 7/7 (byte-identical + consistency + predicate) · regresyon
golden 8/8 + differential 8000/8000 + mapping 3000/3000 + backtest 9000/9000 (bar-walk/step_bar/
backtest değişmedi) · canlı smoke (read-only): 20 aktif sinyal, **4 TP1-bankalı** (ileriye-dönük
korunacak), etkin-stop hatasız.

**v1-handling UYGULANDI:** versiyon-ayrımı (`schema_version` 1→2) + tek-kaynak predicate
`is_legacy_contradictory_live_sl()` (trade_path.py) + read-only analytics sayımı
(`confidence_caveats.legacy_contradictory_live_sl`). **CANLI VERİ:** 187 trade_path,
40 still_forming, **legacy_contradictory_live_sl = 0** → mevcut veride çelişkili v1 satırı YOK
(bug nadir; henüz çözülmüş satır üretmemiş) → öğrenme katmanları için temizlenecek kontaminasyon
yok. CM/Similarity/Lifecycle/Adaptive **data-gated → davranış değişmedi**; predicate + politika
dokümante (aktivasyonda filtre uygulanır). Beklenmeyen fark yok.
