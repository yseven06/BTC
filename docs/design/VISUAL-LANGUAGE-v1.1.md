# TradeMinds Visual Language — "Gece Seansı"

**Sürüm:** v1.2 (Rev-2/K1 ile senkron — **VL içeriği değişmedi**; yalnız sürüm hizalaması) · **Tarih:** 2026-07-04
**Statü:** Design Bible'ın **Ek A'sı (Annex A)** — Art Direction / atmosfer katmanı. Yeni tasarım sistemi değildir.
**Kanonik kaynak:** bu dosya (`docs/design/`). Dosya adı sabittir; güncel sürüm bu başlıkta ve CHANGELOG'da izlenir. Artifact yalnızca görsel aynadır.
**Kanoniklik (bkz. Bible §08/C1):** atmosfer · ışık · motion-bütçesi konularında **bu belge kanoniktir**; token/komponent/layout konularında Bible kanoniktir; çelişkide daha kısıtlayıcı kural kazanır.
**Ana belge:** [DESIGN-BIBLE-v1.1.md](./DESIGN-BIBLE-v1.1.md) · **Changelog:** [CHANGELOG.md](./CHANGELOG.md)

> **Konsept:** Piyasa uyumaz; karanlık bir izleme odasında AI nöbettedir. İlke tek cümle: **ışık = bilgi.**
> **Performans-öncelikli.** Araçlar: CSS · SVG · Canvas · Framer. Three.js/Spline/video gereksiz (§11).

---

## 01 · Sayfanın genel ışık dili

Atmosferin anayasası. Üç kural her sayfada geçerlidir.

1. **Işık = bilgi.** Parlayan her şey anlam taşır. Sayfanın en parlak pikselleri **veri** (fiyat, seviye, skor) ve **birincil CTA**'dır. Dekoratif ışık daima loş ve yönlü — asla içerikle yarışmaz. **Squint testi:** gözünü kıstığında yalnız veri + CTA seçilmeli.
2. **Tek anahtar ışık.** Her sayfada **bir** anahtar ışık kaynağı: sağ-üstten süzülen mavi "ufuk" ışığı; sol-alttan çok zayıf cyan dolgu. İki *yönlü* kaynaktan fazlası yasak. *(Köşe-demirli bokeh diskleri yönsüzdür, ışık kaynağı sayılmaz — §03; yine de ≤2.)*
3. **Cyan = AI'nın parmak izi.** `#22D3EE` asla dekor değildir. Yalnız AI'nın dokunduğu yerde: güven halkası, AI özeti, sinyal-anı vurgusu, hero "tarama" nabzı. Kullanıcı öğrenir: *cyan gördüysem, AI konuştu.*

---

## 02 · Background katman yığını

Beş katman, aşağıdan yukarı. Hepsi CSS/SVG — L4 hariç hiçbiri animasyonlu değildir *(app sayfalarında; landing L1 paralaksı için bkz. §08)*.

| Katman | İçerik | Nerede | Teknik |
|---|---|---|---|
| **L0 · Zemin** | Düz `--bg #070B14`; section almaşığı `--bg-alt #0A101C` | Her yerde | CSS |
| **L1 · Anahtar ışık** | `--light-key` mavi radial sağ-üst + `--light-fill` cyan sol-alt | Her sayfa (app'te statik; landing'de §08 paralaks) | CSS radial-gradient |
| **L2 · Noise** | Mono grain %2–3, overlay blend — banding-katili | landing · auth · **tam-yüzey empty-state** | SVG feTurbulence data-URI, 128px tile |
| **L3 · Grid kâğıdı** | 1px çizgi ızgara %5, radial-maskeyle eriyen | landing hero · **empty-state kart sınırları** | CSS gradient + mask |
| **L4 · Sinyal tozu** | 20–40 loş nokta = taranan varlıklar; ara sıra biri cyan/mavi nabız = "sinyal doğdu" | **yalnız landing hero** | Canvas 2D (≤40 nokta, 30fps cap) |

**Kanonik ışık tokenı (Rev-1/M-hazırlığı):**
`--light-key: radial-gradient(1200px 600px at 78% -10%, rgb(59 130 246 / .11), transparent 60%)`
`--light-fill: radial-gradient(800px 480px at -4% 30%, rgb(34 211 238 / .05), transparent 55%)`
Tüm sayfalar bu değeri kullanır; "%10-12" gibi aralıklar bu tek tokena bağlıdır.

### Sayfa sınıflandırması (Rev-1/H2)
Atmosfer kuralları sayfa sınıfına bağlıdır. Her route bir sınıfa girer:

| Sınıf | Route'lar | İzinli katmanlar |
|---|---|---|
| **landing-tipi** | `/` (landing), pricing, about | L0 · L1 (§08 paralaks) · L2 · L3 (hero) · L4 (yalnız landing hero) · bokeh · scroll efektleri |
| **auth** | login, register, şifre | L0 · L1 (statik) · L2 · bokeh — **hareketli ambient/koreografi yok** (§09) |
| **app-tipi** | dashboard, signals, markets, portfolio, performance, settings, admin, legal, help, onboarding | **yalnız L0 + L1 (statik).** Ambient/paralaks/noise/grid **yasak.** |

**Empty-state istisnası (Rev-1/H2):** App sayfasındaki bir boş-durum için sayfa geneli yine L0+L1 kalır; **yalnız empty-state bileşeninin KART SINIRLARI içinde** L3 grid (ve gerekirse L2 noise) izinlidir ve **veri render edildiği an kalkar.** Yani "app'te L2-L4 yasak" kuralı sayfa-geneli içindir; kart-sınırlı empty-state onun tanımlı tek istisnasıdır.

> App sayfalarında (dashboard/signals/markets…) veri yoğun ekranda metin kristal kalır; atmosfer kapıda kalır.

---

## 03 · Ambient glow & Bokeh

Glow bir ödüldür, hak edilir. Bokeh bir mekân hissidir, dekor değil.

- **glow sahipleri:** yalnız birincil CTA · aktif sinyal vurgusu · AI nabzı. Kart/başlık/ikon glow'u yasak.
- **glow reçetesi:** `--glow-cta: 0 8px 24px -12px <accent>` (Bible §01). Hue daima accent/cyan, asla indigo. *(rest/hover opaklık ayrımı Rev-2/M8.)*
- **bokeh yeri:** landing + auth; sayfa başına **en çok 2 disk**, köşelere demirli, metinle çakışmaz. Yönsüz oldukları için §01'deki "tek anahtar ışık" bütçesine dahil değildir.
- **bokeh tekniği:** radial-gradient falloff. `filter:blur` ile canlı bulanıklık **yasak** (paint fırtınası).
- **semantik ışık:** bull/bear renkleri **asla** atmosfer olmaz — yalnız veri durumu anlatır.

---

## 04 · Noise texture

Amaç "doku hissi" değil — **gradient banding'ini öldürmek** ve karanlığa film greni sıcaklığı vermek.

- **yoğunluk:** %2–3 — asla üstü. Görünür grain = gürültü, ilke ihlali.
- **nerede:** landing · auth · tam-yüzey empty-state (§02 sınıflandırma). **Veri tablosu/grafik üstünde yasak.**
- **teknik:** tek 128px feTurbulence data-URI (bir kez decode, GPU-bedava). Animasyonlu grain yasak. *(Düşük-uç cihazda `mix-blend-mode:overlay` maliyeti için düz opaklık da kabul — Rev-2/L3.)*

---

## 05 · Depth — lüminans merdiveni

Koyu arayüzde gölge görünmez; derinliği **ışık** anlatır. Yüzey yükseldikçe +%3 aydınlanır, hairline belirginleşir.

| Seviye | Yüzey | Hairline |
|---|---|---|
| E0 · Zemin | `#070B14` | `.10` |
| E1 · Kart | `#0C1220` | `.12` |
| E2 · İç yüzey | `#111A2B` | `.16` |
| E3 · Overlay | `#17233A` | `.22` + gölge + blur(16) |

- **Gölge tek token (Rev-1/H3):** `--shadow-e3: 0 16px 40px -20px rgba(0,0,0,.7)` — **yalnız E3** (modal/dropdown/popover). **Kartlar gölgesizdir** (derinlik border + lüminans).
- **backdrop-blur yalnız E3** — Bible'ın "glass yalnız overlay" kuralının atmosfer karşılığı. **Sticky header E3 değildir** (bkz. §08).
- **Rim-light:** E2+ yüzeylerin üst kenarında 1px `rgba(255,255,255,.05–.07)`. Hero ürün kartında rim cyan'a döner (AI dokunuşu).

---

## 06 · Section geçişleri

Sert sınır yok, dalga/diyagonal kesim yok. Üç sessiz araç:

1. **Lüminans almaşması** — ardışık section zeminleri `#070B14 ↔ #0A101C` (+~%2). Göz sınırı hisseder, çizgi görmez.
2. **Ufuk çizgisi** — 1px accent→cyan gradient hairline (uçları şeffaf). **Sayfada en çok 2 kez**, yalnız büyük bölüm dönüşümlerinde (hero→kanıt, içerik→final CTA). *(Bible "brand grad yalnız hero/logo" kuralı dolgu içindir; 1px hairline formu bu §06 kuralına tabidir.)*
3. **Seviye çizgisi motifi** — ürünün kendi dilinden: kesikli seviye çizgisi + fiyat-etiketi çipi; yalnız anlamlı yerlerde (dekor değil). TradeMinds imzası.

---

## 07 · Hero lighting

Bible split-hero'suna ışık planı. Sahne üç ışıkla kurulur — fazlası yasak.
- **① Anahtar** — mavi ufuk, sağ-üst (`--light-key`).
- **② Dolgu** — cyan, sol-alt (`--light-fill`).
- **③ Rim** — ürün kartının üst kenarı, 1px cyan.
- Arkada L3 grid + L4 sinyal tozu.

**Giriş koreografisi — kanonik timeline (Rev-1/M3; toplam ~900ms, bir kez):**

| Adım | Başlangıç | Süre | Easing |
|---|---|---|---|
| Işık sahnede | 0ms | — (statik) | — |
| Başlık + CTA fade-rise | 0ms | 250ms | ease-out |
| Ürün kartı fade | 400ms | 250ms | ease-out |
| Seviye çizgileri (soldan, stagger 80ms) | 500ms | 350ms | ease-out |
| Sinyal tozundan cyan nabız | ~850ms | — | — |

Anlatı: *AI taradı, sinyal doğdu.* **Reduced-motion:** koreografi atlanır, sahne bitmiş hâliyle açılır; nabız statik parlak nokta olur.
*(Bu tablo hero motion timing'inin tek kanonik kaynağıdır; Bible §02'deki anlatı buna atıf yapar.)*

---

## 08 · Scroll atmosferi & Hover hissi

### Scroll — yalnız landing
- **glow paralaks:** L1 ışık katmanı 0.92× hızda kayar (transform-only) — landing'de L1'in tek animasyonlu istisnası budur (§02 dipnotu).
- **reveal:** section girişinde fade + 8px yükselme, stagger 60–80ms, **bir kez** (Framer, transform/opacity).
- **count-up:** istatistik şeridi viewport'a girince 600ms sayar — tek "vay" anı.
- **app sayfaları:** scroll efekti **yasak.**

### Sticky header — kanonik reçete (Rev-1/H1)
Sticky header **glass/E3 değildir**; **blur'suz** çözüm kullanır (daha ucuz + jank'siz):
- `background: rgba(7, 11, 20, .72)` + **alt hairline `.12`**; **backdrop-blur YOK.**
- `scroll > 0` olduğunda aktifleşir (üstte transparan, kaydırınca opaklık + hairline kazanır).
- Bu, Bible §01 glass listesindeki "sticky header" ibaresinin yerine geçen tek kanonik reçetedir.

### Hover — "ısınma"
Metafor: yüzeye dokununca ısınır. Parlamaz, zıplamaz, büyümez.
- **Kart:** +1 lüminans adımı · hairline→accent %28 · −2px lift · 140ms.
- **Satır:** zemin accent %4 tonu · sol hairline accent (aktifte).
- **Birincil CTA:** `--glow-cta` (tek glow sahibi).
- **Süre/eğri:** 120–160ms ease-out; scale/parlak glow yok (CTA hariç). *Hover/focus gibi micro-etkileşimler her bölgede geçerlidir (auth dahil).*

---

## 09 · Motion yoğunluğu — sakinlik bütçesi

Kural: **viewport başına aynı anda en çok 1 ambient animasyon.** Hareket enflasyonu "AI-üretimi" hissinin bir numaralı kaynağıdır.

| Bölge | İzinli | Yasak |
|---|---|---|
| **Landing** | 1 ambient (sinyal tozu **veya** glow drift — ikisi değil) · reveal (bir kez) · count-up · hover ısınması | çoklu ambient · sonsuz döngü dekor · marquee |
| **App** (dashboard/signals/markets…) | micro: hover 120-160ms · state geçişi 150-200ms · skeleton shimmer · sayı-tick · **route geçişi: 150-200ms fade/opacity, layout-anim yok** | ambient · paralaks · scroll-reveal · **count-up** · sayfa-içi dekoratif döngü |
| **Overlay** (modal/drawer/toast) | Framer spring (stiffness ~300, damping ~30) · backdrop fade 150ms | bounce abartısı · 300ms+ giriş |
| **Auth** | statik atmosfer (L1+L2+bokeh) + micro-etkileşim (hover/focus/state) | ambient · reveal · koreografi |

- **Route geçişi (Rev-1/H4):** app sayfaları arası geçiş yalnız 150-200ms fade/opacity; layout-animation yok. Bible P2 "Framer page-transition" kalemi bu sınıra bağlıdır.
- **Liste stagger yalnız landing'dedir** (app'te yasak).
- **Sayı-tick tanımı:** app'te count-up yoktur; canlı veri değişiminde tick = 150-200ms renk/opacity flash (konum/scale animasyonu yok).
- Tümü `prefers-reduced-motion`'da kapanır (ambient dâhil — Canvas statik kare çizer). Bu bütçe Bible'ın "amaçlı motion" ilkesinin sayısal hâlidir.

---

## 10 · Premium hissi & Finans + AI kimliği

Kopya değil, imza. Dört sahiplenilebilir unsur:
- **Sinyal tozu** — hero'daki taranan-varlık noktaları + cyan doğum nabzı.
- **Seviye çizgisi motifi** — SL/TP dilinin anlamlı çerçeveye dönüşümü.
- **Cyan = AI izi** — renk disiplini olarak kimlik.
- **Grafik kâğıdı** — maskeli grid; finansın "kâğıt" hafızası, yalnız boş sahnelerde.

**Premium'un kaynağı** = kısıtlama: tek ışık, tek glow sahibi, %3 altı noise, ≤1 ambient. Dürüstlük ilkesinin atmosfer hali: ışık asla olmayan bir şeyi parlatmaz.

---

## 11 · Performans reçetesi (araç kararı — KANONİK)

> **Rev-1/H9:** Araç-karar tablosu ve sert sınırlar için **tek kanonik kaynak bu bölümdür.** Bible §06 buna atıf yapar.

| Araç | Kullanım | Sınır | Karar |
|---|---|---|---|
| **CSS** gradient/mask/transition | L0-L3, hover, geçişler, bokeh | transform/opacity dışı animasyon yok | **Varsayılan** |
| **SVG** feTurbulence | noise tile (data-URI) | tek 128px tile, statik | **Evet** |
| **Canvas 2D** | sinyal tozu (yalnız landing hero) | ≤40 nokta · 30fps cap · DPR≤2 · tab-gizli/viewport-dışı durur | **Tek ambient** |
| **Framer Motion** | reveal · count-up · overlay spring · route geçişi | dinamik import; layout-animation app'te yok | **P1 ana** |
| **Three.js / WebGL** | — | atmosferin tamamı üstteki dört araçla kurulur | **Gereksiz** |
| **Video bg / Spline** | — | ağırlık + CSP + kontrol kaybı | **Hayır** |

**Sert yasaklar:**
- App sayfalarında ambient/paralaks/scroll-efekti · noise veri üstünde · canlı `filter:blur`.
- Semantik renk (bull/bear) atmosfer olarak · cyan dekor olarak · indigo her yerde.
- Viewport'ta >1 ambient · tam-ekran satüre gradient-mesh · dalga/diyagonal section kesimi.

> **Erişilebilirlik notu (Rev-1/H11):** `--faint` (#5C6980) koyu zeminde küçük metinde AA'yı geçmez; yalnız dekoratif/disabled içindir. Okunur mikro-etiket minimum `--muted` (Bible §01 Kontrast kuralı).

---

**Tek cümle:** *Gece Seansı* — karanlık sahne, tek mavi ufuk ışığı, verinin kendisi parlar; AI dokunduğunda cyan iz bırakır; her şey sakindir çünkü **sakinlik güvendir.**
