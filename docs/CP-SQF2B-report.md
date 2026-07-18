# CP-SQF-2B — Coin / Symbol-tier Outcome Forensic (shadow, read-only)

**Tarih:** 2026-07-18 · **Statü:** shadow/offline karar-desteği (davranış değişikliği YOK)
**Script:** `backend/scripts/sqf2b_coin_tier.py` (read-only; DB'ye yazmaz; deterministik — art arda koşularda byte-identical)
**Veri:** canlı DB · kapalı sinyaller · 2552 sinyal · **58 coin** · generated_at 5 ISO-hafta (W25–W29)

---

## Executive conclusion

Coin bazında **in-sample dispersyon çok güçlü** (stop-rate TRX %2.3 ↔ ALGO %56.5) **ama actionable bir coin-tier edge'i YOK.** Üç bağımsız test bunu gösteriyor: (1) coin-kötülüğü zamanla **kalıcı değil** (erken↔geç yarı Spearman: stop-rate ρ=**0.21**, PF ρ=**0.37** — zayıf; birçok coin yarıyı flip ediyor, ör. ARB %9→%52); (2) **zaman-dürüst blacklist** (bad coin'i erken haftadan seç, geç haftada uygula) OOS'ta en iyi ihtimalle **+0.036 PF** kazandırıyor (geç-dönem 0.971→1.007, ancak yalnız breakeven'ı geçiyor ve **−%18 hacim**); stop-eşikli tanımlar neredeyse sıfır (+0.005); (3) dispersyon **kısmen volatilite-confound'u** (Spearman atr↔stop=0.26 zayıf; düşük-ATR major'lar net iyi ama yüksek-ATR üniform kötü değil).

**KARAR: Coin-tier canlı davranış değişikliği (blacklist/cooldown/threshold) ÖNERİLMİYOR.** Dispersyon büyük ölçüde **örneklem yanılsaması + kısmi vol-confound**; kalıcı coin-alpha kanıtı yok. Bu, önceki forensic'in ("kısıt=alpha, coin-alpha p=0.069 underpowered, sıralama stabil ama etki küçük") ve gözlem-modu kararının doğrulanmasıdır.

---

## A. Evren

- Kapalı: 2552 · coin: 58 · hafta: W25–W29 · **Baseline (tüm):** stop %38.9 · win %36.6 · TP1 %55.2 · PF **0.93** · avgR −0.045 · medR +0.247.
- **Skor per-coin de ayrıştırmıyor:** her coin'in ortalama confidence'ı ~71–73 (kötü ALGO 71.6 ≈ iyi BTC 73.4); risk ~5.0–5.6. Yani coin kimliği skorlara yansımıyor (2A ile tutarlı).

## B. Per-coin tablo (özet; tam tablo script stdout'unda)

**En KÖTÜ (stop%, n≥40):** ALGO 56.5 (PF 0.64) · ICP 54.7 (0.44) · DYDX 52.9 (0.63) · APE 51.6 (0.60) · GMT 50.0 (0.47) · SOL 48.8 (0.81) · ATOM 46.7 (0.58) · FET 46.3 (0.80).
**En İYİ (n≥40):** TRX 2.3 (PF 1.65) · BTC 16.2 (1.62) · GALA 27.5 (1.37) · AAVE 26.8 (2.23) · BCH 24.4 (2.35) · IMX 32.7 (1.52) · EGLD 32.6 (1.73) · RUNE 31.7 (1.49).

## C. Sample tiers + 4 kategori

- **Tier:** large (n≥40): 40 coin · medium (20–39): 17 · <20: 1.
- **C1 · clearly-harmful ADAYLARI** (large n, stop≥48%, PF<0.85, *in-sample*): **ALGO, ICP, DYDX, APE, GMT, SOL**.
- **C2 · neutral/no-edge** (large n, PF 0.88–1.12): LPT, RVN, UNI, ARB, KNC, OP, ETH, SAND, ETC.
- **C3 · potentially-useful ama sample-limited** (PF≥1.15, n<40): DOT(35), MINA(30), DOGE(31), 1INCH(39), COTI(39), XLM(37), ADA(25), XRP(31), BTC(37).
- **C4 · needs-more-data** (n<20): 1 coin.

> ⚠️ C1 "clearly-harmful" **yalnız in-sample** — [D]/[E] gösteriyor ki bunların çoğu kalıcı değil.

## D. Persistence — erken yarı vs geç yarı (W27'de bölme)

- Her iki yarıda ≥10 sinyali olan **31 coin.**
- **Spearman rank-korelasyon (erken↔geç): stop-rate ρ=0.2084 · PF ρ=0.3718.** → **ZAYIF.** Coin-kötülüğü zamanla güçlü biçimde taşınmıyor → büyük ölçüde örneklem yanılsaması.
- **50% stop çizgisini flip eden coinler:** APE 44→56, SOL 40→54, RVN 31→54, APT 50→33, **ARB 9→52**, UNI 50→42, GMT 33→55, ETC 50→25. Yüksek instabilite; ARB erken %9 stop'tan geç %52'ye — coin-geçmişine bakarak karar vermenin tehlikesi.

## E. Zaman-dürüst blacklist OOS testi (KARAR verici)

Bad coin'i **yalnız erken haftalardan** seç, **geç haftalarda** uygula (leakage-güvenli). Geç-dönem baseline: n=1913, stop %41.0, **PF 0.971**.

| Bad tanımı (erken) | Elenen coin | Geç kept PF | Δ PF | Korunan hacim |
|---|---|---|---|---|
| erken stop≥45% (n≥15) | 2 (DYDX, UNI) | 0.976 | **+0.005** | %95.2 |
| erken stop≥50% (n≥15) | 2 (DYDX, UNI) | 0.976 | +0.005 | %95.2 |
| erken stop≥55% (n≥15) | 0 | 0.971 | 0.0 | %100 |
| **erken PF<0.9 (n≥15)** | 9 | **1.007** | **+0.036** | **%81.8** |

→ En iyi durum (PF<0.9 tanımı) geç-dönem PF'ini 0.971→**1.007**'ye taşıyor (breakeven'ı *ancak* geçiyor) ama **%18 hacim** feda ediyor ve **tek bir bölmeye** dayanıyor (walk-forward tekrarı yok). Stop-eşikli tanımlar neredeyse **sıfır** kazanç. Actionable, sağlam bir edge değil.

## F. Beta / volatilite confound

- 57 coin (n≥20) üzerinde: **Spearman(atr_pct, stop-rate) = +0.2573** · Spearman(atr_pct, PF) = **−0.0954** → yüksek-ATR coin'ler *hafifçe* daha kötü, ama **zayıf** korelasyon.
- En düşük-ATR coin'ler **üniform iyi** (TRX 0.15/%2.3 · BTC 0.41/%16.2 · XRP 0.48/%19.4 · BNB 0.37/%30) → likidite/major etkisi net. Ama yüksek-ATR **üniform kötü değil** (ADA 1.16/%24 · AAVE 1.13/%27 iyi; ALICE 1.55/%39.5 orta).
- → Dispersyonun **bir kısmı** volatiliteyle açıklanıyor (özellikle major'ların iyiliği = düşük-vol/yüksek-likidite), ama coin-badness ≠ salt ATR. Yani "coin-tier" ≈ kısmen "vol/likidite-tier" — coin-spesifik alpha değil.

## Net verdict (6 soru)

1. **Coin-tier edge var mı?** — **Actionable edge YOK.** In-sample dispersyon büyük ama persistence zayıf (ρ 0.21), OOS blacklist marjinal (+0.036 PF, breakeven), kısmi vol-confound. Sıralama kısmen stabil ama ekonomik olarak sömürülebilir değil.
2. **Hangi coinler zarar üretiyor?** — In-sample en kötü: ALGO/ICP/DYDX/APE/GMT/SOL/AUDIO/LPT. Ama **yalnız DYDX** (ve PF'e göre UNI) hem erken hem geç yarıda kötü kalıyor + yüksek ATR. Diğerleri kalıcı değil → "clearly harmful" olarak kanıtlanan tek aday **DYDX** (o da sınırda).
3. **Hangi coinlerde sadece sample illusion var?** — Küçük-n yıldızlar (ADA n25, XRP n31, MINA n30, DOGE n31, DOT n35, XLM n37, BTC n37) + yarı-flip edenler (ARB %9→%52, RVN %31→%54, APT, ETC, UNI). C1'in çoğu da in-sample-kötü/OOS-kalıcı-değil.
4. **Hangi coinler shadow watchlist'e alınabilir?** — En fazla **DYDX** (kalıcı-zayıf + yüksek ATR) = *WATCH* (blacklist değil). Düşük-vol major'lar (BTC/XRP/TRX/BNB) "güvenilir tier" gözlemi olarak izlenebilir ama bu likidite/vol etkisi, alpha değil ve trade hacmini çok kısar. **Blacklist gerekçesi yok.**
5. **Canlı davranış değişikliği öneriliyor mu?** — **HAYIR.** Gerekçe: OOS kazanç marjinal (+0.036, breakeven), tek-bölme (walk-forward-sağlam değil), vol-confounded, persistence zayıf. Kör blacklist örneklem yanılsamasını ezberler (ARB örneği). Kısıt coin kimliği değil, **alpha**.
6. **CP-SQF-2C için önerilen sonraki başlık:** Planlı **valid-entry / never_entered ölçümü** (Hat-2). Not: 2A (skor edge yok) + 2B (coin edge yok) birlikte "kısıt=alpha, veri biriktir" sonucunu güçlendirir; 2C muhtemelen entry-fill'in de baskın sorun olmadığını doğrulayıp SQF ölçüm serisini kapatır → seri-verdict F1-a reopen kapısını besler.

---

## Ek — bağımsız doğrulama (adversarial SQL, ≥2 yöntem)

Script'e güvenmeden, her manşet ≥2 bağımsız SQL yöntemiyle yeniden-türetildi (2 verifier agent + 1 self-SQL). Hepsi **CONFIRM**:

| İddia | Yöntem 1 | Yöntem 2 | Verdict |
|---|---|---|---|
| Persistence zayıf (Spearman stop ρ≈0.21, PF ρ≈0.37) | rank()+corr() → stop ρ **0.212** · PF ρ **0.365** (31 coin) | 50%-çizgi sayımı: 31 coin'den her iki yarıda kötü=**2**, flip=**8**, erken-bad→geç-bad yalnız 2/5 | **CONFIRM** |
| Zaman-dürüst blacklist marjinal (geç PF 0.971→~1.007, ~%82 hacim) | erken PF<0.9 (n≥15) → **9 coin**; geç PF **0.973→1.008** (Δ+0.035), korunan **%81.8** | elenen dilim: n=349 (%18.2), PF **0.85**, net-negatif → iyileşme yalnız net-negatif dilimi kesmekten | **CONFIRM** |
| Vol-confound kısmi (Spearman atr↔stop≈0.26) | rank()+corr(): Spearman(atr,stop)=**0.2516**, Spearman(atr,PF)=**−0.0946** (57 coin) | düşük-atr major'lar üniform iyi (TRX/BTC/XRP/BNB) ama yüksek-atr karışık (ADA/AAVE iyi) → confound zayıf | **CONFIRM** (self-SQL; 3. agent StructuredOutput hatası) |

Not: verifier baseline'ları canlı tabloda +1 sinyal drift'i ve rank-tie yöntem farkıyla script'ten yalnız yuvarlama düzeyinde ayrılıyor (0.971 vs 0.973; 0.2573 vs 0.2516) — sonucu değiştirmiyor.

## Ek — çalıştırma

`cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/sqf2b_coin_tier.py`
Read-only · DB'ye yazmaz · davranış değiştirmez · deterministik. Leakage-güvenli: zaman-dürüst testte bad coin yalnız geçmiş haftalardan tanımlanır, gelecek haftalarda değerlendirilir; outcome/return yalnız label.
