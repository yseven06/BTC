# TradeMinds Visual Language — "Gece Seansı"

**Sürüm:** v3.0 (KANONIK) · **Tarih:** 2026-07-18 · *(v3.0 S0 REDESIGN-DOC: **«Enstrüman Odası» v3** — **VL-MOTION-v3 gated native-3D/video/Spline şeridi KAPATILDI** (kullanıcı kararı; landing derinliği yalnız CSS/Canvas-2D; 3D=gelecekte sıfırdan ayrı karar/sprint) · §05 **e3-materyal-v2** (cut-lip + iki-katman gölge + standart scrim + bottom-sheet + kanonik-Modal zorunluluğu) · §03 **efekt-bütçesi-v3** + **BOKEH EMEKLİ** · §09 bayat-satır temizliği (landing count-up "izinli" ibaresi KALDIRILDI — Doctrine yasağıyla tek-kaynak; glow-drift/parallax kapalı-notları) · §01/§02 Karot-emekli + Nabız carve-out düzeltmeleri. Bible v3.0 + Doctrine v2 senkron. Doc-only. bkz CHANGELOG.)* · *(v2.2 CP-PREMIUM-VISUAL-A: **bayat-Karot re-anchor** — DoD-2 "Karot zorunluluğu" → **kompozisyon-zorunluluğu** (taşıyıcı ≥1: owned-numeral kahraman · makbuz · instrument-well; glyph=0) · DoD-4 app-squint {Karot, CTA} → **{kahraman-rakam, birincil-CTA}** · §09 skeleton/stagger/settle Karot-notları → **hairline-iskelet** (kanonik reçete: Bible §03-K pv-yükleme). Yeni dekoratif sembol İCAT EDİLMEDİ; atmosfer/motion bütçeleri ve app/landing sınırı AYNEN; Bible v2.0 + MOTION-DOCTRINE senkron. bkz CHANGELOG.)* · *(v2.1 CP-1 VL-MOTION-v3: **native-motion taksonomisi + gated 3D/video/Spline politikası** — generic/stok/template/sahte/perf-riskli kullanım yasak AYNEN; TradeMinds-native × bilgi-taşıyan 3D/video/motion = **koşullu-serbest gated-future-CP** (8-kabul-kapısı, ayrı onay); video-bg + Spline düz-yasağı → gated-conditional; native-3D DEFERRED → gated-conditional; app-yüzeyi (Dashboard/Signal-Center) ağır-motion yasağı korunur; Karot geri gelmez, yeni glyph yok; bkz "VL-MOTION-v3" bölümü + Bible §00 G-00-15 + CHANGELOG)* · *(v2.0 CP-HERO-DOC: **hero atmosferi Karot'suz REVİZE** — 40-Karot hero-yüzeyi + Karot-squint SUPERSEDED (Karot üründen kaldırıldı, CP-KAROT-DOC). Yeni merkez = Canlı-Masa / live-terminal proof-surface + owned-number + receipt + instrument-well (glyph İKAMESİ YOK); atmosfer/motion bütçeleri + §11 kalıcı-yasaklar AYNEN; bkz §02 "Yaşayan Hero yüzeyi" baş-banner + Bible §02 + CHANGELOG)* · *(v1.5: K-J motion-paketi — `--dur-flash 300` + foton bg-tint dar-tanımı + T3 landing-reveal carve-out; v1.4: Karot geometri revizyonu; bkz. CHANGELOG)*
**Statü:** Design Bible'ın **Ek A'sı (Annex A)** — Art Direction / atmosfer · ışık · motion-bütçesi katmanı. Yeni tasarım sistemi değildir.
**Kanonik kaynak:** bu dosya (`docs/design/`). Dosya adı sabittir; güncel sürüm bu başlıkta ve CHANGELOG'da izlenir. Artifact yalnızca görsel aynadır.
**Kanoniklik (bkz. Bible §08/C1):** atmosfer · ışık · motion-bütçesi konularında **bu belge kanoniktir**; token/komponent/layout konularında Bible kanoniktir; çelişkide **daha kısıtlayıcı kural kazanır** ve her iki belgede aynı revizyonla kapatılır.
**Ana belge:** [DESIGN-BIBLE-v1.1.md](./DESIGN-BIBLE-v1.1.md) · **Changelog:** [CHANGELOG.md](./CHANGELOG.md)

> **Konsept:** Piyasa uyumaz; karanlık bir izleme odasında AI nöbettedir. İlke tek cümle: **ışık = bilgi.**
> **Performans-öncelikli.** Araçlar: CSS · SVG · Canvas 2D · Motion (reveal-only). Three.js/Spline/R3F/WebGL **kimlik-merkezi olarak kalıcı yasak** (§11 · Kalıcı Yasaklar). Karot ve tüm ölçekleri (16/48/200 hero) 2D SVG.
> **(VL-MOTION-v3 · v2.1):** generic/kimlik-merkezi 3D/WebGL/video/Spline yasağı AYNEN; **TradeMinds-native × bilgi-taşıyan** (ürün proof-surface / instrument-well derinliği) kullanım *mutlak-yasak değil* → **gated-conditional future CP** (8-kabul-kapısı + ayrı onay). Tek kanonik ayrım: "VL-MOTION-v3" bölümü. **(S0 v3.0: bu gated şerit KAPATILDI — bkz. bölüm S0-banner'ı; landing derinliği yalnız CSS/Canvas-2D.)**

> **Amaç (v1.3):** v1.1'in atmosfer omurgasını **korumak** ve üzerine (a) yaşayan-Hero doktrinini, (b) motion/perf bütçelerinin ölçülebilir kilitlerini, (c) governance zorlayıcı-fonksiyonlarını ve (d) tek-kaynak renk/hairline/glow migration'larını eklemek. Değişen her değer **Migration (v1.1→v1.3)** satırıyla işaretlidir; hiçbir bölüm numarası/başlığı yeniden adlandırılmadı.

> **Kilit durumu (v1.3 KANONIK):** **Renk kilidi AÇIK** — 20-hücre WebAIM kontrast tablosu dolduruldu (DoD-5 geçti); tüm semantik hex + a11y-türevleri WCAG-hesaplı ve kilitli. **Süre kilidi AÇIK** — motion tek rejim, ayrık token seti (aralıklar kaldırıldı). Aşağıdaki değerler artık açık-uç değildir.

---

## 01 · Sayfanın genel ışık dili

Atmosferin anayasası. Üç kural her sayfada geçerlidir.

1. **Işık = bilgi.** Parlayan her şey anlam taşır. Sayfanın en parlak pikselleri **veri** (fiyat, seviye, skor — enstrüman/Karot) ve **birincil CTA**'dır. Dekoratif ışık daima loş ve yönlü — asla içerikle yarışmaz. **Squint testi:** gözünü kıstığında yalnız **enstrüman (kahraman-rakam/veri) + CTA** seçilmeli *(v3.0: Karot emekli — taşıyıcı = owned-numeral/veri).*
2. **Tek anahtar ışık.** Her sayfada **bir** anahtar ışık kaynağı: sağ-üstten süzülen mavi "ufuk" ışığı; sol-alttan çok zayıf cyan dolgu. İki *yönlü* kaynaktan fazlası yasak. *(Köşe-demirli bokeh diskleri yönsüzdür, ışık kaynağı sayılmaz — §03; yine de ≤2.)*
3. **Cyan = AI'nın parmak izi.** `--cyan #25E0D4` asla dekor değildir. Yalnız AI'nın dokunduğu yerde: güven izi, AI özeti, sinyal-anı vurgusu, Karot omurgası. Kullanıcı öğrenir: *cyan gördüysem, AI konuştu.* Cyan yalnız **çizgi/nokta/iz/omurga**; yüzey/dolgu/buton/başlık **yasak.**
   **Migration (v1.1→v1.3):** cyan literali `#22D3EE` → `--cyan #25E0D4` (owned electric-teal). `--accent-2/--cy` aliasları buraya bağlanır; `#22D3EE` grep = 0.

### Parlaklık = yaşam-döngüsü olayı (hukuki ışık ayrımı)

> Bu madde §01 ışık dilinin governance kilidi; Bible §06 legal ile ortaktır.

- **Direktif:** Parlaklığı asla örtük öneri-sıralaması taşıyacak şekilde kullanma; parlaklık yalnızca **yaşam-döngüsü olayına** (doğum · approaching · kapanış · kazanç) bağlanır. Tazelik / dikkat-çekme / sıralama ışığı **yasak** (hukuki risk).
- **Token/değer:** Parlaklık kaynağı = yalnız yaşam-döngüsü telemetri olayı (birth · approaching_tp · settle · kazanç).
- **Teknik:** Parlak-sinyale-dikkat = örtük öneri sırası = "yatırım tavsiyesi değildir" çerçevesinde hukuki risk. Işık **olaydır, yargı değildir.**
- **DoD:** Hiçbir yüzeyde parlaklık "daha taze / daha önemli öneri" anlamına gelmiyor; her parlaklık/glow tetikleyicisinin kaynağı izlenebilir bir yaşam-döngüsü telemetri alanına bağlı.
- **Ölçüm:** Kod/telemetri denetimi — her glow tetikleyicisinin kaynağı bir lifecycle-event alanına bağlı (evet/hayır); sıralama/tazelik kaynaklı parlaklık = 0.

---

## 02 · Background katman yığını

Beş katman, aşağıdan yukarı. Hepsi CSS/SVG — L4 hariç hiçbiri animasyonlu değildir *(app sayfalarında; landing L1 glow-drift'i için bkz. §08)*.

| Katman | İçerik | Nerede | Teknik |
|---|---|---|---|
| **L0 · Zemin** | Düz `--e0 #070B14`; section almaşığı `--e0`↔E1 bandı | Her yerde | CSS |
| **L1 · Anahtar ışık** | `--light-key` mavi radial sağ-üst + `--light-fill` cyan sol-alt | *(v3.0 düzeltme)* landing (+ app'te YALNIZ Dashboard **Nabız carve-out'u** — Bible dash-nabız-v3, statik; `--light-fill` app'te KULLANILMAZ; glow-drift kapalı) | CSS radial-gradient |
| **L2 · Noise** | Mono grain %2–3, soft-light blend — banding-katili | landing · auth · **tam-yüzey empty-state** | SVG feTurbulence data-URI, 128px tile |
| **L3 · Grid kâğıdı** | 1px çizgi ızgara %5, radial-maskeyle eriyen | landing hero · **empty-state kart sınırları** | CSS gradient + mask |
| **L4 · Sinyal tozu** | 20–40 loş nokta = taranan varlıklar; ara sıra biri cyan/mavi nabız = "sinyal doğdu" | **yalnız landing hero** | Canvas 2D (≤40 nokta, 30fps cap) |

**Migration (v1.1→v1.3):** L0 zemin `--bg #070B14` → `--e0 #070B14`; `--bg-alt` almaşığı E1 bandına hizalanır. Yüzey ad-ailesi tek: `--e0..--e3` (alias `--bg/--surface-0..3` → `--e0..--e3`). Zemin literali `#020817`/`#0A101C` → `--e0`/E-merdiveni; grep `#020817` = 0.

**Kanonik ışık tokenı:**
`--light-key: radial-gradient(1200px 600px at 78% -10%, rgb(59 87 212 / .11), transparent 60%)`
`--light-fill: radial-gradient(800px 480px at -4% 30%, rgb(37 224 212 / .05), transparent 55%)`
Tüm sayfalar bu değeri kullanır; "%10-12" gibi aralıklar bu tek tokena bağlıdır.
**Migration (v1.1→v1.3):** anahtar-ışık rgb `59 130 246` → `59 87 212` (owned-blue ufuk); dolgu rgb `34 211 238` → `37 224 212` (owned cyan).

### Sayfa sınıflandırması
Atmosfer kuralları sayfa sınıfına bağlıdır. Her route bir sınıfa girer:

| Sınıf | Route'lar | İzinli katmanlar |
|---|---|---|
| **landing-tipi** | `/` (landing), pricing, about | L0 · L1 (§08 glow-drift) · L2 · L3 (hero) · L4 (yalnız landing hero) · bokeh · scroll efektleri |
| **auth** | login, register, şifre | L0 · L1 (statik) · L2 · bokeh — **hareketli ambient/koreografi yok** (§09) |
| **app-tipi** | dashboard, signals, markets, portfolio, performance, settings, admin, legal, help, onboarding | **yalnız L0 + L1 (statik).** Ambient/paralaks/noise/grid **yasak.** |

**Empty-state istisnası:** App sayfasındaki bir boş-durum için sayfa geneli yine L0+L1 kalır; **yalnız empty-state bileşeninin KART SINIRLARI içinde** L3 grid (ve gerekirse L2 noise) izinlidir ve **veri render edildiği an kalkar.**

### Yaşayan Hero yüzeyi = landing-hero örneği (app-dashboard ile AYRI motion bütçesi)

> ## ⚠️ REVİZE / SUPERSEDED — Karot-hero atmosferi → Karot'suz canlı-kanıt · *(VL v2.0 · CP-HERO-DOC · 2026-07-18)*
>
> Bu bölümün ("Yaşayan Hero yüzeyi" 40-Karot · §07 Hero-lighting/squint · hero-üst-cümle "40 Karot açılış") **Karot-merkezli kısımları SUPERSEDED** — Karot üründen kaldırıldı (CP-KAROT-DOC v1.7). Tam yeni tez **Bible §02 baş-banner**'ında; VL tarafı (atmosfer/motion) özeti:
> - **Merkez öge:** 40-Karot masası DEĞİL → **Canlı Masa / live terminal proof-surface** (gerçek sinyal masası/bandı) + owned-number hero + proof-receipt + instrument-well. Glyph/şekil YOK.
> - **Atmosfer-çıpası:** "Karot doğdu" (L4 cyan-nabız) yerine → gerçek sinyal satırının **belirişi** · owned-number **settle** · receipt **reveal** (hepsi telemetri-bağlı).
> - **Squint (yeniden):** en parlak 2 = **H1 + birincil-CTA** (Karot DEĞİL; v1.4.1 landing carve-out formalize).
> - **KORUNAN:** tek-anahtar-ışık (§01) · 3-ışık bütçesi (§07) · bokeh ≤2 (§03) · noise/grid L2/L3 · **signal-dust L4** (artık gerçek-sinyal-belirişine bağlanır, Karot-doğumuna değil) · reveal-only motion · **§11 kalıcı-yasaklar (3D/WebGL/R3F/Three/Spline/video/scroll-jack/neon) AYNEN + güçlenir** (+ robot/globe/generic-AI/gradient-mesh + yeni-glyph-yok).
> - **Motion:** `transform`/`opacity` reveal · scrubber / scroll-jack / wheel-intercept / Lenis YOK · idempotent · reduce-motion statik · motion proof görünürlüğüne hizmet eder.
>
> *Aşağıdaki orijinal içerik tarihsel; Karot-bağımlı kısımları normatif DEĞİL.*

> **Açık-uç / bağlayıcı çözüm:** 40-Karot canlı-konsensüs yüzeyi hem landing-hero hem app-dashboard bağlamında geçer; iki bağlamın **motion doktrini AYRIDIR.**

- **Direktif:** Landing açılışını bir tanıtım filmi değil, gerçek-zamanlı gerçek-veriyle beslenen bir **yaşayan AI sistemi** olarak kur; amaç "wow" değil, ilk 10 saniyede AI'yı hissettirmek. Önceden-pişmiş beat/sahne kurgusu **kullanılmaz.**
- **Token/değer:** landing-hero = canlı settle + glow-drift izinli (landing bütçesi); app-dashboard = idle-sessiz, yalnız telemetri-olayı tek-atım `--dur-settle` (≤600 app-tavanı), ambient/drift = 0. **Paylaşılan = Karot render fonksiyonu + veri-mekaniği, motion bütçesi DEĞİL.**
- **Teknik:** Hero, statik pazarlama görseli/video yerine dashboard'un canlı hali olan bir konsensüs yüzeyi render eder. Tüm görsel öğeler (Karot omurgaları, doğum, bölünme, fikir-değiştirme) gerçek sinyal verisinden türer; sahte/mock veri veya scripted timeline **yasak.**
- **DoD:** Landing hero'sundaki her hareketli/ışıklı öğe bir backend telemetri alanına bağlı; scripted/hardcoded açılış sekansı yok; hero içeriği dashboard ile **aynı Karot primitifini** kullanır. İlk-boyama sonrası 10 sn içinde en az 1 canlı olay (doğum/settle) görünür.
- **Ölçüm:** Kod denetimi — hero bileşenlerinde sabit/mock veri kaynağı = fail; her animasyon-tetikleyici bir telemetri alanına iz sürülebilir (grep + review).

### Hero üst-cümle & CTA (birebir)

- **Üst-cümle:** `9 motor. Tek yargı. Gizli değil.` (birebir)
- **Birincil CTA:** `Kendi sinyalini izle` (tek birincil, glow sahibi; ikinci glowlu CTA yok — deneyime davet).
- **Hero açılışı:** 40 Karot / ilk ekran; **≥1 doğum + ≥1 bölünmüş + ≥1 fikir-değiştiren** garanti.
- Şiirsel iç-dil (Karot/közleşme/omurga) UI'da yasak (§10 · iç-dil kuralı).

### 3D/WebGL statüsü (hero)

> **⚠ VL-MOTION-v3 REVİZE (v2.1):** "ŞU AN 0 / DEFERRED" statüsü → **gated-conditional future CP** olarak yeniden-sınıflandı. Generic/dekoratif 3D yasak AYNEN; yalnız **TradeMinds-native × bilgi-taşıyan** proof / instrument-well derinliği, 8-kabul-kapısı + mobil-fallback + reduced-motion-statik + LCP/CLS-koruması + ayrı onayla açılabilir (CP-HERO-NATIVE-3D). Tek kanonik ayrım: "VL-MOTION-v3" bölümü.

- **Direktif:** Karot **ENSTRÜMANI** her ölçekte (16/48/200 hero dahil) istisnasız **2D SVG.** 3D/WebGL yalnızca bilgi taşırsa ve tam perf/erişilebilirlik bütçesini karşılarsa hero'da düşünülebilir; dekoratif 3D **asla.** Koşullu-3D yalnız Karot-DIŞI atmosfer/derinlik katmanına ait olabilir ve **ŞU AN DEFERRED** (VL §11).
- **Token/değer:** 3D/WebGL statüsü = **ŞU AN 0** (DEFERRED, VL §11). Koşullar (açılırsa): bilgi-taşıyan-3D · DPR-cap ≤2 · poster/statik fallback · reduced-motion statik · mobil 2D fallback · lazy/code-split.
- **Teknik:** Mevcut karar — Karot 2D SVG/Canvas'ta sinematik ışık + settle ile render edilir; 3D gelecek-araştırma maddesidir. `hero-3d-webgl-koşullu` Karot'a **uygulanmaz.**
- **DoD:** Bundle'da kimlik-merkezi three/R3F/postprocessing = 0; hero'da kamera-hareketi/scrubbed-timeline/cyan-tarama-beat kodu yok.
- **Ölçüm:** Bundle analizi: initial-chunk'ta three/@react-three/postprocessing yok. Kod taraması: dolly/orbit/scrub-timeline/scan-beat pattern = fail.

---

## 03 · Ambient glow & Bokeh

> **⚠ S0 v3.0 — BOKEH EMEKLİ:** bokeh diskleri (landing + auth) v3'te KULLANILMAZ; premium etki key-light + depth + proof-surface + hairline + controlled-glow + materyal sistemiyle kurulur. Aşağıdaki bokeh satırları tarihsel kayıt; yeniden açılması ayrı karar ister. Glow kuralları AYNEN yürürlükte.

Glow bir ödüldür, hak edilir. Bokeh bir mekân hissidir, dekor değil.

- **HOVER-glow sahibi:** yalnız **birincil CTA.** Kart/panel/başlık/ikon/satır/nav hover'da **asla** glow almaz.
- **OLAY-glow sahibi (hover değil, olay-bağlı):** **CTA + AI-doğum-cyan (Karot omurga underlay dahil) + kullanıcı-kazanç-amber.** Semantik bull/bear **asla** glow (yön tinti = area-fill `fill-opacity .14`, glow değil).
- **glow reçetesi:** `--glow-cta: 0 8px 24px -12px var(--accent)` — hue çözülmüş `--accent #3B57D4` (CTA-dolgu gölge-hue'su; iz/border DEĞİL).
- **glow bütçesi (istisnasız):** opaklık ≤ `.14` · blur `12-24px`. Hover'da yalnız **opacity** artar, blur **sabit** (blur GPU-animasyonlanmaz). Hover geçiş süresi = `--dur-warm 140`.
  **Migration (v1.1→v1.3):** VL §14 önerisi (α .20-.35 / blur 16-32px) **düşürüldü** → kanonik α ≤ `.14` / blur `12-24px` (daha kısıtlayıcı kural kazanır; luminans-depth + premium=az ile tutarlı). CI-lint tavanı `.14`. WebAIM/squint sonrası kilit.
- **bokeh yeri:** landing + auth; sayfa başına **en çok 2 disk**, köşelere demirli, metinle çakışmaz. Yönsüz oldukları için §01 "tek anahtar ışık" bütçesine dahil değildir.
- **bokeh tekniği:** radial-gradient falloff. `filter:blur` ile canlı bulanıklık **yasak** (paint fırtınası).
- **semantik ışık:** bull/bear renkleri **asla** atmosfer olmaz — yalnız veri durumu anlatır.

**Kalıcı temizlik (KALICI YASAK):** SignalBadge/RiskGauge/Button'daki ham renkli glow-rgba (`rgba(0,230,118,·)` · `rgba(255,82,82,·)` vb.) temizlenir; parlaklık yalnız token ailesinden gelir. Ham box-shadow / renkli glow-rgba **CI-red.** Neon/RGB kalıcı yasak. Grep `rgba(0,230,118|rgba(255,82,82` (src+public) = 0.

### efekt-bütçesi-v3 *(S0 KANONU — her efekt anlam taşır)*

| Efekt | Statü | Sınır |
|---|---|---|
| Grain (L2) | VAR | yalnız landing/auth/empty zemini · **statik** · ≤%3 · veri-yüzeyinde YASAK ("atmosfer dışarıda, hassasiyet içeride") |
| Key-light (L1) | VAR | landing + app'te YALNIZ Nabız carve-out (statik; Bible dash-nabız-v3) |
| Diegetik glow | VAR | yalnız CTA + lifecycle-event; **"makbuzda karşılığı olan olay" kuralı** — nedensiz ambient hale yasak |
| Foton-ailesi | VAR | olay-bağlı tek-atım; dar-tanım (§09) |
| Cut-lip | VAR | kart/panel/buton + **E3-cam reçetesine eklenir (S1; e3-materyal-v2)** |
| İki-katman gölge | YENİ (S1) | YALNIZ E3-overlay; tek `--shadow-e3` token-revizyonu |
| Hairline-grid (L3) | VAR/eksik | boş-sahne/empty-state statik craft (S2/S7) |
| **Bokeh** | **EMEKLİ** | kullanılmaz; yeniden-açılış ayrı karar |
| Light-sweep/glint | ELENDİ | kalıcı |
| **Random-particle · orb · kristal · soyut-3D obje · Karot** | **YASAK** | v3-karot-kapanış (Bible §00-V3); landing sinyal-tozu YALNIZ diegetik istisna (L4) |

---

## 04 · Noise texture

Amaç "doku hissi" değil — **gradient banding'ini öldürmek** ve karanlığa film greni sıcaklığı vermek.

- **Direktif:** Near-black midnight zeminde banding'i öldürmek için tek 128px feTurbulence tile kullan; animasyonlu grain, %6 üstü opaklık, veri tablosu/grafik üstünde noise **ebediyen yasak.**
- **Token/değer:** tile 128px · data-URI **<2KB** · blend `soft-light` (düşük-uç cihazda düz opaklık fallback) · alfa `.02–.06` (asla >.06). Zemin tabanı `--e0 #070B14`.
- **Teknik:** Statik tek `<feTurbulence>` SVG tile, data-URI gömülü; `mix-blend-mode:soft-light`. Katman yığınında L2 = noise %2–3, veri render edildiği an app'te kalkar. `filter:blur` canlı bulanıklık + animasyonlu grain **kesin yasak.**
- **Uygulama:** landing · auth · tam-yüzey empty-state; app sayfa-genelinde yasak (**tek istisna: kart-sınırlı empty-state**).
- **DoD:** Landing/auth/tam-empty'de görünür grain YOK ama banding kırılır; app veri yüzeylerinde noise yok; noise tek statik tile'dan gelir; data-URI <2KB.
- **Ölçüm:** noise data-URI byte-boyutu <2048B (build asset kontrolü); computed opacity α ∈ [.02,.06]; app dashboard/signals/markets viewport'larında noise-layer = 0; grep animasyonlu grain/keyframe = 0.
- **Migration (v1.1→v1.3):** blend `overlay` → `soft-light`; opaklık tavanı açıkça `.06`; data-URI boyut kilidi `<2KB` eklendi.

---

## 05 · Depth — lüminans merdiveni

Koyu arayüzde gölge görünmez; derinliği **ışık** anlatır. Yüzey yükseldikçe +1 lüminans basamağı aydınlanır, hairline belirginleşir. **Derinlik = kanıt mesafesi** (yüzeyde sonuç, altında gerekçe, en altta ham veri).

### Yüzey lüminans merdiveni E0–E3 (near-black midnight, OKLCH-kalibreli, WCAG-kilitli)

| Seviye | Yüzey | Hairline |
|---|---|---|
| **E0 · Zemin (Ground)** | `--e0 #070B14` | `--hl10 .10` |
| **E1 · Kart/panel** | `--e1 #0C1220` | `--hl12 .12` |
| **E2 · İç/yükselmiş yüzey + hover ısınma hedefi** | `--e2 #111A2B` | `--hl16 .16` (yalnız etkileşim) |
| **E3 · Overlay/cam** | `--e3 #17233A` | `--hl22 .22` + `--shadow-e3` + backdrop-blur 8-10px |

- **Direktif:** Tüm yüzeyleri yalnızca dört basamaklı E0–E3 setinden türet; beşinci gri asla icat etme, ara-ton hardcode etme. Zemin/yüzeyleri asla saf siyaha (`#000000`) veya nötr-graphite griye kaydırma — daima **midnight-blue tint** taşı.
- **Teknik:** OKLCH-kalibreli near-black midnight-blue tint merdiveni; her basamak bir elevation seviyesini lüminans artışıyla temsil eder (gölge değil lüminans farkı derinlik kurar). Saf siyah OLED'de halation yaratır ve elevation sistemini çökertir.
- **DoD:** src+public'te yüzey rengi olarak yalnız `--e0..--e3` geçer; ham hex yüzey/zemin/kart/overlay'de 0; 5. gri token yok; zemin/yüzeyde `#000000` veya hue'suz gri (r=g=b) yok.
- **Ölçüm:** CI-lint: yüzey/background özelliğinde token-dışı hex reddi; grep `#020817|#0A101C` (src+public) = 0; token sayımı tam 4 (E0-E3); `--e0`'ın RGB kanalları eşit-değil (B>R,G → mavi tint); ölçülen lüminans monotonik artar.
- **Migration (v1.1→v1.3):** E-merdiveni ham hex → `--e0..--e3` CSS değişkeni; hairline satırı white-alpha yerine **slate-taban** `--hl10..--hl22`'ye hizalandı.

### Metin kontrast merdiveni (WCAG-hesaplı, E0–E3 hepsi doğrulandı)

> Renk kilidinin okunabilirlik yüzü. Her metin tokeni tüm yüzey basamaklarında (E0-E3) hesaplanmış kontrast taşır.

- **Token/değer:**
  - `--tx #E8EDF5` — ana metin (E0-E3 hepsi ≥6.3:1; AAA-yakını).
  - `--tx2 #9AA6B8` — ikincil metin / **okunur mikro-etiket floor** (E0-E3 hepsi ≥6.3:1).
  - `--tx3 #5C6980` **KISIT** — okunur metin **DEĞİL** (tümü <4.5:1); yalnız UI-obje/dekor için ve yalnız E0-E2 zeminde; **E3'te UI olarak da kullanma** (<3). Rolleri: dekoratif/disabled + Karot kararsız omurga (UI-iz, ≥3) + közleşme kül tonu.
- **DoD:** Okunur her metin ≥`--tx2`; `--tx3` hiçbir okunur metinde geçmez; `--tx3` E3 zeminde UI-obje olarak da geçmez.
- **Ölçüm:** Kontrast-lint: metin rolündeki token × zemin ≥4.5:1 (küçük) / ≥3:1 (büyük/UI); `--tx3` metin-rolü eşleşmesi = 0; `--tx3`-on-E3 UI = 0.

### Border / hairline alfa merdiveni (slate-taban, semantik + anizotropi)

- **Direktif:** Yüzey ayrımını önce boşlukla, yetmezse hairline ile kur; asla renkle veya kutuyla ayırma; hairline alfasını semantik merdivenden seç.
- **Token/değer (TEK aile, slate-taban `rgba(148,163,184,·)`):**
  - `--hl10 rgba(148,163,184,.10)` — dinlenme / panel-içi bölünme / chart grid
  - `--hl12 rgba(148,163,184,.12)` — **standart/varsayılan** (kart/panel/section/input/tooltip/crosshair · Karot eksen)
  - `--hl16 rgba(148,163,184,.16)` — etkileşim (hover/focus-within)
  - `--hl22 rgba(148,163,184,.22)` — kanıt/odak (input focus, E3 overlay border)
- **Teknik:** Border=ayrışma (anlam değil); anlam renkten gelir. **Anizotropi (imza referansı — "kabin" kenar işlemesi):** dikey kenarlar net (tam alfa), yatay kenarlar soluk (düşük alfa) → ışık-yönü tutarlılığı; yükselen yüzey bir ışık altındaki kabin gibi okunur (üst-kenar cut-lip §05 rim ile birlikte imzayı kurar).
- **DoD:** Yüzey ayrımı kutu/renk ile değil boşluk→hairline sırasıyla; hairline alfası dört semantik değerden biri; anizotropi (dikey>yatay alfa) uygulanır.
- **Ölçüm:** Lint: border-color olarak yalnız `--hl*` ailesi; token sayımı tam 4 (.10/.12/.16/.22); dikey kenar alfası > yatay kenar alfası.
- **Migration (v1.1→v1.3):** COL-10 white-alpha `rgba(255,255,255,·)` beyanı **slate-tabana** hizalandı (fiili kullanım + anizotropi/self-ayar kazanır); `--hl-rest/--hl/--hl-interact/--hl-focus` aliasları `--hl10..--hl22`'ye bağlandı.

### Depth mekaniği (kanıt mesafesi + z-scale)

- **Direktif:** Derinliği YALNIZ lüminanstan üret; blur ile derinlik yaratma. z-eksenini sabit ölçeğe kilitle; ad-hoc z (20..110) temizlenir. Odakta aynı anda **en fazla 2** elevation katmanı.
- **Token/değer:** `z-sticky 10` · `z-dropdown 40` · `z-modal 50` · `z-toast 60` · `z-tour 100`. Gölge yalnız E3: `--shadow-e3: 0 16px 40px -20px rgba(0,0,0,.7)` (tek gölge token, daima `--cut-lip` ile kombine). Kart gölgesiz.
- **Teknik:** Depth ipuçları sırası: birincil=lüminans (E0→E3), ikincil=gölge (yalnız E3 overlay), üçüncül=paralaks (yalnız landing). z-index yalnız bu 5 token'dan.
- **DoD:** Tüm z-index değerleri {10,40,50,60,100}; ad-hoc z yok; odakta eş-zamanlı >2 elevation katmanı yok; derinlik luminanstan okunur.
- **Ölçüm:** Grep: z-index literalleri yalnız {10,40,50,60,100}; dışı = 0. DevTools: eş-anlı açık overlay/elevation ≤2. Derinlik-için-blur (E3 dışı) = 0.

### Rim / cut-lip highlight (kapsam sınırlı)

- **Direktif:** Yükselen **kapalı-yüzeylere** (kart/panel/overlay/buton gövdesi) üst kenarda 1px cut-lip highlight ver.
- **Token/değer:** `--cut-lip: inset 0 1px 0 rgba(255,255,255,.07)` (specular amplitüd ≤1px).
- **Teknik/kapsam:** Karot gibi **çizgi/tel-tabanlı** enstrüman primitifleri kapalı-yüzey olmadığından cut-lip **ALMAZ**; Karot imzası kendi ışık-underlay'idir (§07/Bible §05). Kart hover'da rim cyan'a **dönmez** (cyan yalnız çizgi/iz).
- **DoD:** cut-lip yalnız kart/panel/overlay/buton; Karot SVG'de cut-lip = 0.
- **Migration (v1.1→v1.3):** v1.1'deki "rim cyan'a döner (AI dokunuşu)" ifadesi **kaldırıldı** (cyan-yalnız-çizgi tekeli; AI dokunuşu Karot omurga/iz üzerinden verilir).

### e3-materyal-v2 *(S0 KANONU · uygulama S1)*

Overlay'in TEK premium reçetesi — "jenerik glassmorphism" DEĞİLDİR: near-black'te katmanlamayı E-merdiveni yapar; E3-cam **dar-işlevsel** istisnadır.
- **Panel:** `.glass-e3-overlay` (E3 ~%92 + blur 8-10px + `--hl22` hairline) + **`--cut-lip` üst-kenar ışığı** + **iki-katman `--shadow-e3`** (dar-keskin temas + geniş-yumuşak ambient; tek token revizyonu; gölge YALNIZ E3).
- **Scrim (standart):** `bg-e-0/70` + `backdrop-blur-sm`; panel motion'uyla **senkron** fade; alfa/blur sapması = fail (LockedOverlay blur-md → banda çekilir).
- **Motion:** giriş + **reverse-exit zorunlu** (Yasa-4; **PI-1b**: Dropdown/Tooltip dahil); deterministik-timer; **kesintiye-açık** (kullanıcı aksiyonu animasyonu anında keser).
- **Mobil:** bottom-sheet = `align="bottom"` + slideUp + edge-to-edge + statik drag-handle; touch ≥44px.
- **Kural:** tüm modal/drawer kabukları kanonik `ui/Modal`'dan türer (focus-trap/aria/ESC/scroll-lock tek-kaynak); ad-hoc overlay kabuğu = fail; z-index yalnız token (dropdown 40 / modal 50 / toast 60 / tour 100).
- **DoD (S1):** ad-hoc modal kabuğu = 0 · exit'siz overlay primitifi = 0 · scrim-sapması = 0 · hardcoded z = 0 · 6-mikro-durum tamlığı (default/hover/focus/active/disabled/loading).

---

## 06 · Section geçişleri

Sert sınır yok, dalga/diyagonal kesim yok. Üç sessiz araç:

1. **Lüminans almaşması** — ardışık section zeminleri E0 ↔ E0-alt/E1 bandı (+1 lüminans basamağı). Göz sınırı hisseder, çizgi görmez.
2. **Ufuk çizgisi (su hattı)** — 1px hairline `--hl12` + tek lüminans basamağı (düz yatay hat). **Sayfada en çok 2 kez**, yalnız büyük bölüm dönüşümlerinde (hero→kanıt, içerik→final CTA).
3. **Seviye çizgisi motifi** — ürünün kendi dilinden: kesikli seviye çizgisi + fiyat-etiketi çipi; yalnız anlamlı yerlerde (dekor değil). TradeMinds imzası.

### Section sınırı (su hattı) — kanonik

- **Direktif:** Section geçişini yatay 1px hairline + tek lüminans basamağı olarak kur. Diyagonal, dalga, eğik veya clip-path section kesimi **asla.**
- **Token/değer:** `section-divider: 1px --hl12 + 1 lüminans basamağı`; ufuk çizgisi max 2/sayfa.
- **Teknik:** `section{border-top:1px solid var(--hl12)}` + geçişin bir yanında 1 lüminans basamağı. "Su hattı" yalnız iç-dildir, UI metnine çıkmaz (§10).
- **DoD:** Tüm section geçişleri düz yatay hairline + lüminans basamağı; eğik/dalga kesim yok; sayfada ≤2 ufuk çizgisi.
- **Ölçüm:** DOM: section ayraçlarında clip-path/`transform:skew`/SVG-wave = 0; her section border-top computed = `--hl12`; sayfa başına belirgin ufuk çizgisi ≤2.
- **Migration (v1.1→v1.3):** v1.1 "accent→cyan gradient hairline" → düz `--hl12` hairline + lüminans basamağı (renkli gradient section-ayracı bırakıldı; renk anlamdan, ayrım hairline+boşluktan).

---

## 07 · Hero lighting (yaşayan) — Gerçek-Olay Havuzu

Bible split-hero'suna ışık planı. Sahne üç ışıkla kurulur — fazlası yasak. **Hero yaşayan bir sistemdir, film değildir** (§02 · yaşayan Hero).

> **Gerçek-Olay Havuzu doktrini (kanonik):** Hero'daki her ışık **gerçek bir olayı** temsil eder; sahne, gerçek-veriyle beslenen, scroll-driven, koşullu-3D'ye açık ama şu an 2D bir **olay havuzudur.** Sahte-sinema (önceden-pişmiş beat, dekoratif kamera hareketi, veri temsil etmeyen efekt) **tamamen yasaktır** (§11 · Kalıcı Yasaklar). Veri canlı-değilse (arşiv/gecikmeli), dürüst etiket zorunludur: "canlı-değil / arşiv" görünür işaretlenir; asla canlı gibi sunulmaz.

- **① Anahtar** — mavi ufuk, sağ-üst (`--light-key`).
- **② Dolgu** — cyan, sol-alt (`--light-fill`).
- **③ Rim** — ürün kartının üst kenarı, 1px cut-lip (kapalı-yüzey; Karot değil).
- Arkada L3 grid + L4 sinyal tozu.

### Squint testi (hero DoD · zorlayıcı fonksiyon)

> **REVİZE (VL v2.0 · CP-HERO-DOC)** — landing-hero'da en parlak 2 = **H1 + birincil-CTA** (Karot DEĞİL; Karot kaldırıldı). Legal "parlaklık öneri itmez" AYNEN. Bkz "Yaşayan Hero yüzeyi" baş-banner + Bible §02.

- **Direktif:** Açılış/hero'da gözler kısılınca **en parlak iki öge YALNIZ enstrüman (Karot) ve birincil CTA** olmalıdır; parlaklık hiçbir şekilde öneri/dikkat itmez (legal).
- **Token/değer:** en parlak 2 öge = {Karot enstrümanı, birincil CTA}; dekoratif ışık daima loş/yönlü.
- **Teknik:** Hero'nun en yüksek luminanslı pikselleri veri (Karot omurgası/doğum nabzı) ve CTA olmalı; dekoratif ışık (anahtar/dolgu/rim) daima loş, içerikle yarışmaz. §07 üç-ışık bütçesiyle (anahtar+dolgu+rim) uyumlu.
- **DoD:** Bulanık/düşük-parlaklık render'da yalnızca Karot ve CTA seçiliyor; hiçbir dekoratif öge onlardan parlak değil.
- **Ölçüm:** Hero screenshot'ı Gaussian blur (~8px) + eşikleme sonrası en parlak iki bölge = Karot + CTA (perceptual diff); dekoratif katman luminans ≤ veri luminans.

### Giriş koreografisi — kanonik timeline (yaşayan, telemetri-tetikli)

> **Not (v1.3):** Aşağıdaki sıralama **yapısal reveal** iskeletidir (transform/opacity, bir kez); "doğum/settle" **olayları scripted değildir — telemetri geldiğinde bir kez tetiklenir ve geri sarılmaz** (§08 · scroll = canlı muhakeme). Süreler §09 ayrık süre-token setinden gelir.

| Adım | Başlangıç | Süre (token) | Easing |
|---|---|---|---|
| Işık sahnede | 0ms | — (statik) | — |
| Başlık + CTA fade-rise | 0ms | `--dur-settle 520` giriş bandı içinde (reveal) | ease-out |
| Ürün kartı fade | 400ms | reveal (transform/opacity) | ease-out |
| Karot fitilleri (yatay-nötrden dönüş, stagger 50ms) + karar-ucu settle | 500ms | `--dur-settle 520` (≤600 app-tavanı) | spring (`--ease-signal` fitil-dönüşü) |
| Sinyal tozundan cyan doğum nabzı | telemetri-anı | `--dur-photon 150` (nabız) | — |

Anlatı: *AI taradı, sinyal doğdu.* **Reduced-motion:** koreografi atlanır, sahne bitmiş hâliyle açılır; nabız statik parlak nokta olur; scroll-linked her beat statik tam-opak son-kare olarak görünür (bilgi kaybı 0).
**Migration (v1.1→v1.3):** "Seviye çizgileri stagger 80ms / ~900ms sabit timeline" → Karot fitil-dönüş + karar-ucu settle (stagger **50ms**, `--dur-settle 520`), ve son nabız **telemetri-anı** (sabit ~850ms değil).

---

## 08 · Scroll atmosferi & Hover hissi

### Scroll — global davranış

- **Direktif:** `html{scroll-behavior:smooth}`; `prefers-reduced-motion:reduce` → `auto`. Scroll yön/hızını **asla** ele geçirme.
- **Token/değer:** `html{scroll-behavior:smooth}` · reduced-motion → `auto`. **Kalıcı yasak:** scroll-jacking · wheel-intercept · zorunlu-snap · Lenis.
- **Teknik:** Global native smooth-scroll; reduced-motion'da anlık. Kullanıcının scroll ekseni/hızı programatik ele geçirilmez.
- **DoD/Ölçüm:** Grep `lenis`/`smooth-scroll` importu = 0; `preventDefault` wheel/touchmove hız-hijack'ı = review-red; `scroll-snap-type: *mandatory` pin-sahne ≤0 (landing tek pin istisnası hariç); reduced-motion'da bilgi kaybı 0.

### Scroll — yalnız landing (Gerçek-Olay Havuzu · yaşayan muhakeme)

- **glow-drift:** L1 ışık katmanı **0.92× hızda** kayar (transform-only) — landing'in tek **animasyonlu ambient** istisnası budur (§02 dipnotu). Noise **statiktir**, ambient-sayıma girmez. *(v3.0 not: glow-drift Doctrine §9'da KAPALI-beklemededir — bu satır tavan-tanımıdır, izin değildir; geçerli hal = statik key-light.)*
- **reveal:** section girişinde fade + 8px yükselme, stagger 50ms (`stagger-liste`), **bir kez** (transform/opacity), süre `--dur-settle 520`. *(v3.0/S6: + CSS `animation-timeline: scroll()/view()` scroll-driven tek-atım mikro-koreografi — IO-fallback; yalnız landing; Doctrine v2 sözlüğü.)*
- ~~**count-up:** istatistik şeridi viewport'a girince `--dur-settle 520` sayar — tek "vay" anı (yalnız landing).~~ *(v3.0 KALDIRILDI: count-up HER YERDE yasak — Motion Doctrine Yasa-1/§5; sayının kendisi değerlidir, ara değer yalan söyler.)*
- **Direktif (scroll = canlı AI muhakemesi, scrubber DEĞİL):** Scroll ilerledikçe kanıt AÇILIR (AI düşünür → motorlar uzlaşır → konsensüs → karar doğar); ancak scroll bir video-scrubber gibi kullanılamaz — scroll geri alınınca muhakeme **geri sarılmaz**, olaylar birer kez olur (idempotent, tek-yön). Her ışık gerçek bir olayı temsil eder; canlı-değilse dürüst "arşiv" etiketi taşır (§07 Gerçek-Olay Havuzu).
- **Teknik:** Scroll-progress yalnızca kanıt katmanlarının görünürlüğünü/derinliğini açar (transform/opacity), zaman-eksenini ileri-geri sürmez; scroll-progress **gerçek telemetriye** bağlıdır. Birincil araç: native CSS `animation-timeline: scroll()/view()` (`@supports` guard) + IntersectionObserver fallback (bir kez, unobserve).
- **app sayfaları:** scroll efekti **yasak.**
- **Parallax:** yalnız landing (analiz-katmanı temsili); **maks 3 strata, hız farkı ≤0.06, transform-only**; app'te paralaks 0. L1 glow-drift (0.92×) landing'in tek animasyonlu L1 istisnası. *(v3.0 not: parallax + drift Doctrine §9'da KAPALI-beklemededir; bu satır tavan-tanımıdır, izin değildir — açılış ayrı kullanıcı-onayı ister.)*
  **Migration (v1.1→v1.3):** eski dekoratif hero-parallax taşıyıcısı **atıldı**; yaşayan-Hero için paralaksın rolü ≤3 strata analiz-katmanı temsili olarak sınırlandı (§11 · Gerçek-Olay Havuzu).

### Sticky header — kanonik reçete

Sticky header **glass/E3 değildir**; **blur'suz** çözüm kullanır (daha ucuz + jank'siz):
- `background: rgba(7, 11, 20, .72)` + **alt hairline `--hl12`**; **backdrop-blur YOK.**
- `scroll > 0` olduğunda aktifleşir (üstte transparan, kaydırınca opaklık + hairline kazanır); geçiş `--dur-state 180`.

### Hover — "ısınma" (tek lehçe, iki bağlam)

Metafor: yüzeye dokununca ısınır. Parlamaz, zıplamaz, büyümez.

- **Direktif:** Tüm etkileşimli yüzeylerde TEK hover lehçesi "ısınma"; iki bağlam:
  - **(a) YÜZEY-ISINMA** (kart/panel/tile) = +1 lüminans (E1→E2) + `translateY(-2px)`, `--dur-warm 140` ease-out.
  - **(b) SATIR-ISINMA** (tablo/liste satırı) = YALNIZ +1 lüminans (E1→E2), `transform: none` (satır asla zıplamaz/kaymaz).
- **Token/değer:** yüzey: bg E1→E2 + `translateY(-2px)`, `--dur-warm 140` ease-out; satır: yalnız bg→E2, transform yok; hover-glow: yalnız CTA (blur sabit, α artar).
- **Teknik:** CSS-only, GPU-safe. Kart/ikon/başlık/panel hover'da **asla** glow. `SignalCard` render-modunu prop/context ile bildirir: kart-modu (-2px) vs tablo-satırı modu (transform 0). reduced-motion'da transform kaldırılır, lüminans geçişi kalır.
- **DoD:** Tek CSS util/token ailesinden türer; kart hover -2px + E2; tablo satırı hover 0px + E2; hiçbir kart/ikon/başlık hover'da box-shadow/glow üretmez.
- **Ölçüm:** tablo satırı hover'da computed transform === identity; kart hover translateY === -2px; grep `hover:bg-white|hover:bg-accent-secondary|hover:bg-indigo` → 0; hover-glow lint kart/panel selector'ında box-shadow yasağı (CI); timing = `--dur-warm 140`.
- **Migration (v1.1→v1.3):** v1.1 "hairline→accent %28 · satır zemin accent %4 tonu" → renk-yükseltme yerine **lüminans-ısınma** (E1→E2); satır artık **sıfır transform** (v1.1 kart -2px korunur, satır -2px kaldırıldı).

### Hover = provenance açar (AI değerinde kaynak)

- **Direktif:** AI'nın dokunduğu HER değer, hover'da (veya klavye-focus'ta) tek uzaklıkta kaynağını açar: `skor 82 ← 9 motor · 3'ü SAT` biçimi.
- **Token/değer:** cyan 1px iz (AI dokunuşu) `--cyan #25E0D4`; provenance içerik yüzeyi E3 (`--e3 #17233A`) glass. Tetik: hover + `:focus-visible`; giriş `--dur-micro 140`, anında çıkış.
- **Teknik:** Her AI-türevi sayısal hücrede 1px cyan iz görünür; hover/focus E3 yüzeyli panel açar. İçerik backend telemetri alanından gelir (isimlendirilmiş motor + yön + katkı); sahte/placeholder provenance **yasak**; veri yoksa iz de yoktur (cyan yoksa AI konuşmadı).
- **DoD:** Cyan izi olan her hücre hover/focus'ta gerçek motor dökümü açar; iz sahte veriyle doldurulamaz; klavye ile de erişilir.
- **Ölçüm:** cyan-iz taşıyan hücre sayısı === provenance açan hücre sayısı; provenance içeriği telemetri alanına bağlı (snapshot testi); klavye-focus provenance görünürlüğü a11y testi.

### Focus ring (tek kanonik)

- `focus-ring: 2px solid var(--accent-ui) #4E6BE3, offset 2px` — her etkileşimlide (Karot dahil). ring-3/3px jenerik **atılır.** Tek tanım Bible §01 INT-12; VL bu satıra referans verir.
- **a11y gerekçesi:** `--accent #3B57D4` 1px/2px-UI olarak E2/E3'te kontrast eşiğini geçmez (2.90/2.62 < 3); focus-ring/border/nav-accent için **`--accent-ui #4E6BE3`** kullanılır (E0-E3 hepsi ≥3: 4.25/4.04/3.76/3.39; white-on 4.63). Bu bir kimlik değişikliği değil, a11y-zorunlu accent türevidir. `--accent` yalnız **CTA dolgu**; iz/border olarak **kullanma.**

---

## 09 · Motion yoğunluğu — sükûnet bütçesi (tek rejim · ayrık süre-token)

Kural: **viewport başına aynı anda en çok 1 ambient animasyon.** Hareket enflasyonu "AI-üretimi" hissinin bir numaralı kaynağıdır.

> **Süre kilidi (v1.3 KANONIK · aralıklar KALDIRILDI):** Motion tek rejim, ayrık token seti. Her `transition-duration` yalnız aşağıdaki değerlerden biri olabilir; token-dışı değer = **CI-red.**
> `--dur-micro 140` · `--dur-state 180` · `--dur-photon 150` · `--dur-warm 140` · `--dur-settle 520` · `--dur-route 180` · `--dur-overlay 360` · **stagger 50ms.**
> **App sert-tavan 600ms** (hiçbir app-motion `--dur-overlay 360`'ı aşmaz; settle 520 tavana yakın üst sınırdır).

| Bölge | İzinli | Yasak |
|---|---|---|
| **Landing** | reveal (bir kez, T3) · scroll-driven tek-atım mikro-koreografi *(v3.0/S6)* · hover ısınması *(v3.0: glow-drift/parallax KAPALI-beklemede; **count-up YASAK** — bayat "izinli" ibareleri kaldırıldı)* | çoklu ambient · sonsuz döngü dekor · marquee · count-up |
| **App** (dashboard/signals/markets…) | micro: hover `--dur-warm 140` · state geçişi `--dur-state 180` · **hairline-iskelet** *(v2.2: "sinyal-Karot skeleton" emekli — Bible §03-K pv-yükleme)* · foton-tick `--dur-photon 150` · **route geçişi `--dur-route 180` ışık-devri, layout-anim yok** | ambient · paralaks · scroll-reveal · **count-up** · sayfa-içi dekoratif döngü |
| **Overlay** (modal/drawer/toast) | spring (stiffness ~300, damping ~30, settle `--dur-overlay 360`) · backdrop fade `--dur-photon 150` | bounce abartısı · süre-tavan aşımı |
| **Auth** | statik atmosfer (L1+L2; *bokeh v3.0 EMEKLİ — §03*) + micro-etkileşim (hover/focus/state) | ambient · reveal · koreografi |

### Frekans / sükûnet bütçesi — motion nadir olaya saklı

- **Direktif:** Yüksek-frekans güncellemeleri (canlı fiyat, cmdK) animasyonsuz bırak — **foton flaşı** yeter; hareketi düşük-frekans/yıkıcı olaylara (yeni sinyal, invalidation) sakla; kesilebilir jestte momentum koru; yaş > eşik → statik.
- **Token/değer:** viewport başına ≤1 ambient (yalnız landing) · yüksek-frekans → foton `--dur-photon 150` flaş (konum/scale sabit) · düşük-frekans olay → ayrılmış mikro-hareket `--dur-settle 520` (≤600 tavan) · yaş > X → statik (X = veri-gated).
- **Teknik:** Frekans-tabanlı bütçe; sık güncellenen değerler (canlı fiyat, komut paleti) hareket taşımaz, yalnız foton flaşı (`--dur-photon 150` +1 lümen, konum sabit). Aynı satırda ≥2 canlı sayı foton'ları **senkronize edilmez** (yapay "canlılık dalgası" yasak). Bayatlayan/eski veride hareket durur (yaş damgası).
- **DoD:** Canlı fiyat hücresi hareketsiz (yalnız foton); aynı satırdaki foton'lar senkron değil; eski veri statik + yaş damgalı; landing'de aynı anda ≤1 ambient.
- **Ölçüm:** Canlı fiyat güncellemesinde layout-shift=0, yalnız opacity/color flaşı (`--dur-photon 150`) **veya v1.5 veri-fotonu: olay-bağlı geçici `background-color` tint'i (`--dur-flash 300`)**; landing ambient ≤1; foton tetikleyicileri per-hücre bağımsız (ortak zamanlayıcı yasağı).
- **v1.5 veri-foton dar-tanımı (K-J):** bg-tint YALNIZ gerçek telemetri olayına bağlı, geçici (tek-atım, sönümlü) ve **coalesced** (görünür değişim başına 1; satır-başı ≥~2s) olabilir; kalıcı/hover/dekoratif `background-color` transition'ları bu istisnaya GİRMEZ. Tint rengi yalnız mevcut bull/bear alfa-ailesinden (`/10–/15` bandı — 20-hücre setindeki rozet hücreleriyle aynı aile; yeni hex/alfa yok); "bull/bear asla glow/atmosfer" kuralı aynen geçerlidir (bu glow değil, alan-içi tint). Flash-anı metin-kontrast ölçümü uygulama-CP'sinin DoD'udur.

### Süre tablosu (kapalı küme · ayrık token)

| Token | Değer | Not |
|---|---|---|
| `--dur-micro` | 140ms | Hover/press mikro-etkileşim. Foton ayrı (color-flash). |
| `--dur-state` | 180ms | Aç/kapa/geçiş; sticky-header aktivasyonu. *(v2.2: "Karot fitil-dönüşü" ibaresi emekli — Karot kaldırıldı.)* |
| `--dur-photon` | 150ms | Sayı güncelleme +1 lümen flaşı; konum/scale sabit. Overlay backdrop fade de bu token. |
| `--dur-warm` | 140ms | Kart yüzey-ısınma + satır-ısınma (ease-out). |
| `--dur-settle` | 520ms | Reveal/settle (landing T3). *(v2.2: "Karot doğum settle" ibaresi emekli — Karot kaldırıldı. v1.5: "count-up" ibaresi kaldırıldı — count-up Motion Doctrine'de yasaktır.)* App-motion üst sınır bandı (≤600 sert-tavan). |
| `--dur-route` | 180ms | Route ışık-devri (giden −1/gelen +1 luminans); layout-anim yok, CLS=0. View Transitions API kullanılmaz. |
| `--dur-overlay` | 360ms | Modal/dropdown/toast/palette spring settle; app-motion 600 tavanı içinde. |
| `--dur-flash` | 300ms | **v1.5 (K-J):** veri-foton bg-tint (yukarıdaki dar-tanım). İlk kullanım M-P1 (SignalTable fiyat hücresi). |
| `stagger` | 50ms | Liste-giriş + hairline-iskelet liste-sırası *(v2.2: "Karot 9-motor fitil-dönüşü" emekli)*. App'te izinli TEK anlamlı stagger. |
| `press-scale` | .985 (lg) / .96 (sm) | Global press geri bildirimi; süre = `--dur-micro 140`. reduced-motion'da kaldırılır. |

- **Kanonik easing:** `--ease-signal: cubic-bezier(.2,.8,.2,1)` (tek tanım, §06 Bible). Route: giden `ease-in` (−1 lum), gelen `ease-out` (+1 lum). **`ease-in-out` YASAK.** Layout ASLA animasyonlanmaz.
- **Route ışık-devri (ölçüm):** giden computed lightness −1 E-basamağı, gelen +1 (before/after assert).
- **Lint (süre kilidi):** `transition-duration` ∈ {140,150,180,**300**,360,520} (+ stagger 50) token seti dışı = **red**; hiçbir değer 600ms sert-tavanı aşmaz. *(v1.5: enforcement üçlüsü senkron — `trademinds-gates.cjs` + `design-gates.mjs` + `motion-selftest.mjs`.)*
- **v1.5 T3 landing-reveal carve-out (K-J):** landing'in tek-seferlik açılış koreografisinde öğe-başı süreler kanonik set-İÇİ kalır (≤520 + stagger 50); **SEKANS TOPLAMI ≤1.2s** yalnız landing'de izinlidir (`once` + `sessionStorage` + reduced-motion'da tamamen atlanır; IntersectionObserver-tetikli, scroll-scrubbing değil). **App'in 600ms tek-animasyon sert-tavanı DEĞİŞMEZ** — carve-out landing'e mühürlüdür (glow-drift emsali).
- Tümü `prefers-reduced-motion`'da kapanır (ambient dâhil — Canvas statik kare çizer).
- **Migration (v1.1→v1.3):** süre **aralıkları** (120–160 / 150–200 / ~500-600 …) → **ayrık token** (140/150/180/360/520 + stagger 50); "skeleton shimmer / sayı-tick renk-flash" → **sinyal-Karot skeleton (boş-Karot) + foton-tick**; route "fade/opacity" → "ışık-devri (giden −1/gelen +1 lum)"; durum-etiketli shimmer kalıcı yasak (§11).

---

## 10 · Premium hissi & Finans + AI kimliği

Kopya değil, imza. Sahiplenilebilir unsurlar:
- **Karot enstrümanı** — 9 motorun tek yargıya uzlaşması; hero'daki taranan-varlık noktaları + cyan doğum nabzı.
- **Seviye çizgisi motifi** — SL/TP dilinin anlamlı çerçeveye dönüşümü.
- **Cyan = AI izi** — renk disiplini olarak kimlik (yalnız çizgi/nokta/iz).
- **Grafik kâğıdı** — maskeli grid; finansın "kâğıt" hafızası, yalnız boş sahnelerde.

**Premium'un kaynağı** = kısıtlama: tek ışık, tek glow sahibi, %6 altı noise, ≤1 ambient. Dürüstlük ilkesinin atmosfer hali: ışık asla olmayan bir şeyi parlatmaz.

### Rakip ayrışma konumu

- **Direktif:** Ayrışma konumunu **TradingView-netlik + Bloomberg-yoğunluk + Linear-craft + AI-konsensüs/yaşam-döngüsü** ekseni olarak sabitle; "47. güzel-fintech" olmayı ve rakibe yakınsamayı reddet.
- **Token/değer:** Konum = TradingView-netlik + Bloomberg-yoğunluk + Linear-craft + AI-konsensüs.
- **Teknik:** Rakipler veriyi gösterir; TradeMinds veriyi + AI'nın ona ne kadar inandığını (konsensüs) + her çağrının dürüst hayat/ölümünü (yaşam-döngüsü) gösterir.
- **DoD:** Screenshot line-up yabancı-kör testinde (§ DoD) ekran, kategori/ürün olarak ayırt edilebilir; kıyas setine TR rakipleri (TradingView/Matriks/Midas) dahil.
- **Ölçüm:** Çeyreklik yabancı-kör screenshot line-up: bağımsız gözlemci ekranı rakiplerden ayırt edebiliyor mu (evet/hayır oranı); ayırt edilemezse release bloklanır. *(Özgünlük tek ölçüm-kapısı; SOTD/ödül gibi nitel notlar ölçüm sayılmaz.)*

### Logo-kapalı tanınırlık (P2 · zorlayıcı fonksiyon)

- **Direktif:** Kimliği, logo kapalıyken yalnızca ekran görüntüsünden "bu TradeMinds" dedirtecek şekilde kur; taşıyıcılar: **Karot silueti + `--e0` near-black midnight + terminal-renk paleti + sahipli numeral.**
- **Token/değer:** Taşıyıcılar: Karot-siluet · `#070B14` near-black · bull `#2FBE9A` / bear `#E14640` / cyan `#25E0D4` · sahipli tabular numeral.
- **Teknik:** En güçlü zorlayıcı fonksiyon; ancak sahipli-tipografi (kahraman rakam) ve konsensüs-enstrüman fiili formu yerleşmeden otomatik kayıp. **Bugünkü statü: geçmez (dürüst kabul).**
- **DoD:** Çeyreklik denetimde logo maskelenmiş 3+ ekran dış gözlemciye gösterildiğinde "TradeMinds" olarak tanınabiliyor; tanınmıyorsa **açık borç** olarak kaydedilir (release-blokaj değil, kimlik-borcu).
- **Ölçüm:** Logo-maskeli tanıma testi: baseline = **%0 ("geçmez", kayıtlı borç)**; ilk kilometre-taşı (font+silüet üretimi) sonrası hedef ≥%40, çeyreklik artan.

### İç-dil (UI'a çıkmaz)

- **Direktif:** Karot / közleşme / omurga / su-hattı / kesim-dudağı gibi şiirsel adları yalnızca ekip iç-dilinde kullan; bu adlar UI metnine, etikete, tooltip'e **asla** çıkmaz.
- **DoD/Ölçüm:** UI string taramasında (`Karot`,`közleşme`,`omurga`,`su hattı`,`kesim dudağı`) eşleşme = 0; belge/kod-yorumu dışında görünmez.

---

## 11 · Performans reçetesi (araç kararı — KANONİK · WebGL-siz/koşullu-3D)

> Araç-karar tablosu ve sert sınırlar için **tek kanonik kaynak bu bölümdür.** Bible §06 buna atıf yapar.

| Araç | Kullanım | Sınır | Karar |
|---|---|---|---|
| **CSS** gradient/mask/transition + `animation-timeline: scroll()/view()` | L0-L3, hover, geçişler, bokeh, landing scroll-driven reveal | transform/opacity dışı animasyon yok; `@supports` guard + IO fallback | **Varsayılan** |
| **SVG** feTurbulence | noise tile (data-URI) | tek 128px tile, statik, <2KB | **Evet** |
| **Canvas 2D** | sinyal tozu + Karot (yalnız landing hero canlı) | ≤40 nokta · 30fps cap · DPR≤2 · tab-gizli/viewport-dışı durur | **Tek ambient** |
| **Motion** (reveal-only) | reveal · overlay spring · route ışık-devri | dinamik import; layout-animation app'te yok; **≤~35KB gz initial** | **App-motion tek kütüphane** |
| **GSAP / R3F / Three / postprocessing** | — | initial-bundle DIŞI (yalnız gerekliyse lazy/code-split); **kimlik-merkezi kalıcı yasak** | **Initial-bundle-dışı / kimlik-yasak** |
| **Video bg / Spline** | — | ağırlık + CSP + kontrol kaybı | **Kalıcı yasak** (generic); native = gated-future ↓ |

> **⚠ VL-MOTION-v3 REVİZE (v2.1):** Yukarıdaki "GSAP/R3F/Three" ve "Video bg / Spline" satırlarının yasağı **generic/kimlik-merkezi** kullanım için AYNEN geçerli; **TradeMinds-native × bilgi-taşıyan** (ürün proof-surface / instrument-well) kullanım *mutlak-yasak değil* → **gated-conditional future CP** (8-kabul-kapısı + ayrı onay). Tek kanonik ayrım: "VL-MOTION-v3" bölümü.

### Gerçek-Olay Havuzu — WebGL-siz, koşullu-3D DEFERRED

- **Direktif:** Yaşayan-Hero şu an **WebGL-siz** kurulur (Karot + atmosfer 2D SVG/Canvas 2D). Koşullu-3D (Karot-DIŞI atmosfer/derinlik katmanı) **DEFERRED**; açılırsa bilgi-taşımalı ve tam bütçe (DPR-cap ≤2 · poster/statik fallback · reduced-motion statik · mobil 2D fallback · lazy/code-split) karşılamalı. Her ışık gerçek bir olayı temsil eder; sahte-sinema yasak (§07/Kalıcı Yasaklar).
- **DoD/Ölçüm:** initial-chunk three/R3F/postprocessing = 0; koşullu-3D açık değilken hero WebGL bağlamı oluşturmaz (canvas.getContext('webgl*') = 0); her hero ışık/hareket telemetri-alanına iz sürülebilir.

### App animasyon aracı — tek kütüphane, reveal-only, ≤35KB gz

- **Direktif:** App-motion için tek kütüphane kullan (Motion, reveal-only); GSAP/R3F initial-bundle **DIŞINDA** tut; scroll-driven CSS `animation-timeline` landing'de birincil (IO fallback).
- **Token/değer:** app-motion = Motion (reveal-only) · kütüphane toplamı **≤~35KB gz** (initial) · GSAP/R3F → lazy/code-split · landing scroll = CSS `animation-timeline: scroll()/view()` + `@supports` + IntersectionObserver fallback.
- **DoD:** Initial bundle'da motion kütüphane toplamı ≤~35KB gz; GSAP/R3F initial-bundle'da yok; app-motion tek kütüphaneden; landing scroll CSS-timeline + IO fallback ile.
- **Ölçüm:** Bundle analiz: initial-chunk motion-kütüphane gz toplamı ≤35KB (CI bundle-size gate); GSAP/three/R3F initial-chunk'ta 0; `@supports (animation-timeline: scroll())` guard + IO fallback varlığı denetlenir.
- **Açık-uç / kilit-öncesi:** **Ölçülebilir kısım (≤35KB gz + GSAP/R3F initial=0) kilit** (araç-adından bağımsız geçerli). Yalnız kütüphane ADI = Motion açık-uçtur (nihai stack ürün-tarafı kararla kesinleşir).

### Scroll teknolojisi — telemetri-bağlı progress, video-scrubber değil

- **Direktif:** Yaşayan-Hero scroll-progress'ini **gerçek telemetriye** bağla — scroll-scrub bir video-scrubber DEĞİLDİR; araç: CSS scroll-driven (`animation-timeline`) + IntersectionObserver fallback; ağır kütüphane (GSAP) yalnız gerekliyse, R3F initial-bundle-dışı lazy.
- **Token/değer:** scroll-progress = gerçek telemetri · birincil: CSS `animation-timeline: scroll()/view()` + `@supports` · fallback: IO (bir kez) · GSAP yalnız gerekliyse · R3F → lazy.
- **DoD/Ölçüm:** hero scroll-driven değerler telemetri-state'e bağlı (statik video-frame scrub = 0); `@supports` + IO fallback mevcut; bundle: R3F/three initial-chunk = 0.

### Performans bütçeleri — 60fps, per-frame allocation yok, viewport-gate, 40-settle bütçesi

- **Direktif:** 60fps (16.67ms/frame; ~10ms JS+render) bütçesini tut; per-frame yalnız uniform/opacity güncelle, **allocation yapma**; Page Visibility + IntersectionObserver ile viewport/tab-dışı render'ı durdur; `will-change` yalnız aktif elemanda (bitince kaldır).
- **40-settle bütçesi (transform/opacity-only):** Aynı anda settle/doğum animasyonu ≤~8 eş-zamanlı öğe; yalnız transform/opacity özellikleri animasyonlanır (layout/paint tetikleyen özellik yasak); dropped-frame = 0. (40-Karot havuzunda tüm settle'lar aynı anda değil, stagger 50ms ile dalgalanır; herhangi bir anda aktif ≤~8.)
- **Token/değer:** 60fps = 16.67ms/frame (~10ms JS+render) · per-frame: yalnız uniform/opacity, 0 allocation · Page Visibility + IO → viewport/tab-dışı durur · `will-change` yalnız aktif eleman · kütüphane ≤~35KB gz · eş-zamanlı settle ≤~8, transform/opacity-only.
- **DoD:** Aktif animasyonda ortalama frame ≤16.67ms; per-frame allocation 0; tab-gizli/viewport-dışı animasyon durur; kalıcı `will-change` = 0; eş-zamanlı settle ≤~8; settle'da layout/paint-tetikleyen özellik animasyonu = 0.
- **Ölçüm:** DevTools Performance: frame ≤16.67ms (dropped-frame = 0), Memory'de per-frame GC-sawtooth yok; `document.hidden`'da rAF-tick 0; off-screen animasyon durur; grep kalıcı `will-change` = review-flag; settle sırasında animasyonlanan özellikler ⊆ {transform, opacity}.

### Erişilebilirlik notu

`--tx3` (`#5C6980`) koyu zeminde okunur küçük metinde AA'yı **geçmez** (E0-E3 hepsi <4.5); yalnız dekoratif/disabled + Karot kararsız omurga (UI-obje/iz rolü, E0-E2'de ≥3; **E3'te UI olarak da kullanma**, <3) + közleşme kül tonu içindir. Okunur mikro-etiket minimum `--tx2` (`#9AA6B8`). Focus/border/nav-accent = `--accent-ui #4E6BE3` (E0-E3 hepsi ≥3); `--accent #3B57D4` yalnız CTA-dolgu (iz/border FAIL).

---

## Kalıcı Yasaklar (ebedi red · negatif-kural)

Aşağıdaki teknikler kimlik/ambient/dekor amacıyla **asla** kullanılmaz; ihlal = **release-blokaj** (CI-lint + review-gate).

> **⚠ VL-MOTION-v3 REVİZE (v2.1):** Aşağıdaki liste **generic/kimlik-merkezi/dekoratif/sahte** kullanım için tam olarak geçerlidir (release-blokaj). **Tek istisna:** *TradeMinds-native × bilgi-taşıyan* 3D/WebGL/video/Spline = **gated-conditional future CP** (8-kabul-kapısı + ayrı onay; "VL-MOTION-v3" bölümü). Native istisna generic yasakları GENİŞLETMEZ — robot/globe/orb/avatar · neon/cyberpunk/Matrix/RGB · template · sahte-sinema · scroll-jack/wheel-intercept/Lenis · yeni-glyph icadı AYNEN yasak.

- **Kimlik-merkezi Three.js / R3F / @react-three/postprocessing (Bloom)** · **video-background** · **Spline** · **gradient-mesh-satüre** · **scroll-scrubbed WebGL sinematik hero.**
- **Sahte/dekoratif sinematik hero (sahte-sinema TAMAMEN YASAK):** önceden-pişmiş 5-beat film · dekoratif kamera dolly/orbit/pull-back · dekoratif **cyan-tarama beat'i** · veri temsil etmeyen her hero efekti · canlı-değil veriyi canlı gibi sunma (dürüst "arşiv" etiketi zorunlu). *(Yaşayan Hero / Gerçek-Olay Havuzu korunur — atılan yalnız sahte katmandır; ~190KB kimlik-chunk emekli.)*
- **scroll-jacking · wheel-intercept · zorunlu-snap (>1 pin) · Lenis** (§08).
- **sonsuz-pulse · dönen-radar · idle-tarama · sahte-progress · konfeti.**
- **cyan-yüzey/dolgu/buton/başlık** (cyan yalnız çizgi/nokta/iz/omurga) · **bull/bear-atmosfer/glow rengi** · **mor-pembe-gradient-text** · **neon/Matrix/cyberpunk/RGB-kitsch.**
- **`--accent #3B57D4` iz/border/nav-accent olarak** (E2/E3'te <3 FAIL; UI-accent = `--accent-ui #4E6BE3`) · **`--accent-hover #3450C6` iz/border olarak** (yalnız CTA-dolgu hover) · **`--tx3` okunur metinde** veya **E3-üstü UI olarak.**
- **kırpılmış-eksen** (Lie-Factor doktrini; baseline daima kırpılmamış, Lie Factor=1).
- **ham renkli glow-rgba / ham box-shadow glow** (`rgba(0,230,118,·)` · `rgba(255,82,82,·)`) · **2-katman drop-shadow** (kart) · **durum-etiketli shimmer** · **ring-3/3px focus** · **animasyonlu grain** · **canlı `filter:blur`.**
- **App sayfalarında** ambient/paralaks/scroll-reveal/autoplay/count-up.
- **`ease-in-out`** (giren ease-out / çıkan ease-in) · **layout-animation** (CLS=0) · **süre-token seti dışı `transition-duration`** (140/150/180/360/520 + stagger 50 dışı = red; 600ms sert-tavan aşımı).

**Ölçüm:** CI-lint + bağımlılık taraması: three/@react-three/spline import (kimlik amaçlı) = 0; ham renkli glow-rgba = 0; kırpılmış-eksen chart config = 0; Lenis/smooth-scroll-hijack importu = 0; `--accent` iz/border eşleşmesi = 0; süre-token-dışı transition = 0.

---

## VL-MOTION-v3 · Native-Motion Taksonomisi (generic-yasak / TradeMinds-native-koşullu) · *(v2.1 · CP-1 · 2026-07-18)*

> **Kanoniklik:** Bu bölüm, motion/3D/video için **"mutlak-yasak vs koşullu-serbest"** ayrımının **tek kanonik kaynağıdır**; §11 tablosu · Kalıcı Yasaklar · Bible §00 G-00-15 · Bible §02 hero-3d-koşullu buraya atıf yapar. **Doc-only** — hiçbir davranış değişmez; uygulama ayrı CP'ler (aşağıda sıra kilidi). **Karot geri gelmez; yeni glyph/ikon/sembol icat edilmez.**

> **⚠ S0 v3.0 KAPANIŞ (kullanıcı kararı · 2026-07-18):** Bu bölümün **gated-conditional şeridi** (CP-HERO-NATIVE-3D · CP-HERO-PROOF-VIDEO · native-Spline) **KAPATILDI** — redesign-v3 planında tutulmaz; 8-kapı çerçevesi ve aşağıdaki gated tablo **tarihsel kayıttır**. Landing derinliği = yalnız **CSS/Canvas-2D** (CP-HERO-PROOF-SURFACE satırı "şimdi açık" olarak GEÇERLİ kalır — tablodaki tek yaşayan satır budur). 3D gelecekte ancak **SIFIRDAN, ayrı karar + ayrı sprint** ile açılabilir. Karot/soyut-obje/kristal/orb zaten şerit-dışıydı; **v3-karot-kapanış** (Bible §00-V3) ile her formu kalıcı-yasak. CP-sırası maddeleri 3-4 (Reference-Research + NATIVE-3D/VIDEO) bu kapanışla birlikte **iptal**; madde 2 (PROOF-SURFACE) v3-sprint-sırası S5'e devredildi.

### Neden bu revizyon
Önceki doktrin bazı teknikleri (video-bg · Spline · native-3D) **düz/koşulsuz** yasakladı. Bağlayıcı yeni yön (kullanıcı, 2026-07-18): yasak asıl olarak **generic/stok/template/sahte/perf-riskli** kullanımadır; **ürünün kendi gerçek veri/proof/instrument-well dilinden türeyen** motion/3D/video ise mutlak-yasak değil **koşullu-serbest** olmalıdır. Bu bölüm o ayrımı test-edilebilir kapılarla kurar; generic yasaklar aynen kalır.

### İki-eksen taksonomi
Her motion/derinlik/efekt önerisi **iki ekseni birlikte** geçmeli:
- **Köken ekseni:** *TradeMinds-native* (ürünün gerçek verisi / proof-surface / instrument-well / receipt / owned-number / live-terminal dilinden doğar) ↔ *generic* (stok asset, template galeri estetiği, ürün-dışı gösteri).
- **Kanıt ekseni:** *bilgi-taşıyan* (gerçek telemetri/proof görünürlüğüne hizmet eder) ↔ *dekoratif* (yalnız "wow").

**Yalnız `native × bilgi-taşıyan` bölgesi koşullu-serbesttir.** Diğer üç bölge (`native × dekoratif` · `generic × bilgi-taşıyan` · `generic × dekoratif`) **yasak.** Native olmak dekoratif efekti; bilgi-taşımak generic estetiği meşrulaştırmaz — iki kapı da açık olmalı.

### Mutlak-yasak KALAN (generic — release-blokaj, değişmedi)
generic 3D globe · robot / AI-avatar · random Spline orb · cyberpunk / neon / Matrix / RGB-kitsch · gradient-mesh-satüre · mor-pembe-gradient-text · template galeri estetiği (aurora-bg / neon-kart / dev-gradient-tipo) · **sahte-sinema** (önceden-pişmiş beat · dekoratif kamera dolly/orbit/pull-back · dekoratif cyan-tarama · veri temsil etmeyen efekt · canlı-değil veriyi canlı gibi sunma) · scroll-jacking · wheel-intercept · zorunlu-snap (>1 pin) · Lenis · sonsuz-pulse · dönen-radar · idle-tarama · sahte-progress · konfeti · casino / coin-hype · **Karot ikamesi / yeni glyph icadı** · kimlik-merkezi Three / R3F / Bloom initial-bundle chunk'ı · kırpılmış-eksen.

### Koşullu-serbest OLAN (yalnız `native × bilgi-taşıyan` × 8-kapı geçerse · GATED FUTURE CP)
| Teknik | Eski statü | Yeni statü |
|---|---|---|
| Native-3D / WebGL (Karot-DIŞI, proof / instrument-well derinliği) | DEFERRED | **Gated-conditional future CP** (CP-HERO-NATIVE-3D) |
| Video (ürün proof-surface capture / motion-capture) | düz Kalıcı yasak | **Gated-conditional future CP** — stok/generic video-bg yasak KALIR |
| Spline (native proof-surface / instrument-well) | düz Kalıcı yasak | **Gated-conditional future CP** — generic orb/globe/avatar yasak KALIR |
| Canvas-2D / CSS derinlik (transform/opacity/mask/gradient) | izinli (§11) | **Dep-siz · şimdi açık** (CP-HERO-PROOF-SURFACE) |

> "Serbest" DEĞİL: yukarıdaki üç gated satır ancak ilgili CP'de **8-kabul-kapısı** denetimi + **ayrı kapsam-onayı** ile açılabilir. Onay öncesi implementasyon = yasak.

### 8 kabul kapısı (koşullu-serbest için · HEPSİ geçilmeli; biri fail → red)
1. **Gerçek-veri / proof:** her hareketli/derin/ışıklı öge bir gerçek veri/telemetri alanına iz-sürülebilir (mock / scripted-timeline = fail).
2. **Native, stok-değil:** köken ürün proof-surface / instrument-well; stok / generic / template asset = fail.
3. **LCP korunur:** H1 LCP-statik kalır; 3D-canvas / video LCP elemanı OLAMAZ; boyut-rezervli lazy yükleme.
4. **CLS 0:** alan rezervi (min-h) ile; layout-animation yok.
5. **Mobil fallback:** WebGL / video → mobil 2D veya statik fallback zorunlu (mevcut DOM proof-surface = fallback).
6. **Reduced-motion statik:** `prefers-reduced-motion: reduce` → poster / statik; bilgi kaybı 0.
7. **App'e taşmaz:** 3D / video / parallax **YALNIZ landing / marketing**; Dashboard / Signal Center / SignalTable ağır-motion yasağı (Bible dash-ambient-yasak · §11) korunur; app-motion yalnız mikro-geçiş / luminance / receipt-hover / route-light.
8. **Fallback/poster + perf-bütçe + legal:** poster planı · initial motion-lib ≤35KB gz · GSAP / R3F / three initial-chunk = 0 (lazy / code-split) · DPR-cap ≤2 · 60fps (frame ≤16.67ms, per-frame 0-allocation, viewport/tab-dışı durur) · **no-fake-data + "TradeMinds yatırım danışmanı değildir" dürüstlük çizgisi** korunur.

### App-yüzeyi sınırı (yeniden-doğrulanır, değişmedi)
Dashboard · Signal Center · SignalTable · tüm app veri-yüzeyleri: ağır-3D / WebGL · scroll-jack · autoplay · ambient-parallax **YASAK** (Bible dash-ambient-yasak · §11). App-içi tek yaşayan-hero formu = Dashboard **Nabız bandı** (≤~120px, olay-bağlı, statik-ışık, scroll'suz). 3D / video / parallax değerlendirmesi **yalnız landing** kapsamındadır.

### CP sırası (KİLİT)
1. **VL-MOTION-v3** (bu · doc-only).
2. **CP-HERO-PROOF-SURFACE** — dependency'siz derinlik / reveal polish (CSS / transform / opacity / Canvas-2D / instrument-well; gerçek veriyle bağlı; yeni dep / asset / 3D / video YOK).
3. **Reference Research Sprint** — Dribbble · motionsites.ai · ödüllü siteler (yalnız **prensip-çıkarımı + negatif-katalog**; birebir asset repo'ya girmez — §01-K referans-politikası · Bible G-00-04 yabancı-kör).
4. **CP-HERO-NATIVE-3D _veya_ CP-HERO-PROOF-VIDEO** — gated future; önce referans-research + asset / perf / fallback planı; 8-kabul-kapısı denetimi; ayrı kapsam-onayı.

---

## Definition of Done (v1.3)

Kimliği aşındırmaya karşı **zorlayıcı DoD kapıları** — istisnasız uygulanır; herhangi biri fail → **release-blokaj** (kimlik-borcu kapıları hariç, aşağıda işaretli).

1. **Glow/Lumen lint (CI-red).** Ham `box-shadow` / renkli glow-rgba CI'da RED; parlaklık yalnız token ailesinden. Glow opaklık ≤`.14`, blur `12-24px`, blur-animasyonu 0. Karot underlay opacity `.14` (istisnasız tavan), statik 2px enstrüman-blur (whitelist-muaf).
2. **Kompozisyon zorunluluğu** *(v2.2 re-anchor — eski "Karot zorunluluğu"; Karot ürün-UI'dan kaldırıldı, Bible v1.7)*. Her sinyal yüzeyi kompozisyon-taşıyıcılardan en az birini taşır: **owned-numeral kahraman (`num`) · makbuz-satırı (craft-makbuz-grameri) · instrument-well** (Bible §03-K). Dekoratif glyph/sembol = 0; grep `<Karot` = 0 (kalıcı); three/R3F initial = 0.
3. **Screenshot line-up (çeyreklik yabancı-kör).** Bağımsız gözlemci ekranı TR/global rakiplerden ayırt edebiliyor (evet/hayır oranı loglanır); ayırt edilemezse release bloklanır.
4. **Squint testi** *(v2.2 re-anchor)*. Viewport'ta blur(~8px)+eşikleme sonrası en parlak 2 öge: **app = {kahraman-rakam (owned-numeral), birincil-CTA}** (Bible §03-K) · **landing = {H1, birincil-CTA}** (v2.0 CP-HERO-DOC). Dekoratif luminans ≤ veri luminansı. (Ambient glow-drift daima loş/yönlü, vurgu ≤2 bütçesine girmez.)
5. **WebAIM kontrast kilidi (AÇIK).** Tüm semantik hex (`--bull/--bear/--accent/--accent-ui/--accent-hover/--cyan/--amber`) × E0-E3 = **20-hücre ölçüm tablosu DOLU** (DoD-5 geçti); metin ≥4.5:1 / UI-iz ≥3:1; rol-kısıtları (`--bear` metin yalnız E0/E1 · `--accent` yalnız CTA-dolgu · `--accent-ui` UI-iz · `--tx3` non-metin & non-E3-UI) uygulanır. Yeni hücre eklenirse yeniden kilit gerekir.
6. **Scroll bütünlüğü.** Lenis/scroll-jacking/wheel-hijack = 0; reduced-motion'da bilgi kaybı 0; scroll geri alındığında doğmuş Karot geri-sarılmaz (idempotent).
7. **Motion bütçesi (süre kilidi AÇIK).** initial motion-lib ≤35KB gz; GSAP/R3F/three initial = 0; app-route'ta ambient/paralaks/count-up = 0; 60fps (frame ≤16.67ms, dropped-frame 0), per-frame allocation 0; `transition-duration` ∈ {140,150,180,360,520}+stagger 50, 600ms tavan aşımı = 0; eş-zamanlı settle ≤~8 (transform/opacity-only).
8. **Her piksel bir sebeple (P5/P6).** Border/radius/hairline/spacing/shadow/glow/opacity/timing gerekçesini tek cümlede yazamadığın her değer review'da düşer; "moda/trend" gerekçesi otomatik red.
9. **Logo-kapalı tanınırlık (kimlik-borcu kapısı, release-blokaj DEĞİL).** Bugün baseline %0 ("geçmez", kayıtlı borç); font+silüet üretimi sonrası ≥%40 hedef, çeyreklik artan.
10. **Dark-only (kayıtlı bilinçli erteleme).** Ürün dark-only (E0-E3 near-black); light-tema token seti üretilmez, fakat **"bilinçli ertelendi"** olarak kayıtlı (açılırsa sürüm revizyonu gerekir). Kodda light-theme yolu/token = yok.

> **Governance / süreç-kayıt ayrımı:** Jüri kararı, araç kullanımı (Higgsfield vb.) bu standarda **madde olarak işlenmez.** Higgsfield yalnız ref (konsept/storyboard/motion/3D/materyal) için; üründe **birebir asset-kopyası olarak asla** kullanılmaz. Strateji belgeleri (director-cut/ruthless-correction vb.) **normatif referanslanmaz**; aktif = docs/design v1.1/v1.3.

---

## Migration Map (v1.1 → v1.3)

**Tek-kaynak renk (alias → kanonik ad → kanonik hex · WCAG-kilitli):**

| Alias / emekli literal | Kanonik | Not |
|---|---|---|
| `--bg`, `--surface-0`, `#020817`, `#0A101C` | `--e0 #070B14` | Zemin (near-black midnight-blue tint; `#000000` DEĞİL). 6 konum (tailwind.config, globals.css, layout themeColor, manifest theme+bg, ShareCardModal, TradingViewChart embed). |
| `--surface-1` | `--e1 #0C1220` | Kart/panel. |
| `--surface-2` | `--e2 #111A2B` | İç/yükselmiş + hover ısınma hedefi. |
| `--surface-3` | `--e3 #17233A` | Overlay/cam (gölge+blur yalnız burada). |
| `--text` | `--tx #E8EDF5` | Ana metin + `::selection-fg` (E0-E3 hepsi ≥6.3:1). |
| `--muted` | `--tx2 #9AA6B8` | İkincil metin / okunur mikro-etiket floor (E0-E3 hepsi ≥6.3:1). |
| `--faint` | `--tx3 #5C6980` | **KISIT:** okunur metin DEĞİL (tümü <4.5); UI-obje/dekor yalnız E0-E2 (E3'te UI olarak da yasak, <3). Dekoratif/disabled + Karot kararsız omurga (≥3) + közleşme kül. |
| `#10B981` (emerald) | `--bull #2FBE9A` | Teal-emerald; her yüzey ≥6.69:1 (metin dahil; WebAIM geçti, kilitli). Karot tinti + chart mum/TP. |
| `#F4556E`, `#F0564B` | `--bear #E14640` | Warm-red (hue 20-27°, chroma≤0.16). **KISIT:** metin YALNIZ E0/E1 (4.83/4.59); UI/glyph/1px E0-E3 (E3 3.85≥3). Input-hata dahil. WebAIM/COL-11 sonrası kilit. |
| `#3B82F6`, `#2563EB`, indigo | `--accent #3B57D4` | TEK accent-kimlik (owned-blue). **KISIT: YALNIZ DOLGU (CTA bg);** üzerine metin `--tx` (5.10) veya `#FFFFFF` (6.00). 1px-UI olarak E2/E3'te FAIL (2.90/2.62) → **iz/border/nav-accent için KULLANMA.** `--ac-tx` = `--tx #E8EDF5` (yeni hex YOK). |
| *(a11y-türev)* | `--accent-ui #4E6BE3` | **[YENI · a11y-zorunlu accent türevi, kimlik değişikliği DEĞİL]** 1px-UI (focus ring / border / nav-accent). E0-E3 hepsi ≥3 (4.25/4.04/3.76/3.39) + white-on 4.63. Focus-ring bu token. |
| *(a11y-türev)* | `--accent-hover #3450C6` | **[YENI]** YALNIZ CTA-dolgu hover (white-on 6.75); asla iz/border değil. |
| `#22D3EE`, `--accent-2`, `--cy` | `--cyan #25E0D4` | Owned electric-teal. Yalnız çizgi/nokta/iz/omurga (iz her yüzey 9.49-11.89). WebAIM sonrası kilit. |
| `#FBBF24`, `--warn` | `--amber #F5A524` | TEK sarı (kazanç + chart sinyal-işareti + başarı-toast). Her yüzey 7.69-9.64. Idle/ambient amber yasak. |
| `--hl-rest/--hl/--hl-interact/--hl-focus`, `rgba(255,255,255,·)` | `--hl10/--hl12/--hl16/--hl22` `rgba(148,163,184,·)` | Slate-taban tek aile (4 alfa .10/.12/.16/.22). White-alpha beyanı slate-tabana hizalandı. |

**Migration (renk kilidi · WebAIM sonrası uygulanır):** focus-ring/nav/input-focus → `--accent-ui`; `#3B82F6`/`#2563EB`/indigo → owned (`--accent` dolgu / `--accent-ui` UI); `#F4556E`/`#F0564B` → `--bear #E14640`; `#22D3EE` → `--cyan #25E0D4`; `#10B981` → `--bull #2FBE9A`; `#FBBF24` → `--amber #F5A524`.

**Diğer değer/davranış migration'ları:**

| Konu | v1.1 | v1.3 | Bölüm |
|---|---|---|---|
| Anahtar ışık rgb | `59 130 246` | `59 87 212` (owned-blue) | §02 |
| Dolgu ışık rgb | `34 211 238` | `37 224 212` (owned cyan) | §02 |
| Noise blend / tavan | overlay / %3 | soft-light / α≤.06 / data-URI <2KB | §04 |
| Section ayracı | accent→cyan gradient hairline | düz `--hl12` hairline + lüminans basamağı | §06 |
| Kart rim | üst kenar cyan'a döner | `--cut-lip` (renksiz inset); cyan yalnız iz/omurga | §05/§07 |
| Focus ring | `--accent` 2px | `--accent-ui #4E6BE3` 2px (a11y: accent E2/E3 <3) | §08 |
| Hero timeline son beat | sabit ~850ms nabız / stagger 80ms | telemetri-anı doğum nabzı / Karot settle stagger **50ms**, `--dur-settle 520` | §07 |
| Hover | hairline→accent %28 · satır -2px · zemin accent %4 | lüminans-ısınma E1→E2 (`--dur-warm 140`); kart -2px, **satır transform 0** | §08 |
| Route geçişi | fade/opacity | ışık-devri (giden −1/gelen +1 lum), `--dur-route 180`; `ease-in-out` yasak | §09 |
| Skeleton / tick | shimmer / renk-flash | boş-Karot skeleton (stagger 50ms) / foton-tick (`--dur-photon 150` +1 lümen) | §09 |
| CTA glow | (VL§14 α .20-.35 / blur 16-32px) | α ≤`.14` / blur `12-24px` (daha kısıtlayıcı kazandı) | §03 |
| Süre rejimi | aralıklar (120-160 / 150-200 / ~500-600 …) | **ayrık token** (micro 140 · state 180 · photon 150 · warm 140 · settle 520 · route 180 · overlay 360 · stagger 50); 600ms sert-tavan | §09 |
| Motion aracı | Framer | Motion (reveal-only, ≤35KB gz); GSAP/R3F lazy/kimlik-yasak | §11 |
| Scroll | landing reveal | + telemetri-bağlı yaşayan muhakeme (Gerçek-Olay Havuzu); scrubber DEĞİL; Lenis kalıcı yasak | §08/§11 |
| 3D/WebGL | "gereksiz" | kimlik-merkezi **kalıcı yasak**; koşullu-3D DEFERRED; Karot her ölçek 2D SVG; 40-settle transform/opacity-only bütçesi | §02/§11 |
| cmdK | (açık) | güvenli-varsayılan = **rozet kaldırma** (⌘K affordance gösterilmez) karar verilene dek | §09/DoD |

**Migration disiplini (C1/C2):** Her değer değişikliği **commit + sürüm-artışı + CHANGELOG** üçlüsüyle girer. Çelişkide daha kısıtlayıcı kural kazanır ve iki belgede (Bible token/komponent · VL atmosfer/motion) tek revizyonla kapatılır.

---

**Tek cümle:** *Gece Seansı* — karanlık sahne, tek mavi ufuk ışığı, verinin kendisi (Karot) parlar; AI dokunduğunda cyan iz bırakır; her ışık gerçek bir olaydır ve her şey sakindir çünkü **sakinlik güvendir.**