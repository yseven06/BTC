# P0.8 / P2.3 — Adaptive Learning v2 — HAZIRLIK ANALİZİ (kod YOK)

**Tarih:** 2026-06-30 · **Statü:** ANALİZ. Onaylı sıra #8. Roadmap'te **P2 tier = VERİ-GATED**.

## 0. Kapsam gerilimi (önce netleşmeli — KEY2/M3 ile aynı desen)
Adaptive v2'nin özü (P2.3): *"regime-koşullu adaptif ağırlık + outcome-label → KARAR; shadow/A-B
ölçüm harness'i (adaptif vs base fayda)."* Bunun:
- **POLİTİKA yarısı** (adaptif ağırlık mantığını değiştirip kararı etkilemek) = **TP/SL üretimi gibi
  AI-davranış değişikliği → BP2-gated + VERİ-gated.** Faz 3 policy matematiğine dokunur.
- **ÖLÇÜM yarısı** (adaptif gerçekten base'i yeniyor mu) = **telemetri-önce, veri-bağımsız** prensip;
  BP2'nin tam da istediği "önce ölç, sonra davranış değiştir" ön koşulu.

→ KEY2/CM-v2 ile aynı: **veri-bağımsız ölçüm/telemetri altyapısı şimdi; politika değişikliği DEFERRED.**

## 1. Mevcut mimari (Faz 3 — adaptif ağırlık motoru)
- **Konum:** `coin_memory.py`. **RESOLVE:** `regime_weights` (base × `_REGIME_TILTS` → normalize) →
  `get_effective_weights` (base→regime→**learned**→normalize) → `load_effective_weights`.
  **UPDATE:** `_recompute_adaptive_weights` (engine hit-rate → clamped multiplier) + `update_coin_memory`.
- **Çağrı yeri:** `scheduler.py:177-205` → `detect_regime` → `load_effective_weights(regime, mem)` →
  `AIDecisionEngine.analyze_and_decide(engine_weights=...)` → `signal_generator` composite_score ağırlığı.
- **Guard'lar:** `MIN_SAMPLES_FOR_ADAPTIVE=20` (hücre), `MIN_ENGINE_SAMPLES=12` (motor), band **0.55–1.75x**.
  `adaptive_weights` = base'e-göre-çarpan (1.0 nötr); ≥20 örnek + ≥1 motor hazır olana dek **None**.
- **ÖNEMLİ sınır:** Faz 3 **YALNIZ** composite_score/confidence + yön'ü etkiler — **entry/SL/TP/R:R'ı
  ETKİLEMEZ** (CM v2/TP-SL ile dik). Tek ortak nesne `CoinMemory` satırı.

## 2. Veri-gate kanıtı (CANLI, 2026-06-30)
- **130 coin_memory hücresi → yalnız 2'si** adaptive-AKTİF (total_signals≥20 + adaptive_weights set).
- **max total_signals = 22** (eşiğin 2 üstü). Hücreler arası toplam resolved = 397.
- → Adaptive vs base **kontrastı neredeyse YOK** (2/130). Politika ayarı da, ölçümü de şu an **veri-aç**.
  M3'ten **daha ağır** gated.

## 3. Kapsam: IN (şimdi) vs DEFERRED
**DEFERRED (veri+onay+BP2 sonrası policy fazı):** adaptif ağırlık v2 mantığı, outcome-label→karar,
band/eşik retune, regime-koşullu v2. → `_REGIME_TILTS`/`_recompute_adaptive_weights`/`get_effective_weights`
matematiği/`composite_score` **DOKUNULMAZ**.

**IN (veri-bağımsız, telemetri-önce — küçük):**
- **(A8-1) Doğum-anı telemetri kancası:** her sinyalde kullanılan `engine_weights` + `adaptive_active`
  bayrağı + `regime`'i `extra.birth`'e ekle (additive). Bugün **kaydedilmiyor** → adaptif-vs-base
  ölçümü ileride mümkün olsun. (BP2 "önce telemetri".)
- **(A8-2 ops.) Read-only ölçüm reader:** çözülen sinyallerde adaptive_active=True vs False win-rate/
  realized karşılaştırması (per-cell gate + graceful, CM2-4 deseni). Karar üretmez; yalnız ölçer.

## 4. Mimari etki
| Bileşen | Etki |
|---|---|
| `_REGIME_TILTS` / `_recompute_adaptive_weights` / `get_effective_weights` / composite_score | **DEĞİŞMEZ** (policy). |
| birth telemetri (`extra.birth`) | (A8-1) additive alan (weights_used/adaptive_active) — AI kararı değişmez. |
| analytics | (A8-2) yeni read-only ölçüm — additive. |
| Similarity / TP-SL / resolution_core | **DOKUNULMAZ.** |

→ A8-1/A8-2 additive/read-only; üretim kararına sıfır müdahale (kullanılan ağırlık zaten hesaplanıyor,
yalnız KAYDEDİLİR).

## 5. Riskler / edge-case'ler
- **Veri-açlığı (en önemli):** 2/130 aktif → A8-2 ölçümü şu an istatistiksel anlamsız; karar VERME,
  yalnız telemetri biriktir. Politika kesinlikle erken.
- **Kapsam sızıntısı:** ağırlık mantığı/karar **değişmez**; A8-1 yalnız "ne kullanıldı"yı kaydeder.
- **BP2:** önce ölç (telemetri), sonra (veri olunca) shadow/A-B ile fayda kanıtla, en son policy.

## 6. Plan (küçük commit'ler — onay sonrası, veri-bağımsız kısım)
- **A8-1:** birth telemetri additive kanca (weights_used + adaptive_active + regime) + birim test +
  canlı smoke. Regresyon/parity korunur.
- **A8-2 (ops.):** read-only ölçüm reader (per-cell gate, graceful) + test.
- **DEFERRED:** politika v2 + shadow/A-B fayda harness'i → veri checkpoint + ayrı onay.

## 7. Öneri (karar gerekiyor)
Adaptive v2'nin **uygulanabilir özü şu an yalnız küçük bir telemetri kancası** (A8-1); politikası
**M3'ten ağır veri-gated** (2/130). Üç ardışık veri-gated madde (CM-v2 M3, Adaptive v2, Similarity v2)
var. İki makul yol:
1. **A8-1 telemetri kancasını şimdi ekle** (ileride ölçüm hazır) + Adaptive v2 politikasını DEFERRED
   işaretle — sıraya sadık, BP2 telemetri-önce, küçük/güvenli.
2. **Adaptive v2'yi tümüyle DEFERRED işaretle** (M3 gibi) + **veri-bağımsız değer üreten P1.2'ye geç:**
   *Lifecycle aksiyon katmanı + proaktif bildirim* (roadmap P1, "veri-bağımsız hemen değer";
   tamamlanan P0.2 per-user notifications üzerine kurulur; "sinyalin bozuluyor" erken-uyarı = ayrışma).
→ **Önerim: (2) + (1)'i ucuz bir ek olarak** — yani P1.2'ye geç (gerçek kullanıcı değeri), Adaptive
v2 telemetri kancasını (A8-1) fırsat oldukça ekle. Ama karar senin.
