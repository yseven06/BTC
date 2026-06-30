# P0.6 — TP/SL & Risk Management — KAPANIŞ RAPORU

**Tarih:** 2026-06-30 · **Statü:** KAPANDI (KEY2 hariç → policy fazına ertelendi)

## 1. Yapılanlar (commit'ler)
**Audit:** 23-ajan adversarial workflow → **14 doğrulanmış bug** (2 over-claim reddedildi).

**BP2-güvenli düzeltmeler (geçerli girdide byte-identical):**
- `85aa27c` BUG-12 Sortino sahte-oran + BUG-13 short max-drawdown (rapor-only).
- `71dac34` BUG-4 risk_score 1-10 sözleşmesi + BUG-5 pozisyon-boyutu None-guard + D5 fail-loud risk_level.
- `901adff` BUG-1 sıfır-ATR çökmesi → tek-kaynak `safe_last_atr`.

**Zengin telemetri (additive, motor sabit):**
- `73ab31c` SignalTradePath.extra — 26 türetilen metrik (`build_trade_path_extra`, tek-kaynak `_safe_div`).
- `d560361`+`bb4c9b0`+`e827c65` birth telemetri — `extra.birth` (38 alan), `SignalSnapshot.extra` (migration 0004 uygulandı+stamp), fail-open.

**Read-only analitik:**
- `fc0d9f0` `/analytics/tpsl-quality` + `/analytics/risk-scale-audit` (tek-kaynak `tpsl_analytics`).
- `6a210de` (C) calibration-readiness gate (`sample.calibration_ready`).

**KEY1 — tek source-of-truth resolution çekirdeği (b1→d):**
- `753f858`→`8cc40a8`→`348e87d` canlı tracker → `resolution_core.step_bar` (byte-identical: golden 8 + differential 8000 + mapping 3000).
- `07b751f`→`583f53c`→`9589382`→`87b6540` backtest → `step_bar` (per-trade 9000 + uçtan-uca SHA256-identical).
- `8e94dd8` execution_model validator + bias doc.
- `8ddf13c` KEY1-c backtest D2/D3 canlı-metodoloji hizalama (before/after raporlu).
- `2247817`→`1d984e9`→`65f6922` KEY1-d canlı-SL scale-out fix (BUG-6/7/8, ileri-dönük, schema_version=2, v1-predicate).

## 2. Before/After özet
- Düzeltmeler: geçerli girdide byte-identical; yalnız dejenere/hata yolları düzeltildi.
- Telemetri/analitik: additive, motor davranışı değişmedi.
- KEY1-c (backtest D2/D3): backtest sayıları **bilinçli** canlı-metodolojiye hizalandı (regresyon değil).
- KEY1-d (canlı-SL): TP1-bankalı sinyaller artık doğru (BE'de kapanış), TP1-yok byte-identical.

## 3. Test/doğrulama (hepsi PASS)
golden 8/8 · differential 8000/8000 · mapping 3000/3000 · backtest-equivalence 9000/9000 ·
live_sl 7/7 · uçtan-uca backtest SHA256-identical · canlı smoke'lar (BUG-1 atr==0=0, risk_score
[1,10], birth wiring, live-SL etkin-stop). resolution_core/step_bar/trade_path/backtest/canlı
parity korundu.

## 4. Riskler / edge-case'ler
- Bekleyen canlı-e2e: yok (P0.6 keyless tamamlandı). Birth telemetri canlı doldurma organik
  (sonraki generation). Mobil/Lighthouse → P0.5 (Antigravity).
- v1-çelişkili live-SL satırı canlıda **0** (kontaminasyon yok).

## 5. KEY2 → DEFERRED (policy fazı)
min-TP1/SL floor (BUG-2/3) + risk-boundary/forex/asset retune = TP/SL üretim politikası + R:R
alanı → **KEY1 sonrası ayrı policy fazı** (kullanıcı kararı) + veri-gated (193/~250-300).
calibration_ready=True olunca açılacak. Detay: docs/KEY2-analysis.md.

## 6. Tüm açık P0.x madde incelemesi
| Madde | Durum | Not |
|---|---|---|
| **P0.1 Stripe Subscription** | ✅ Kod (S1-S6) · ⏳ S7 canlı e2e | S7 kullanıcının Stripe test anahtarlarını bekliyor |
| **P0.2 Per-user Notifications** | ✅ TAMAM | — |
| **P0.3 Turnstile** | ✅ Kod · ⏳ tam canlı e2e | Cloudflare anahtarları (kullanıcı) |
| **P0.4 Deploy/Prod/Beta** | ✅ Keyless TAMAM · ⏳ gerçek yayın | env değerleri + Legal v1.0 |
| **P0.5 Mobil + PWA** | ✅ Kod TAMAM · ⏳ gerçek-cihaz/Lighthouse | Antigravity |
| **P0.6 TP/SL & Risk** | ✅ KAPANDI (audit+fix+telemetri+analitik+KEY1) · KEY2 DEFERRED | bu rapor |
| **P0.7 Coin Memory v2** | 🔶 SIRADAKİ (hazırlık analizi) | data-gated (193→250-300) |
| **P0.8 Adaptive v2** | ⏳ | data-gated, policy |
| **P0.9 Similarity v2** | ⏳ | data-gated |
| **P0.10 Landing dönüşüm** | ⏳ | — |
| **KEY2 (P0.6'dan)** | ⛔ DEFERRED → policy fazı | data-gated + üretim-politikası |

**Bekleyen canlı-e2e (kullanıcı kaynak/anahtar):** Stripe S7 · Turnstile tam akış · gerçek prod
yayın (env+Legal) · mobil/Lighthouse (Antigravity).
