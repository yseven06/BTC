# Roadmap Yeniden Değerlendirme — 2026-06-30 (ANALİZ, kod YOK)

**Amaç:** Güncel durum matrisi + bağımlılıklar + tamamlananlar/ertelenenler + yeni öncelik önerisi
+ kısa/uzun vade etkileri. **Kalıcı öncelikler korunur:** 1) Lifecycle v2 · 2) Coin Memory v2 ·
3) Similarity v2 · 4) Adaptive Learning v2.

## 0. Yönetici özeti (tek paragraf)
Dört kalıcı zekâ-önceliğinin **veri-bağımsız ALTYAPISI büyük ölçüde tamamlandı**; ama hepsinin
**POLİTİKA/davranış çekirdeği yeknesak biçimde VERİ-GATED** (~200 trade_path var; gereken ~250-300 +
per-cell yoğunluk; adaptive 130 hücreden 2 aktif). Veri-kilidini açan tek şey **beta** → beta ise
**senin sağlayacağın anahtarlar/Legal bilgisiyle BLOKE**. Sonuç: daha fazla zekâ-v2 altyapısı azalan
getiri; gerçek darboğaz **beta + veri**. Bağımsız ilerletilebilir en yüksek değer = **P1.1 TP/SL & R:R
(veri-bağımsız sinyal-kalitesi)** — KEY1 bunu açtı, backtest artık geçerli gate, ve **beta öncesi
yapılırsa beta verisi daha kalibre mantıkla birikir** (zekâ-v2'nin öğreneceği veri kalitesi artar).

## 1. Güncel durum matrisi
| Faz | Tier | Statü | Bağımlılık | Gate / Bloke |
|---|---|---|---|---|
| P0.1 Stripe sub | P0 | Kod S1-S6 ✅ · S7 e2e ⏳ | — | **Senin Stripe anahtarların** |
| P0.2 Per-user notif | P0 | ✅ **TAMAM** | — | — |
| P0.3 Turnstile | P0 | Kod ✅ · e2e ⏳ | — | **Senin Cloudflare anahtarların** |
| P0.4 Deploy+Beta | P0 | Keyless ✅ · yayın ⏳ | P0.1/0.3 | **env değerleri + Legal v1.0 (şirket bilgisi)** |
| P0.5 Mobil+PWA | P0 | Kod ✅ · cihaz doğrulama ⏳ | — | **Antigravity (gerçek cihaz/Lighthouse)** |
| **BETA AÇILIŞI** | P0 | ⏳ **KEYSTONE** | P0.1/0.3/0.4/Legal | **Senin anahtarların + şirket bilgisi** |
| P1.1 **TP/SL & R:R** | P1 | ⛔ ertelendi (policy) | **KEY1 ✅** | Davranış-değişimi (onay+backtest); floor kısmı veri-gated |
| P1.2 Lifecycle aksiyon | P1 | ✅ **backend TAMAM** | P0.2 ✅ | P12-4 frontend → backlog |
| P2.1 Sinyal eşik kalibrasyonu | P2 | ⛔ | beta verisi | **veri-gated** |
| P2.2 **Coin Memory v2** | P2 | M1+M2 ✅ · M3 ⛔ | trade_path + P1.1 | **veri-gated (M3 ≥250-300)** |
| P2.3 **Adaptive Learning v2** | P2 | A8-1 ✅ · politika ⛔ | beta + ölçüm | **veri-gated (2/130 aktif)** |
| P2.4 **Similarity v2** | P2 | ⛔ başlanmadı | veri + perf | **veri/ölçek-gated (ANN premature)** |
| P2.5 Lifecycle kalibrasyon | P2 | ⛔ | resolved veri | **veri-gated** |
| P3.1 Landing dönüşüm | P3 | ⛔ | **beta trafiği** | ölçülecek dönüşüm yok |
| P3.2 Perf & ölçeklenebilirlik | P3 | ⏳ ilerletilebilir | — | veri-bağımsız (ama P3 tier) |
| P3.3 BIST tam açılış | P3 | Pilot 5/38 ✅ | Pro plan ✅ | egress/polling analizi (ilerletilebilir) |
| P4 İşlem yürütme | P4 | ⛔ greenfield | ayrı legal track | **Phase 3'e ertelendi** |

## 2. Tamamlananlar (bu oturum + öncesi)
- **P0.2** per-user notifications · **P0.6** TP/SL & Risk audit + BP2-güvenli fix + telemetri +
  analitik + **KEY1 (b1→d)** tek-kaynak resolution (golden/diff/mapping/backtest byte-identical).
- **P0.7 Coin Memory v2 M1+M2** (fold-hardening + additive tm_stats + drop&rebuild + read-only reader).
- **P0.8 Adaptive v2 A8-1** telemetri kancası (byte-identical).
- **P1.2 Lifecycle aksiyon katmanı backend** (opt-in + formatter + fan-out + tracker hook).
- Keyless kod: P0.1 (S1-S6), P0.3, P0.4, P0.5.

## 3. Ertelenenler (+ neden)
- **KEY2** (min-TP1/SL floor + risk-retune) → policy fazı + **veri-gated** (≥250-300).
- **CM v2 M3** (Similarity besleme + ince dilim) → **veri-gated** (per-cell 1 hücre eşik üstü).
- **Adaptive v2 politikası** → **veri-gated** (2/130 aktif) + BP2.
- **P1.1 TP/SL & R:R** → "KEY1 sonrası policy fazı" (KEY1 artık BİTTİ → kilit kalktı).
- **P12-4** Lifecycle frontend/metrics → UX/observability backlog.
- **P4** işlem yürütme → Phase 3 (legal).

## 4. Kritik bağımlılık zinciri (THE bottleneck)
```
Senin anahtarların/Legal bilgisi  ─►  BETA AÇILIŞI  ─►  gerçek kullanıcı + çözülmüş sinyal verisi
                                                              │
        ┌─────────────────────────────────────────────────────┼─────────────────────────────┐
        ▼                         ▼                            ▼                              ▼
  P2.2 CM v2 M3            P2.3 Adaptive v2 politika     P2.4 Similarity v2 (ANN)     P2.1/P2.5 kalibrasyon
```
→ **4 kalıcı önceliğin POLİTİKASI da aynı veri-kapısına bağlı.** Zekâ-v2 altyapısını daha fazla
itmek (infra zaten hazır) **azalan getiri**; çekirdek darboğaz **beta + veri**.

## 5. Yeni öncelik önerisi
**Analiz, gerçek bir öncelik nüansı ortaya koyuyor** (senin "ancak analiz gerçekten gerektiriyorsa"
şartını karşılar): **P1.1 (TP/SL & R:R) artık veri-bağımsız ilerletilebilir TEK yüksek-değer çekirdek
faz** — çünkü (a) **KEY1 kilidi kaldırdı**, (b) backtest **geçerli BP2 gate**, (c) roadmap'in kendi
uyarısı: *"beta verisi kalibre edilmemiş mantıkla birikir"* → P1.1'i **beta ÖNCESİ** yapmak, 4 zekâ-
önceliğinin sonradan öğreneceği **veri kalitesini artırır**. P1.1'in floor-kalibrasyonu veri-gated
kalır; ama R:R-açık-filtre / SMC OB-FVG entry / TP-sıralama-koruması **veri-bağımsız**.

**Sıralama önerisi (öncelikler korunur):**
1. **P1.1 veri-bağımsız sinyal-kalitesi** (davranış-değişimi → analiz+onay+backtest before/after). *Beta-öncesi veri kalitesini yükseltir.*
2. **Beta-hazırlık sertleştirme** (bağımsız yapılabilen kısım): backend dep bump + fastapi yükseltme, Legal metinlerini SPK/KVKK/ETK best-practice'e taşıma (yalnız şirket-bilgisi sana bağlı), pre-beta smoke. *Anahtarların geldiğinde beta anında açılır.*
3. **(Sen anahtar/karar sağlayınca)** Beta → veri → **P2.2/2.3/2.4 politikaları sırayla**.
4. P3.2 perf + P3.3 BIST → paralel/fırsatçı (düşük tier).

## 6. Seçeneklerin kısa/uzun vade etkisi
| Seçenek | Kısa vade | Uzun vade |
|---|---|---|
| **P1.1 TP/SL & R:R** (öneri) | Daha gerçekçi seviyeler + kötü-R:R eleme → anında sinyal güveni | Beta verisi kalibre birikir → 4 zekâ-v2 daha iyi öğrenir; ayrışma |
| Beta-hazırlık sertleştirme | Görünür değer düşük | Kritik-yol sürtünmesini kaldırır → tüm zekâ-v2 daha erken açılır |
| Similarity v2 (ANN) şimdi | Düşük (brute-force zaten yeterli) | Premature optimizasyon; veri gelince zaten gerekecek |
| Zekâ-v2 politikası (veri-gated) şimdi | İstatistiksel zayıf/yanlış kalibrasyon riski | BP2 ihlali; geri-alma borcu |
| P3.2 perf | Yük düşük → fark edilmez | Ölçek gelince değerli; şimdilik erken |

## 7. Karar noktası (senin onayın)
Öneri: **P1.1 TP/SL & R:R'yi sonraki çekirdek faz yap** (veri-bağımsız alt-kapsam; floor veri-gated
kalır). Davranış-değiştiren olduğu için: **önce KEY2/P1.1 kapsam analizi + etki raporu + alternatifler
→ onayın → sonra küçük commit + backtest before/after.** Alternatif: beta-hazırlık sertleştirme
(dep bump + Legal metin) ile kritik-yolu kısalt. İkisini de sıralı yapabiliriz; önceliği sen ver.
