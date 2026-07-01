# KEY2 Analiz Raporu — kapsam, mimari etki, uygulama planı (kod YOK)

> ## 🔁 STATÜ GÜNCELLEME: **DEFERRED / YENİDEN DEĞERLENDİRİLECEK** — 2026-07-02, Shadow Evaluation sonrası
> **Varsayım (KEY2'nin dayandığı):** dar TP/SL sistematik olarak zararlıydı (gürültü-bandı seviyeler → erken stop / sahte TP).
> **Shadow Evaluation sonucu (read-only, üretimin `resolution_core`'u ile floored yeniden-çözüm, fidelity %88):**
> varsayım **mevcut veriyle DOĞRULANMADI.** Hibrit floor (`max(k×ATR, %X×fiyat)`) etkisi:
> - %0.5 floor (28 fidelity-geçen): stop-rate 86→75% AMA win-rate 79→71%, **expectancy 0.483→0.495% (≈düz), profit-factor 6.32→4.96 (kötüleşti)** — net **wash**.
> - %0.3 floor (extreme tail): **sıfır etki** (seviyeler genişlese de aynı sonuç).
> - Sıkı-seviyeli işlemler aslında **net-pozitif** (TP1 scale-out gürültüyü kâra çeviriyor) → "dar = zararlı" premise'i zayıf.
> - Fayda yalnız **bear + ranging**'de görünüyor (stop↓, expectancy↑); bull/low-vol düz.
>
> **Kod değişikliği YAPILMADI. Production davranışı DEĞİŞMEDİ.** KEY2 production geliştirme listesinden çıkarılmadı;
> **daha fazla veri (özellikle v2 + bear/ranging yoğunluğu) oluştuğunda yeniden değerlendirilecek.** Kanıt: docs/KEY2-shadow-eval.md.

> ## ⛔ STATÜ (önceki): **DEFERRED → POLICY FAZI (KEY1 sonrası)** — 2026-06-30, kullanıcı kararı
> KEY2'nin uygulanabilir özü (min-TP1/SL **floor** BUG-2/3, risk-boundary/forex/asset **retune**)
> = TP/SL ÜRETİM POLİTİKASI + R:R alanı → **bu fazda UYGULANMAZ**, ayrı policy fazına ertelendi.
> Ayrıca **veri-gated** (187 / ~250-300 trade_path). Yapılan tek şey: **(C) calibration-readiness
> gate** (`analytics tpsl-quality sample.calibration_ready`) — policy fazı bu True olunca açılır.
> Backtest artık geçerli BP2 gate olduğundan, policy fazı geldiğinde floor/retune **tarihsel
> doğrulanabilir** (shadow-eval + before/after). **P0.6 bu kararla KAPANDI.**

**Statü:** ANALİZ. Veri-gated. **KARAR: DEFERRED (yukarı).**

## 0. Kritik kapsam gerilimi (önce netleştirilmeli)
Orijinal sentez KEY2'nin **manşet işi** şunlardı:
- **min TP1/SL distance floor** (BUG-2/3) → `signal_generator`'da TP1/SL üretim geometrisini değiştirir.
- **volatility_class sınır / forex / asset-premium retune** → risk-skoru + HOLD gate (R:R/risk politikası).

Senin **kesin dışladığın** alanlar: *TP/SL üretim mantığı, R:R politikası, TP-yakınlık hesapları,
Adaptive policy.* → **KEY2'nin manşet işi = tam olarak bu dışlanan alan.** Dolayısıyla floor +
risk-retune **bu fazın DIŞINDA** kalır; senin dediğin gibi **"KEY1 sonrası ayrı policy fazı"**.

→ **Kısıtlı KEY2 (şimdi yapılabilecek) = yalnız SALT-OKUNUR doğrulama/kanıt/izleme altyapısı**
(üretim mantığına dokunmaz). Floor/retune'un KENDİSİ değil, onu güvenle yapmaya hazırlayan zemin.

## 1. Kapsam: IN (şimdi) vs DEFERRED (policy fazı)
**DEFERRED (ayrı policy fazı, veri+onay sonrası):** min-TP1/SL floor, risk-boundary/forex/asset
retune, configurable-overlap (canlı/backtest davranışı), Adaptive.

**IN (kısıtlı KEY2, şimdi — hepsi salt-okunur/additive):**
- **(A) Back-to-back replay regression harness** — KEY1 gate'inin "güven metriği": çözülmüş canlı
  sinyalleri çekirdek üzerinden replay edip saklanan outcome/realized'i ürettiğini doğrular.
- **(B) Shadow-policy evaluation tool (read-only)** — tarihsel trade_path'lerde ALTERNATİF geometri
  (ör. hipotetik min-TP1 floor) "ne olurdu"yu hesaplar; **canlıyı/üretimi DEĞİŞTİRMEZ**, sonuç
  `extra.shadow` (rezerve slot) veya rapor olarak. Floor'un etkisinin KANITINI üretir.
- **(C) Calibration-readiness / data-gate monitoring** — trade_path sayısı 250-300'e ilerleyişi +
  hazır-olma bayrağı (analytics zaten `below_checkpoint` veriyor).

## 2. Mimari etki (mevcut source-of-truth BOZULMAZ)
| Bileşen | Etki |
|---|---|
| `resolution_core` / `step_bar` | **DEĞİŞMEZ.** (A) ve (B) çekirdeği TÜKETİR (resolve_trade_path/step_bar çağırır), değiştirmez. |
| `trade_path` | `extra.shadow` **zaten rezerve** (Commit 4) → (B) additive doldurur; şema/contract değişmez. |
| `schema_version=2` | **DEĞİŞMEZ** (shadow additive; contract era aynı). |
| analytics | (B)/(C) sonuçları **yeni read-only** alan/endpoint (additive); mevcut aggregate'ler bozulmaz. |
| backtest/live parity | **KORUNUR** — (A) parity'yi DOĞRULAR; (B) parity-doğrulanmış çekirdeği kullanır. |

→ Hepsi salt-okunur / additive / tek-kaynağı tüketir. Üretim mantığına sıfır dokunuş.

## 3. Uygulama planı (minimal, DRY, küçük commit'ler — onay sonrası)
- **K2-1 (replay harness):** `tests/` + opsiyonel script. Çözülmüş canlı sinyalleri
  `resolve_trade_path` ile replay → saklanan outcome/realized'i tolerans içinde üretir mi.
  **NOT:** collector `limit=100` (son mum) → tam-tarihsel pencere yok; differential (8000 in-memory)
  zaten LOGIC parity'yi KANITLADI. Bu yüzden K2-1 = differential-stili in-memory parity testi
  (kesin) + yakın-örnek gerçek-veri smoke (kısmi, caveat'lı). Düşük marjinal değer (logic zaten kanıtlı).
- **K2-2 (shadow-eval tool):** `app/services/`'de salt-okunur `evaluate_shadow_geometry(rows, alt_levels_fn)`
  — alternatif seviyelerle realized'i yeniden hesaplar (step_bar TÜKETİLİR), before/after aggregate döner.
  `alt_levels_fn` hipotetiktir (üretime girmez). **Floor'un etkisini ölçer = policy fazı için kanıt.**
  *(Kapsam notu: floor FORMÜLÜ shadow/read-only bağlamda; canlı üretim DEĞİŞMEZ — yine de sınırda,
  onayın gerekir.)*
- **K2-3 (readiness):** trade_path sayacı + hazır-olma raporu (analytics `below_checkpoint` zaten var
  → minimal ek).

## 4. Veri-gate durumu
- **Mevcut: 187 trade_path** (gerekli ~250-300). → Floor kalibrasyonu için **henüz erken** (ve zaten
  policy fazına deferred). (B) shadow-eval anlamlı sonuç için de daha çok veri ister.

## 5. Riskler / edge-case'ler
- **Kapsam kayması riski (en önemli):** (B) shadow-eval floor formülünü içerir; yanlışlıkla üretime
  sızması KESİNLİKLE yasak. Mitigasyon: read-only, `alt_levels_fn` yalnız shadow; `signal_generator`
  dokunulmaz; testle korunur.
- Replay (A) veri-drift/still-forming sınırlı (KEY1-b2'de raporlandı) → strict kanıt differential'dır.
- Veri azlığı (187): shadow-eval/floor sonuçları istatistiksel zayıf → karar VERME, yalnız kanıt biriktir.

## 6. Coin Memory v2'ye geçmeden ön koşullar (analiz)
*(Phase-2 sırası: P0.6 sonrası P0.7 Coin Memory v2.)*
- **Veri yeterliliği:** CM v2 (tm_stats→politika) anlamlı per-symbol/regime histogram için ~250-300+
  trade_path ister (şu an 187). **Beta'nın veri üretmesi keystone** ([[phase2-roadmap]]).
- **Telemetri tutarlılığı:** ✅ KEY1-d ile canlı-SL satırları artık tutarlı (v2); v1-çelişki=0.
  CM rollup (`update_trade_mgmt_stats`) v2 predicate'ini aktivasyonda uygulamalı.
- **Tek-kaynak çözüm:** ✅ KEY1 ile backtest+canlı tek `step_bar` → CM/shadow aynı çekirdeğe dayanır.
- **schema_version disiplini:** ✅ v2 marker + predicate hazır (eski/yeni ayrımı).
- **AÇIK ön-koşul:** CM v2 "politika" (tm_stats'tan ağırlık/karar) **BP2-gated davranış değişikliği**
  → kendi analiz+shadow+gate döngüsü gerekir (KEY1 mimarisi bunu mümkün kılar).

## 7. Öneri
KEY2'nin **özü doğru biçimde DEFERRED** (dışlanan üretim alanı + veri-gated). Şimdi yapılabilecek
(A/B/C) çoğunlukla **zaten mevcut** (differential parity + analytics below_checkpoint). En yüksek
değerli minimal ek: **(B) shadow-eval altyapısı** (floor'u UYGULAMADAN etkisini ölçer — policy fazının
kanıt motoru), istersen + **(C) readiness raporu**. **(A) düşük marjinal** (logic zaten kanıtlı).
→ **Karar senin:** (1) yalnız (C) minimal readiness + KEY2'yi resmî deferred ilan et; (2) (B) shadow-eval
altyapısını da kur (read-only, onaylı); (3) P0.6'yı kapat, KEY2'yi policy fazına bırak, P0.7'ye geç.
