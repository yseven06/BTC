# P0.7 — Coin Memory v2 — HAZIRLIK ANALİZİ & PLAN (kod YOK)

**Tarih:** 2026-06-30 · **Statü:** ANALİZ (yalnız analiz+planlama; kod yazılmadı) · veri-gated.
**Kaynak:** 4-ajan paralel kod-haritalama (similarity, adaptive, metric-envanteri, mevcut-CM) +
sentez. (Workflow'un design-sentez ajanı structured-output cap'ine takıldı; map'ler kurtarıldı,
sentez bu dokümanda elle yapıldı.)

## 0. Tek cümlede durum
**`CoinMemory.tm_stats` zaten YAZILIYOR ama ÜRETİMDE HİÇBİR YERDE OKUNMUYOR** (seed edilmiş,
tüketilmeyen v2 cache). CM v2'nin işi yeni bir motor kurmak DEĞİL; mevcut türetilebilir cache'i
**(a) temizle/sertleştir, (b) eksik agregatlarla additive genişlet, (c) OKU/yüzeye çıkar** —
hepsi KEY1 source-of-truth'u (`signal_trade_path`) tüketerek, üretim/policy mantığına dokunmadan.

## 1. trade_path + schema_version=2 nasıl kullanılacak
- **SoT = `signal_trade_path`** (değişmez, KEY1, `schema_version=2`). CM v2 bunun üzerinde
  **türetilebilir rollup CACHE**'tir (`tm_stats`); SoT asla budanmaz → cache her an drop&rebuild edilebilir.
- **Metriklerin ÇOĞU zaten first-class kolon** (resolution anında `compute_trade_path` yazıyor):
  `mfe_r/mae_r/mfe_atr/mae_atr`, `sl_dist_pct`, `atr_pct_at_signal`, `cur_reached_tp1/2/3`,
  `cur_bars_to_tp1`, `cur_gave_back_after_tp1`, `cur_realized_return`, `bars_total`, `mfe/mae_bar_idx`
  + `extra` (planned_rr_tp1/2/3, tp1_dist_atr, mfe_to_tp1, mae_to_sl, captured_tp1_potential).
  → CM v2 = **saf AGREGASYON**; yeni ham telemetri YOK, yeni kolon YOK.
- **v1-hijyen (KRİTİK AÇIK):** mevcut `update_trade_mgmt_stats` **her path'i koşulsuz** fold ediyor —
  `is_legacy_contradictory_live_sl()` çağırmıyor, `schema_version>=2` gate'i yok. → tm_stats çelişkili
  v1 live-SL satırı içerebilir. **CM v2 fold'da bu predicate'i + schema_version gate'ini uygulamalı**
  (KEY1-d'de yazdığımız tek-kaynak predicate; tpsl_analytics zaten `legacy_contradictory_live_sl` sayıyor).
- **cur_\* policy-koşullu:** `cur_*` alanları MEVCUT TP/SL policy'sine bağlıdır. CM v2 bunları
  agregelerken **"policy-conditional" etiketiyle** saklamalı; ileride bir TP/SL policy değişirse
  (KEY2 policy fazı) cache **yeniden türetilir**, bayat `cur_*` agregelerine güvenilmez. (Drop&rebuild bunu zaten ucuz kılıyor.)

## 2. Coin Memory veri modeli
**Tek satır / (symbol, timeframe)** — `uq_coin_memory_symbol_tf`. Aynı satırda **iki ayrık katman**:

| Katman | Alanlar | Durum |
|---|---|---|
| **v1 (Faz 3 POLICY — DOKUNMA)** | total/wins/losses, engine_stats, regime_stats, outcome_label_stats, adaptive_weights, avg_bars_to_outcome | engine-skor ağırlık öğrenimi; KEY2-sonrası policy alanı |
| **v2 seed (CM v2 yüzeyi)** | `tm_stats` JSON {regime: bucket, '_all': bucket}, `tm_sample_count` | türetilebilir cache; **reader YOK** |

**Mevcut bucket** (`_empty_bucket`): `{n, mfe_r_sum, mae_r_sum, hist_mfe_r[9], hist_mae_r[9],
tp1, tp2, tp3, give_back}`. Histogram: `TM_R_EDGES=[0.25,0.5,0.75,1,1.5,2,3,5]` (+overflow).
**Additive-list tasarımı** (parent = child'ların toplamı) → drop&rebuild ve regime-merge ucuz.

**CM v2 model kararı:** **YENİ TABLO/KOLON YOK.** `tm_stats` JSON'unu **additive genişlet**
(eski bucket'lar `.get(key, default)` ile yeni anahtarları kazanır). Keying: regime + `_all`
korunur; direction/session/volatility-bucket gibi ince dilimler **bucket patlamasını önlemek için
on-read SoT'tan türetilir** (SoT'ta `gen_session/volatility_bucket/direction` ham kolonları var).
İçeri bir `tm_schema_version` işaretçisi (additive) eklenebilir (v1/v2 cache ayrımı).

## 3. Metrik mimarisi (MFE/MAE, Avg R, Avg Bars, stop-too-tight, entry-quality)
**DRY ilke:** `tpsl_analytics.compute_tpsl_quality` zaten bu metriklerin **global/cache'siz**
versiyonunu hesaplıyor; tm_stats onun **per-cell cache**'i. Tanımları **yeniden yazma, paylaş**.

| Metrik | Kaynak (zaten var) | tm_stats'ta durum | CM v2 işi |
|---|---|---|---|
| **MFE/MAE (R)** | kolon `mfe_r/mae_r` | ✅ `mfe_r_sum/mae_r_sum` + hist | hazır (avg=sum/n on-read) |
| **MFE/MAE (ATR)** | kolon `mfe_atr/mae_atr` | ❌ rollup yok | additive: `mfe_atr_sum/mae_atr_sum` |
| **Avg R** | `mfe_r_sum/n` | ✅ türetilir | on-read (saklama yok) |
| **Avg Bars** | kolon `cur_bars_to_tp1`, `bars_total` | ❌ (yalnız coin-geneli `avg_bars_to_outcome`) | additive: `bars_to_tp1_sum`, `bars_total_sum` |
| **stop-too-tight** | label `CORRECT_DIR_TIGHT_SL` (canon def) + `mae_to_sl` (extra) + `sl_before_tp` (DERIVE) | ❌ per-cell yok | additive: regime-keyed `tight_sl` sayacı (label veya mae_r≈1 & mfe_r yüksek) |
| **entry-quality** | `planned_rr_tp1`, `tp1_dist_atr`, `mfe_to_tp1`, `captured_tp1_potential` (extra); `sub_1_rr` (tpsl_analytics) | ❌ per-cell yok | additive: `planned_rr_tp1_sum`, `sub1_rr` sayacı, tp1_r hist |
| **realized/dispersion** | kolon `cur_realized_return` | ❌ | additive: `realized_sum` + **`*_sumsq`** (varyans/std için) |

**Önemli:** `sl_before_tp` **saklanan kolon değil, TÜRETİLİR** (kilitli karar — `path_reader.py`).
CM v2 aynı türetimi kullanmalı, kolonu otorite kabul etmemeli. `trade_geometry.py`
(safe_div/planned_rr/dist_pct) tek-kaynak; `tpsl_analytics._planned_rr` (yerel kopya, satır 52-59)
**3. kopya eklenmeden** trade_geometry'ye konsolide edilmeli (küçük DRY borcu).

## 4. Similarity (Faz 6) + Adaptive (Faz 3) entegrasyon noktaları
**Similarity (similarity.py) — bugün SignalTradePath'i HİÇ okumuyor (CM v2'nin doldurduğu boşluk):**
- **Entegrasyon B (en düşük risk, ÖNERİLEN):** feature vektörünü/distance matematiğini DEĞİŞTİRME;
  yalnız **OUTPUT dict'ine** TOP_K komşunun trade-management roll-up'ını ekle (medyan give-back,
  tipik MFE-R, "bu kurulum genelde kârın X'ini geri verir"). `signals.py:674-679` tek tüketici →
  tek-nokta, yeni route yok. **Mevcut `has_data` gate'ini miras al** (8-komşu eşiği).
- **Entegrasyon A (sonra, dikkatli):** trade-mgmt boyutlarını feature vektörüne ekle → distance
  ölçeği değişir, `MAX_DISTANCE`/clamp yeniden ayarı gerekir. Şimdilik **gerekmez**.
- **ZORUNLU:** Similarity'ye trade-path türevli veri beslenirse aday sorgusu
  `is_legacy_contradictory_live_sl`/`schema_version>=2` predicate'ini **eklemeli** (bugün hiç
  filtresi yok → kirli v1 satırlarına sessiz regresyon riski).

**Adaptive (Faz 3) — POLICY katmanı, KAPSAM DIŞI (yalnız harita):**
- `get_effective_weights/_recompute_adaptive_weights/_REGIME_TILTS/composite_score` **DOKUNULMAZ.**
- Faz 3 (pre-fill engine skorlama) ve CM v2 (post-fill path yönetimi) **diktir**; tek ortak nesne
  `CoinMemory` satırı. Bu **DRY kazancı**: bir satır, iki türetilebilir rollup (`adaptive_weights`
  vs `tm_stats`), şema tekrarı yok. CM v2 `adaptive_weights`'e VEYA TP/SL/R:R üretimine **asla yazmaz**.
- Faz 3'ün veri-gate idiomunu **kopyala**: `MIN_SAMPLES_FOR_ADAPTIVE=20` per-cell + graceful fallback.

## 5. Migration / telemetry ihtiyaçları
- **Migration: YOK (ALTER yok).** `tm_stats` JSON; tüm yeni alanlar additive. `tm_sample_count`
  zaten var. Gerekirse `tm_stats` içine `tm_schema_version` (additive anahtar).
- **Telemetry: YOK (yeni ham alan gerekmez).** Tüm CM v2 metrikleri mevcut first-class kolon/extra'nın
  agregasyonu. (KEY1-d ile telemetri zaten tutarlı: v2 + predicate hazır.)
- **Backfill: one-shot REBUILD** (online migration DEĞİL). tm_stats türetilebilir cache olduğundan:
  drop → `signal_trade_path`'i (legacy-filtreli, schema_version>=2) yeni fold mantığıyla replay et.
  Idempotent, SoT'a yazmaz, resolution_core/trade_path'e dokunmaz. KEY1 korunur.

## 6. Uygulama sırası & milestone planı (küçük, doğrulanabilir commit'ler — onay sonrası)
**M1 — Rollup doğru + zengin (veri katmanı):**
- **CM2-1:** fold'u sertleştir — `update_trade_mgmt_stats`'te `is_legacy_contradictory_live_sl` +
  `schema_version>=2` gate uygula (kontaminasyon açığını kapat). Birim test. *(İleri-dönük; davranış:
  tm_stats artık kötü satır yutmaz.)*
- **CM2-2:** bucket'ı additive genişlet (`mfe_atr_sum/mae_atr_sum`, `bars_*_sum`, `tight_sl`,
  `planned_rr_tp1_sum`/`sub1_rr`, `realized_sum`+`*_sumsq`). Eski bucket'lar `.get` default ile uyumlu. Test.
- **CM2-3:** one-shot rebuild script (drop&replay, legacy-filtreli, idempotent) → backfill. SoT read-only.
- **CM2-DRY:** `tpsl_analytics._planned_rr` → `trade_geometry.planned_rr` konsolidasyonu (golden-safe).

**M2 — Okuma yüzeyi (CM v2'nin eksik yarısı):**
- **CM2-4:** `compute_coin_tm_summary(mem, regime)` reader (tpsl_analytics tanımlarını DRY kullan) +
  **per-cell gating** (`tm_sample_count` < MIN → ham sayı evet, türev oran/öneri HAYIR; global
  `calibration_ready` ile hizalı). `signals.py:652` payload'una additive ekle. Test + canlı smoke.

**M3 — Genişletme (veri-gated, ≥ checkpoint):**
- **CM2-5 (opsiyonel):** Similarity OUTPUT zenginleştirme (Entegrasyon B, legacy-filtreli, gated).
- İnce dilimler (direction/session/volatility) on-read türetme (gerekirse).

## 7. Riskler / edge-case'ler
- **Per-cell seyreklik (en önemli):** ~193 path global; çoğu (symbol,tf,regime) hücresi tek-haneli.
  → per-cell `MIN_TM_SAMPLES` gate (similarity 8 / Faz3 20 benzeri) + global `calibration_ready`;
  eşik altı **ham sayı göster, oran/öneri gösterme**.
- **Bucket şekil değişimi:** eski cache'te yeni anahtar yok → `.get(key, default)` + rebuild ile çöz.
- **cur_\* policy-koşullu:** TP/SL policy değişirse (KEY2 fazı) cache yeniden türetilmeli; "policy-
  conditional" etiketle, bayat agregeye güvenme.
- **Kapsam sızıntısı:** CM v2 `adaptive_weights`/TP-SL/R:R'a **asla yazmaz** — yalnız okur/rollup.
- **Fail-open korunur:** rollup + reader resolution'ı/endpoint'i bloklamaz (warning + skip).

## 8. CM v2'ye başlamadan ön koşullar
- ✅ KEY1 (tek-kaynak step_bar), ✅ schema_version=2 + predicate, ✅ metrikler first-class kolon,
  ✅ tm_stats additive-list seed + tm_sample_count, ✅ KEY1-d telemetri tutarlı (v1-çelişki=0).
- ⏳ **Veri-gate:** global ~193 / 250-300; **per-cell çok daha seyrek** → M1/M2 (rollup+reader)
  veri-bağımsız yapılabilir (cache doğruluğu + graceful-degrade yüzey), ama **anlamlı per-cell
  içgörü/M3 checkpoint'i bekler**. Beta'nın veri üretmesi keystone.
- 🔒 **Kapsam çiti:** TP/SL üretim, R:R, TP-yakınlık, Adaptive POLICY — **dokunulmaz** (KEY2/policy fazı).

## 9. Öneri
**M1 (CM2-1 fold-hardening + CM2-2 genişletme + CM2-3 rebuild + DRY)** veri-gate'ten bağımsız,
güvenli ve değerli: kontaminasyon açığını kapatır, cache'i zenginleştirir, KEY1'i korur. Ardından
**M2 (CM2-4 reader)** "yazılıp okunmayan" cache'i nihayet UI/API'ye taşır (graceful-degrade). **M3**
veri checkpoint'ine gated kalır. → İlk adım önerim: **CM2-1 (fold-hardening)** — küçük, izole,
ileri-dönük, mevcut KEY1-d predicate'ini rollup'a uygular (tutarlılık tek-kaynak).
