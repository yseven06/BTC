# TM v2 — Phase 1 Teknik Spec: Offline Replay & Policy Harness

> **Kapsam:** Phase 1 = **saf offline analiz**. `signal_trade_path` (+ `coin_memory`) okur, **canlıya hiçbir şey yazmaz**, davranışı değiştirmez → freeze ile tam uyumlu. Çıktı: politika karşılaştırma raporu + kalibre edilmiş adaptive scale-out eğrisi.
> Üst tasarım: `docs/trade-management-v2-design.md`. Kilitli kararlar: `memory/tm-v2-design-notes.md`.
> Bu doküman implementasyon değil; **implementasyona geçince sıfır mimari belirsizlik** hedefler.

---

## 1. Modül sınırları

Yeni izole paket `app/trade_mgmt/` (Phase 1'de canlı hiçbir yol buradan import etmez):

| Dosya | Sorumluluk | Bağımlılık |
|---|---|---|
| `types.py` | Tüm dataclass'lar (PathRecord, ManagementParams, TradeState, ReplayResult, PolicyScore, Segment). | yok (saf) |
| `path_reader.py` | `signal_trade_path` → `PathRecord`; türetimler (`tp1_r`, `sl_before_tp`); kalite bayrakları. | models (read-only) |
| `policies/base.py` | `Policy` ABC + `ManagementParams`. | types |
| `policies/catalog.py` | Somut politikalar: `FixedCurrent`, `TrailAfterTP1`, `BEAfterTP2`, `AdaptiveScaleout`. | base, scaleout |
| `scaleout.py` | **Adaptive Scale-out karar modülü** (prior eğri + çarpanlar). | types |
| `replay.py` | `CounterfactualReplayer`: PathRecord × Policy → ReplayResult. | types, policies |
| `scoring.py` | `PolicyScorer` + segmentasyon. | types |
| `report.py` | Rapor (markdown + konsol). | hepsi |
| `scripts/tm_replay_report.py` | Offline runner (tek giriş noktası; `activate_bist_pilot` gibi). | hepsi + DB read |

**Sert sınır:** yalnız DB **read**; yazma yok; `tracker`/`scheduler`/`signal_generator` sıcak yollarından import yok. Phase 1 tamamen `python -m scripts.tm_replay_report` ile çalışan batch.

---

## 2. Veri modelleri (`types.py`)

```python
@dataclass(frozen=True)
class PathRecord:                 # signal_trade_path satırının tiplenmiş okuması
    signal_id; asset_id; symbol; timeframe; direction; regime
    outcome; detail_label; resolved_at; schema_version; source
    entry; sl; tp1; tp2; tp3      # self-contained fiyatlar
    mfe_r; mae_r; mfe_atr; mae_atr; mfe_pct; mae_pct
    bars_total; mfe_bar_idx; mae_bar_idx; sl_dist_pct; atr_pct_at_signal
    cur_reached_tp1; cur_reached_tp2; cur_reached_tp3
    cur_bars_to_tp1; cur_post_tp1_mfe_r; cur_post_tp1_mae_r
    cur_gave_back_after_tp1; cur_realized_return
    intrabar_ambiguous; still_forming_resolution
    # --- türetilenler (saklanmaz; PathReader üretir) ---
    tp1_r: float | None           # = (tp1-entry)/(entry-sl), policy-independent R
    tp1_atr: float | None         # = (tp1-entry)/(atr_pct%·entry)
    sl_before_tp: bool | None     # cur_reached_tp1 / intrabar_ambiguous / outcome'dan
    confidence_flags: tuple[str]  # {"still_forming","intrabar_ambiguous","no_tp2_price",...}

@dataclass(frozen=True)
class ManagementParams:
    tp1_scale_frac: float | None  # sabit oran (None → adaptive_curve kullan)
    adaptive_curve: ScaleCurve | None
    post_tp1_mode: Literal["BREAKEVEN","TRAIL"]
    trail_rule: Literal["ATR_K","R_K","STRUCTURE"] | None
    trail_k: float | None
    trail_activate_at_r: float | None
    be_after: Literal["TP1","TP2"]
    time_stop_bars: int | None
    early_exit_on: frozenset[str]  # {"INVALIDATING","REGIME_FLIP"}

@dataclass(frozen=True)
class TradeState:                 # replay adımı + (gelecekte) runtime aynı tip
    direction; entry; sl; tp1; tp2; tp3; atr_pct; regime
    bars_elapsed; current_r; cur_mfe_r; cur_mae_r
    hit_tp1; hit_tp2; hit_tp3; post_tp1_mfe_r; post_tp1_mae_r
    lifecycle_status

@dataclass(frozen=True)
class ReplayResult:
    realized_r: float; exit_reason: str; scale_events: list  # [(frac, r_at_exit, why)]
    gave_back: bool; bars_held: int; confidence: float; flags: tuple[str]

@dataclass(frozen=True)
class PolicyScore:
    n; excluded_n; expectancy_r; avg_r; median_r; p25_r
    profit_factor; giveback_rate; win_rate; max_mae_r
```

---

## 3. PathReader

1. `SELECT * FROM signal_trade_path WHERE source='live' AND schema_version=<target>`.
2. Her satır → `PathRecord`; türetimler:
   - `tp1_r = abs(tp1-entry)/abs(entry-sl)` (entry/sl/tp1 varsa; yoksa None).
   - `tp1_atr = abs(tp1-entry)/(atr_pct_at_signal/100·entry)`.
   - `sl_before_tp`: `cur_reached_tp1=True → False`; `intrabar_ambiguous=True → None`; `cur_reached_tp1=False ∧ outcome∈{loss} → True`; expired/no-SL → None.
3. **Kalite bayrakları** (`confidence_flags`): `still_forming_resolution`, `intrabar_ambiguous`, `mfe_r is None`, `tp2/tp3 price yok`. Satır atılmaz; bayraklanır (replay güveni düşürülür / segmentlenir).
4. Döner: `list[PathRecord]` + okuma özeti (toplam, dışlanan, bayrak sayıları).

---

## 4. Policy arayüzü + katalog

```python
class Policy(ABC):
    params: ManagementParams
    def decide(self, state: TradeState) -> PolicyDecision: ...   # runtime + replay ortak
```

Katalog (Phase 1 karşılaştırma seti):
- **`FixedCurrent`** — bugünkü tracker politikası: TP1'de %50 çık + SL→entry (BE), TP2 %30, TP3 kalan. **Fidelity çapası** (bkz. §6).
- **`TrailAfterTP1`** — TP1'de %X çık + kalanı trail (BE değil).
- **`BEAfterTP2`** — TP1'de küçük çıkış, BE'ye TP2'den sonra geç.
- **`AdaptiveScaleout`** — TP1 oranını `scaleout.py` eğrisinden hesaplar (§5).
- **Parametre süpürmesi** — `AdaptiveScaleout`'un eğri kırılımları + çarpan güçleri grid'i.

---

## 5. Adaptive Scale-out — AYRI KARAR MODÜLÜ (`scaleout.py`)

> **Tasarım kararı (kullanıcı, 2026-06-28):** TP1 scale-out oranı **asla sabit olmayacak**. Özellikle **TP1 girişe çok yakınsa** yüksek oranlı çıkış mantıksız → düşük scale-out + kalanı trail/TP2. Oran şu faktörlere göre adaptif: TP1↔entry mesafesi, TP1'in **R oranı**, ATR%/volatilite, coin geçmişi, timeframe, rejim, confidence/probability, geçmiş give-back, TP1→TP2 devam olasılığı.

**Neden R-tabanlı çekirdek:** `%` mesafe yanıltıcı (düşük-vol'de %1 büyük, yüksek-vol'de küçük). `tp1_r = TP1 ödülü / SL riski` ölçekten bağımsız ve **policy-independent** → coin/TF/vol arası karşılaştırılabilir (Faz 1 felsefesi).

**Prior eğri (veri yokken; principled başlangıç):**

| `tp1_r` | `base_frac` | Gerekçe |
|---|---|---|
| < 0.5 | **0.20** | TP1 girişe çok yakın → küçük çıkış, hedefe koşmaya bırak |
| 0.5–1.0 | 0.33 | ılımlı |
| 1.0–1.5 | 0.50 | dengeli |
| 1.5–2.5 | 0.60 | anlamlı kazanç → daha çok de-risk |
| > 2.5 | 0.70 | TP1 zaten büyük → çoğunu al |

**Çarpanlarla ayar (clamp'li; Phase 1 grid-sweep, Phase 2 öğrenilir):**
```
frac = clamp( base_frac(tp1_r)
              × giveback_mult(segment_giveback)     # give-back↑ → frac↑ (kârı al)
              × continuation_mult(tp1_to_tp2_prob)  # TP2 olasılığı↑ → frac↓ (koştur)
              × vol_mult(atr_pct / volatility)      # aşırı vol → hafif↑
              × conf_mult(confidence | probability),# yüksek güven → frac↓ (koştur)
              lo=0.10, hi=0.70 )
```
**Kalan-mod (remainder) kararı:**
```
if tp1_r < 0.5:                      remainder = TRAIL   # zar zor kıpırdadı → BE'ye kilitleme
elif giveback↑ and tp2_prob↓:       remainder = BREAKEVEN  # koru
else:                               remainder = TRAIL   # kazananı koştur
```
**`segment_giveback` ve `tp1_to_tp2_prob` kaynağı:** `coin_memory.tm_stats[regime]`'den (`give_back/n`, `tp2/tp1`). Yeterli örnek yoksa → üst seviye (global) → yoksa nötr çarpan (1.0). Hiyerarşik fallback.

**Phase 1 görevi:** bu eğri + çarpan grid'ini replay ile süpürüp **expectancy'yi maksimize eden kalibre eğriyi** önermek. Yukarıdaki sayılar *başlangıç prior'ı*; rapor veriyle düzeltilmiş halini verir.

**TP1 anlamlılık tabanı (`MIN_MEANINGFUL_R`) — bkz. design §7.6 (merkezi ilke):** "TP1 alındı ama P/L ~+%0.09" sorununun replay tarafı. `tp1_r < MIN_MEANINGFUL_R` olan path'lerde yüksek scale-out **cezalandırılır** (küçük kârı kilitleyip koşuyu öldürmek expectancy'yi düşürür). Replayer bu eşiği grid'de süpürür; rapor en iyi `MIN_MEANINGFUL_R`'yi önerir. Bu eşik aynı zamanda Phase 3 TP-geometry tabanını besler (anlamsız-yakın TP1 doğmasını engelle).

---

## 6. Replay algoritması (`replay.py`)

**Girdi:** `PathRecord` + `Policy`. **Çıktı:** `ReplayResult` (realized-R). **Yöntem:** saklanan özet primitiflerden (tam intrabar yol yok) + belgeli varsayımlar.

```
def replay(rec, policy) -> ReplayResult:
  # 1) TP1'e hiç ulaşılmadı mı?
  if not rec.cur_reached_tp1:
      if outcome SL/loss → realized_r = -1.0 (tam pozisyon SL'de, R birimi)
      elif expired      → realized_r = clamp(cur_realized_return / R)   # kapanış
      return ...

  # 2) TP1'e ulaşıldı → scale-out
  frac1 = policy.scale_frac(state_at_tp1)           # FixedCurrent: sabit; Adaptive: eğri
  realized = frac1 * tp1_r                            # TP1'de çıkan kısım
  rem = 1 - frac1
  mode = policy.remainder_mode(...)

  # 3) Kalan pozisyonun kaderi (özetten)
  if mode == BREAKEVEN:
      if cur_reached_tp2:  realized += rem_split(tp2_r, tp3_r, reached_tp3)
      elif gave_back:      realized += rem * 0.0      # BE dönüşü (give-back ölçümü)
      else:               realized += rem * est_close_r
  elif mode == TRAIL:
      # post_tp1_mfe_r tepe; trail mesafesi düşülür (YAKLAŞIK — §8 sınır)
      if cur_reached_tp2/3: realized += rem_split(...)
      else: realized += rem * max(0, post_tp1_mfe_r - trail_k)   # trail-stop tahmini
  return ReplayResult(realized, ..., flags=approx_flags)
```

**Önemli kurallar:**
- R birimi = `entry↔sl` (sl_dist_pct). Tüm getiriler R cinsinden → ölçekten bağımsız.
- `still_forming` (mfe None) veya `tp2/tp3 price` yoksa → ilgili dal `flags`'a "approx" yazar, güven düşürülür; isteğe bağlı segment dışı.
- `intrabar_ambiguous` → SL-first muhafazakâr (mevcut tracker ile tutarlı).
- **Trailing replay yaklaşıktır** (özet veriden tam eğri yok). Phase 1 bu yüzden **önce yaklaşıklığa dayanmayan** politikalara güvenir: scale-out oranı, BE-after-TP1-vs-TP2, time-stop. Trailing sonuçları "düşük güven" etiketiyle raporlanır.

---

## 7. Politika değerlendirme akışı (`scoring.py`)

```
records = PathReader.load()
segments = segment(records, by=[("global",), ("regime",), ("coin","tf","regime")])
for seg in segments:
    if seg.n < MIN_SAMPLES[seg.scope]: mark INSUFFICIENT; fallback üst seviye
    for policy in catalog:
        results = [replay(r, policy) for r in seg.records]
        score[seg][policy] = aggregate(results)   # PolicyScore
    rank by expectancy_r  s.t.  giveback_rate ≤ FixedCurrent.giveback  AND  p25_r ≥ FixedCurrent.p25_r
    best[seg] = top (gated)
```
Eşikler (ilk öneri; ilk rapordan kalibre): `MIN_SAMPLES = {global: 30, regime: 40-50, (coin,tf,regime): 20}` — mevcut `MIN_SAMPLES_FOR_ADAPTIVE=20` ile hizalı.

**Birincil hedef:** expectancy (R). **Kısıt:** give-back ve sol-kuyruk (p25_r) `FixedCurrent`'tan kötüye gitmemeli (insan-gibi: kârı koru, felaketi büyütme).

---

## 8. Rapor çıktıları (`report.py`)

Markdown artefakt (scratch/ altına; araç commit etmez) + konsol özet:
1. **Veri özeti** — N, segment dağılımı, dışlanan/bayrak sayıları.
2. **FIDELITY CHECK (kabul kapısı)** — `replay(FixedCurrent)` ↔ gözlenen `cur_realized_return` dağılımı (ort-mutlak-fark + KS). Geçmezse alt-politika sayılarına güvenilmez → replay düzeltilir.
3. **Segment × politika tablosu** — her segment için {policy → expectancy_r, giveback_rate, PF, avg_r, p25_r, win_rate, n}.
4. **En iyi politika + uplift** — segment başına `FixedCurrent`'a göre kazanım.
5. **Kalibre adaptive scale-out eğrisi** — `tp1_r → frac` önerisi (veri-temelli).
6. **TP1 ANLAMLILIK DAĞILIMI** (design §7.6) — TP1'e ulaşan path'lerde `tp1_r` ve gerçek-% histogramı; **küçük-P/L payı** (ör. realized < %0.2 olan "TP1 alındı" oranı) → kullanıcının "+%0.09 TP1" gözlemini niceler; önerilen `MIN_MEANINGFUL_R` tabanı.
7. **Veri-yeterlilik bayrakları** — hangi segment eşiği geçti.
8. **Caveat'lar** — trailing-approx, low-n. (Komisyon/fee **bilinçli kapsam dışı** — kullanıcı kararı; saf fiyat-yolu R'si.)

---

## 9. Fail-open (Phase 1 yorumu)

Offline olduğu için "fail-open" = **kötü satıra dayanıklılık**: null/ambiguous satırlar atlanır/bayraklanır, işlem durmaz; tek satır asla exception fırlatıp raporu düşürmez; dışlanan sayısı loglanır. Canlı sisteme **sıfır** dokunuş → freeze riski yok.

---

## 10. Performans maliyeti

- 1 DB read (N satır). Replay **O(1)/satır** (özet matematik, bar-bar değil).
- Toplam ≈ O(N × P × S): N~10²–10³, P~5–10 politika, S~onlarca segment → ~10⁴–10⁵ trivial işlem, **<1 sn**.
- Batch/offline; sıcak yola **sıfır** ek yük. Bellek: N PathRecord (~birkaç yüz KB).

---

## 11. Test stratejisi

| Katman | Test |
|---|---|
| **Unit** | Replay golden testleri (sentetik PathRecord → beklenen R); scale-out eğri sınırları (tp1_r kırılımları, clamp); `sl_before_tp` doğruluk tablosu; scoring matematiği (expectancy/PF/giveback). |
| **Fidelity / kabul** | `replay(FixedCurrent)` gerçek veri üzerinde gözlenen `cur_realized_return` dağılımını tolerans içinde **yeniden üretmeli**. Alt-politika sayılarına güvenmeden önce **ZORUNLU kapı**. |
| **Edge** | still_forming (mfe null), intrabar_ambiguous, tek-bar çözüm, expired, tp2/tp3 price yok. |
| **Determinizm** | Date.now/random yok; aynı veri → aynı rapor. |
| **Yok** | Canlı/integration testi gerekmez (offline, yazma yok). |

---

## 12. Definition of Done (Phase 1)

- [ ] `python -m scripts.tm_replay_report` gerçek veride çalışıyor.
- [ ] **Fidelity check geçiyor** (replay FixedCurrent ↔ gözlenen realized).
- [ ] Rapor: segment başına "en iyi politika vs mevcut" + uplift veriyor.
- [ ] Kalibre adaptive scale-out eğrisi öneriliyor.
- [ ] Veri-yeterlilik açıkça raporlanıyor (hangi segment hazır).
- [ ] Canlı davranış **değişmedi**; yeni paket hiçbir sıcak yoldan import edilmiyor.

---

## 13. Phase 1 → Phase 2 devri

Phase 1 raporu "X politikası Y rejiminde mevcut'u Z R geçiyor" derse, Phase 2:
- Kalibre eğriyi/parametreleri `coin_memory.tm_policy`'ye yazan `AdaptiveLearner` (gated, fail-open, step-limit).
- `ManagementParams` aynı tip → replay'de doğrulanan politika **birebir** runtime'a taşınır ("öğrendiğin neyse onu uygula").
- Real-time PolicyEngine + TM StateMachine + LifecycleBridge (üst tasarım §7, §12).
