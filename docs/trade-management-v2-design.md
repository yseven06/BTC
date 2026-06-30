# Trade Management v2 — Mimari Tasarım & Teknik Karar Dokümanı

> Durum: **TASARIM** (implementasyon değil). Sistem freeze/gözlem modunda; bu doküman
> veri birikirken hazırlanır, yeterli veri oluşunca doğrudan implementasyona geçilir.
> Kod yazılmadı, davranış değişmedi. Kaynaklar: gerçek kod tabanı + 2026-06-28 Coin
> Memory Faz 2 checkpoint bulguları.

İlgili kalıcı kararlar: `memory/tm-v2-design-notes.md`, `memory/lifecycle-freeze-and-roadmap.md`.
Phase 1 implementasyon spec'i: `docs/trade-management-v2-phase1-spec.md`. Görsel diyagramlar (state machine + veri akışı) sohbet oturumunda üretildi; aşağıda §6 ve §3 ASCII karşılıkları.

---

## 0. Bir cümlede tez

TradeMinds bugün **statik** bir sinyal üretiyor (sabit entry/SL/TP1-2-3) ve çözümü **sabit-kodlu** bir
yönetim politikasıyla (TP1'de %50 çık + SL'i breakeven'a çek, TP2 %30, TP3 kalan) simüle ediyor.
**Trade Management v2**, bu yönetim politikasını (a) `signal_trade_path` üzerinde **offline karşı-olgusal
replay** ile *öğrenir*, (b) gerçek zamanlı olarak her aktif sinyale **insan trader gibi yönetim tavsiyesi**
üretir — hepsi **fail-open** ve **gözlem-amaçlı** (icra yok; kullanıcı tavsiyeyi uygular).

---

## 1. Checkpoint bulguları → tasarımı nasıl şekillendiriyor

| Bulgu (2026-06-28) | Tasarım sonucu |
|---|---|
| **TP1'e ulaşanların %72'si kazancı geri verdi** (`give_back=31/43`, `tp1_then_breakeven=30`). | Bu, mevcut **sabit "TP1 sonrası hard-BE"** politikasının doğrudan ölçümü. TM v2'nin **1 numaralı sınanacak hipotezi**: hard-BE yerine *trailing* / daha büyük TP1 scale-out / BE-after-TP2. Path verisi (`post_tp1_mfe_r`, `post_tp1_mae_r`, `mfe_r`) bunu replay etmeye yeter. |
| **Coin bazlı adaptif için veri yetersiz** (66 path, 0 hücre ≥20). | Öğrenme **hiyerarşik fallback** ile: `global → regime → (coin,tf)`. Coin seviyesi yalnız `MIN_SAMPLES` dolunca devreye girer; o ana kadar regime/global politika. |
| **`sl_before_tp` türetilecek, saklanmayacak.** | TM v2 analiz katmanı sıralamayı `cur_reached_tp1`, `intrabar_ambiguous`, `cur_bars_to_tp1` vs `bars_total`, `outcome`'dan üretir. Yeni kolon yok. |
| **Asıl gelecekteki boşluk: post-SL karşı-olgusal** ("SL sonrası TP'ye gider miydi?"). | Bar-walk SL'de `break` ediyor → stop-sonrası yol gözlenmiyor. **Phase 3**'te gözlem-amaçlı eklenecek; "SL çok mu dar" sorusunun tek doğru kaynağı. |
| %77 örnek 15m; 4h/1d çok ince. | TM v2 **önce 15m (gerekirse 1h)**; yüksek TF'ler "havuz politikasını miras alır". |

---

## 2. Tasarım ilkeleri (Faz 1 felsefesinin devamı)

1. **Observe, don't disturb.** TM v2 trade'in outcome'unu, seviyelerini veya çözümünü **asla** değiştirmez. Ürettiği şey *tavsiye/aksiyon önerisi* ve *öğrenilmiş politika parametreleri*.
2. **Policy-independent raw kalır kaynak.** `signal_trade_path` ham, politikadan bağımsız primitive'leri tutar (MFE/MAE in %/R/ATR, bar index'leri). Tüm politika kararları bunlardan **türetilir** (replay) — saklanmaz.
3. **Fail-open her yerde.** Her TM v2 hesabı try/except zarfında; hata → sabit varsayılan politikaya düş / tavsiye verme. Çözümü, coin_memory çekirdeğini, sinyal üretimini **asla bloklamaz**.
4. **Öğren, sonra uygula.** Önce offline replay ile en iyi politikayı bul; sonra gerçek zamanlıya bağla. Hiçbir parametre veriyle doğrulanmadan canlıya geçmez.
5. **Hiyerarşik güven.** Yeterli örnek yoksa daha genel seviyeye düş (coin→regime→global→sabit). `MIN_SAMPLES` kapıları.
6. **Versiyonlu.** Politika ve metrik tanımları `schema_version`/`policy_version` ile damgalanır; era karışmaz.

---

## 3. Genel mimari

```
                         ┌──────────────────────────────────────────────┐
                         │              SİNYAL ÜRETİMİ (mevcut)           │
                         │  signal_generator: entry/SL/TP1-2-3 (ATR'li)   │
                         └───────────────┬──────────────────────────────┘
                                         │ Signal + SignalSnapshot (doğum bağlamı)
                                         ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                        TRACKER (mevcut bar-walk, her 2 dk)                     │
   │  bar bazında: MFE/MAE, TP/SL tetikleme, intrabar_ambiguous, scale-out sim.    │
   │                                                                               │
   │   ┌── GERÇEK ZAMANLI ────────────┐        ┌── ÇÖZÜMDE (resolution) ────────┐  │
   │   │ TM v2 · Real-time Policy     │        │ signal_trade_path (immutable)  │  │
   │   │ Engine  → yönetim TAVSİYESİ  │        │ + coin_memory.tm_stats rollup  │  │
   │   └──────────────┬───────────────┘        └───────────────┬────────────────┘  │
   └──────────────────┼────────────────────────────────────────┼──────────────────┘
                      │ advisory (UI + lifecycle)               │ ham veri
                      ▼                                         ▼
        ┌─────────────────────────┐            ┌─────────────────────────────────┐
        │ LIFECYCLE (mevcut)       │            │ TM v2 · Adaptive Learning (OFFLINE)│
        │ active/weakening/        │◄───────────┤ counterfactual replay → en iyi   │
        │ invalidating/approaching │  koordine  │ politikayı öğren → coin_memory'ye │
        └─────────────────────────┘            │ tm_policy yaz (fail-open, gated) │
                                               └─────────────────────────────────┘
```

İki kalp: **(1) Offline Adaptive Learning** = beyin (politikayı öğrenir), **(2) Real-time Policy Engine** = eller (öğrenilen politikayı her aktif sinyale tavsiye olarak uygular). Aralarındaki köprü `coin_memory`.

---

## 4. Modüller & sorumlulukları

| Modül | Tip | Sorumluluk | Mevcut/Yeni |
|---|---|---|---|
| **PathReader** | offline+rt | `signal_trade_path` + `coin_memory.tm_stats`'tan metrik okuma; sıralamayı (`sl_before_tp`) türetme. | Yeni (saf okuma) |
| **PolicyInterface** | her ikisi | Bir yönetim politikasının sözleşmesi: `decide(state) → action`. Saf fonksiyon, durumdan aksiyona. | Yeni |
| **Policy katalog** | her ikisi | Somut politikalar: `FixedCurrent` (bugünkü 50/30/BE), `TrailAfterTP1`, `BEAfterTP2`, `ATRTrail`, `StructureTrail`. | Yeni |
| **CounterfactualReplayer** | offline | Bir path'i (ham OHLC değil; saklanan MFE/MAE/bar-idx primitifleri) verilen politikayla yeniden yürütüp realized-R üretir. Politikaları karşılaştırır. | Yeni (saf analiz) |
| **PolicyScorer** | offline | Replay sonuçlarını skorlar: expectancy (R), give-back oranı, PF, avg-R, max-MAE, hit dağılımı. Pooled → regime → coin. | Yeni |
| **AdaptiveLearner** | offline | En iyi politika + parametrelerini seçer; `MIN_SAMPLES` kapıları + decay; `coin_memory.tm_policy`'ye yazar (fail-open). | Yeni |
| **Real-time PolicyEngine** | rt | Her aktif sinyal için canlı durumu okur, öğrenilen (yoksa sabit) politikayı çalıştırır, **yönetim tavsiyesi** üretir. | Yeni |
| **TM StateMachine** | rt | Sinyal başına yönetim durumu (Entry→TP1→BE→TP2→Trailing→Exit). PolicyEngine'i sürer. | Yeni |
| **LifecycleBridge** | rt | TM aksiyonlarını lifecycle durumuyla koordine eder (INVALIDATING → kilitle/çık vb.). | Köprü |
| **TMAdvicePresenter** | rt | Tavsiyeyi UI'a + `signal_status_history`'ye yansıtır (gözlem). | Yeni |

> Hiçbiri sinyal üretimini, çözüm mantığını veya coin_memory çekirdeğini değiştirmez.

---

## 5. Veri akışı: Signal → Trade → Coin Memory → Adaptive Learning

```
Signal (entry/SL/TP, snapshot=doğum bağlamı)
   │  tracker bar-walk (her 2 dk)
   ▼
Trade path gözlemi  ── gerçek zamanlı ──►  Real-time PolicyEngine ──► Yönetim tavsiyesi (UI/lifecycle)
   │  çözümde (resolution)
   ▼
signal_trade_path (immutable ham primitive)  +  coin_memory.tm_stats (regime-keyed histogram rollup)
   │  offline (periyodik / checkpoint)
   ▼
CounterfactualReplayer × Policy katalog ──► PolicyScorer ──► AdaptiveLearner
   │  öğrenilen politika params (gated, fail-open)
   ▼
coin_memory.tm_policy  ──► (geri besleme) Real-time PolicyEngine bir sonraki sinyalleri bununla yönetir
```

**Gerçek zamanlı kol** (tracker her geçişte): canlı durum → tavsiye. **Offline kol** (checkpoint/periyodik): birikmiş path → öğrenilen politika. İkisi `coin_memory` üzerinden buluşur. Döngü kapalı ama **yavaş ve denetimli** (overfit'e karşı).

---

## 6. Trade Management State Machine

Sinyal başına yönetim durumu. **Observability lifecycle'dan AYRI** ama onunla koordineli (§12).

```
                 ┌─────────┐  fiyat entry bölgesine girdi
   (sinyal doğdu)│  ARMED  │──────────────► ┌─────────┐
                 └─────────┘                │ IN_TRADE│ (tam pozisyon, SL=ilk SL)
                                            └────┬────┘
                                  TP1 tetik │            │ SL tetik / INVALIDATING+derin retrace
                                            ▼            ▼
                                     ┌───────────┐   ┌────────┐
                                     │ SCALED_TP1│   │ STOPPED│ (çıkış)
                                     │ (kısmi çık│   └────────┘
                                     │  + SL yön.)│
                                     └─────┬─────┘
                       politika kararı ────┼──────────────────────────┐
                       (ÖĞRENİLEN)         ▼                           ▼
                                   ┌──────────────┐            ┌──────────────┐
                                   │ BREAKEVEN_LOCK│           │   TRAILING    │
                                   │ (SL=entry)    │           │ (SL=trail mes.)│
                                   └──────┬────────┘           └──────┬────────┘
                                          │ TP2/TP3 / retrace         │ TP2/TP3 / trail-stop
                                          ▼                           ▼
                                       ┌─────────────────── EXIT ───────────────────┐
                                       │  realized-R, give-back, exit nedeni kaydı   │
                                       └─────────────────────────────────────────────┘
```

**Kritik düğüm = SCALED_TP1 sonrası dallanma:** bugün **her zaman** `BREAKEVEN_LOCK` (SL=entry). Checkpoint diyor ki bu, kalanın %72 ihtimalle breakeven'a geri dönmesine yol açıyor. TM v2 bu dalı **öğrenir**: `BREAKEVEN_LOCK` mı, `TRAILING` mi, ne kadar TP1 scale-out, ne zaman BE — regime/coin'e göre.

| Durum | Bugünkü (sabit) davranış | TM v2'de ne öğrenilir |
|---|---|---|
| ARMED→IN_TRADE | entry bölgesine değince | (sabit) |
| IN_TRADE | SL=ilk SL; tam poz. | erken-çıkış: WEAKENING+rejim dönüşünde kısmi azalt? |
| SCALED_TP1 | TP1'de %50 çık, SL→entry | **scale-out oranı** (%? ), **BE vs trail** seçimi |
| BREAKEVEN_LOCK | SL=entry sabit | trailing'e mi geçilmeli, hangi koşulda |
| TRAILING | (yok) | trailing mesafesi (ATR/R/structure), aktivasyon eşiği |
| EXIT | TP2 %30 / TP3 kalan / SL / expiry | TP yerleşimi çarpanları, time-stop |

---

## 7. Policy Engine tasarımı

**Sözleşme (saf, durumdan-aksiyona, yan etkisiz):**

```
PolicyDecision = {
  action: HOLD | SCALE_OUT(frac) | MOVE_SL(price|rule) | TRAIL(distance_rule) | EXIT | NO_OP,
  reason: str,            # insan-okur ("TP1 sonrası ATR-trail; rejim trending_bull")
  confidence: float,      # politikanın bu durumdaki güveni (örnek sayısına bağlı)
  source: learned|fixed   # şeffaflık
}

Policy.decide(TradeState) -> PolicyDecision
```

`TradeState` (gerçek zamanlı, hepsi tracker'ın zaten hesapladığından): `direction, entry, sl, tp1/2/3, current_price, bars_elapsed, cur_mfe_r, cur_mae_r, hit_tp1/2/3, post_tp1_mfe_r, post_tp1_mae_r, regime, lifecycle_status, atr_pct`.

**Parametreli politika ailesi** (öğrenilen sayılar bu parametrelere oturur):

```
ManagementParams = {
  tp1_scale_frac,            # TP1'de çıkılacak oran (bugün 0.50)
  post_tp1_mode,             # BREAKEVEN | TRAIL
  trail_rule,                # ATR×k | R×k | structure(swing-low)
  trail_activate_at_r,       # trailing hangi R kârından sonra
  be_after,                  # TP1 | TP2  (BE'ye ne zaman geçilir)
  time_stop_bars,            # avg_bars_to_outcome'dan türetilir
  early_exit_on,             # {INVALIDATING, regime_flip} → kısmi/tam azalt
}
```

**Özellik:** Aynı `ManagementParams` hem (a) offline replay'de (politika karşılaştırma) hem (b) gerçek zamanlı tavsiyede kullanılır → **öğrenilen ile uygulanan birebir aynı politika**. Bu, "öğrendiğin neyse onu uygula" garantisini verir.

**Fail-open:** `tm_policy` yoksa/az-örnekliyse `FixedCurrent` (bugünkü 50/30/BE) varsayılanı; PolicyEngine hata verirse tavsiye gizlenir, trade etkilenmez.

---

## 7.5 Adaptive Scale-out Policy — AYRI KARAR MODÜLÜ ⭐

> **Kullanıcı kararı (2026-06-28):** TP1 scale-out oranı **kesinlikle sabit kalmayacak**. Mevcut tracker'daki sabit %50 (sonra hard-BE) → checkpoint'teki %72 give-back'in kök nedeni. **Özellikle TP1 girişe çok yakınsa** yüksek oranlı çıkış mantıksız: küçük kârı kilitleyip yukarıyı öldürür. Bu durumda **%20-30 düşük scale-out + kalan için trailing / TP2 devamı** daha doğru.

Bu yüzden TP1 scale-out, Policy Engine içinde **bağımsız bir karar modülü** (`scaleout.py`). Oran şu faktörlerin fonksiyonu:

| Faktör | Etki |
|---|---|
| **TP1↔entry mesafesi / `tp1_r`** (R = ödül/risk) | Çekirdek. `tp1_r` düşük → düşük frac (koştur); yüksek → yüksek frac (de-risk). |
| ATR% / volatilite | Aşırı vol → hafif↑ (belirsizlik). |
| coin geçmişi (`tm_stats`) | Yüksek geçmiş give-back → frac↑ (kârı al). |
| timeframe | Segment ekseni. |
| rejim | Segment ekseni (regime-keyed). |
| confidence / probability | Yüksek güven → frac↓ (koştur). |
| geçmiş give-back oranı | give-back↑ → frac↑. |
| TP1→TP2 devam olasılığı (`tm_stats.tp2/tp1`) | Yüksek → frac↓ (kalanı koştur). |

**R-tabanlı prior eğri** (policy-independent; `%` değil çünkü `%` vol'e göre yanıltıcı):

| `tp1_r` | base_frac | mantık |
|---|---|---|
| < 0.5 | **0.20** | TP1 girişe çok yakın → küçük çıkış + **trailing** (BE'ye kilitleme) |
| 0.5–1.0 | 0.33 | ılımlı |
| 1.0–1.5 | 0.50 | dengeli |
| 1.5–2.5 | 0.60 | anlamlı kazanç |
| > 2.5 | 0.70 | çoğunu al |

`frac = clamp(base_frac × giveback_mult × continuation_mult × vol_mult × conf_mult, 0.10, 0.70)`.
Kalan-mod: `tp1_r<0.5 → TRAIL`; `giveback↑ ∧ tp2_prob↓ → BREAKEVEN`; aksi halde `TRAIL`.

Prior eğri başlangıç; **Phase 1 replay bunu veriyle kalibre eder** (grid-sweep → expectancy max). Tam detay + sözde-kod: `docs/trade-management-v2-phase1-spec.md` §5.

---

## 7.6 TP1 Anlamlılığı (TP1 Significance) — MERKEZİ İLKE ⭐⭐

> **Kullanıcı gözlemi (2026-06-28):** Bazı sinyallerde TP1 entry'ye çok yakın. "TP1 alındı" deniyor ama gerçek P/L yalnızca **+%0.09** civarı. Bu, trader gözüyle **"anlamlı TP1" hissettirmiyor** ve kullanıcıda *trade mantığı zayıf* algısı yaratıyor. Bu, TM v2'nin hem **adaptive scale-out** hem **TP geometry** tasarımının **merkezi maddelerinden biri**.

**İlke:** TP1, "teknik olarak dokunulmuş bir çizgi" değil, **anlamlı bir kâr kademesi** olmalı.

**Anlamlılık ölçütü** (tek metrik değil, bileşik — hepsi policy-independent):
- **R-multiple** — `tp1_r = (tp1−entry)/(entry−sl)`. Çekirdek ölçü. `tp1_r` çok düşükse TP1 anlamsız küçük.
- **ATR mesafesi** — `tp1_atr = (tp1−entry)/ATR`. Volatiliteye göre normalize ("bu coin için bu mesafe gerçek mi?").
- **Volatilite/rejim** — aynı % farklı rejimde farklı anlam taşır.
- **Coin davranışı** — `tm_stats`: bu coin'de TP1 sonrası tipik koşu (`hist_mfe_r`), TP1→TP2 devam oranı.

**İki yanıt (birbirini tamamlayan):**

1. **Adaptive Scale-out (runtime, §7.5):** TP1 anlamsız-yakınsa (düşük `tp1_r`/`tp1_atr`) → **yüksek scale-out YAPMA**. Bunun yerine **düşük scale-out (~%20) + trailing veya TP2'ye devam** — küçük kârı kilitleyip pozisyonu öldürme. ("TP1 girişe çok yakınsa yüksek oranlı çıkış mantıksız.")

2. **TP Geometry (doğumda, signal_generator — Phase 3):** TP1'i **minimum anlamlı mesafe tabanıyla** yerleştir. Bugün `tp1 = current_price + 1.5×ATR` ama en yakın dirence snap edilince (`nearest_res`) TP1 entry'ye çok yakın düşebiliyor → asıl kök neden. Öneriler:
   - **TP1 floor:** `tp1_r ≥ MIN_MEANINGFUL_R` ve `tp1_atr ≥ MIN_ATR` garanti et; dirence snap sonucu taban altına düşerse → o direnci **TP1 olarak kullanma** (bir sonrakine taşı / TP1'i atla / TP1≈TP2 birleştir).
   - **Anlamsız-TP1 bayrağı:** taban sağlanamıyorsa sinyali "yakın-TP1" diye işaretle (scale-out modülü buna göre defansif davransın).

**Algı/etiketleme notu:** "TP1 alındı ama P/L +%0.09" görünümü kullanıcı güvenini zedeliyor → "TP1 reached" göstergesi **anlamlı yakalamayı** yansıtmalı (sadece çizgiye dokunmayı değil). UI ham "touch" yerine "anlamlı TP1" eşiğini kullanmalı. (UX detayı; çekirdek karar yine scale-out + geometry.)

**Phase 1 ölçümü:** Replay raporu, "TP1'e ulaşan path'lerin `tp1_r` ve gerçek-% dağılımını" çıkarır ve **küçük-P/L payını** (ör. realized < %0.2 olanlar) raporlar → kullanıcının gözlemini **veriyle niceler** ve `MIN_MEANINGFUL_R` tabanını kalibre eder (bkz. phase1-spec §8).

---

## 8. Adaptive Learning Engine tasarımı

**Girdi:** `signal_trade_path` (immutable). **Çıktı:** `coin_memory.tm_policy` (öğrenilen `ManagementParams` + skorlar + örnek sayısı + versiyon).

**Algoritma (offline, periyodik/checkpoint):**

1. **Segment:** path'leri `(coin, timeframe, regime)` ekseninde grupla; hiyerarşi `global ⊃ regime ⊃ (coin,tf,regime)`.
2. **Replay:** her segment için, Policy katalogundaki her aday politikayı `CounterfactualReplayer` ile tüm path'lerde yeniden yürüt → realized-R dağılımı. (Path primitiflerinden: MFE/MAE eğrisi yerine saklanan `mfe_r, mae_r, post_tp1_*, bar_idx`'ler + monoton excursion varsayımı; sınırları §16'da.)
3. **Skorla:** expectancy(R), give-back oranı, profit factor, avg-R, p25 R (sol kuyruk), max-MAE. **Birincil hedef = expectancy**, kısıt = give-back ve sol-kuyruk kötüleşmemeli.
4. **Seç + kapıla:** segmentte `n ≥ MIN_SAMPLES_TM` ise en iyi politikayı kabul et; değilse bir üst seviyeye düş. Değişimi **küçük adımlı** uygula (mevcut politikadan ani sapma değil; step-limit) — overfit/streak koruması.
5. **Yaz:** `coin_memory.tm_policy` (fail-open). Versiyonla + örnek sayısıyla.
6. **Decay/recency (Phase 3):** eski path'lere düşük ağırlık (rejim/piyasa değişimi).

**Eşikler** (mevcut `MIN_SAMPLES_FOR_ADAPTIVE=20` ile uyumlu):
- `MIN_SAMPLES_TM_REGIME = 40-50` (havuz/rejim politikası için)
- `MIN_SAMPLES_TM_COIN = 20` (coin,tf,regime adaptasyonu için — `MIN_SAMPLES_FOR_ADAPTIVE` ile hizalı)
- Altındaysa → bir üst seviyeye fallback.

---

## 9. Coin Memory: hangi alan nasıl kullanılır

| Alan | Okuyan | Kullanım |
|---|---|---|
| `tm_stats[regime].hist_mfe_r` | Learner | MFE dağılımı → TP yerleşimi / trailing aktivasyon eşiği. "Tipik koşu ne kadar?" |
| `tm_stats[regime].hist_mae_r` | Learner | MAE dağılımı → SL mesafesi / "stop çok dar mı" ön-sinyali. |
| `tm_stats[regime].{tp1,tp2,tp3,give_back,n}` | Learner | Give-back oranı → BE-vs-trail kararı; scale-out tuning. |
| `avg_bars_to_outcome` | Learner | `time_stop_bars` türetimi. |
| `regime_stats / wins / losses / total_signals` | Learner | Koşullu kenar; düşük-edge rejimde yönetimi daha defansif yap. |
| `adaptive_weights` (mevcut, engine ağırlıkları) | — | TM v2 **dokunmaz**; ayrı eksen (motor güveni). |
| **`tm_policy` (YENİ)** | Learner yazar / PolicyEngine okur | Öğrenilen `ManagementParams` + skor + n + version. Köprü alanı. |

`tm_policy` şekli (öneri — `tm_stats` yanında ayrı JSON kolon, veya `tm_stats["_policy"]`):
```
{ "_version": 1,
  "global":  {"params": {...}, "n": 312, "score": {...}},
  "trending_bull": {"params": {...}, "n": 58, "score": {...}},
  "<coin>|15m|ranging": {"params": {...}, "n": 24, "score": {...}}  # veri olunca
}
```

---

## 10. Öğrenilen vs sabit kararlar

| Karar | Öğrenilen (veriyle) | Sabit (guardrail / varsayılan) |
|---|---|---|
| TP1 scale-out oranı | ✅ regime/coin'e göre | başlangıç varsayılan %50 |
| TP1 sonrası mod (BE vs Trail) | ✅ | varsayılan BE (bugünkü) |
| Trailing mesafesi & aktivasyonu | ✅ (ATR×k / R×k) | makul aralık sınırları |
| BE zamanlaması (TP1 mi TP2 mi) | ✅ | TP1 |
| Time-stop (bars) | ✅ (`avg_bars_to_outcome`) | expiry (mevcut) |
| Erken çıkış (INVALIDATING/regime-flip) | ✅ eşik | açık/kapalı varsayılan |
| **Risk birimi (1R) tanımı** | ❌ | sabit (entry↔SL) |
| **SL'i pozisyon aleyhine genişletme** | ❌ — asla | yasak (guardrail) |
| **Min örnek kapıları, hysteresis, step-limit** | ❌ | sabit |
| **Fail-open fallback politikası** | ❌ | `FixedCurrent` |
| TP/SL doğum geometrisi (signal_generator) | ⏳ Phase 3 (en invaziv) | Phase 1-2'de sabit |

---

## 11. Gerçek zamanlı vs offline

| Bileşen | Gerçek zamanlı (tracker geçişi) | Offline (checkpoint/periyodik) |
|---|---|---|
| Canlı `TradeState` okuma | ✅ | — |
| Yönetim tavsiyesi üretimi | ✅ (öğrenilen params'ı uygular) | — |
| TM StateMachine güncelleme | ✅ | — |
| `signal_trade_path` yazımı | çözümde (mevcut) | — |
| `tm_stats` rollup | çözümde (mevcut) | — |
| Counterfactual replay + scoring | — | ✅ |
| `tm_policy` öğrenimi/yazımı | — | ✅ |
| Post-SL karşı-olgusal analiz | — | ✅ (Phase 3) |

İlke: **ağır öğrenme offline**, gerçek zamanlı kol yalnız *hazır params'ı okuyup uygular* (ucuz, deterministik, fail-open).

---

## 12. Lifecycle & Instrumentation entegrasyonu

- **Lifecycle (active/weakening/invalidating/approaching_tp) = gözlem/uyarı.** TM v2 = **yönetim overlay'i**. İkisi ayrı eksende, koordineli:
  - `INVALIDATING` + TP1 geçilmiş → TM: "kalanı BE/kısmi kilitle".
  - `WEAKENING` + `APPROACHING_TP` → TM: "kâr al / scale-out öne çek".
  - `APPROACHING_TP` → TM: "scale-out'a hazırlan".
- **LifecycleBridge** bu eşlemeyi tek yerde tutar; lifecycle eşiklerine/koduna **dokunmaz**, sadece okur.
- **Instrumentation (signal_trade_path) = TM v2'nin yakıtı.** TM v2 yeni bir ham alan *eklemez* (Phase 1-2); var olan primitiflerden türetir. Phase 3'te tek olası eklenti: post-SL karşı-olgusal (gözlem-amaçlı).
- **Observability:** TM tavsiyeleri `signal_status_history`'ye (veya ayrı ince bir TM-event akışına) gözlem olarak yazılabilir → sonradan "TM tavsiyesi doğru muydu?" analizi.

---

## 13. Fail-open prensibi nasıl korunur

1. Gerçek zamanlı PolicyEngine **try/except** zarfında; hata → tavsiye gizle, trade akışı etkilenmez.
2. `tm_policy` yok/az-örnek → `FixedCurrent` varsayılanına düş (bugünkü davranış birebir).
3. Offline Learner ayrı süreç/iş; çökerse canlı sistem etkilenmez, eski `tm_policy` kullanılır.
4. TM v2 **hiçbir** çözüm/outcome/coin_memory-çekirdek yazımını değiştirmez; yalnız `tm_policy` (yeni, izole) yazar — o da fail-open.
5. Phase 1 tamamen **offline analiz** → canlı sistemde sıfır risk (freeze ile uyumlu).

---

## 14. Trade Path & Coin Memory'den okunan metrikler

**`signal_trade_path` (replay/öğrenme):** `mfe_r, mae_r, mfe_atr, mae_atr, mfe_bar_idx, mae_bar_idx, bars_total, sl_dist_pct, atr_pct_at_signal, regime, direction, outcome, detail_label, cur_reached_tp1/2/3, cur_bars_to_tp1, cur_post_tp1_mae_r, cur_post_tp1_mfe_r, cur_gave_back_after_tp1, cur_realized_return, intrabar_ambiguous, still_forming_resolution, schema_version, source`.

**Türetilenler (saklanmaz):** `sl_before_tp` (← `cur_reached_tp1` + `intrabar_ambiguous` + `cur_bars_to_tp1`/`bars_total` + `outcome`); ordering, whipsaw bayrağı, clean-win bayrağı.

**`coin_memory` (politika/segment):** `tm_stats[regime].*`, `avg_bars_to_outcome`, `regime_stats`, `total_signals/wins/losses`, **`tm_policy` (yeni)**.

---

## 15. "İnsan gibi trade yönetimi" eşlemesi

Kullanıcının hedefi: profesyonel bir trader gibi davranan yönetim. Eşleme:

| İnsan trader davranışı | TM v2 mekanizması |
|---|---|
| "Kârı koru, geri verme" | Give-back metriği birincil kısıt; TP1 sonrası trailing/scale-out öğrenimi (checkpoint'in 1 numaralı bulgusu). |
| "Kazananı bırak koşsun" | `hist_mfe_r` → trailing aktivasyonu; erken hard-BE yerine koşu izni. |
| "Kaybedeni çabuk kes" | INVALIDATING/regime-flip erken-çıkış; time-stop. |
| "Pozisyonu kademeli azalt" | Öğrenilen scale-out oranları (sabit 50/30 değil). |
| "Volatiliteye/rejime göre adapte ol" | regime-keyed politika; `atr_pct`/`volatility_ratio` ile trailing mesafesi. |
| "Stop'a takılıp tersine dönme (whipsaw)" | `mae_r`≈1 + yüksek `mfe_r` analizi + **post-SL karşı-olgusal** (Phase 3) → "SL çok mu dar". |
| "Sezgi değil, geçmiş performans" | Tüm parametreler veriyle öğrenilir, örnek-kapılı, açıklanabilir (`reason`). |

---

## 16. `sl_before_tp` & post-SL karşı-olgusal (kilitli kararlar)

- **`sl_before_tp`:** doldurulmaz; gerektiğinde §14'teki alanlardan türetilir. (Detay: `memory/tm-v2-design-notes.md`.)
- **Replay'in sınırı (dürüst not):** Saklanan primitifler max-excursion (MFE/MAE) ve bunların bar-index'leri; **tam intrabar yol değil**. Bu yüzden bazı politikalar (örn. tam trailing eğrisi) için replay *yaklaşık*tır. Bunun sonuçları:
  - Monoton/■tek-tepe varsayımıyla iyi tahmin edilen politikalar: scale-out oranı, BE-after-TP1-vs-TP2, time-stop. (Phase 1 bunlara odaklan.)
  - Tam intrabar yol gerektirenler (sıkı ATR-trailing) için → çözümde ek primitive (örn. trailing-replay için "drawdown-from-peak serisi"nin özetini) ya da bar-walk içi opsiyonel gözlem (Phase 3) düşünülür.
- **Post-SL karşı-olgusal (asıl yüksek ROI):** bar-walk SL'de `break` ettiğinden stop-sonrası N-bar yol gözlenmiyor. Phase 3'te gözlem-amaçlı (outcome'u değiştirmeyen) "post-SL takip" → "SL çok mu dar / whipsaw" sorusunun tek doğru cevabı.

---

## 17. Fazlı implementasyon planı

### Phase 1 — Offline Replay & Policy Harness  *(saf analiz; freeze ile tam uyumlu; davranış değişmez)*
- `PathReader`, `PolicyInterface`, Policy katalog (`FixedCurrent`, `TrailAfterTP1`, `BEAfterTP2`, `ATRTrail`), `CounterfactualReplayer`, `PolicyScorer`.
- Çıktı: **"Politika karşılaştırma raporu"** — mevcut sabit 50/30/BE'yi alternatiflerle kıyasla (pooled → regime). Özellikle: hard-BE vs trailing give-back/expectancy farkı.
- **Kapı:** Coin Memory Faz 2 checkpoint (~250-300 path; her rejim ≥40-50). Veri yetince koş.
- Risk: sıfır (canlıya yazmaz).

### Phase 2 — Learned Policy Store + Real-time Advisory  *(gözlem; icra yok)*
- `coin_memory.tm_policy` şeması + `AdaptiveLearner` (gated, fail-open, step-limit).
- Real-time `PolicyEngine` + `TM StateMachine` + `LifecycleBridge` + `TMAdvicePresenter`.
- Her aktif sinyal için **insan-okur yönetim tavsiyesi** (UI'da; "TP1 sonrası ATR-trail, çünkü trending_bull'da give-back %X").
- Fail-open: `tm_policy` yok → `FixedCurrent`; hata → tavsiye gizli.
- Risk: düşük (yalnız tavsiye + izole `tm_policy` yazımı).

### Phase 3 — Adaptive Refinement + Post-SL Counterfactual + Geometri Geri-beslemesi
- Coin,tf bazlı adaptasyon (veri dolunca); decay/recency; rejim-split.
- **Post-SL karşı-olgusal instrumentation** (gözlem-amaçlı, fail-open) → "SL çok dar mı".
- (En invaziv, en son) Öğrenilen TP/SL geometrisini **signal_generator**'a geri besle (doğumdan itibaren daha iyi seviyeler) — **TP1 anlamlılık tabanı dahil** (§7.6: `tp1_r ≥ MIN_MEANINGFUL_R`, dirence-snap anlamsız-yakın TP1 üretiyorsa düzelt). Ayrı onay/ölçüm döngüsü gerekir.
- Risk: artан → her alt-adım kendi A/B ölçümüyle.

---

## 18. Açık riskler & kararlar (implementasyon öncesi netleştirilecek)

1. **Replay sadakati** (§16): MFE/MAE özetinden tam trailing replay yaklaşık. Phase 1 bunu kabul eden politikalarla başlasın; tam-yol gereken politikalar için Phase 3'te ek özet primitive kararı.
2. **Tavsiye mi, otomatik geometri mi?** Phase 2 = sadece tavsiye (kullanıcı uygular). Geometriyi otomatik değiştirmek (Phase 3) ayrı, denetimli karar.
3. **`tm_policy` konumu:** yeni JSON kolon mu, `tm_stats["_policy"]` mı (migration maliyeti vs izolasyon). Phase 2 başında karar.
4. **Örnek eşikleri** (`MIN_SAMPLES_TM_*`) ilk replay raporundan kalibre edilecek — şimdilik 40-50 (regime) / 20 (coin) öneri.
5. **Komisyon/fee modellemesi — KAPSAM DIŞI (kullanıcı kararı 2026-06-28):** Binance/MEXC gibi borsa fee detayları modele eklenmeyecek; gereksiz kalabalık. TM v2 skorlaması saf fiyat-yolu R'si üzerinden çalışır (fee'siz). Asıl odak "anlamlı TP1 / give-back" (§7.6), küçük fee aşınması değil.

---

*Sonraki tetikleyici: Coin Memory Faz 2 checkpoint (`scratch/coinmem_health.py` mantığı) eşikleri tutunca → Phase 1 (offline replay raporu) implementasyonuna geç.*
