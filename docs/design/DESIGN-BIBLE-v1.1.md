# TradeMinds Design Bible

**Sürüm:** v1.1 (Rev-1 uygulandı) · **Tarih:** 2026-07-03
**Statü:** Ürünün resmî ve tek tasarım standardı (normatif).
**Kanonik kaynak:** bu dosya (`docs/design/DESIGN-BIBLE-v1.1.md`). Artifact yalnızca görsel aynadır; çelişki halinde bu markdown kazanır.
**Eki:** [VISUAL-LANGUAGE-v1.1.md](./VISUAL-LANGUAGE-v1.1.md) (Annex A — atmosfer/Art Direction).
**Değişiklik geçmişi:** [CHANGELOG.md](./CHANGELOG.md).

> Amaç: ürünü Stripe · Linear · Vercel · Cursor · Perplexity · TradingView seviyesinde premium, kurumsal ve güven veren bir SaaS'a taşımak. Bu belge her ekranın uyacağı tek tasarım standardıdır.

---

## 00 · Tasarım İlkeleri

Her karar bu beş ilkeye dayanır. Çelişki olursa sıra: **kullanıcı → ilke → estetik**. (Belge-düzeyi kanoniklik için bkz. §08 Governance.)

1. **Dürüstlük = tasarım.** Asla sahte veri, temsili-gizli grafik, placeholder metin. Rakam gösteremiyorsak "—" gösteririz. Güven ürünün tek gerçek değeri; her piksel onu korur. Squint testi: gözünü kıstığında yalnız veri + CTA seçilmeli.
2. **Data-first netlik.** Ekran okunmaz, taranır. Önce özet, sonra detay. Durum sayıyla değil biçimle de kodlanır (pill, şerit, renk). Sayısal her şey `tabular-nums`.
3. **Sakin güven.** Cömert boşluk, tek accent, sessiz nötrler. Gürültü yok. "Kurumsal" = abartısızlık. Bir yerde cesur ol, geri kalanı sustur.
4. **AI + finans dili.** Görsel kelime dağarcığı = mum grafikleri, seviye çizgileri (SL/Giriş/TP), R-katları, güven halkaları. Jenerik gradyan değil; ürünün kendi materyali distinktifliği taşır.
5. **Amaçlı motion.** Animasyon dikkat yönlendirir, süslemez. Micro (hover) + entrance (scroll-reveal) + hero ambient — hepsi `prefers-reduced-motion` korumalı. Az çoktur. (Sayısal bütçe: VL §09.)

---

## 01 · Design System

Tüm üründe tek standart. Tokenlar tek kaynaktan (CSS değişkeni) türer; Tailwind literalleri bu değişkenlere bağlanır — palet-drift biter.

> **Normatiflik notu (Rev-1/H5):** Değerlerde bu **token tablosu** kanoniktir. Belgelerdeki/Artifact'teki demo CSS örnekleri açıklayıcıdır, normatif değildir — çelişkide token tablosu kazanır.

### Renk Sistemi
Tek accent (mavi) + AI-cyan partner (çok az). Semantik bull/bear accent'ten **ayrı**. Nötrler maviye eğik seçilmiş slate.

| Token | Değer | Kullanım |
|---|---|---|
| `--bg` (Ground) | `#070B14` | Zemin |
| `--bg-alt` | `#0A101C` | Section almaşığı (VL §02 L0) |
| `--surface-1` | `#0C1220` | Kart yüzeyi (E1) |
| `--surface-2` | `#111A2B` | İç yüzey (E2) |
| `--surface-3` | `#17233A` | Overlay yüzeyi (E3) |
| `--accent` | `#3B82F6` | Tek accent |
| `--accent-2` | `#22D3EE` | AI-cyan (yalnız AI bağlamı — VL §01) |
| `--bull` | `#10B981` | Semantik yükseliş |
| `--bear` | `#F4556E` | Semantik düşüş |
| `--warn` | `#FBBF24` | Uyarı / sinyal işareti |
| `--text` | `#E8EDF5` | Ana metin |
| `--muted` | `#9AA6B8` | İkincil metin / okunur mikro-etiket |
| `--faint` | `#5C6980` | **Yalnız dekoratif / disabled** (bkz. Kontrast kuralı) |
| Brand grad | `linear-gradient(#3B82F6→#22D3EE)` | Dolgu olarak yalnız hero/logo; 1px hairline formu (ufuk çizgisi) VL §06'ya tabidir |

**Hairline merdiveni** (VL depth ile ortak — §depth): `.10` (E0) · `.12` (E1, varsayılan) · `.16` (E2) · `.22` (E3), taban `rgba(148,163,184,·)`.

**Kontrast kuralı (Rev-1/H11):** `--faint` (#5C6980) koyu zeminde küçük metinde WCAG AA (4.5:1) altındadır (~3.6:1). Bu yüzden `--faint` **yalnız dekoratif öğe veya disabled durum** içindir. **Okunur mikro-etiket (fiyat/veri etiketi, tablo başlığı vb.) minimum `--muted`** kullanır. DoD'un "kontrast AA" maddesi bununla denetlenir.

### Typography
- **Ölçek:** 12 · 13 · 14 · 16 · 20 · 26 · 34 · 46 · 60 (oran ≈1,25). Hero display üst sınırı için `clamp(40px, 7vw, 72px)`.
- **Ağırlık:** 400 (body) · 500 (label) · 600 (alt-başlık/buton) · 650 (display). *650 için variable font gerekir; statik-ağırlık senaryosunda 700'e yuvarlanır.*
- **Font:** `next/font` ile self-host (Geist/Söhne benzeri), `@import` yok (CLS=0, KVKK dostu).
- Tüm sayı/fiyat `tabular-nums`. (Locale/format standardı Rev-2/H7'de eklenecek.)

### Spacing · 4px temel
`4 (xs) · 8 (sm) · 12 (md) · 16 (lg) · 24 (xl) · 32 (2xl) · 48 (3xl) · 64 (section)`. Aralık **her zaman** flex/grid `gap` ile; per-element margin çakışması yok.

### Radius (Rev-1/H5)
`8 kontrol · 10 buton/input · 12 kart · 16 panel · 999 pill`.

### Shadow · Border · Glass (Rev-1/H1, H3)
- **Shadow — tek token:** `--shadow-e3: 0 16px 40px -20px rgba(0,0,0,.7)`. **Yalnız E3 overlay** (modal/dropdown/popover). **Kartlar gölgesizdir** — derinlik border + lüminans ile (VL §depth).
- **Border:** 1px hairline `rgba(148,163,184,.12)` — glass yerine varsayılan.
- **Glass (backdrop-blur):** **yalnız overlay = modal / dropdown / popover.** Sticky header glass DEĞİLDİR; blur'suz opaklık + alt hairline kullanır (kanonik sayısal reçete: VL §08). Kartlarda glass yok.

### Glow (Rev-1/H3, H1)
- **Adlandırılmış token:** `--glow-cta: 0 8px 24px -12px <accent>`. Bu bir **glow**'dur, gölge değildir. *rest/hover opaklık ayrımı (.35/.55) Rev-2/M8'de sabitlenecek.*
- **Sahipleri (VL §03 kanonik):** yalnız birincil CTA · aktif sinyal vurgusu · AI nabzı. Kart/başlık/ikon glow'u yasak.
- **Hue daima accent/cyan.** Semantik renk (bull/bear) **asla glow/atmosfer olmaz** — yalnız düz renk/border/badge olarak veri durumu anlatır. (İndigo glow kaldırılır.)

### Grid
12 kolon · container `max-w 1200` · gutter 24. Breakpoint: `sm 640 · md 768 · lg 1024 · xl 1280` — **sm katmanı zorunlu**.

### Icon
Lucide, 1.5px stroke, 20px grid. Semantik doğru (Temel Analiz = `Landmark`, Makro = `Globe`). Unicode glyph yerine lucide. İkon-buton = `aria-label`.

### Button
- Variant: **primary** (dolu accent) · **secondary** (hairline) · **ghost** · **danger**.
- Boyut: sm 32 / md 40 / lg 44. Radius 10 (H5).
- Odak: görünür ring (`:focus-visible`). *Focus token spesifik değerleri Rev-2/M13.*
- Glow yalnız primary'de (`--glow-cta`). Her buton **ne olacağını** söyler.

### Badge
Tek `<Badge>` primitifi, variant'la: `bull · bear · outcome (TP KAZANDI / STOP OLDU / BAŞABAŞ / SÜRESİ DOLDU) · warn · neutral · accent (PRO)`. "PATLADI" gibi argo yok. Bugünkü 10+ ad-hoc badge birleşir.

### Input
Her kontrol etiketli (`label`/`aria-label`). Hata durumu bear rengi + yardım metni. *Tam form-validation deseni Rev-2/M17.*

### Card
Tek `<Card>` primitifi: hairline border + düz yüzey (**gölgesiz**, H3). Türevler: `StatTile`, `SignalCard`. Kart içeriği arka-plan feed'iyle değişmez (fiyat↔TP/SL swap yasak).

### Table
Semantik `<table>` (div-grid değil). `md` altında satır → **kart**'a dönüşür. Doğru desen repo'da `signal-history`'de zaten var.

### State Sistemi — Loading / Empty / Error
Üçü **ayrı** durum. En kritik kural: **backend hatası asla "0 sinyal / %0 başarı" olarak gösterilmez.** Hata → "—" + "Tekrar dene". Empty → sakin mesaj + CTA. Loading → skeleton (spinner değil).

### Toast
Tek toast primitifi. Bugünkü `window.alert()` (24 yer) kaldırılır. Fiil-net copy ("Yayınla"→"Yayınlandı"). *Davranış spesifikasyonu (süre/pozisyon/max) Rev-2/M15.*

### Modal
Tek `<Modal>`: `role="dialog"` + focus-trap + Escape + backdrop-blur (E3). Bir kez düzelt, her yerde kullan. Stacking sırası Rev-2/M12 (z-scale).

---

## 02 · Hero (sıfırdan)

İlk 5 saniyede tek soruya cevap: **"Bu ürün ne yapıyor?"** Premium · dolu-ama-sakin · güven + AI + finans + kurumsal.

- **Layout:** Split-hero. **Sol:** thesis (H1 + alt metin + iki CTA + gerçek istatistik şeridi). **Sağ:** canlı sinyal kartı (sembol · yön badge · TP/Giriş/SL ladder) — ölü yan-boşluk yerine ürünün ne yaptığını gösteren kanıt.
- **CTA:** birincil "Ücretsiz Başla" (dolu accent + `--glow-cta`) + ikincil "Canlı sinyalleri gör". `flex-wrap` zorunlu (mobil taşma yok).
- **Copy:** "kanıtlanmış" → "doğrulanabilir"; "kurumsal/Institutional" kaldırılır. "Yatırım tavsiyesi değildir" görünür.
- **İlk-boya:** marketing içeriği **SSR**; yalnız auth-redirect + canlı-stat client-island. Spinner-gate kalkar (hızlı LCP + crawlable).
- **Motion & ışık:** koreografi ve ışık planı **kanonik olarak VL §07**'de. (Ambient tek kanonik çözüm = L4 "sinyal tozu"; gradient-mesh kullanılmaz — VL §11.)
- **Scroll davranışı:** hero sabit; sırayla reveal: nasıl çalışır (3 adım) → canlı istatistik şeridi (count-up) → şeffaflık/dürüst sınırlar → güven (KVKK/güvenlik) → final CTA. Sticky header CTA hep erişilir.

---

## 03 · Dashboard (bilgi hiyerarşisi baştan)

Kullanıcı **3 saniyede** anlamalı: Bugün ne oldu? · Aktif sinyal var mı? · Portföyüm nasıl? · AI ne düşünüyor? · Risk nedir?

**Kart sırası:**
1. **Durum bandı** — tek satır özet ("Bugün 3 sinyal kapandı · 2 kazanç · net +1,8R") + dönem seçici. Gerçek veri yoksa "—", asla 0.
2. **Aktif sinyaller** — actionable kartlar; boşsa net empty-state; sayı birimli ("3 sinyal"). İçerik feed'le değişmez.
3. **Portföy / performans** — equity mini-chart + Başarı/PF/Getiri (dönem-duyarlı) + InvestmentDisclaimer; metrikler "hipotetik" çerçeveli.
4. **AI görüşü** — rejim + Korku&Açgözlülük + kısa AI özeti.
5. **Risk** — aktif sinyallerin risk dağılımı + tek net uyarı satırı (nötr dil).
6. **Piyasa (bağlam)** — tek "Kripto Piyasası"; **sahte delta'lar + sentetik grafik + Forex/işlevsiz sekmeler kaldırılır**; gerçek veri veya net "temsili" etiketi.

**Sil:** sabit yüzdeler, sentetik market-cap grafiği, Genel/Kripto/Hisse/Forex sekmeleri.
**Ekle:** error-state, risk disclaimer, sayı birimleri, ScoreRing etiketi.
**Tut:** rate-limit banner + skeleton + EmptyState + "başabaş dahil" dipnotu.

---

## 04 · Markets (premium ama TradingView değil)

Amaç netlik + premium his; terminal derinliği değil.
- **Filtre bar:** segmented control (Tümü · Kripto · Hisse · N varlık — birimli) + arama + sıralama; BIST-kapalı rozeti "Son kapanış".
- **Market kartı (grid, default):** logo · sembol · fiyat (`tabular`) · 24s % (semantik renk) · mini-sparkline (area-fill + vurgulu uç). Hover: hafif lift. Tıkla → analiz.
- **Tablo görünümü:** semantik `<table>` · sıralanabilir başlık · `md` altı → kart. 200 kart canlı-fiyatta **batch-render**.
- **Heatmap (ops. · P2):** kategori/coin ısı haritası.
- **Loading:** kart-skeleton grid. **Mobil:** grid tek kolon; filtre chip'leri yatay-scroll; tablo → kart; touch 44px.

---

## 05 · Signals (kart anatomisi)

Sinyal kartı ürünün kalbi. Daha okunur · güvenilir · profesyonel.
- **Ladder:** TP/Giriş/SL renk-şeritli dikey merdiven — yön ve mesafe tek bakışta. Fiyatlar `tabular-nums`, tutarlı ondalık.
- **AI Güven:** halka **etiketli** ("kazanma olasılığı değildir" tooltip). Çıplak "%76" yanıltıcı.
- **R:R** ve **Risk** ayrı, adlandırılmış; Kalite/Güven tek skora indirgenir.
- **Sonuç badge:** STOP OLDU / TP KAZANDI / BAŞABAŞ / SÜRESİ DOLDU — tek dil.
- **İçerik sabit:** canlı fiyat gelince TP/SL kaybolmaz.
- **Kart = link:** detay drawer'a; kart sakin, detay derinlemesine.

---

## 06 · Motion Language

Doğru araç, doğru yerde. Kural: performansı bozma, `prefers-reduced-motion` onurlandır, aşırılıktan kaçın.

> **Kanoniklik (Rev-1/H9):** Araç-karar tablosu ve sert sınırlar için **kanonik kaynak = VL §11 (Performans reçetesi)**. Aşağıdaki sayfa-eşlemesi açıklayıcıdır; araç verdict'leri VL §11 ile birebir aynıdır.

| Bölge | Kanonik araç |
|---|---|
| Hover, badge, kart lift, skeleton, buton | **CSS** (varsayılan) |
| Reveal · count-up · overlay spring · route geçişi | **Framer Motion** (P1/P2; sınırlar VL §09) |
| Hero ambient | **Canvas 2D** "sinyal tozu" (VL §02 L4) |
| Three.js · Spline · Video | **Gereksiz / Hayır** (VL §11) |

- **Hero'da:** Canvas 2D ambient + Framer kart/seviye-çizgi reveal. (Three.js/Spline/gradient-mesh değil.)
- **Scroll'da:** Framer scroll-reveal + stat count-up (**yalnız landing** — VL §09).
- **Kartlarda:** CSS hover "ısınma" (VL §08), skeleton shimmer.

---

## 07 · Öncelik · P0 / P1 / P2

**P0 — Beta öncesi zorunlu (dürüstlük + profesyonellik + hukuki hijyen):**
- Sahte veriyi sil (sabit delta'lar + sentetik market-cap grafiği).
- Dev-mesajlarını temizle ("BAŞLAT.bat…", FRED env uyarısı).
- Ödeme hunisini beta'da kapat (pricing "yakında" · Yükselt CTA gizle · checkout kapalı · waiver-consent toplama yok).
- Legal `[doldurulacak]` placeholder'ları doldur + "taslak" ibaresi kaldır + Help gerçek destek kanalı.
- İşlevsiz/yalancı sekmeler kaldır · error-state ekle · risk disclaimer dashboard'a.
- "BETA" kimliği + kayıt notu · sayı chip'lerine birim · over-claim temizliği.

**P1 — Kalite sıçraması:**
- Tasarım-sistemi tek-kaynak: renk token (glow/drift) + `tailwind-merge` + `next/font` + tip-ölçek + tabular-nums.
- Split-hero + canlı sinyal-kartı + ambient (Canvas) + spinner-gate kaldır (SSR).
- Mobil: tabloları kart-laştır + `sm:` katmanı + CTA/dropdown taşma.
- A11y fonksiyonel bug'lar: Header arama ölü sonuçları · modalları dialog · ikon-buton aria-label · dead butonlar.
- Kart/badge birleştirme · ScoreRing etiketi · içerik-swap durdur · "PATLADI"→"STOP OLDU" · Share-card.
- Motion katmanı-1 (CSS hover + Framer scroll count-up, **landing**).

**P2 — Beta sonrası olgunlaşma:**
- Refactor: signals God-file + çift çeviri katmanı + api.ts böl.
- Performans: canlı-fiyat batch-render + WS churn + `next/dynamic` chart lib + polling ayır.
- Motion katmanı-2/3: Framer **route geçişi (150-200ms fade/opacity, layout-anim yok — VL §09)** + scroll-timeline (landing); Markets heatmap.
- Paylaşılan primitifler (Modal/Badge/DataTable/SegmentedControl) + toast (`alert()` yerine) + spacing token + i18n kararı.

---

## 08 · Governance — bu belge nasıl kullanılır

### Standart
Her yeni ekran bu Bible + VL'ye göre geliştirilir. Yeni bir renk/spacing/komponent gerekiyorsa **önce buraya token eklenir**, sonra kullanılır — tek kaynak korunur. Repo'da zaten var olan doğru desen çoğaltılır, yeniden icat edilmez.

### Belge-düzeyi kanoniklik (Rev-1/C1)
İki belge çeliştiğinde:
- **Atmosfer / ışık / motion-bütçesi** konularında → **VISUAL-LANGUAGE (Annex A) kanoniktir.**
- **Token / komponent / layout** konularında → **DESIGN-BIBLE kanoniktir.**
- Aynı konuda çelişki varsa → **daha kısıtlayıcı kural kazanır** ve çelişki **her iki belgede aynı revizyonla** giderilir.

### Sürümleme (Rev-1/C2)
- Bu markdown dosyaları (`docs/design/`) **tek resmî kaynaktır.** Artifact yalnızca görsel aynadır.
- **Revizyon = commit + sürüm artışı + CHANGELOG satırı.** Standart, onaysız değişmez; sapma önerisi getirilmez, gerekirse önce sürüm revizyonu önerilir.

### Definition of Done (görsel) — Rev-1/H10 ile genişletildi
1. Token'dan türer (hardcode renk/spacing yok).
2. 3 state (loading/empty/error) ayrı ve dürüst.
3. Mobil doğrulandı (`sm`+ · tablo→kart).
4. A11y: aria-label · dialog · odak · **kontrast AA** (`--faint` okunur metinde kullanılmaz — §01).
5. Motion `reduced-motion` korumalı.
6. Sahte/placeholder/dev-metni yok.
7. **Viewport başına ≤1 ambient; app sayfalarında ambient/paralaks/scroll-efekti yok (VL §09).**
8. **Cyan yalnız AI bağlamında (VL §01).**
9. **Squint testi: en parlak pikseller = veri + CTA (VL §01).**
10. **Noise ≤%3 ve veri üstünde yok (VL §04).**

> Özet: beyin zaten güçlü (dürüstlük altyapısı, disclaimer, consent); yüz onu ele veriyordu. P0 sızıntıları temizler, P1 tasarım-sistemi + hero premium hissi verir. Bu belge o hissin kalıcı sözleşmesidir.
