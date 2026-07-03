# P1 Sprint Planı — Premium Kalite Sıçraması

**Tarih:** 2026-07-03 · **Statü:** PLAN (uygulama başlamadı — her paket ayrı onayla başlar)
**Standart:** [Design Bible v1.1](design/DESIGN-BIBLE-v1.1.md) + [Visual Language v1.1](design/VISUAL-LANGUAGE-v1.1.md) (LOCKED — sapma yok; gerekirse önce sürüm revizyonu)
**Zemin:** [P0 Complete Report](P0-COMPLETE-REPORT.md) (P0-1→P0-6 tamam) · Plan, 2026-07-03 güncel kod taramasıyla doğrulandı.

---

## 0 · Sprint-Düzeyi Kurallar

### Disiplin (P0 ile aynı, bağlayıcı)
Her alt-commit: **analiz → kapsam → uygulama → before/after → canlı doğrulama → regresyon (tsc 0 hata + konsol temiz) → küçük izole commit → dur/raporla.** Backend'e (AI motoru, BP2) dokunulmaz; tüm paketler frontend-only.

### Bağımsızlık Sözleşmesi (paketler birbirini beklemez)
1. **Semantik sınıf kuralı:** Tüm paketler mevcut semantik Tailwind sınıflarını kullanır (`bg-bg-primary`, `accent-primary`, `text-text-muted`…). P1.2 bu sınıfların *değerlerini* Bible paletine çevirdiğinde önce/sonra yazılan her şey otomatik yeni palete biner. → Hiçbir paket P1.2'yi beklemez; P1.2 hiçbir paketi bozmaz.
2. **Hero ↔ Motion ayrışması:** P1.1 hero'yu VL §07'nin **"bitmiş sahne"** hâliyle (reduced-motion son karesi — VL'ye birebir uygun) statik teslim eder. Koreografi + sinyal tozu P1.4'tedir. P1.4'ün yalnız "hero koreografi" alt-commit'i P1.1'e bağlıdır; P1.1 yapılmamışsa o alt-commit atlanır, kalanı (reveal/count-up/hover) mevcut sayfaya uygulanabilir.
3. **A11y ↔ Primitif ayrışması:** P1.5 = *mevcut* elemanlardaki etkileşim/a11y kırıkları (arama, aria-label, tablo→kart, taşma). P1.6 = *yeni primitifler* (Modal `role="dialog"` dâhil, Badge, toast). Çakışma yok.
4. **Dosya-çakışma matrisi** (paketler atlanabilir/ertelenebilir; aynı dosyaya sıra-dışı girilirse yalnız rebase dikkati):
   `app/page.tsx` → P1.1 + P1.4 + (P1.5 CTA) · `dashboard/page.tsx` → P1.3 + P1.6 · `signals/page.tsx` → P1.5 + P1.6 · `globals.css`/`tailwind.config.ts` → P1.2 (+P1.4 hover utility).

### Sprint-düzeyi ön koşullar (senden onay gerekenler)
| # | Karar | Gereken paket |
|---|---|---|
| K1 | **Rev-2 kısmi standart revizyonu (Bible v1.2):** H6 chart tokenları + H7 locale standardı + H8 migration haritası Bible'a eklenir (LOCKED kural: önce standart, sonra uygulama) | P1.2 |
| K2 | **`framer-motion` bağımlılığı** ekleme onayı (~30KB, dynamic import) | P1.4 |
| K3 | **`tailwind-merge`** bağımlılığı ekleme onayı (küçük util) | P1.2 |
| K4 | Hero sağ-kart veri kaynağı: **son kapanan sinyal** (public endpoint mevcut — öneri) vs aktif sinyal (public değil) | P1.1 |

### Kod-taraması doğrulanmış envanter (2026-07-03)
`framer-motion`/`gsap`/`tailwind-merge` kurulu **değil** · `#020817` **6 dosyada** · `#f97316` **2 dosyada** · `indigo` 1 · `alert()` **~21 çağrı** · `role="dialog"` yalnız **1** · `PATLADI` 1 (signals:170) · `prefers-reduced-motion` yalnız 1 (globals) · locale **karışık** (tr-TR 9 / en-US 5 dosya) · font **Google @import** (Inter+JetBrains Mono, globals.css:9) · signals listesi 7-kolon css-grid **breakpoint'siz** (:1135,:1189) · landing CTA satırı **flex-wrap'siz** (:128) · rejim verisi sinyal payload'ında **var** (api.ts:357) · risk verisi **hazır** (api.ts:171 `risk_level`, :952 `by_risk`).
⚠️ Düzeltme: Bible §01'in "tablo→kart deseni signal-history'de zaten var" notu kodda **doğrulanamadı** — P1.5'te desen yeni yazılır (Bible v1.2 revizyonunda bu cümle düzeltilmeli — K1 kapsamına eklendi).

---

## P1.1 · Hero Premium Redesign

**Amaç:** İlk 5 saniyede "bu ürün ne yapıyor?" cevabı (Bible §02): split-hero — sol thesis (H1+alt metin+CTA'lar+gerçek istatistik şeridi), sağ **canlı sinyal kartı** (TP/Giriş/SL ladder = ürün kanıtı); spinner-gate kaldırılıp landing **SSR-first** olur (hızlı LCP + crawlable); VL §07 ışık planı **statik** kurulur (L1 anahtar/dolgu + L3 grid kâğıdı + kart rim-light — "bitmiş sahne"); "Son Kazanan Sinyaller" win-wall'u dürüst **"Son Kapanan Sinyaller"** karma kesitine döner (kazanç+kayıp, outcome rozetli — P0'dan devir).

**Etkilenen ekranlar:** Yalnız landing (`/`).
**Etkilenen component'ler:** `app/page.tsx` (yapısal yeniden düzen) · YENİ `components/landing/HeroSignalCard.tsx` (statik ladder kartı) · `globals.css`'e VL ışık utility'leri (`--light-key`/`--light-fill`/grid-paper — landing'de kullanılır, app zemini değişmez) · auth-redirect mantığı client-island'a ayrışır.
**Tahmini risk:** **ORTA.** (1) SSR dönüşümü: `'use client'`+`useAuth` gate (page.tsx:64-66) yanlış ayrışırsa girişli kullanıcı flash görür → redirect-island deseniyle izole edilir, davranış-eşdeğerliği ayrı commit'te kanıtlanır. (2) Sağ kart verisi: K4 kararı (öneri: public signal-history'den son kapanan — dürüst + mevcut API). (3) Hydration uyuşmazlığı riski → canlı smoke.
**Ön koşullar:** K4 kararı. (Standart hazır; başka bağımlılık yok. P1.2'yi beklemez — semantik sınıf kuralı.)
**Doğrulama:** Logged-out canlı: spinner'sız ilk boya + squint testi (en parlak piksel = veri+CTA) · logged-in: redirect davranışı birebir · 375-414px: CTA taşmasız (flex-wrap) · tsc + konsol · (ops.) Lighthouse LCP before/after notu.
**Tahmini commit kapsamı:** **4 küçük commit** — (a) spinner-gate → redirect-island (davranış-eşdeğer, görsel değişiklik yok), (b) split-hero layout + HeroSignalCard, (c) VL statik atmosfer (L1+L3+rim) + win-wall→karma kesit, (d) mobil/ince ayar + copy denetimi.

---

## P1.2 · Design System Tek-Kaynak

**Amaç:** Bible §01 token tablosu **tek kaynağa** iner: `:root` CSS değişkenleri → `tailwind.config.ts` bağlanır; palet migration `#020817→#070B14` seti (H8 haritasıyla: tailwind.config, globals, layout `themeColor`, manifest, ShareCard tuvali, tradingview.ts); `--glow-cta`/`--shadow-e3`/hairline merdiveni/radius `8·10·12·16·999`; **next/font** self-host (Inter+JetBrains Mono — @import kalkar, CLS=0); `cn()`'e **tailwind-merge**; turuncu/indigo drift temizliği + H6 chart tokenlarının chart'lara uygulanması; H7 tek-kaynak locale formatter (tr-TR).

**Etkilenen ekranlar:** TÜMÜ (görsel etki global; davranış değişmez).
**Etkilenen component'ler:** `tailwind.config.ts` · `globals.css` · `lib/utils.ts` (cn + formatter'lar) · `app/layout.tsx` · `public/manifest.webmanifest` · `ShareCardModal.tsx` (canvas hex'leri) · `lib/tradingview.ts` + `TradingViewChart.tsx` (tema eşleme) · `#f97316` geçen 2 dosya (chart token'a) · en-US kullanan 5 dosya (formatter'a).
**Tahmini risk:** **YÜKSEK-GÖRSEL / DÜŞÜK-DAVRANIŞSAL.** Her ekranın zemini/tonu değişir (amaç bu) → screenshot-diff disipliniyle yönetilir. tailwind-merge, cn() sınıf-çakışma çözümünü değiştirir (düşük ama gerçek — smoke). Locale değişimi fiyat gösterimini değiştirir (`1,234.56`→`1.234,56`) — bilinçli, H7 standardıyla.
**Ön koşullar:** **K1 (Bible v1.2 Rev-2 kısmi: H6+H7+H8 — uygulamadan ÖNCE standart onayı)** + K3 (tailwind-merge).
**Doğrulama:** 5 ana ekranın (landing/dashboard/signals/markets/pricing) before/after screenshot seti · token no-op eşleme commit'inde **piksel-eşdeğerlik** beklentisi, migration commit'inde yalnız planlı fark · tsc + konsol · grep: eski hex'ler 0'a iner (H8 haritası kapanış kriteri).
**Tahmini commit kapsamı:** **6 küçük commit** — (a) `:root` token tanımları + tailwind bağlama (görsel **no-op**), (b) palet migration (eski→yeni değerler, H8 sırasıyla), (c) next/font + @import kaldırma, (d) tailwind-merge + cn, (e) chart/turuncu/indigo temizliği (H6 uygulaması), (f) locale tek-kaynak formatter (H7 uygulaması).

---

## P1.3 · Dashboard Premium Redesign

**Amaç:** Bible §03 3-saniye hiyerarşisi: **1 Durum bandı** ("Bugün N sinyal kapandı · X kazanç · ort. %Y" — mevcut `periodClosedCount`+win/loss'tan; veri yoksa "—") → **2 Aktif sinyaller** → **3 Portföy/performans** (disclaimer zaten P0-5'te) → **4 AI görüşü** (F&G [var] + rejim [sinyal payload'ından türetilir, api.ts:357] + kısa özet) → **5 Risk** (aktif sinyallerin `risk_level` dağılımı — api.ts:171/:952) → **6 Piyasa** (bağlam, en alta iner). Sayı chip'lerine birim ("3 sinyal", "5 varlık").

**Etkilenen ekranlar:** Yalnız `/dashboard`.
**Etkilenen component'ler:** `dashboard/page.tsx` (bölüm yeniden sıralama + 3 yeni sayfa-içi kart: DurumBandı, AIGörüşü, RiskDağılımı) · mevcut fetch'ler yeterli (yeni endpoint YOK — BP2 dokunulmaz).
**Tahmini risk:** **ORTA.** Bölüm taşıma sırasında 30sn polling/refresh davranışı ve mevcut kartların state bağları korunmalı (P0-5'teki `dataError` gate'i dâhil). Rejim türetimi per-sinyal veridendir (global rejim endpoint'i yok) — kart "aktif sinyallerde baskın rejim" olarak dürüst etiketlenir; sinyal yoksa rejim satırı gizlenir.
**Ön koşullar:** Yok. (P1.1/P1.2'den bağımsız; ScoreRing etiketi P1.6'da — burada yalnız yerleşim.)
**Doğrulama:** Canlı 3-saniye testi (beş soru: bugün ne oldu / aktif var mı / portföy / AI / risk — tek viewport'ta sırayla) · refresh/polling regresyonu · error-state (dataError) hâlâ çalışır · tsc + konsol · before/after screenshot.
**Tahmini commit kapsamı:** **4 küçük commit** — (a) Durum bandı kartı, (b) bölüm yeniden sıralama (salt taşıma, içerik değişmez), (c) AI görüşü + Risk kartları, (d) birimler + ince ayar.

---

## P1.4 · Motion Katmanı-1

**Amaç:** VL §09 bütçesine birebir: **Landing** — Framer scroll-reveal (fade+8px, stagger 60-80ms, *bir kez*) + istatistik count-up (600ms, viewport'a girince) + VL §07 hero giriş koreografisi (kanonik timeline: 0/250 başlık → 400/250 kart → 500/350 çizgiler → ~850 nabız) + **L4 sinyal tozu** (Canvas 2D: ≤40 nokta · 30fps cap · DPR≤2 · tab-gizli/viewport-dışı durur). **App** — yalnız CSS micro: hover "ısınma" (+1 lüminans · hairline→accent %28 · −2px · 140ms — VL §08) utility'si. Tümü `prefers-reduced-motion`'da kapanır (Canvas statik kare çizer).

**Etkilenen ekranlar:** Landing (ana yüzey); app-geneli hover utility (görsel mikro-cila, davranışsal değil).
**Etkilenen component'ler:** `app/page.tsx` (reveal/count-up sarmalayıcıları) · YENİ `components/landing/SignalDust.tsx` (Canvas) + küçük `useCountUp`/`Reveal` yardımcıları · `globals.css` hover-ısınma utility · `package.json` (framer-motion, dynamic import).
**Tahmini risk:** **ORTA.** Yeni bağımlılık (bundle ~30KB → dynamic import ile landing'e izole); Canvas düşük-uç cihaz maliyeti (VL sınırları + pause koşulları uygulanır); SSR/hydration ile Framer etkileşimi (P1.1'in SSR'ı üstünde — client-island'da tutulur). VL bütçe bekçisi: viewport başına ≤1 ambient (toz VEYA glow-drift; ikisi değil).
**Ön koşullar:** **K2 (framer-motion onayı).** Hero-koreografi alt-commit'i P1.1'e bağlı (yapılmadıysa atlanır — kalan alt-commit'ler bağımsız).
**Doğrulama:** Canlı: reveal *bir kez* tetiklenir, count-up doğru, DevTools performance'ta toz ≤30fps + tab-gizli pause · `prefers-reduced-motion` emülasyonunda **tümü kapalı** (DoD md.5) · bundle-size farkı raporlanır · tsc + konsol.
**Tahmini commit kapsamı:** **4 küçük commit** — (a) framer kurulumu + reveal/count-up (landing), (b) hero koreografisi (VL §07 timeline), (c) SignalDust canvas + pause koşulları, (d) app hover-ısınma CSS utility.

---

## P1.5 · Mobile & Accessibility

**Amaç:** Kırık mobil/a11y'yi onar (Bible §07 P1): **signals listesi** 7-kolon css-grid (:1135) `md` altında **kart görünümüne** döner (desen yeni yazılır — envanter düzeltmesi: hazır desen yok); kritik ekranlara `sm:` katmanı + taşma onarımları (landing CTA `flex-wrap` [:128 — P1.1 yaptıysa atlanır], dropdown/chip taşmaları); **Header**: arama sonuç satırları tıklanabilir olur (Link + klavye), ölü "Tümünü gör" ve alert()-stub tema menüsü işlevlenir ya da kaldırılır, ⌘K handler; ikon-butonlara **aria-label** passı; touch hedefleri ≥44px.

**Etkilenen ekranlar:** Signals (liste) · Header (tüm app) · landing/mobil taşmalar · markets touch hedefleri.
**Etkilenen component'ler:** `signals/page.tsx` (yalnız liste render bölümü — God-file split P2'de, cerrahi dokunuş) · `components/layout/Header.tsx` · ikon-buton geçen paylaşılan bileşenler (aria-label).
**Tahmini risk:** **DÜŞÜK-ORTA.** signals God-file içinde cerrahi değişiklik (liste bölümü izole edilir; regresyon smoke şart). Header aramasına navigasyon eklemek yeni davranış (sembol→analiz rotası) — mevcut rota konvansiyonuyla.
**Ön koşullar:** Yok. (Modal `role="dialog"` bilinçli olarak P1.6'da — çakışma önleme.)
**Doğrulama:** DevTools device-emulation 375/414px (Chrome eklentisi ~784px'e clamp'liyor — emülasyonla doğrulanır): tablo→kart kırılımı, taşma sıfır · klavye-gezinme: arama sonuçları Tab+Enter ile açılır · axe/manuel aria denetimi (değişen bileşenlerde) · tsc + konsol.
**Tahmini commit kapsamı:** **4 küçük commit** — (a) signals tablo→kart (md-altı), (b) Header arama işlevlendirme + ölü kontroller, (c) aria-label passı, (d) `sm:`/taşma passı (CTA dâhil).

---

## P1.6 · Component Refactor (P1 kapsamı)

**Amaç:** Bible §01 primitif birleştirmeleri (P1-dilimi; derin refactor — God-file/api.ts split — P2'de kalır): **tek `<Badge>`** (variant: bull/bear/outcome/warn/neutral/accent; `SignalBadge` + ad-hoc pill'ler katlanır; **"PATLADI"→"STOP OLDU"** [signals:170] dâhil outcome dili tekleşir) · **tek `<Modal>`** (`role="dialog"` + focus-trap + Escape; şu an yalnız 1 dialog var — 5 modal taşınır) · **toast primitifi** + **~21 `alert()`** çağrısının değişimi (bloklamayan, fiil-net copy) · **ScoreRing** etiket prop'u ("AI Güven" + "kazanma olasılığı değildir" tooltip'i) · dashboard sinyal kartlarında **içerik-swap durdurma** (canlı fiyat TP/SL'yi ezmez — birlikte görünür) · **ShareCard** düzeltme (tuval metin/veri; P0-6'da "Institutional" temizlendi, kalan görsel borç) · signals ↔ SignalDetailSection **çift çeviri katmanı** ortak sözlüğe iner (yalnız sözlük çıkarma).

**Etkilenen ekranlar:** App-geneli (signals, dashboard, signal-history, pricing, settings, admin…).
**Etkilenen component'ler:** YENİ `ui/Badge.tsx` · `ui/Modal.tsx` · `ui/toast` · GÜNCELLENEN `ScoreRing.tsx` · `ShareCardModal.tsx` · `SignalBadge.tsx` (Badge'e katlanır) · dashboard/signals kart blokları · YENİ `lib/signal-labels.ts` (ortak sözlük).
**Tahmini risk:** **ORTA-YÜKSEK dokunma yüzeyi, mekanik nitelik.** Çok dosyaya dokunur ama her değişim birebir eşleme; risk yönetimi = primitif-başına ayrı commit + ekran-ekran smoke. alert()→toast bloklamama davranış değişikliğidir (bilinçli; onay-akışı `confirm()` değil — düşük risk).
**Ön koşullar:** Yok. (P1.2 yapıldıysa Badge/Modal token'ları hazır olur; yapılmadıysa semantik sınıflarla — bağımsız.)
**Doğrulama:** Primitif-başına: grep before/after (`PATLADI` 0 · `alert(` 0 · `role="dialog"` tüm modallar) + ekran-ekran canlı smoke + klavye (Escape/focus-trap) + tsc + konsol.
**Tahmini commit kapsamı:** **6 küçük commit** — (a) Badge primitifi + outcome dili (PATLADI dâhil), (b) Modal primitifi + 5 modal taşıma, (c) toast + alert() değişimi, (d) ScoreRing etiket + kullanım yerleri, (e) içerik-swap durdurma + ShareCard, (f) ortak sinyal-sözlüğü.

---

## Özet Tablo

| Paket | Risk | Ön koşul | Commit | Ana çıktı |
|---|---|---|---|---|
| P1.1 Hero | Orta | K4 (veri kaynağı) | 4 | Split-hero + SSR + statik VL sahnesi |
| P1.2 Design system | Yüksek-görsel | **K1 (Bible v1.2)** + K3 | 6 | Token tek-kaynak + palet migration + next/font |
| P1.3 Dashboard | Orta | — | 4 | 3-saniye hiyerarşisi + AI/risk kartları |
| P1.4 Motion | Orta | **K2 (framer)** (+P1.1 yalnız koreografi için) | 4 | Reveal/count-up/koreografi/sinyal tozu + hover |
| P1.5 Mobile & A11y | Düşük-orta | — | 4 | Tablo→kart + Header onarımı + aria + sm |
| P1.6 Component refactor | Orta (geniş yüzey) | — | 6 | Badge/Modal/toast + ScoreRing + swap/ShareCard |

**Toplam:** ~28 küçük izole commit · 6 bağımsız paket · sıra: 1→6 (kullanıcı kararı) ama her paket tek başına uygulanabilir/ertelenebilir.

**P2'ye bilinçli bırakılanlar:** signals God-file + api.ts split · canlı-fiyat batch-render/WS churn · route-transition + scroll-timeline · Markets heatmap · DataTable/SegmentedControl primitifleri · i18n kararı.
