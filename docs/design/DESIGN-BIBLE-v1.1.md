# TradeMinds Design Bible

**Version:** v1.7 (KANONIK) · **Tarih:** 2026-07-18 · *(v1.7 CP-KAROT-DOC: **Karot ürün-UI DEPRECATION** — Karot artık üründe zorunlu kimlik / merkez-enstrüman / marka-işareti DEĞİL; §05 [karot-01…15 + sahne-ölçekleri] ürün-UI için SUPERSEDED (tarihsel kayıt olarak korundu). Yeni kimlik = kompozisyon / typography / owned-numeral / instrument-well / proof-receipt / dark-terminal (glyph ikamesi YOK; §05 baş-banner + §1124). UI kaldırma CP-KAROT-UI1/2/3, ölü-kod CP-KAROT-CLEAN. bkz CHANGELOG.)* · *(v1.6 CP-PV1-A: Kompozisyon & Sahneleme katmanı — kap-hiyerarşisi [chrome/panel/well] · veri-kuyusu · kahraman-rakam · makbuz-grameri · sessiz-buton · Karot sahne-ölçekleri · referans-politikası; bkz. §01 sonu + §05 karot-sahne-ölçekleri + CHANGELOG. v1.5 CP-PIA: bilgi-mimarisi kilidi [Durum Odası · İstihbarat Merkezi · widget-taşıma · sorumluluk-tablosu · IA-guardrail], bkz. §02/§03/§04. v1.4: Karot geometri revizyonu + Geometry Freeze, bkz. §05 karot-02/15)*
**Statü:** Ürünün resmî ve tek tasarım standardı (normatif). Kanonik kaynak = bu dosya (`docs/design/`).
**Kanoniklik & sürümleme:** Dosya adı sabittir; güncel sürüm bu başlıkta + [CHANGELOG](./CHANGELOG.md)'da izlenir. Artifact yalnızca görsel aynadır; çelişkide bu markdown kazanır. Revizyon = commit + sürüm artışı + CHANGELOG satırı (C1/C2, §08).
**Eki:** [VISUAL-LANGUAGE](./VISUAL-LANGUAGE-v1.1.md) (Annex A — atmosfer/Art Direction/motion-bütçesi).

> **Amaç:** ürünü Stripe · Linear · Vercel · TradingView · Bloomberg-dürüstlük seviyesinde premium, kurumsal ve güven veren bir SaaS'a taşımak. **Konumlandırma (tek kanonik cümle):** *"TradeMinds = ölçekte-okunan-dürüst-konsensus; fark efektte değil dürüstlük duruşunda."* Kimlik atomik değil bileşiktir (10 katman); merkez DNA = ölçekte okunan görünür 9-motor konsensusu (bir okuma biçimi), ışık yalnızca destekleyici.

> **v1.3 (KANONIK) kapsamı:** §00 governance doktrini (10-katman bileşik kimlik, 6-önerme turnusolü, kalıcı tabu listesi), §01 tek-kaynak owned palet (renk kilidi AÇIK) + hairline/glow/tipografi/state/global-base primitifleri, §02 yaşayan Hero, §03 3-kuşak dashboard IA + yoğunluk sözleşmesi, §05 Karot konsensüs enstrümanı (tam spec), §06 motion doktrini (tek-rejim süre token seti + kaynak-isimli hareket), §08 DoD 5 zorlayıcı fonksiyon. Değişen değerler her maddede **Migration (v1.1→v1.3)** satırıyla işaretlidir. **Bu sürümde kilitlenen:** 20-hücre WebAIM tablosu doldu → semantik renk kilidi AÇIK (DoD-5 geçti); süre araçları tek-rejim ayrık token setine indirildi.

---

## 00 · Tasarım İlkeleri

Her karar bu ilkelere dayanır. Çelişki olursa sıra: **kullanıcı → ilke → estetik**. Belge-düzeyi kanoniklik için bkz. §08 Governance. §00 maddeleri **governance-seviyesi review-gate**'lerdir: PR'da işaretlenmemiş/savunulamayan karar reddedilir.

### G-00-01 · Kimlik = 10 katmanın birleşimi (bileşik kimlik doktrini)
- **Direktif:** Hiçbir tek katmanı (AI-Thought · Karot · Hero-Exp · Dashboard-Exp · Motion · Interaction · Typography · Color · Premium-Craft · Micro-Details) tek başına "kimlik" ilan etme; her tasarım kararı bu 10 katmanın BİRLİKTE tutarlı yayılımı olarak değerlendirilir.
- **Token/değer:** 10 katman listesi (yukarıda).
- **Teknik:** Kimlik atomik değil bileşiktir: tek güçlü fikrin (görünür konsensus) her yüzeye tutarlı taşınması. Review'da bir öge yalnızca kendi katmanında değil, 10 katmanla tutarlılık açısından denetlenir.
- **DoD:** Her yeni ekran/komponent PR'ında "10 katmandan hangileri dokunuldu + çelişki var mı" kontrol satırı işaretli; tek katmanı kimlik ilan eden karar reddedilir.
- **Ölçüm:** PR-checklist maddesi (manuel review-gate): 10-katman tutarlılık satırı işaretli/işaretsiz — ikili lint-benzeri kapı.

### G-00-02 · Merkez kimlik DNA'sı = ölçekte-okunan görünür AI konsensusu
- **Direktif:** Kimliğin ağırlık merkezini ışık/parlaklık değil, ölçekte okunan görünür 9-motor konsensusu (bir OKUMA BİÇİMİ) olarak kabul et; ışığı yalnız destekleyici (olay/yaşam-döngüsü) sistem olarak kullan.
- **Token/değer:** 9-motor konsensus okuması = merkez; ışık = destekleyici.
- **Teknik:** Eski "parlaklık=ışık=kimlik" merkezi terk edildi (izole kartta okunamaz, parlaklık=güven×tazelik hukuki risk, tokenlar kopyalanabilir). Yeni merkez sahtelenemez, işlevsel, 9-motor mimarisine bağlı.
- **DoD:** "Işığı ana taşıyıcı yapıyor" kararı reddedilir; kimlik taşıyıcısı = konsensus enstrümanı (Karot) + provenance + kahraman-rakam.
- **Ölçüm:** Review-gate: gerekçe "ışık ana kimlik" → red; "konsensus/dürüstlük" → geçer (+ logo-kapalı test G-08-05).

### G-00-03 · Konumlandırma cümlesi (tek kanonik cümle)
- **Direktif:** Konumlandırmayı tek kanonik cümleyle sabitle, tüm tasarım/kopya kararlarını hizala: *"TradeMinds = ölçekte-okunan-dürüst-konsensus; fark efektte değil dürüstlük duruşunda."*
- **Token/değer:** Kanonik cümle: `ölçekte-okunan-dürüst-konsensus`.
- **Teknik:** DNA'nın tek-satır özeti; "fark efektte değil dürüstlük duruşunda" görsel-havai-fişek/efekt yarışını yapısal olarak reddeder.
- **DoD:** Cümle §00'da birebir yer alır; yeni ana-mesaj/hero-copy bununla çelişmez.
- **Ölçüm:** Metin denetimi: cümlenin §00'da birebir varlığı + hero-copy çelişki taraması.

### G-00-04 · Rakip ayrışma konumu
- **Direktif:** Ayrışma konumu = TradingView netliği + Bloomberg dürüst yoğunluğu + Linear craft + AI-konsensus/yaşam-döngüsü ekseni. "47. güzel-fintech" olmayı ve rakibe yakınsamayı reddet.
- **Token/değer:** Konum = TradingView-netlik + Bloomberg-yoğunluk + Linear-craft + AI-konsensus.
- **Teknik:** Rakipler veriyi gösterir; TradeMinds veriyi + AI'nin ona ne kadar inandığını (konsensus) + her çağrının dürüst hayat/ölümünü (yaşam-döngüsü) gösterir.
- **DoD:** Screenshot line-up yabancı-kör testinde (§08) ekran kategori/ürün olarak ayırt edilebilir; kıyas setine TR rakipleri (TradingView/Matriks/Midas) dâhildir.
- **Ölçüm:** Çeyreklik yabancı-kör line-up: bağımsız gözlemci ekranı rakiplerden ayırt edebiliyor mu (evet/hayır oranı); ayırt edilemezse release bloklanır. **(Özgünlük ölçümünün tek kapısı bu maddedir; G-00-16/G-08-18 nitel-notlar buna bağlanır.)**

### G-00-06 · 6-önerme imza turnusolü (P8)
- **Direktif:** Her tasarım/motion/ışık/renk kararı şu altı önermeden EN AZ BİRİYLE tek cümlede savunulabilmeli; savunulamayan karar alınmaz: (1) Az efekt (2) Doğru efekt (3) Işık=Bilgi (4) Derinlik=Kanıt (5) Hareket=Olay (6) Sükûnet=Güven.
- **Token/değer:** 6 önerme: Az-efekt · Doğru-efekt · Işık=Bilgi · Derinlik=Kanıt · Hareket=Olay · Sükûnet=Güven.
- **Teknik:** Governance-seviyesi imza filtresi; G-00-07 (anlamsız efekt yok) ve G-00-10 (her-piksel-sebep) uygulama kapısı. "Moda/trend/güzel" gerekçe değildir.
- **DoD:** PR review'da karar açıklaması 6 önermeden birine tek cümleyle bağlanmış; bağlanamayan öge reddedilir.
- **Ölçüm:** Review-gate: her tartışmalı görsel karar için "6-önerme referansı" alanı doldurulmuş (var/yok); boş → red.

### G-00-07 · Anlam taşımayan efekt yasağı (P1)
- **Direktif:** Her efekt bilgi / güven / analiz / karar / zaman / AI-düşünme / sinyal-üretimi / veri-akışı anlatmalı; "güzel görünüyor" / "trend" gerekçeli her efekt OTOMATİK reddedilir.
- **Teknik:** Efekt anlamsallık zorunluluğu (§06 kaynak-isimli motion ile aynı ruh): her hareket/parlaklık bir telemetri alanını isimlendirir. Dekoratif efekt kimlik-dışıdır.
- **DoD:** Her efekt/animasyon için tek cümlelik "ne anlatıyor" gerekçesi yazılı; "güzel/trend" içeren gerekçe reddedilir.
- **Ölçüm:** Review-gate + kod taraması: gerekçesiz veya "trend/decorative" etiketli efekt sayısı = 0.

### G-00-08 · Premium = az; cesaret = daha çok sükûnet (P3/P7)
- **Direktif:** Premium'u glow/renk/animasyon miktarıyla değil ışık-boşluk-ritim-materyal-tipografi + sükûnetle üret; "cesur ol" = "daha çok sükûnet + tek gerçek olay".
- **Token/değer:** Premium = ışık+boşluk+ritim+materyal+tipografi+sükûnet (efekt-miktarı DEĞİL).
- **Teknik:** Çok glow/renk/animasyon premium değil template-kokusudur. Tek accent, tek dürüst karanlık zemin, tek gerçek olay.
- **DoD:** "Premium hissi için efekt ekleme" gerekçesi reddedilir; premium artışı boşluk/materyal/tipografi/sükûnet üzerinden savunulur (G-00-06).
- **Ölçüm:** Squint testi (§08) + viewport başına vurgu ≤2; aşan ekran red.

### G-00-09 · Tek görsel dil — her sayfa aynı DNA (P4)
- **Direktif:** Tüm yüzeylerde tek görsel DNA; aynı işi iki farklı görsel dilde yapan iki yüzey = ihlal.
- **Teknik:** Template-kokusu sistemsizlikten gelir; tek-kaynak primitifler (Card/Button/Modal/Toast/Badge) istisnasız kullanılır, sayfa-yerel lehçe üretilmez.
- **DoD:** Aynı işlevi iki farklı desenle çözen ikinci yüzey birleştirilene dek PR bloklanır.
- **Ölçüm:** Kod taraması: aynı işlev için paralel primitif/lehçe sayısı → 1 hedefi; >1 ihlal.

### G-00-10 · Her piksel bir sebeple (P5/P6)
- **Direktif:** Border / radius / hairline / spacing / shadow / glow / opacity / timing gerekçesini tek cümlede yazamadığın her değeri review'da düşür; "moda" asla gerekçe olamaz.
- **Token/değer:** Gerekçe zorunlu alanlar: border · radius · hairline · spacing · shadow · glow · opacity · timing.
- **DoD:** Yeni/değiştirilen her görsel token/değer için tek cümlelik gerekçe PR'da yazılı; gerekçesiz değer reddedilir.
- **Ölçüm:** Review-gate: token/değer değişikliği başına gerekçe-satırı var/yok; "moda/trend" içeren gerekçe otomatik red.

### G-00-11 · Dürüstlük fiziğe kodlu (Lie Factor = 1)
- **Direktif:** Dürüstlüğü görsel fiziğe göm: közleşme (kapanan sinyal kararır+çöker, kayıp saklanmaz), sahte-kesinlik yok, Lie Factor=1 (kırpılmamış baseline, saklanmayan SL), düşük-güven zayıf görünür, çatışma yumuşatılmaz.
- **Token/değer:** Lie Factor = 1 · kırpılmamış baseline · közleşme (−2 lümen basamağı iner).
- **Teknik:** Kapanan kart −2 lümen basamağı kararır + sıralamada dibe çöker. Baseline kırpılmaz, SL saklanmaz, bölünmüş/kararsız konsensus dürüstçe zayıf render edilir.
- **DoD:** Chart baseline kırpılmamış; kapanan kartta kararma+çöküş; düşük-güven soluk render. **Ancak közleşen kartın outcome badge'i tam-kontrast kalır (D2, §01) — geçmiş sonuç asla sönmez.**
- **Ölçüm:** Grafik denetimi: eksen baseline'ı sıfırdan mı (Lie Factor=1) + kapanan-kart lümen düşüşü ölçümü (−2 basamak).

### G-00-14 · 8 imza ögesi (kimlik taşıyıcı liste)
- **Direktif:** İmza ögeleri setini sabit tut, her sinyal-yüzeyinde ilgili ögeleri kullan: Lümen-ölçek · Karot (merkez) · doğum-nabzı · cyan-iz · kanıt-fitili · yaşayan-seviye · közleşme · ışık-maskeli-grid.
- **Token/değer:** 8 imza: Lümen-ölçek · Karot · doğum-nabzı · cyan-iz · kanıt-fitili · yaşayan-seviye · közleşme · ışık-maskeli-grid.
- **Teknik:** Bu 8 öge logo-kapalı yükü taşır; detay tanımları §05/§01/§06'da. §00'da yalnız kanonik liste + rol.
- **DoD:** Her sinyal yüzeyi en az ilgili imza(lar)ı içerir (Karot zorunlu, kapanışta közleşme zorunlu).
- **Ölçüm:** Yüzey denetimi: sinyal-yüzeyi başına imza kontrol listesi (Karot zorunluluğu §08 lint ile çapraz).

### G-00-16 · SOTD / ödül hükmü (craft hedefi, spektakl reddi) — *nitel-gate*
- **Direktif:** Shader-spektakl SOTD'yi hedefleme (finans-güven duruşunu bozar); hedef = en-iyi-craft + özgün bilgi-tasarımı; kabul edilebilir kategori Awwwards Developer/Honorable + jüri-craft.
- **Teknik:** Havai-fişek eskir, dürüst enstrüman eskimez. Benzersizlik görsel-spektaklden değil gerçekten-yeni-bilgi-tasarımı (görünür AI-konsensusu) + kusursuz craft'tan gelir.
- **DoD:** Ödül/showcase hedefinde "shader-spektakl SOTD" reddedilir; craft+bilgi-tasarımı kategorisi seçilir.
- **Ölçüm:** *Ölçüm-yok / nitel-gate.* Özgünlük ölçümü G-00-04 screenshot line-up'a bağlanır.

### G-00-18 · Her glow bir yaşam-döngüsü olayına bağlı (glow ≠ dikkat aracı) — *legal-ışık kodda* [O2]
- **Direktif:** Işık üreten (glow/foton-flaş/doğum-nabzı/underlay) HER öge zorunlu bir `data-lifecycle-event` enum değeri taşır: `{birth | approaching_tp | invalidation | user_win}`. Bu enum dışında hiçbir kalıcı/dekoratif glow üretilemez; glow bir dikkat/öneri aracı OLAMAZ (legal). Tazelik/güncellik ışığı dikkat için kullanılamaz.
- **Token/değer:** `data-lifecycle-event ∈ {birth, approaching_tp, invalidation, user_win}` (zorunlu attribute); enum-dışı ışık = 0. Işık-sahipleri glow bütçesiyle (§01 craft-glow) ortak: CTA-hover (olay değil, tek istisna) + AI-doğum-cyan (`birth`) + kullanıcı-kazanç-amber (`user_win`) + yaşam-döngüsü-geçişleri (`approaching_tp`/`invalidation`).
- **Teknik:** Legal-ışık koda bağlanır: her ışıklı DOM ögesi telemetri kaynağını `data-lifecycle-event` ile isimlendirir; bu §00-07 (anlamsız efekt yasağı) + §06 kaynak-isimli motion'ın makine-doğrulanabilir hâlidir. Parlaklık asla öneri/dikkat itmez (squint testi G-00-08/§08 ile çapraz).
- **DoD:** Işık üreten her öge `data-lifecycle-event` taşır; enum-dışı değer veya attribute'suz glow = red; CTA-hover glow'u tek muaf (olay değil etkileşim, yine de dekoratif değil).
- **Ölçüm:** Kod taraması: glow/foton/underlay üreten DOM ögelerinde `data-lifecycle-event` kapsamı %100; enum-dışı literal=0; CTA-hover dışı attribute'suz box-shadow-glow=0.

### Kalıcı Yasaklar (§00 · ebedî red)

**G-00-15 · Kalıcı tabu listesi.** Şu ögeler kalıcı olarak yasaktır, asla kullanılmaz:
Three.js (kimlik-merkez) · video-background · Spline · gradient-mesh-satüre · scroll-jacking · sonsuz-pulse · dönen-radar · idle-tarama · sahte-progress · cyan-yüzey/dolgu · bull/bear-atmosfer-rengi · mor-pembe-gradient-text · neon/Matrix/cyberpunk/RGB-kitsch · kırpılmış-eksen.
- **Teknik:** İhlal CI-lint (glow/box-shadow/renkli-rgba) + review-gate ile yakalanır. Kırpılmış-eksen Lie-Factor'ü, cyan-yüzey AI-çizgi-tekelini, bull/bear-atmosfer renk-semantiğini kırar.
- **Ölçüm:** CI-lint + bağımlılık taraması: `three`/`@react-three`/`spline` import (kimlik amaçlı) = 0; ham renkli glow-rgba = 0; kırpılmış-eksen chart config = 0. İhlal = release-blokaj.

**G-00-17 · F-vs-T göz hareketi folkloru — KALICI RED.** "F-şekilli vs T-şekilli göz hareketi" türü temelsiz UX-folklorunu asla tasarım gerekçesi yapma; bu iddia atıldı. Layout gerekçeleri ölçülebilir okuma/tarama davranışına (bilgi-önceliği) dayanır.
- **Ölçüm:** Review-gate: layout gerekçelerinde "F-pattern/T-pattern göz hareketi" ifadesi = 0. **(Tek kanonik madde budur; §03 dash-göz-hareketi yasağı buna referans verir.)**

---

## 01 · Design System

Tüm üründe tek standart. Tokenlar tek kaynaktan (CSS değişkeni) türer; Tailwind literalleri bu değişkenlere bağlanır — palet-drift biter.

> **Normatiflik notu:** Değerlerde bu **token tablosu** kanoniktir. Demo CSS örnekleri açıklayıcıdır — çelişkide token tablosu kazanır. Tüm renk/hairline/glow/süre değerleri §08 Kanonik Token Tablosu'yla birebir aynıdır.

### Renk Sistemi

Tek accent (owned-blue) + AI-cyan partner (yalnız çizgi/nokta/iz). Semantik bull/bear accent'ten **ayrı** ve **kazanılır** (varsayılan/dekor değil). Nötrler maviye eğik near-black midnight.

> **Renk kilidi AÇIK (v1.3).** 20-hücre WebAIM tablosu (5 semantik hex × 4 yüzey) tamamen dolduruldu; her hücre rol-eşiğini (metin ≥4.5:1 · UI/grafik-obje/iz ≥3:1) geçti → **DoD-5 geçti (§08)**. Değerler artık kilitlidir; a11y-zorunlu iki türev (`--accent-ui`, `--accent-hover`) + accent-üzeri-metin (`--ac-tx`) eklenmiştir. Türevler **kimlik değişikliği DEĞİL**, erişilebilirlik-zorunlu owned-türevlerdir.

#### Yüzey merdiveni (E0–E3) — COL-01 / COL-02

- **Direktif:** Tüm yüzeyleri yalnızca dört basamaklı E0–E3 setinden türet; beşinci gri icat etme, ara-ton hardcode etme. Zemin/yüzeyleri asla saf siyaha (#000000) veya nötr-graphite griye kaydırma; daima midnight-blue tint.
- **Token/değer:**

| Token | Değer | Kullanım |
|---|---|---|
| `--e0` | `#070B14` | Zemin (Ground) · near-black midnight-blue tint |
| `--e1` | `#0C1220` | Kart/panel yüzeyi (E1) |
| `--e2` | `#111A2B` | İç/yükselmiş yüzey + hover ısınma hedefi (+1 basamak) |
| `--e3` | `#17233A` | Overlay/cam yüzeyi (modal/dropdown/toast/tooltip/palette/provenance). Gölge+blur yalnız burada. |

- **Teknik:** OKLCH-kalibreli midnight-blue tint merdiveni; her basamak bir elevation seviyesi (E0 zemin → E1 kart → E2 iç → E3 overlay). Gölge değil luminans farkı derinlik kurar. Saf siyah OLED'de halation yaratır + elevation'ı çökertir; midnight tint hem kimlik ayrımı (graphite Linear/Vercel'den ayrışır) hem elevation tabanı. Metin okunabilirliği: `--tx`/`--tx2` E0–E3'ün hepsinde ≥6.3:1 (COL-11 doğruladı).
- **DoD:** src+public'te yüzey rengi olarak yalnız `--e0..--e3`; ham hex yüzey/zemin/kart/overlay'de 0; 5. gri yok; `#020817`/`#000000` grep=0; `--e0` RGB kanalları eşit-değil (B>R,G).
- **Ölçüm:** CI-lint token-dışı hex reddi; `grep '#020817|#0A101C|#000000'` (src+public)=0; token sayımı tam 4; E0→E3 ölçülen luminans monotonik artar.
- **Migration (v1.1→v1.3):** `--bg #070B14 → --e0`; `--surface-1..3 → --e1..--e3`; `--bg-alt #0A101C` **emekli** (section almaşığı luminans merdivenine iner). Zemin `#020817 → --e0 #070B14` (6 konum: tailwind.config · globals.css · layout.tsx themeColor · manifest theme+background · ShareCardModal · TradingViewChart embed zemin).

#### Metin tonu merdiveni (tx/tx2/tx3) — COL-03

- **Direktif:** Metni yalnızca üç tonluk tx/tx2/tx3 setinden seç; dördüncü metin grisi ekleme. `--tx3` okunur metin DEĞİLDİR — yalnız UI-obje/dekor/disabled rolündedir.
- **Token/değer:**

| Token | Değer | Kullanım · kısıt |
|---|---|---|
| `--tx` | `#E8EDF5` | Ana metin + `::selection-fg`. E0–E3'ün hepsinde ≥6.3:1. |
| `--tx2` | `#9AA6B8` | İkincil / okunur mikro-etiket floor (placeholder, uppercase etiket, eksen etiketi, error-neden). E0–E3'ün hepsinde ≥6.3:1. |
| `--tx3` | `#5C6980` | **KISIT: okunur metin DEĞİL** (E0–E3'ün hepsinde <4.5:1). Yalnız dekoratif/disabled + Karot kararsız omurga (UI-obje/iz rolü) + közleşme kül tonu. Kullanım için taban E0–E2; **E3'te UI-obje olarak da kullanma** (<3:1, FAIL). |

- **Teknik:** `--tx3` koyu zeminde tüm okunur metinde AA-altıdır (<4.5:1) → okunur metin/etiketlerde YASAK; okunur mikro-etiket minimum `--tx2`. Kararsız-omurga/közleşme UI-obje/iz rolündedir → WebAIM ≥3:1 kapısına tabidir ve bu rolde yalnız E0–E2 üzerinde kullanılır (E3'te <3:1 olduğu için orada UI-obje olarak da yasak).
- **DoD:** Okunur metin/etiket `--tx3` kullanmaz; `--tx3` yalnız decoration/disabled/kararsız-omurga/közleşme ve yalnız E0–E2 zemininde; dördüncü ton yok.
- **Ölçüm:** WebAIM: `--tx` & `--tx2` E0–E3'e karşı ≥4.5:1 (fiilen ≥6.3:1); `--tx3` yalnız non-text → metin-oranı muaf, E0–E2 UI-obje kullanımı ≥3:1 doğrulanır; lint: okunur-metin selektörlerinde `--tx3` flag + `--tx3`-on-E3 UI kullanımı flag.
- **Migration (v1.1→v1.3):** `--text → --tx`; `--muted → --tx2`; `--faint → --tx3`.

#### Semantik renkler (bull/bear/accent/cyan/amber) — COL-04..08 · *KİLİTLİ (WebAIM DoD-5 geçti)*

- **Direktif:** Yükseliş/kazanç → `--bull`; düşüş/zarar/stop → `--bear`; tek accent-dolgu → `--accent`; 1px-UI/iz-accent → `--accent-ui`; AI-izi → `--cyan` (yalnız çizgi/nokta/iz); kullanıcı-kazanç olayı → `--amber` (olay-bağlı+bütçeli). Semantik renk **asla glow/atmosfer** olmaz; renk **kazanılır** (varsayılan/dekor değil). Her rengin kullanım-kısıtı WCAG-hesaplıdır (aşağıda) ve bağlayıcıdır.
- **Token/değer:**

| Token | Değer | Kullanım · WCAG kısıtı (KİLİTLİ) |
|---|---|---|
| `--bull` | `#2FBE9A` | Semantik yükseliş; teal-emerald. Her yüzeyde (E0–E3) ≥6.69:1 — **metin dâhil serbest**. |
| `--cyan` | `#25E0D4` | AI izi, owned electric-teal. İz her yüzeyde 9.49–11.89:1. Yalnız çizgi/nokta/iz/omurga; yüzey/dolgu/buton/başlık YASAK. |
| `--amber` | `#F5A524` | Kullanıcı-kazanç/gurur-anı + chart sinyal-işareti + başarı-toast. Her yüzeyde 7.69–9.64:1. Yalnız olay-bağlı+bütçeli; idle/ambient/dekor amber YASAK. |
| `--bear` | `#E14640` | Semantik düşüş; warm-red terminal. **KISIT: okunur METİN yalnız E0/E1** (E0 4.83:1 / E1 4.59:1 ≥4.5). UI/glyph/1px-hairline E0–E3 (E3 3.85:1 ≥3). E2/E3'te metin FAIL — metinde kullanma. |
| `--accent` | `#3B57D4` | TEK accent-**dolgu** (owned-blue). **KISIT: YALNIZ DOLGU** (CTA bg · yön-nötr seri-dolgu · seçim-tint). Üzerine metin `--tx` (5.10:1) veya `#FFFFFF` (6.00:1). **1px-UI/iz/border olarak E2/E3'te FAIL** (2.90 / 2.62 <3) → iz/border/ring için KULLANMA. |
| `--accent-ui` | `#4E6BE3` | **[a11y-türevi — YENİ]** 1px-UI accent: focus-ring · border · nav-accent · input-focus. E0–E3'ün hepsinde ≥3:1 (E0/E1/E2/E3: 4.25 / 4.04 / 3.76 / 3.39) + white-on 4.63:1. Kimlik değişikliği DEĞİL; `--accent`'in erişilebilirlik-zorunlu iz-türevi. |
| `--accent-hover` | `#3450C6` | **[YENİ]** YALNIZ birincil CTA-**dolgu** hover (white-on 6.75:1). Asla iz/border/ring değil. `--accent`'in −1 luminans hover türevi. |
| `--ac-tx` | `= --tx (#E8EDF5)` | Accent-dolgu üzeri okunur metin. `--accent` bg üzerinde 5.10:1 (≥4.5). **Yeni hex YOK** — `--tx`'e alias. |

- **Teknik:** `--bull` teal-emerald (para/sakin-güven, renk-körü-güvenli, neon değil), her yüzeyde metin dâhil serbest. `--bear` warm-red (kan/tuğla, chroma-capped); kontrast L üzerinden kurulur ama okunur metinde yalnız E0/E1 zemin izinli. `--accent` owned-blue (jenerik SaaS mavisi değil), **yalnız dolgu**; iz/border/ring rolü `--accent-ui` türevine devredildi (accent'in E2/E3 iz-kontrastı yetmediği için — a11y zorunluluğu, kimlik kaymadı). `--accent-ui` = tüm 1px accent iş yükü (focus/nav/border/input-focus). `--accent-hover` = yalnız CTA-dolgu hover. `--cyan` = AI-sınırının görünür işareti; Karot omurga çizgisi cyan-tekeliyle uyumlu tek istisna. `--amber` = üçüncü anlamlı ışık (mavi=insan/AI, amber=başarı). İkinci parlak kromatik accent YASAK.
- **DoD:** Her semantik renk tek ad+tek hex; emekli literaller grep=0; bull/bear glow=0; cyan yalnız stroke/line/dot; amber yalnız kazanç-olayda; `--bear` metin yalnız E0/E1; `--accent` yalnız dolgu (iz/border/ring'te 0); focus-ring/nav/input-focus/border yalnız `--accent-ui`; CTA-hover yalnız `--accent-hover`.
- **Ölçüm:** WebAIM 20-hücre tablosu (COL-11) DOLU + tüm hücreler eşik-geçer; `grep '#10B981|#F4556E|#F0564B|#3B82F6|indigo|#22D3EE|#FBBF24|#2563EB'` (src+public)=0; renk-körü simülasyonunda bull vs bear ayrışır; lint: `--accent` box-shadow/border/outline kullanımı=0 (yalnız bg); `outline`/`border`/`ring` accent-literali == `--accent-ui`.
- **Migration (v1.1→v1.3):** `--bull #10B981 → #2FBE9A` (Karot tinti + chart mum/TP render literalleri dâhil); `--bear #F4556E / #F0564B → #E14640` (input-hata dâhil); `--accent #3B82F6/indigo/#2563EB → #3B57D4`; **focus-ring/nav/input-focus/border → `--accent-ui #4E6BE3`** (accent'ten ayrıştırıldı); **CTA-hover → `--accent-hover #3450C6`** (eski `#2563EB` emekli); `--accent-2/--cy #22D3EE → --cyan #25E0D4`; `--warn #FBBF24 → --amber #F5A524` (tek sarı token, başarı-toast + chart sinyal-işareti aynı `--amber`).

#### Tek-accent + renk-kazanılır doktrini — COL-09
- **Direktif:** Yön rengini (bull/bear) yalnızca uzlaşma kazanınca gövdeye doldur; bölünmüş/kararsız halde renk kullanma (cyan-nötr bırak); rengi varsayılan/dekor olarak asla kullanma.
- **Teknik:** Karot uzlaşma kazanınca (eksen-geçiş <2 AND ortalama|güven|≥0.30) yön tinti area-fill (fill-opacity 0.14) olarak gövdeye dolar; bölünmüş/kararsız halde renk YOK. Bu "renk-kazanılır" imzasını fiziksel olarak kodlar.
- **DoD:** Bölünmüş/kararsız Karot ve durum yüzeyleri renksiz/cyan-nötr; yön rengi yalnız kazanan-uzlaşmada; hiçbir yüzey varsayılan-renkli değil.
- **Ölçüm:** Runtime: bölünmüş-hal render'ında bull/bear yok (yalnız cyan); squint: en parlak pikseller veri+CTA; viewport başına kromatik-accent ≤1.

#### Hairline / border alfa merdiveni — COL-10
- **Direktif:** Yüzey ayrımını önce boşlukla, yetmezse hairline ile kur; asla renkle/kutuyla ayırma; hairline alfasını semantik merdivenden seç.
- **Token/değer:**

| Token | Değer | Kullanım |
|---|---|---|
| `--hl10` | `rgba(148,163,184,.10)` | Dinlenme / panel-içi bölünme / chart grid |
| `--hl12` | `rgba(148,163,184,.12)` | Standart/varsayılan (kart/panel/section/input/tooltip/crosshair/Karot slot-kılavuzu) |
| `--hl16` | `rgba(148,163,184,.16)` | Etkileşim (hover/focus-within) |
| `--hl22` | `rgba(148,163,184,.22)` | Kanıt/odak (input focus, E3 overlay border) |

- **Teknik:** Slate-tabanlı white-value; koyu E1'de belirgin, açık E3'te yumuşar. Border=ayrışma (anlam değil); anlam renkten gelir. Anizotropi: dikey kenarlar net (tam alfa), yatay kenarlar soluk (düşük alfa) → ışık-yönü tutarlılığı. Accent'li 1px kenar/ring gerektiğinde renk `--accent-ui` (accent-dolgu değil).
- **DoD:** Yüzey ayrımı boşluk→hairline sırasıyla; alfa dört semantik değerden biri; anizotropi (dikey>yatay) uygulanır.
- **Ölçüm:** Lint: border-color yalnız `--hl*` ailesi veya `--accent-ui` (ham rgba + `--accent`-border reddi); token sayımı tam 4; dikey kenar alfası > yatay.
- **Migration (v1.1→v1.3):** Taban = slate `rgba(148,163,184,·)` (fiili kullanım kazandı; COL-10 white-alpha beyanı slate-tabana hizalandı). `--hl-rest/--hl/--hl-interact/--hl-focus → --hl10/--hl12/--hl16/--hl22`. Karot eksen hairline **.16 → .12** (statik kılavuz; .16 yalnız etkileşime saklandı). Grid (.10) < eksen (.12) hiyerarşisi korunur.

#### OKLCH/WCAG kontrast kilidi (WebAIM DoD gate) — COL-11 · *KİLİTLİ (tablo DOLU, DoD-5 geçti)*
- **Direktif:** Her semantik hex E0–E3'e karşı WebAIM ile doğrulanmış ve rol-eşiğini geçmiştir; bundan sonra değer değişikliği ancak yeni 20-hücre doğrulaması + sürüm-revizyonuyla yapılır.
- **Token/değer:** Gate eşikleri: metin ≥4.5:1 · UI/grafik-obje/iz ≥3:1 (E0 `#070B14`, E1 `#0C1220`, E2 `#111A2B`, E3 `#17233A`).
- **Teknik/DoD:** 5 semantik hex × 4 yüzey = 20 ölçüm tablosu **tamamen dolduruldu**; sonuç: `--bull` her yüzeyde ≥6.69:1 (metin dâhil) · `--cyan` iz 9.49–11.89 · `--amber` 7.69–9.64 — üçü koşulsuz geçti. `--bear` metin yalnız E0/E1 (4.83/4.59), UI E0–E3 (E3 3.85) — kısıtlı geçti. `--accent` dolgu-üzeri-metin `--tx` 5.10 / white 6.00 geçti, 1px-UI E2/E3 FAIL (2.90/2.62) → `--accent-ui #4E6BE3` türetildi (E0–E3 ≥3, white-on 4.63). `--accent-hover #3450C6` white-on 6.75. Kısıtlar COL-03/COL-04..08'e işlendi.
- **Ölçüm:** 20-hücre tablosu §01/§08'e işlenmiş ve her hücre eşik-geçer (0 açık hücre); tablo yeniden-doğrulanmadan hiçbir semantik hex değişmez.

#### Renk — Kalıcı Yasaklar
**COL-12 · Eski glow-rgba temizliği.** SignalBadge/RiskGauge/Button gölgelerindeki ham renkli glow-rgba (`rgba(0,230,118,·)` / `rgba(255,82,82,·)` vb.) yasaktır; parlaklık yalnız glow token ailesinden. Neon/RGB kalıcı red.
- **Ölçüm:** `grep 'rgba(0,230,118|rgba(255,82,82'` (src+public)=0; CI-lint ham renkli box-shadow build-red.

### Typography

Görsel hiyerarşi 3 metin ağırlığı + ayrı numeral ekseniyle kurulur. Rakamlar tipografik kahramandır (logo-kapalı tanınmanın ana taşıyıcısı).

#### typo-type-scale · Tip ölçeği (H1–mikro-etiket) [O6]
- **Direktif:** Başlık/gövde/veri/etiket punto ve tracking'ini tek role-bağlı ölçekten türet; ad-hoc font-size yok.
- **Token/değer:**

| Rol | Punto / satır / tracking |
|---|---|
| H1 (display) | 32px · tracking −0.025em · weight 650 |
| H2 | 24px · tracking −0.02em · weight 650 |
| H3 | 18px · tracking −0.015em · weight 650 |
| H4 | 15px · tracking 0 · weight 500 |
| Gövde | 15px · line-height 1.6 · weight 400 |
| Veri (tablo) | 13px · tabular · weight 400 (numeral 480–540) |
| Mikro-etiket | 11px · tracking +0.08em · UPPERCASE · weight 500 · `--tx2` |

- **Teknik:** Negatif tracking optik-boyutla artar (büyük başlıkta daha sıkı). Veri satırı 13px tabular (Bloomberg-yoğunluğu, §03). Mikro-etiket rengi min `--tx2` (`--tx3` yasak). Ölçek-dışı punto (17/20/28…) yok.
- **DoD:** Tüm metin ölçekten; H1 32/−0.025 · H2 24/−0.02 · H3 18/−0.015 · H4 15 · gövde 15/1.6 · veri 13 · mikro 11/+0.08/UPPER; ölçek-dışı font-size=0.
- **Ölçüm:** computed font-size ∈ {11,13,15,18,24,32}; H1 letter-spacing≈−0.025em; mikro-etiket 11px/uppercase/`--tx2`; ölçek-dışı literal grep=0.

#### typo-font-family · Gövde / mono / numeral altyapısı
- **Direktif:** Gövde `system-ui` yığını (line-height 1.6, antialiasing); kod/mono `ui-monospace`; numeral altyapısı sahipli set gelene dek Inter variable (next/font self-host).
- **Token/değer:**

| Rol | Değer |
|---|---|
| Gövde font-family | `system-ui, -apple-system, 'Segoe UI', sans-serif` |
| Mono font-family | `ui-monospace, 'Cascadia Mono', Consolas, monospace` |
| Numeral altyapısı | Inter variable (next/font self-host, `@import` YOK, CLS=0) |

- **Teknik:** OS-native gövde → CLS=0, sıfır ağ maliyeti. Inter yalnız numeral/display ekseni için; dış font-CDN yasak (KVKK dostu). Mono: kod · eksen etiketi · hex · tabular teknik değer.
- **DoD:** Gövde computed `system-ui` ile başlar; line-height 1.6 + antialiased; mono `ui-monospace`; dış `@import` font isteği 0; Inter yalnız numeral/display.
- **Ölçüm:** computed font-family; network 3rd-party font=0; CLS=0; `grep '@import.*font'`=0.
- **Migration (v1.1→v1.3):** "Geist/Söhne benzeri self-host" → gövde `system-ui` stack + numeral `Inter variable`; `@import` yasağı korunur.

#### typo-tabular-nonnegotiable · Tabular-nums pazarlıksız
- **Direktif:** TP · SL · Giriş · fiyat · skor · olasılık · R:R dâhil istisnasız her sayısal alan `tabular-nums`; sütunlar ondalık ayracında (tr-TR virgül) hizalı; güncellemede konum/scale ASLA oynamaz (yalnız foton flaşı).
- **Token/değer:** `font-variant-numeric: tabular-nums` (global body + tüm sayısal hücre); ondalık ayracı tr-TR virgül (Intl); sağ hiza için `text-align:right` + sabit ondalık basamak reçetesi; güncelleme sinyali foton flaşı `--dur-photon` (150ms) / +1 lümen (konum sabit).
- **Teknik:** Gövdede tek sefer `tabular-nums` (body kuralı) → proporsiyonel numeral kaçağı yapısal engellenir. Canlı hücrede layout animasyonlanmaz; yalnız opacity/lümen. Uç-durum reçetesi `.num-cell` (aşağıda typo-num-cell).
- **DoD:** Proporsiyonel numeral yok; canlı güncellemede satır/sütun yatay zıplamaz; sütun ondalıkta hizalı; güncelleme yalnız foton.
- **Ölçüm:** computed `tabular-nums`; canlı fiyat 10 tick boyunca boundingClientRect.x sabit (0 kayma); ondalık ayracı x satırlar arası ≤1px sapma.

#### typo-num-cell · Tabular uç-durumları (`.num-cell`) [O9]
- **Direktif:** Her sayısal hücre `.num-cell` reçetesinden render edilir: sağ-hizalı, sabit ondalık-slot, `tabular-nums`; negatif işaret ayrı hizalı slotta; taşan değer basamak-tavan + "…" + tam-değer tooltip; değişken hassasiyet aynı sütunda ondalık-nokta hizasında kalır.
- **Token/değer:**
  - `.num-cell` = `text-align:right` + `font-variant-numeric:tabular-nums` + sabit ondalık-basamak slotu.
  - Negatif işaret: ayrı sabit-genişlik slot (işaret sütunu), sayı hizasını bozmaz.
  - Truncation: `max-basamak` tavanı aşılırsa "…" + `title`/Tooltip'te tam değer (provenance-dışı genel Tooltip).
  - Değişken hassasiyet: `≥1000 → 2 ondalık` · `1–1000 → 2–4` · `<1 → 4–6` · `<0,001 → 6–8` (Locale reçetesiyle tek kaynak); ondalık-nokta X-hizası tüm satırlarda sabit.
- **Teknik:** Ondalık-nokta sabit sütunda tutulur (tabular advance) → farklı hassasiyetteki komşu satırlar noktada hizalı. Truncation layout'u genişletmez; tam değer daima erişilebilir (tooltip/`aria`). Negatif slot foton-flaşında da kaymaz.
- **DoD:** Tüm sayısal hücreler `.num-cell`'den; ondalık-nokta satırlar arası hizalı; negatif işaret slotu sayıyı kaydırmaz; taşan değerde "…"+tam-değer tooltip; hassasiyet Locale reçetesine uyar.
- **Ölçüm:** ondalık-nokta X sapması satırlar arası ≤1px; negatif/pozitif satırda sayı-başlangıç X sabit; truncation'da tam-değer `title`/tooltip DOM'da; hassasiyet basamak-sayısı Locale eşiğine uyar.

#### typo-weight-tracking · Ağırlık disiplini + negatif tracking
- **Direktif:** Ekran başına en fazla 3 metin ağırlığı; display/hero başlıklar negatif tracking'le sıkışır, gövde nötr; uppercase mikro-etiketler sabit reçete; gradient-text başlık EBEDİYEN yasak (tek istisna: landing logosu).
- **Token/değer:**

| Rol | Değer |
|---|---|
| Ağırlıklar | 400 gövde / 500 label / 650 display (≤3 metin ağırlığı/ekran) |
| Numeral weight bandı | 480–540 (variable eksen; statik fallback 500; **≤3 kuralından MUAF**) |
| tracking display/hero | −0.015em (H1 650) … −0.025em (@48px+; ağırlık değil TRACKING optik-boyutla değişir) |
| tracking gövde | 0 (nötr) |
| uppercase etiket | 11px · +0.08em · **500** · `--tx2` |
| gradient-text | YASAK (landing logosu tek istisna) |

- **Teknik:** Negatif tracking yalnız büyük optik boyda (≈48px+ → −0.025em; tip-ölçeği H1 32px −0.025em ile hizalı). Ağır-display ayrı ağırlık DEĞİL; 650'de kalır, yalnız tracking değişir. Uppercase etiket rengi min `--tx2` (`--tx3`/faint yasak).
- **DoD:** Ayrık metin font-weight ≤3; display negatif tracking / gövde 0; uppercase 11px/+0.08em/500/`--tx2`; landing dışı gradient-text yok.
- **Ölçüm:** distinct computed metin-weight ≤3; display letter-spacing ∈ [−0.025em, −0.015em], gövde 0; `grep 'background-clip:text|text-fill-color'` yalnız landing-logo.
- **Migration (v1.1→v1.3):** Ölçek/ağırlık modeli → 400/500/650 üçlü + ayrı numeral bandı; uppercase etiket **600 → 500** (≤3 garantisi). Eski "600 alt-başlık/buton" ağırlığı emekli.

#### typo-owned-numeral · Sahipli tabular numeral seti (kahraman rakam) [K1a] · *açık uç: font ÜRETİMİ bekliyor*
- **Direktif:** Rakamlar tipografik kahraman + logo-kapalı tanınmanın ana taşıyıcısı. **ARA-KÖPRÜ (bugün aktif):** Inter variable + `font-feature-settings: "tnum" 1, "zero" 1, "ss01" 1, "cv05" 1` + weight ekseni {480/520/560}. **SAHİPLİ SET (hedef, tarihli milestone):** Inter numerallerini sahipli glyph setine taşımak. Ara-köprüden sahipli-sete geçiş tek adımda; iki set aynı anda üründe yok.
- **Token/değer:**
  - Ara-köprü feature-set: `"tnum" 1, "zero" 1, "ss01" 1, "cv05" 1` (Inter'de bugün açık).
  - Weight ekseni: `480 / 520 / 560` (numeral display kademeleri; ≤3-ağırlık kuralından MUAF).
  - **GLYPH SPEC (sahipli-set hedefi, ölçülebilir):** sabit tabular advance (her rakam eşit ilerleme) · ondalık-nokta sabit sütun-genişliği · x-height & cap-height hedefi tanımlı (gövde uyumu) · slashed-zero ZORUNLU (`"zero" 1`, Inter'de BUGÜN aktif).
  - **Milestone statüsü:** `köprü-aktif` (Inter + feature-set + weight ekseni, bugün) → `owned-bekliyor` (sahipli glyph üretimi, tarihli). Family adı `—` (üretilmedi).
- **Teknik:** KARAR kesin, ÜRETİM beklemede. slashed-zero + tnum + ss01/cv05 tabular altyapıya bağlı ve bugün açık; sahipli set landing-logosu dışı her sayısal yüzeyde tekilleşir. Vizyon (kahraman-rakam, logo-kapalı taşıyıcı) küçültülmez — köprü yalnız üretim gelene dek geçici altyapıdır.
- **DoD:** Font gelene dek numeraller Inter + köprü feature-set + {480/520/560}; sahipli set gelince tek commit'te tüm sayısal alanlar döner (iki numeral seti aynı anda üründe yok); logo-kapalı ekranda numeral karakteri "bu TradeMinds" okumasına katkı (G-08-05).
- **Ölçüm:** computed `font-feature-settings` köprü-setini içerir; numeral weight ∈ {480,520,560}; `"zero"` aktif (slashed-zero render); migration kapanışı `grep` ikinci numeral family=0; logo-kapalı çeyreklik line-up.

#### icon-lucide-system · İkonografi
- **Direktif:** Tüm ikonlar Lucide (1.5px stroke, 20px grid); boyut sabit merdivenden; her ikon eylem/durum, ASLA dekoratif; panel/kart başlığında süs ikonu yasak; durum noktaları lümen ölçeğinden okur.
- **Token/değer:** Lucide · stroke 1.5px · grid 20px · boyut merdiveni 14/16/20/24px · ikon-buton zorunlu `aria-label` · durum noktası rengi lümen ölçeğinden (dekoratif renk değil).
- **Teknik:** Tek ikon dili (Unicode/karışık set yasak); semantik doğruluk (Temel=Landmark, Makro=Globe). Durum noktaları renk-tek-kanal-değil kuralına tabi (nokta+metin/işaret).
- **DoD:** Tüm ikonlar Lucide 1.5px/20px; boyut ∈{14,16,20,24}; salt-dekor ikon yok; başlıkta süs ikonu yok; ikon-buton aria-label; durum noktaları lümenden.
- **Ölçüm:** stroke-width==1.5px; boyut ∈{14,16,20,24}; aria-label kapsamı %100; başlık DOM'unda dekoratif `<svg>`=0; Lucide-dışı ikon import=0.

### Locale & Format

Tek locale: **tr-TR**. Elle string kurma yasak; her sayı/tarih `Intl` üzerinden (`Intl.NumberFormat('tr-TR')` / `Intl.DateTimeFormat('tr-TR')`; `en-US`/elle ayraç yasak). Fiyat ondalık (typo-num-cell ile tek kaynak): ≥1000→2 · 1–1000→2-4 · <1→4-6 · <0,001→6-8. Para: USD `$` öneki (`$1.234,56`); kripto çifti sembolsüz + birim başlıkta. Büyük sayı `formatLargeNumber` (Mn/Bn) tek kaynak. Tarih `gg AAA yyyy` (+`SS:dd`), kullanıcı yerel saat dilimi. Tek kaynak formatter `lib/utils.ts`; komponent doğrudan `toLocaleString` çağırmaz. `tabular-nums` tüm sayısal alanlarda.
- **Migration (v1.1→v1.3):** `en-US → tr-TR formatter` (dashboard · portfolio · PriceDisplay · ShareCardModal · lib/utils.ts — 5 konum). Kapanış: `en-US` yalnız `lib/utils.ts`'te tr-TR'ye döner.

### Spacing — iki-ritim (craft-spacing-two-rhythm)
- **Direktif:** Boşlukları 8-tabanlı merdivenden türet; aynı ekranda iki ritim: veri satırı sıkı (4px iç / 8px arası) + chrome cömert (24px nefes). Ayrımı önce boşluk, yetmezse hairline; asla kutu/kart. Section: landing 96–128px, app 24–32px.
- **Token/değer:** `4/8/12/16/24/32/48/64/96/128px` (veri-içi 4px istisna); veri-satırı 4px iç/8px arası; chrome 24px; section landing 96–128 / app 24–32.
- **Teknik:** Tüm aralık flex/grid `gap` (per-element margin çakışması yok).
- **DoD:** İki ritim aynı ekranda görünür; ayrımlar boşluk>hairline>asla-kutu; section aralıkları landing 96–128 / app 24–32.
- **Ölçüm:** computed gap 8'in katı (4 istisna veri-içi); veri satırı row-gap≈8px, chrome padding≥24px; margin-collapse çift-boşluk=0.
- **Migration (v1.1→v1.3):** Eski `64 section` tek değeri → iki-ritim + landing/app ayrık section aralığı (96–128 / 24–32).

### Radius (craft-radius-scale)
- **Direktif:** Radius'u tek role-bağlı merdivenden türet; Karot RADYUSSUZ; jenerik default yok. `radius-input = radius-button = 10` bilinçli ORTAK-DEĞERdir (alias): iki kontrol aynı fiziksel köşeyi paylaşır, semantik ayrım (buton=eylem, input=giriş) korunur; yapay farklılaştırma yapılmaz.
- **Token/değer:** `radius-control 8 · radius-button 10 · radius-input 10 (= radius-button alias) · radius-card 12 · radius-panel 16 · radius-pill 999 · radius-karot 0`.
- **Teknik:** `radius-input`/`radius-button` ortak 10 değeri bilinçlidir (buton+input aynı satırda hizalanınca köşe tutarlılığı); iki ayrı token adı semantik izlenebilirlik için korunur ama değer alias'tır. `radius-karot=0` YALNIZ Karot SVG primitifine (viewBox root); içeren kart/panel kendi role-radius'unu (12/16) korur — Karot radyussuzluğu kabin radius'unu iptal etmez.
- **DoD:** Kontrol=8, buton/input=10 (ortak), kart=12, panel=16, chip=999; Karot=0; ölçek-dışı ad-hoc radius yok.
- **Ölçüm:** radius literalleri ∈{8,10,12,16,999,0}; Karot-selektör computed 0px; kart-selektör 12px; input==buton==10px; ara radius (6/14/20)=0.

### Shadow · Border · Glass · Depth · Cut-lip · Kabin imzası

#### craft-shadow-single-token · Shadow
- **Direktif:** Kartlar gölgesiz (derinlik luminanstan); gölge YALNIZ E3 overlay'de tek token; 2-katman gölge kalıcı YASAK.
- **Token/değer:** `--shadow-e3: 0 16px 40px -20px rgba(0,0,0,.7)`; kart gölge = yok; daima `--cut-lip` ile kombine.
- **DoD/Ölçüm:** `--shadow-e3` dışı drop-shadow=0; 2+ katmanlı box-shadow (cut-lip inset hariç)=0; E3 overlay computed shadow = tanımlı değer.

#### craft-cut-lip-top-highlight · Üst-kenar highlight
- **Direktif:** Yükselen **kapalı-yüzeyin** (kart/panel/overlay/buton) üst kenarına 1px ışık dokusu; specular amplitüd ≤1px. "Kesim dudağı" yalnız iç-dil.
- **Token/değer:** `--cut-lip: inset 0 1px 0 rgba(255,255,255,.07)`; amplitüd ≤1px.
- **Teknik:** Karot gibi çizgi/tel-tabanlı enstrüman kapalı-yüzey OLMADIĞINDAN cut-lip ALMAZ; Karot imzası kendi ışık-underlay'idir.
- **Ölçüm:** computed box-shadow inset = `inset 0 1px 0 rgba(255,255,255,0.07)`; kart/panel/overlay/buton cut-lip=%100; Karot-selektör cut-lip=0.

#### craft-cabin-signature · Kabin imzası (eksen-hizalı kabin) [O5]
- **Direktif:** Kart/panel "kabin" imzasını yalnız MEVCUT tokenlardan üret; YENİ motif eklemeden üç mevcut ögeyi birlikte uygula: (1) **border-anizotropi** — dikey kenar net (`--accent-ui`-tint ~1px, ışık-yönü), yatay kenar soluk (`.06` alfa); (2) **cut-lip** üst-kenar highlight (`--cut-lip`); (3) **luminans-depth** (E1→E2 basamağı, gölgesiz). Bu üçü birlikte "eksen-hizalı kabin" okumasını verir.
- **Token/değer:** dikey-kenar: 1px `--accent-ui`-tint (düşük alfa, ışık-yönlü net kenar) · yatay-kenar: `rgba(148,163,184,.06)` (soluk) · üst: `--cut-lip` · derinlik: luminans E1→E2 (gölge yok). Hepsi mevcut token ailesinden; yeni değişken YOK.
- **Teknik:** Anizotropi COL-10 ışık-yönü kuralının kabin-ölçekli uygulamasıdır (dikey>yatay). Accent-tint dikey kenar `--accent-ui` türevinden alınır (accent-dolgu değil, 1px-UI kısıtına uyar). Kabin imzası glow DEĞİLDİR (luminans + hairline + cut-lip); §00-18 lifecycle-glow enum'una tabi değildir.
- **DoD:** Kart/panel dikey kenarı `--accent-ui`-tint net, yatay kenarı `.06` soluk; üst-kenar cut-lip; derinlik luminanstan (gölge=0); yeni motif/token eklenmedi.
- **Ölçüm:** dikey-kenar alfası > yatay-kenar (.06); dikey-kenar rengi `--accent-ui` türevi; kabinde drop-shadow=0; cut-lip inset mevcut.

#### craft-depth-luminance-evidence · Depth = kanıt mesafesi
- **Direktif:** Derinliği kanıt mesafesi olarak YALNIZ luminanstan üret (yüzeyde sonuç, altında gerekçe, en altta ham veri); blur ile derinlik yaratma; z-ekseni sabit ölçeğe kilitli; odakta ≤2 katman.
- **Token/değer:** `z-sticky 10 · z-dropdown 40 · z-modal 50 · z-toast 60 · z-tour 100`; odak-katman max 2; luminans E0→E3.
- **DoD/Ölçüm:** z-index ∈{10,40,50,60,100}; ad-hoc z (20..110)=0; eş-zamanlı elevation ≤2; derinlik-için-blur (E3 dışı)=0.

#### craft-blur-e3-only · Blur / backdrop-blur
- **Direktif:** `backdrop-blur` YALNIZ E3 overlay, 8–10px; animasyonlanmaz; dekoratif blur yok; `prefers-reduced-transparency:reduce → opak fallback`.
- **Ölçüm:** `backdrop-filter`/`filter:blur` yalnız overlay, 8–10px; @keyframes/transition içinde blur=0; reduced-transparency fallback mevcut.

#### craft-glass-single-exception-e3 · Glass
- **Direktif:** Cam YALNIZCA E3 overlay (modal/dropdown/toast); kart/panel/hero ASLA cam; viewport'ta ≤3 cam öge; iki paralel glass sistemi tek dile.
- **Ölçüm:** backdrop-filter taşıyan öge/viewport ≤3, yalnız overlay rolünde; kart/panel/hero'da 0; tek glass primitifi.

#### craft-reduced-transparency-fallback · Şeffaflık-azalt fallback [D3]
- **Direktif:** `prefers-reduced-transparency: reduce` YALNIZ blur/glass'ı değil, ışık üreten katmanları da opak/statik fallback'e indirir: (a) E3 cam → opak E3 yüzey; (b) **Karot glow-underlay opacity → 0 (statik, underlay kalkar)**; (c) **foton-flaş → opak/statik son-durum (flaş animasyonu yok, değer yerinde)**. Bilgi kaybı olmadan opaklaşır.
- **Token/değer:** reduce durumunda: `backdrop-filter: none` + opak E3 · Karot underlay `opacity: 0` (statik) · foton-flaş `transition: none` (değer anında, luminans-flaş yok). Bilgi (değer, Karot geometrisi, outcome) korunur.
- **Teknik:** Fallback bilgi taşıyan katmanı SİLMEZ; yalnız şeffaf/animasyonlu ışık katmanını opak/statiğe çevirir. Karot omurga/fitiller görünür kalır (yalnız glow-underlay kapanır); sayı güncellenir (yalnız flaş kapanır).
- **DoD:** reduce'ta cam→opak; Karot glow-underlay opacity 0 (geometri görünür); foton-flaş statik (değer güncel); hiçbir bilgi kaybı yok.
- **Ölçüm:** `prefers-reduced-transparency:reduce` simülasyonunda backdrop-filter=none; Karot underlay computed opacity=0; foton transition=none; Karot/sayı içerik DOM'da mevcut.

### Glow — iki eksen (craft-glow-budget-three-owners)
- **Direktif:** Renkli glow'u yalnız token ailesinden üret; opaklık ≤.14, blur 12–24px; blur ASLA animasyonlanmaz (yalnız opacity). Bull/bear ASLA glow. Her glow §00-18 `data-lifecycle-event` enum'una bağlıdır (CTA-hover tek muaf).
- **Token/değer:**

| Anahtar | Değer |
|---|---|
| `--glow-cta` | `0 8px 24px -12px var(--accent)` |
| glow-opacity-max | `.14` (istisnasız; Karot underlay dâhil) |
| glow-blur-range | `12–24px` (Karot enstrüman-içi statik 2px underlay muaf) |
| glow-owners-hover | yalnız birincil CTA (olay değil; §00-18 muaf) |
| glow-owners-event | CTA + AI-doğum-cyan (`birth`) + kullanıcı-kazanç-amber (`user_win`) + yaşam-döngüsü-geçişleri (`approaching_tp`/`invalidation`), Karot omurga underlay dâhil |

- **Teknik — iki eksen:** (a) **HOVER-glow** = yalnız birincil CTA; kart/ikon/başlık/panel/satır/nav hover'da ASLA glow (§00-18 muaf ama yine dekoratif değil). (b) **OLAY-glow** = §00-18 enum'lu (`birth`/`approaching_tp`/`invalidation`/`user_win`); hover değil, telemetri-olay bağlı. Semantik yön tinti = area-fill (fill-opacity .14), glow değil.
- **DoD/Ölçüm:** ham renkli box-shadow=0 (yalnız token, CI-red); computed glow opaklık ≤.14, blur 12–24px; @keyframes içinde blur/filter animasyonu=0; bull/bear glow=0; olay-glow'da `data-lifecycle-event` attribute mevcut.
- **Migration (v1.1→v1.3):** VL§14 CTA önerisi (α .20-.35 / blur 16-32px) → kanonik α≤.14 / blur 12–24px'e **düşürüldü** (daha kısıtlayıcı kural kazanır, C1; luminans-depth + premium=az ile tutarlı). İndigo glow kaldırıldı.

### Grid
12 kolon · container `max-w 1200` · gutter 24. Breakpoint `sm 640 · md 768 · lg 1024 · xl 1280` — **sm katmanı zorunlu**.

### Button (INT-03 / INT-04) · primitif×state matris [O6]
- **Direktif:** Yalnız birincil CTA glow taşır (`--glow-cta`, hover `--accent-hover`); secondary/ghost/danger ASLA glow. Radius 10; press scale .985 (lg) / .96 (sm); focus 2px `--accent-ui` ring (bkz INT-12). Her buton fiil-net söyler. Primary hover'da ASLA cyan'a dönme, ASLA eski indigo-600. Aşağıdaki 6-durum matrisi eksiksiz uygulanır.
- **Token/değer:**
  - Varyantlar: `primary · secondary · ghost · danger`.
  - **State matrisi (her varyant için):**

  | State | Davranış |
  |---|---|
  | default | bg varyanta göre; primary=`--accent` dolgu, danger=`--bear`-tint |
  | hover | primary bg `--accent → --accent-hover` + `--glow-cta` α artar (blur sabit); non-primary yalnız +1 luminans/hairline `.16`, glow=0 |
  | active | `transform: scale(.985)` (lg) / `.96` (sm); süre `--dur-micro` (140ms) |
  | focus | `outline: 2px solid var(--accent-ui)` (focus-visible), her varyantta |
  | disabled | opacity düşük, `--tx3` metin, pointer-events yok, glow yok |
  | loading | metin→inline boş-Karot mikro-skeleton/spinner-yok; genişlik sabit (layout kaymaz) |

  - radius-button 10px; `--glow-cta` yalnız primary.
- **Teknik:** Primary hover bg `--accent → --accent-hover`; glow α hover'da artar, blur sabit. `:active{transform:scale(.985)}`; reduced-motion'da scale kaldırılır. Focus ring `--accent-ui` (accent-dolgu 1px-UI kısıtından muaf değil → türev kullanılır). Registry: her varyant×state versiyonlu component-registry'ye (C2, §08) kayıtlı.
- **DoD:** 4 varyant × 6 state eksiksiz; yalnız primary glow; non-primary box-shadow=none; radius 10; press scale kodda; focus-visible ring `--accent-ui` her varyantta; loading'de genişlik sabit.
- **Ölçüm:** non-primary computed box-shadow===none; `grep 'hover:bg-accent-secondary|hover:bg-indigo|hover:.*cyan'`(buton)=0; border-radius===10px; focus outline==`--accent-ui`; 24 (4×6) state kombinasyonu registry'de.
- **Migration (v1.1→v1.3):** `--accent-hover #2563EB → #3450C6` (owned); focus-ring `--accent → --accent-ui`; cyan-hover (12 yer) + indigo-600 hover **emekli**; variant sayısı korunur (primary/secondary/ghost/danger).

### Input (INT-05 / INT-06) · primitif×state matris [O6]
- **Direktif:** Input E1 zemin, hairline `.12` border; focus hairline `.22` + 2px `--accent-ui` ring; placeholder `--tx2`; etiket zorunlu. Hata durumu ASLA yalnız renk: bear hairline + alan-altı 12px yardım metni (neden) + ikon üçlüsü. Aşağıdaki 6-durum matrisi eksiksiz uygulanır.
- **Token/değer:**
  - bg `--e1`; radius 10; placeholder `--tx2` (`--tx3` yasak); sayısal input `.num-cell` reçetesine uyar.
  - **State matrisi:**

  | State | Davranış |
  |---|---|
  | default | `border: 1px solid var(--hl12)` |
  | focus | border `--hl22` + `outline: 2px solid var(--accent-ui)` |
  | error | `--bear` hairline (E1 zemin → metin E0/E1 kısıtına uyar) + 12px neden (`--tx2`) + lucide 16px ikon (üç kanal, WCAG 1.4.1) |
  | disabled | opacity düşük, `--tx3` metin/placeholder, etkileşim yok |
  | read-only | statik yüzey, hairline `.10`, imleç text ama düzenlenemez, ring yok |
  | success | kısa `--bull` hairline onayı (olay-bağlı, kalıcı dekor değil) + opsiyonel 16px check ikon |

- **Teknik:** Rest `background:var(--e1); border:1px solid var(--hl12)`. Focus `.12→.22` + `outline:2px solid var(--accent-ui)`. Hata üç kanal (renk+metin+ikon). `--bear` hairline UI/glyph kısıtına uyar (E1'de ≥3). Registry: her state versiyonlu component-registry'ye (C2) kayıtlı.
- **DoD:** 6 state eksiksiz; rest `.12` / focus `.22` + `--accent-ui` ring; placeholder `--tx2`; her input etiketli; her hata üç kanalla, grayscale'de ayırt edilebilir; read-only ve success ayrık.
- **Ölçüm:** computed border rest `.12` / focus `.22`; focus outline==`--accent-ui`; placeholder color==`--tx2`; hata DOM'da bear-border + 12px metin + ikon; 6 state registry'de.
- **Migration (v1.1→v1.3):** Rev-2/M17 form-validation borcu INT-05+INT-06 ile kapanır; `--bear #F4556E → #E14640`; focus-ring `--accent → --accent-ui`.

### Card (craft-card-shadowless-luminance)
- **Direktif:** Her sinyal/veri kartı E1 zemin, radius 12, kabin imzası (craft-cabin-signature: anizotropik hairline + cut-lip + luminans-depth); ASLA box-shadow. Hover tek ısınma (+1 luminans E1→E2, −2px translateY, `--dur-warm` 140ms); ASLA glow. Kapanan kartı közleştir (−2 luminans, kül tonu, sıralamada dibe) — AMA outcome badge tam-kontrast kalır (D2).
- **Token/değer:** `--e1`; radius-card 12px; kabin imzası (dikey `--accent-ui`-tint / yatay `.06` / `--cut-lip`); hover +1 lum / translateY(−2px) / `--dur-warm` (140ms) ease-out; közleşme −2 lum (kül `--tx3` ailesi).
- **Teknik:** `box-shadow:var(--cut-lip)` (yalnız inset üst-kenar). Türevler `StatTile`, `SignalCard`. Kart içeriği feed'le değişmez (fiyat↔TP/SL swap yasak). **SignalCard iki render-modu:** (a) kart-modu = yüzey-ısınma translateY(−2px); (b) tablo-satırı modu = satır-ısınma transform 0 (INT-01). Közleşme = **kalıcı durum** (motion olayı değil, §01 micro-közleşme); outcome badge D2 kuralıyla sönmez.
- **DoD:** 0 drop-shadow (yalnız cut-lip inset); hover glow yok; kapanan kart kararır+dibe çöker, silinmez; outcome badge közleşmede tam-kontrast.
- **Ölçüm:** Card/SignalCard/StatTile'da inset-dışı/renkli box-shadow=0; hover translateY===−2px (kart) / 0 (satır); kapanan kart sort index=son; közleşen kartta outcome badge computed kontrast ≥ eşik.

### micro-közleşme · Közleşme (kapanan sinyal — dürüstlük fiziği) [D2]
- **Direktif:** Kapanan sinyal kartı −2 lümen basamağı iner (kararır), kül tonunda listede kalır, sıralamada dibe çöker — kayıp saklanmaz/silinmez. Dürüstlük hem renkte (kararma) hem konumda (çökelme). **AMA outcome badge (sonuç rozeti) TAM-KONTRAST kalır** (TP KAZANDI=`--bull`, STOP OLDU=`--bear`, okunur) — geçmiş sonuç asla sönmez. Kalıcı durum (motion olayı değil).
- **Token/değer:** közleşme = −2 lümen (luminans-only, gölgesiz); kart gövde kül tonu (`--tx3` ailesi, yön-rengi söner); **outcome badge muaf: tam-kontrast** (`--bull`/`--bear` semantiği + `--tx`/okunur metin); sıralama dibe; geçiş ≤`--dur-settle` (520ms) tek atım, sonra statik.
- **Teknik:** Kapanış lifecycle'ı Karot omurgasına DOKUNMAZ, durum katmanında yaşar (§05). Kart gövdesi (fiyat/etiket/omurga-tinti) küle döner; yalnız outcome badge kontrastı korur → kullanıcı sonucu (kazandı/kaybetti) her zaman net okur. Kayıp Sicil'de (kümülatif isabet/PF/drawdown) kalır. G-00-11 ile hizalı.
- **DoD:** Kapanış öncesi/sonrası gövde luminans −2 basamak; kapalı sinyal DOM'da (silinmez, en altta); yön-tinti gövdede nötrleşir; **outcome badge tam-kontrast okunur kalır**.
- **Ölçüm:** kapanış öncesi/sonrası gövde luminans −2 basamak; kapalı sinyal DOM'da en altta; gövde yön-tinti computed==kül tonu; outcome badge computed kontrast ≥4.5:1 (okunur, sönmemiş).

### Badge · 4-semantik × statik/etkileşim matris [O6]
- **Direktif:** Tek `<Badge>` primitifi, variant'la; 4 semantik durum × iki etkileşim-modu (statik / etkileşimli-hover) matrisiyle. Argo yok; renk semantik-veri kuralına tabidir; bull/bear glow taşımaz.
- **Token/değer:**
  - Variantlar: `bull · bear · outcome (TP KAZANDI / STOP OLDU / BAŞABAŞ / SÜRESİ DOLDU) · warn · neutral · accent (PRO)`.
  - **4-semantik × statik/etkileşim:** her semantik (bull/bear/warn/neutral) hem statik (salt-gösterim, hover yok) hem etkileşimli (tıklanır/filtreleyen — hover'da +1 luminans/hairline `.16`, glow=0) render'a sahiptir.
  - outcome badge = D2 gereği közleşmede bile tam-kontrast.
- **Teknik:** 10+ ad-hoc badge tek primitife birleşir. Etkileşimli badge hover'da glow ALMAZ (yalnız luminans/hairline). Renk asla tek-kanal değil (metin/işaret eşlik eder). Registry: variant×mod versiyonlu registry'ye (C2) kayıtlı.
- **DoD:** Tek Badge primitifi; 4 semantik × {statik, etkileşim}; etkileşimli-hover glow=0; outcome tam-kontrast; ad-hoc badge=0.
- **Ölçüm:** ad-hoc badge komponenti grep=0; etkileşimli badge computed hover box-shadow=none; outcome badge kontrast ≥4.5:1; variant×mod registry'de.

### Toast (INT-09) · states [O6]
- **Direktif:** Tek Toast primitifi: üstten düşen E3 kesit. Başarı = tek atım amber (`user_win` glow); hata = lümen düşüşü + neden; bilgi = nötr. Tüm `window.alert()` (24 yer) kaldırılır; fiil-net copy.
- **Token/değer:** yüzey `--e3`; giriş üstten düşüş (haber yönü), süre `--dur-overlay` (360ms); **states:** `success` (`--amber` tek atım, `data-lifecycle-event="user_win"`) · `error` (lümen düşüşü + neden `--tx2`) · `info` (nötr, luminans-only) · `dismiss` (yukarı çıkış + fade); z-toast 60.
- **DoD/Ölçüm:** `grep 'alert('`=0; z-index===60; başarı amber tek atım; hata neden metni DOM'da; 4 state (success/error/info/dismiss) ayrık.
- **Migration (v1.1→v1.3):** Rev-2/M15 borcuna yön/yüzey/başarı-hata ayrımı eklendi; `--warn → --amber`.

### Modal (INT-10) · states [O6]
- **Direktif:** Tek `<Modal>`: cam (backdrop-blur) yalnız burada tek istisna; backdrop −1 luminans + focus-trap + ESC + açılış `--dur-overlay` (360ms) merkezde doğar. Tüm `window.confirm()` (10 yer) kaldırılır; kritik eylem kendi Modal'ımızla (ad + sonuç + geri-alınabilirlik).
- **Token/değer:** yüzey `--e3` + backdrop-blur 8–10px; backdrop −1 luminans; **states:** `open` (merkez doğuş, `--dur-overlay`) · `close` (fade + shrink, `--dur-overlay`) · `backdrop-fade` (`--dur-photon`/150ms) · reduced-transparency → opak E3 (D3); z-modal 50.
- **DoD/Ölçüm:** `grep 'confirm('`=0 + el-yapımı fixed inset-0 modal=0; role='dialog' + focus-trap; ESC kapatır; z-index===50; open/close/backdrop states ayrık; reduce'ta opak.
- **Migration (v1.1→v1.3):** Rev-2/M12 stacking ile hizalı (z-50); ad-hoc z (50/60/100/110) tekilleşir.

### Dropdown (INT-07)
14 native `<select>` tamamı TEK `<Dropdown>` primitifine göç eder: E3 cam panel + backdrop-blur 8–10px + hairline; açılış `--dur-overlay` (360ms); klavye gezinme (ok) + ESC + focus yönetimi; z-dropdown 40. Native select bırakılmaz (`grep '<select'`=0).

### Table
Semantik `<table>` (div-grid değil). `md` altında satır → **kart**'a dönüşür. Tablo-satırı hover: yalnız +1 lümen, transform 0 (satır zıplamaz). ~~Karot 16px silüet ölçeğinde satır içinde render (§05).~~ *(SUPERSEDED v1.7 · CP-KAROT-UI1 — satır-içi Karot kaldırılıyor; satır dili = bar / sayı / badge / metin hiyerarşisi.)* Sayısal hücreler `.num-cell` reçetesine uyar (sağ-hiza, ondalık-slot, tabular). *(Mobil-kart deseni P1.5'te yazılır.)*

### Chart Tokens (karot-12)
- **Direktif:** Grafikleri dürüstlük kurallarıyla render et: yaşayan seviye çizgileri (TP/SL telemetriyle canlanır), ışık-maskeli grid, tabular eksen etiketi, KIRPILMAMIŞ baseline (Lie Factor=1), grid hairline, mum bull-teal/bear. Kırpılmış eksen ebedî YASAK. Yaşayan seviye canlanması §00-18 lifecycle-event enum'una (`approaching_tp`/`invalidation`) bağlıdır.
- **Token/değer:** mum bull `--bull` / bear `--bear`; seviye TP `--bull` · Giriş `--accent` · SL `--bear`; sinyal işareti `--amber`; grid hairline `--hl10`; eksen etiketi `--tx2` + mono + tabular; ışık sırası grid<eksen<seri<aktif-seviye; baseline kırpılmamış. (Giriş seviye çizgisi `--accent` dolgu-değil-1px ise `--accent-ui` kullanılır — accent 1px-UI kısıtı.)
- **Teknik:** Seviye çizgileri telemetriyle "yaşar" (TP/SL yaklaştıkça parlaklık artar, `data-lifecycle-event` taşır). Eksen etiketi ≥`--tx2` (`--tx3` yasak). Grid ışık-maskeli, eksenden sönük (`.10`). TradingView embed'in tam tema eşlemesi kapsam dışı (Rev-2/M16); embed'in yalnız zemin rengi E0'a tabi.
- **DoD:** Tek chart token setinden; kırpılmış baseline yok; seviye telemetriyle canlanır; eksen ≥`--tx2`; mum owned tokena migrate; Giriş 1px-çizgi `--accent-ui`.
- **Ölçüm:** baseline min=0 / dürüst-min lint; `grep` kırpılmış-eksen=0; mum hex literal (#10B981|#F4556E)=0; seviye telemetri-canlanması doğrulanır (`data-lifecycle-event` mevcut).
- **Migration (v1.1→v1.3):** Turuncu `#f97316` → chart token (dashboard/page.tsx · charts/TradingChart.tsx — 2 konum, warn'a eşitlenmez); mum `#10B981/#F4556E → --bull/--bear`; sinyal işareti `--warn → --amber`; Giriş-çizgisi `--accent → --accent-ui` (1px iz kısıtı).

### State Sistemi — Loading / Empty / Error

#### micro-loading-boş-karot · Loading = boş-Karot skeleton
- **Direktif:** Spinner tamamen kaldır (30 kopya emekli, tam-sayfa ilk-yük istisnası); sinyal loading = Karot'un kendisi; skeleton = boş-Karot (9 fitil yatay-nötr, motor rapor verdikçe açısına döner). Durum etiketleri GERÇEK pipeline adımları; sahte progress/gecikme yasak; cyan-tarama YOK. <300ms işte jenerik skeleton gösterilmez (grace-window).
- **Token/değer:** grace-window <300ms (jenerik); skeleton = boş-Karot (omurga x=SPINE_X, 9 eşit-aralık slot fitili yatay-nötr); fitil-dönüş stagger 50ms; süre `--dur-state` (180ms); "durum-etiketli shimmer" YASAK.
- **Teknik:** Sinyal-Karot skeleton (boş-Karot = üretim başladı) grace'ten MUAF, her zaman gösterilir. Etiketler backend pipeline adımlarına bağlı; sahte yüzde/gecikme üretilemez.
- **DoD:** İnline spinner yok (tam-sayfa hariç); <300ms jenerik işte skeleton yanmaz; sinyal loading boş-Karot; sahte progress yok.
- **Ölçüm:** inline spinner import=0 (tam-sayfa hariç); 250ms yapay işte skeleton render edilmez; skeleton Karot render fonksiyonunu kullanır; `shimmer`/fake-progress class=0.
- **Migration (v1.1→v1.3):** v1.1 "skeleton (spinner değil)" → boş-Karot skeleton; "durum-etiketli shimmer" KALDIRILDI (shimmer yasağı).

#### micro-empty-olay-defteri · Empty = Olay Defteri
- **Direktif:** Boş durum ölü ekran değil kalıcı kayıt: "sen yokken: 3 doğum, 2 kapanış" — kaçırılan olayların toplanma yeri. Sevimli illüstrasyon/emoji yasak. Sakin metin + tek CTA + kart-sınırlı noise (app'teki TEK app-noise istisnası).
- **Token/değer:** kart-sınırlı noise L2 (128px feTurbulence, α .02–.06) + gerekirse L3 grid, YALNIZ empty-state kart sınırında; veri gelince kalkar. Zemin `--e1`; hairline `.12`; tek CTA (accent-dolgu); illüstrasyon/emoji=0.
- **DoD:** Tüm boş yüzeyler tek EmptyState primitifinden; çıplak-metin empty=0; içerik kaçırılan olayları listeler; noise yalnız kart sınırında.
- **Ölçüm:** EmptyState kapsamı = tüm boş yüzeyler (çıplak-metin=0); emoji/illüstrasyon=0; noise-layer yalnız empty-kart içinde.

#### micro-error-state · Error (dürüst eksik veri)
- **Direktif:** Hata ASLA "0" görünmez; daima "—" + neden + tekrar-dene. Sıfır yanıltır; eksik veri dürüstçe. Error primitifi tek kaynak.
- **Token/değer:** eksik-veri işareti `—` (em-dash, tabular hizada, `0` yerine); neden `--tx2`; tekrar-dene tek CTA/ghost; renk yön taşımaz (nötr); sayısal alan `.num-cell` (tabular hiza).
- **DoD:** Veri yokken hiçbir alanda 0 yok; "—"+neden+tekrar-dene tek primitiften; "—" tabular hizayı korur.
- **Ölçüm:** veri-yok senaryosunda literal `0`=yok, `—`=var; Error primitifi tek kaynak; "—" komşu sayılarla hizalı (ondalık-slot).
- **Migration (v1.1→v1.3):** v1.1 "backend hatası asla 0/%0" ilkesi → `micro-error-state` primitifi (15+ çıplak sayfa tek kaynağa bağlanır).

### Global / Base primitifler

#### micro-cyan-yoğunluk-bütçesi · Cyan-iz yoğunluk bütçesi [O4]
- **Direktif:** Cyan (`--cyan`) YALNIZCA AI-türevi VE aşikâr-olmayan değerde kullanılır (konsensus / güven / yaşam-döngüsü); ham fiyat/hacim/piyasa-verisi cyan ALMAZ (bunlar nötr/tabular). Viewport başına cyan-iz bütçesi ≤ (aktif Karot omurgası + 1 açık provenance izi).
- **Token/değer:** cyan-izin izinli anlamları: konsensus-omurga · güven-türevi · yaşam-döngüsü-izi · provenance-hattı. Yasak: ham fiyat/hacim/OHLC/market-cap cyan. Bütçe: viewport'ta cyan-iz ≤ 1 aktif-Karot + 1 açık-provenance.
- **Teknik:** Cyan = AI-sınırının görünür işareti (COL-04..08 cyan-tekeli); ham piyasa verisi AI-türevi olmadığından cyan alamaz → cyan enflasyonu (her yerde cyan) kimliği ucuzlatır. Bütçe squint testiyle çapraz (§00-08).
- **DoD:** Cyan yalnız AI-türevi/aşikâr-olmayan değerde; ham fiyat/hacim cyan=0; viewport cyan-iz ≤ (aktif Karot + 1 provenance).
- **Ölçüm:** ham fiyat/hacim selektörlerinde `--cyan` grep=0; viewport'ta cyan-taşıyan öge sayısı ≤ 1 Karot + 1 provenance; cyan kullanım-anlamı AI-türevi listesinde.

#### micro-selection-tint · `::selection` accent-tint
- **Direktif:** Global tek `::selection` + `::-moz-selection`; seçim vurgusu owned-accent tint; tarayıcı-mavisi default asla yürürlükte. Metin kontrastı korunur.
- **Token/değer:** `--selection-bg: color-mix(in oklab, var(--accent) 22%, transparent)` (accent-dolgu tint, seçim bir dolgu-yüzeyidir); `--selection-fg: var(--tx)` (`--ac-tx`). Cyan/bull/bear ASLA seçim rengi (nötr accent).
- **Ölçüm:** global CSS'te tam 1 `::selection`; 5 yüzeyde computed bg==`--selection-bg`; seçili metin `--tx`-on-seçim ≥4.5:1.

#### micro-cursor-crosshair · Karot-eksenli crosshair
- **Direktif:** Grafik/chart yüzeyinde imleç = Karot dikey-eksenine hizalı price-crosshair (yatay+dikey ince kılavuz + eksen fiyat/zaman okuması); YALNIZ chart yüzeyinde; genel UI'da standart pointer/text — dekoratif custom cursor yasak.
- **Token/değer:** crosshair çizgi `--hl12`; aktif eksen okuması `--cyan` veya nötr `--tx3`; genişlik 1px; kapsam = chart bileşeni sınırları.
- **Teknik:** Kontrollü overlay (native `cursor:crosshair` değil); dikey çizgi Karot omurga dili (x=SPINE_X mantığı; chart'ta son-fiyat hizası). transform/opacity ile takip, layout yok; grafik dışına çıkınca kaybolur.
- **Ölçüm:** crosshair yalnız chart bileşeninde; chart-dışı custom cursor=0; takip 60fps (transform-only). *(Tam eksen-okuma spec'i FJ#2/§05 ile olgunlaşır — açık uç.)*

#### micro-tooltip-genel-dil · Genel tooltip (provenance-hover dışı)
- **Direktif:** Provenance-hover dışı tüm buton/ikon/kısayol açıklamaları tek Tooltip primitifinden; native `title=` göçürülür. Tooltip = "şerh": E3 kesit, tek gölge token, hairline `.12`. (typo-num-cell truncation tam-değer tooltip'i de bu primitiften.)
- **Token/değer:** zemin `--e3`; hairline `--hl12`; radius-control 8px; gölge `--shadow-e3`; punto 13px; giriş `--dur-state` (180ms), transform+opacity; backdrop 8–10px (E3 ise).
- **Teknik:** Klavye focus'ta da açılır (a11y). Provenance-hover AYRI mekanizmadır (AI değeri kaynağı); genel tooltip onunla karışmaz.
- **Ölçüm:** `grep 'title='`(interaktif)=0; Tooltip tek kaynak; zemin==E3 & border==`--hl12`; klavye-focus'ta açılır. *(Delay-in + gölge-token Toast/Modal E3 ile ortak kilitli.)*

#### micro-foton-tıklaması · Foton flaşı (sayı güncelleme fiziği)
- **Direktif:** Sayı güncellenince `--dur-photon` (150ms) +1 lümen flaşı; konum/scale ASLA oynamaz (yalnız parlaklık). Press scale .96 (sm) / .985 (lg). Bayat canlı veri basamaklı söner (yaş damgası); yaş>eşik → statik. Aynı satırda ≥2 canlı sayı foton'ları senkronize edilmez. reduced-transparency'de foton statik (D3).
- **Token/değer:** foton `--dur-photon` (150ms) +1 lümen (opacity/luminans, transform+opacity); press scale .96/.985 (süre `--dur-micro`/140ms); follow-through `--dur-warm` (140ms); easing `--ease-signal`. Yaş eşiği X = açık uç (veri-gated).
- **Teknik:** Sayı DOM'da yerinde kalır (`.num-cell` slotu sabit); layout/scale sabit. Her sayı kendi telemetri olayında tetiklenir (yapay canlılık dalgası yok). reduce → transition:none, değer anında (D3).
- **Ölçüm:** güncelleme öncesi/sonrası bounding-box identik (px farkı=0); flaş ~150ms; press scale .96/.985; aynı-satır iki flaş zaman-damgası farklı; reduce'ta transition=none.

---

*(§00–01 KANONİK — v1.3. Süre tokenları tek-rejim: `--dur-micro 140 · --dur-state 180 · --dur-photon 150 · --dur-warm 140 · --dur-settle 520 · --dur-route 180 · --dur-overlay 360` + stagger 50ms; app sert-tavan 600ms (overlay aşmaz); transition-duration bu token seti dışı = lint-red. **Süre netleştirme:** 7 semantik token = 5 ayrık değer `{140,150,180,360,520}`ms (`--dur-route`=`--dur-state`=180 · `--dur-warm`=`--dur-micro`=140 bilinçli ortak-değer/alias; `--dur-photon` 150 foton-flaşı + overlay backdrop-fade paylaşır). Glow blur 12–24px statik görsel parametredir (motion-süresi DEĞİL) → "aralık yok" kuralı kapsamı dışındadır. Renk kilidi AÇIK: 20-hücre WebAIM tablosu doldu, DoD-5 geçti. **v1.5 eki (K-J, 2026-07-12):** +`--dur-flash 300` → 8 semantik token = 6 ayrık değer `{140,150,180,300,360,520}`ms; foton istisnası dar-tanımlı `background-color` tint'ini de kapsar (yalnız olay-bağlı/geçici/coalesced — VL §Ölçüm); geçici bull/bear-tint yalnız mevcut `/10–/15` alfa-ailesinden (COL-11 hex kilidi açılmadı; "bull/bear asla glow/atmosfer" değişmedi — bu alan-içi tint'tir); T3 landing-reveal sekans-toplamı ≤1.2s carve-out'u landing-mühürlüdür, app 600ms sert-tavanı değişmez.)*



## 01-K · Kompozisyon & Sahneleme Katmanı · *(v1.6 CP-PV1-A)*

> **Statü:** doc-only karar kilidi. Primitif-uygulama = **PV1-B** (ayrı onay); ekran-recompose = **CP-SIGNAL / CP-DASH** (ayrı onaylar). **CP-PV1 yeni tasarım İCADI DEĞİLDİR:** token/yasak/motion/primitif-craft (§01/§06) kilitli ve uygulanmış; bu katman o parçaların **ekranda nasıl sahneleneceğini** kilitler.
> **Teşhis (kanıtlı):** template hissi primitiflerden değil şuradan gelir — (a) **tek-kap-tipi tiranlığı** (her içerik aynı GlassCard'da), (b) eşit-ağırlık iskeleti (v1.5 CP-PIA kırdı), (c) **ölçek cesareti yokluğu** (kahraman-rakam=0; Karot ≤32px), (d) veri-kuyusu dilinin yokluğu, (e) makbuz-gramerinin tek-biçim olmaması.

### craft-kap-hiyerarşisi · Üç yüzey sınıfı: chrome / panel / well (bench doctrine)
- **Direktif:** "Kap, yalnız veri taşıyan şeyde." Üç yüzey sınıfı: **chrome** (kapsız — hairline-ayrım + boşluk; başlık/filtre/metin-modül), **panel** (E1 kap = bugünkü GlassCard; yalnız gruplanmış veri), **well** (enstrüman-kuyusu, craft-veri-kuyusu). Sayfa silüeti kutu-grid'den TEZGÂHA döner: bir viewport'ta kap-sayısı düşer, ayrım hairline+boşlukla taşınır.
- **Token/değer:** Surface varyantları `chrome | panel | well`; panel = mevcut GlassCard davranışı (default, byte-identical).
- **Teknik:** GlassCard tek-kap tiranlığı **additive varyant API'siyle** kırılır — mevcut kullanım BOZULMAZ (default=panel aynı kalır; ekranlar opt-in göçer, recompose CP'lerinde). Chrome yüzeyde border/bg yok; ayrım `hl10/hl12` yatay-kural + spacing.
- **DoD:** Aynı viewport'ta >3 eşdeğer-ağırlık panel = red (v1.5 dash-ia-guardrail-4 ile hizalı); chrome-içerik kapa alınmışsa gerekçe şart.
- **Ölçüm:** ekran-başına panel sayısı (hedef: dashboard ≤4, signal-center ≤3 panel + 1 well-tablo + 1 dock); squint'te silüet "tezgâh" okur (kutu-grid=fail).

### craft-veri-kuyusu · Enstrüman-kuyusu (instrument well)
- **Direktif:** Chart / tablo / Karot-sahnesi kapları içeriğinden BİR BASAMAK KARANLIK oturur: E1-panel içinde **E0-inset kuyu**. "Derinlik = kabın içine bakmak" — Bloomberg-dürüstlüğünün kopyasız çevirisi. Veri, kuyudaki tek parlak ögedir.
- **Token/değer:** kuyu bg = `--e0`; iç-hairline `inset 0 0 0 1px var(--hl10)`; kuyu-içi grid ≤ hl10 (tek özel değer, YALNIZ well içinde); kuyu radius = `--radius-card`.
- **Teknik:** Bu iki kullanım (iç-hairline + kuyu-grid) §01 glow/hairline bütçesine eklenen YEGÂNE yeni sanktioned kullanımdır; başka yeni glow/blur/gölge/gradient bütçesi AÇILMAZ. TradingView/recharts temaları kuyu-içinde owned-palete tam eşlenir (uygulama CP-DASH/markets).
- **DoD:** Enstrüman (chart/canlı-tablo/Karot-sahnesi) çıplak panel-yüzeyinde durmaz — kuyu içinde; kuyu içinde dekoratif öge=0.
- **Ölçüm:** 6-önerme: "Derinlik=Kanıt"; kuyu-dışı inset-hairline kullanımı=0; kuyu-içi en yüksek luminans = veri (grid/chrome değil).

### craft-kahraman-rakam · Ekran başına 1 kahraman-rakam
- **Direktif:** Her ana ekranın TEK kahraman-rakam hakkı vardır (40–56px, `tabular-nums`, owned-numeral): Dashboard-Sicil = **Dönem Net Getiri** · Signal-Center-Dock = **konsensus-skoru**. Altında zorunlu makbuz-satırı (craft-makbuz-grameri). G-00-02 kimlik-taşıyıcı üçlüsünün (Karot · provenance · kahraman-rakam) üçüncüsü İLK KEZ sahnelenir.
- **Token/değer:** boyut 40–56px; ekran-başına adet = 1; vurgu-bütçesine (≤2) DAHİL; **count-up ASLA** (§06 yasağı — dürüstlük: sayı olduğu değerde doğar).
- **DoD/Ölçüm:** ana ekranda kahraman-rakam sayısı == 1; makbuzsuz kahraman-rakam = fail; count-up/odometer pattern = fail.

### craft-makbuz-grameri · Provenance tek-biçimi
- **Direktif:** Her AI/istatistik iddiasının makbuzu TEK gramerle yazılır: `n=142 · 30g · v1` (orta-nokta ayraç · `--tx2` · mono-numeral · 11-12px). Kullanım yerleri: kahraman-rakam altı · tooltip gövdesi · AI-cümle ucu · Sicil başlıkları. Ölçüm-kültürünün görsel imzası — "fark efektte değil dürüstlük duruşunda"nın mikro-tipografisi.
- **Token/değer:** ayraç `·` · renk `--tx2` · numeral mono/tabular · sıra: örneklem → dönem → era/sürüm.
- **Teknik:** Tooltip gövdesi makbuz-formuna döner (başlıksız, tek satır + kaynak); provenance-hover (AT-2) içerik-sözleşmesi değişmez, yalnız görsel gramer tekleşir.
- **DoD/Ölçüm:** makbuz-taşıyan yüzeylerde serbest-biçim provenance metni = 0; gramer-dışı ayraç/sıra = fail.

### craft-sessiz-buton · Buton nadirdir
- **Direktif:** Ürün istihbarat-ürünüdür; buton NADİR ve KESİNDİR. Görünür-primary (dolgu+glow) **sayfa başına ≤1** (mevcut tek-CTA-glow bütçesiyle hizalı). Veri-satırı İÇİNDE buton YASAK — satır-içi eylem link/ghost/metin-hairline'dır. İkincil eylemler metin+hairline.
- **Token/değer:** primary/sayfa ≤1; satır-içi `<Button variant="primary|secondary">` = 0.
- **DoD/Ölçüm:** sayfa-tarama: primary-buton sayısı ≤1; SignalTable/veri-satırı içinde buton-elementi = 0.

### craft-referans-politikası · Referans görseller = prensip + negatif-katalog (kopya değil)
- **Direktif:** Dış referanslar (site/video/galeri) BİREBİR KOPYALANMAZ; yalnız iki kullanım meşrudur: (1) **prensip-çıkarımı** — tek-kahraman-nesne sahnesi · eyebrow→display→paragraf→tek-CTA grameri · sahne-değişimli pacing ("az ama kesin") · cesur karanlık-boşluk; (2) **negatif-katalog** — template-galeri estetiği (3D-maskot, aurora-bg, neon-kart, dev-gradient-tipo, "Copy full prompt" yakınsaması) yabancı-kör testin (G-00-04) başarısızlık örnekleridir; bu desenlere yakınsayan karar reddedilir.
- **Teknik:** three.js/3D-model/kamera-orbit/scroll-scrub yolu zaten kalıcı-kapalı (§02 hero-sahte-sinematik-yasak). Prensip-çıkarımı her zaman Bible token/kural diline yeniden-ifade edilir; dış çıktı (kod/asset) repo'ya girmez.
- **DoD/Ölçüm:** G-00-04 çeyreklik yabancı-kör line-up tek kapı; "referansta böyleydi" tek başına gerekçe DEĞİLDİR (6-önerme şartı aynen).

---

## 02 · Hero

İlk 10 saniyede tek his: **ürünün AI'sini canlı hissettirmek.** Yaşayan AI sistemi (tanıtım filmi değil); tüm görsel ögeler gerçek sinyal verisinden türer. Hero YAŞAR — sahte sinema tamamen yasak; her motion bilgi taşır, her ışık gerçek bir olayı temsil eder.

### hero-app-içi-sınır · App-içi hero = yalnız Dashboard Nabız bandı · *(v1.5 CP-PIA)*
- **Direktif:** §02 yaşayan-Hero **landing'in** işidir. App içinde ayrı bir pazarlama-hero'su YOKTUR; yaşayan-Hero'nun app-içi tek meşru formu Dashboard üst **Nabız bandı**'dır (bkz. §03 dash-nabız-bandı). Sinematik/scroll-tetikli hero-motion yalnız landing'de değerlendirilir; app'te scroll-jacking/parallax/scroll-scrub yasağı (hero-scroll-canlı-muhakeme + §06) istisnasız geçerlidir.
- **Token/değer:** app-içi hero formu = Nabız bandı (≤~120px, canlı); app pazarlama-hero = 0; sinematik-scroll = yalnız landing.
- **DoD/Ölçüm:** app rotalarında ≥240px statik pazarlama-hero bloğu = fail; app'te scroll-tetikli hero-koreografi = 0; landing-hero bu maddeden muaf (kendi §02 kuralları).

### hero-yaşayan-sistem · Hero = yaşayan AI sistemi (film değil)
- **Direktif:** Landing açılışı tanıtım filmi/sinematik değil, gerçek-zamanlı gerçek-veriyle beslenen yaşayan AI sistemi; amaç "wow" değil ilk 10 sn'de AI'yı hissettirmek. Önceden-pişmiş beat/sahne YOK.
- **Token/değer:** hedef ilk 10 sn AI algısı; içerik kaynağı = canlı backend telemetrisi (`SignalSnapshot` / lifecycle-event).
- **Teknik:** Statik pazarlama/video yerine dashboard'un canlı hali (konsensus yüzeyi). Tüm ögeler (Karot omurgaları, doğum, bölünme, fikir-değiştirme) gerçek veriden; scripted timeline/mock yasak. Hero = aynı Karot DNA'sının landing'deki yüksek-yoğunluk örneği. Her hareketli/ışıklı öge gerçek bir olaya bağlıdır — dekoratif değil.
- **DoD:** Her hareketli/ışıklı öge bir telemetri alanına bağlı; scripted/hardcoded açılış yok; hero dashboard ile aynı Karot primitifi.
- **Ölçüm:** hero'da sabit/mock veri=fail; her animasyon-tetik telemetri alanına iz sürülebilir; ilk-boyama sonrası 10 sn içinde ≥1 canlı olay (doğum/settle).

### hero-gerçek-olay-havuzu · Yaşayan Hero'nun garanti mekaniği (merkezi çözüm K3)
- **Direktif:** Hero, canlı telemetriden beslenen **kayan pencereden** çeker: son N GERÇEK olay (doğum / bölünme / fikir-değiştirme) bir havuzda tutulur; hero bu havuzdan seçim yapar. Olaylar gerçektir, yalnızca zaman-kaydırmalıdır. Böylece "daima ≥1 üç-hal temsili + 10 sn'de ≥1 olay" garantisi sahte veri üretmeden FİZİKSEL olarak sağlanır.
- **Token/değer:** kayan pencere = son N gerçek olay havuzu · her öge → bir `SignalSnapshot`/lifecycle-event referansı (mock=0) · soğuk-başlangıç fallback = son-24s arşiv, "canlı değil · arşiv" etiketiyle.
- **Teknik — üç kural:**
  1. **Referans zorunlu:** Havuzdaki her öge gerçek bir `SignalSnapshot`/lifecycle-event'e referanslıdır; hero'da mock/sentetik olay sayısı = 0.
  2. **Canlı superseder:** Canlı olay geldiğinde havuzu SUPERSEDER (gerçek-zaman önceliklidir; kayan pencere yalnızca boşluğu doldurur).
  3. **Dürüst soğuk-başlangıç:** Düşük-hacim/soğuk-başlangıçta hero son-24s arşivine düşer ve durumu "canlı değil · arşiv" etiketiyle DÜRÜSTÇE bildirir (sahte canlılık üretmez).
- **Tanım (kalıcı):** "Gerçek-olay havuzundan seçim script DEĞİLDİR; sentetik/uydurma veriyle beslemek script'tir." Bu ayrım hero'nun yaşayanlığını sahte-sinemadan ayıran kanonik sınırdır.
- **DoD:** Hero'daki her öge bir gerçek olay kaydına iz sürülebilir; canlı olay geldiğinde havuz-ögesi geri çekilir; soğuk-başlangıçta arşiv etiketi görünür; ilk viewport'ta üç dürüst hal (≥1 bölünmüş + ≥1 doğum + ≥1 fikir-değiştiren) daima temsil edilir.
- **Ölçüm:** hero ögelerinde snapshot-referansı %100 (referanssız öge=fail); canlı-olay enjekte edildiğinde ≤N-window içinde eski öge yerini bırakır; soğuk-başlangıç senaryosunda "arşiv" etiketi DOM'da; squint-testi (hero-squint-testi-dod) korunur.

### hero-canlı-konsensüs-masası · Açılış içeriği
- **Direktif:** Hero açılışı "canlı konsensüs masası": çok sayıda Karot aynı anda okunur; biri gözünün önünde doğar (settle), biri bölünmüş kalır (AI karar veremedi), biri dün fikir değiştirdi. Bu üç dürüst durum açılışta daima temsil edilir (garanti mekaniği hero-gerçek-olay-havuzu ile sağlanır).
- **Token/değer:** ilk ekran = 40 Karot eş-zamanlı (30–40 bandı); daima ≥1 bölünmüş + ≥1 doğum + ≥1 fikir-değiştiren.
- **Teknik:** Dashboard 40-Karot yoğunluk kanıtıyla (§03) aynı açılış mekaniğini paylaşır; **paylaşılan = Karot render fonksiyonu + veri-mekaniği, motion bütçesi DEĞİL.** Landing-hero (canlı settle + glow-drift) ile app-dashboard (idle-sessiz) AYRI motion bütçelidir.
- **DoD:** İlk viewport'ta 40 okunabilir Karot; her açılışta ≥1 bölünmüş+doğan+fikir-değiştiren; hepsi aynı render fonksiyonundan.
- **Ölçüm:** ilk ekranda ≥40 Karot fitil-yapısı DOM'da; açılış state'inde split≥1, birth≥1, changed≥1.

### hero-copy-cta · Açılış kopya + tek CTA
- **Direktif:** Hero üst cümlesi *"9 motor. Tek yargı. Gizli değil."*; altında dürüstlük satırı; tek birincil CTA *"Kendi sinyalini izle"* (siteye değil, deneyime davet). İkinci parlak/rakip CTA yok.
- **Token/değer:** üst cümle `9 motor. Tek yargı. Gizli değil.` (birebir); CTA `Kendi sinyalini izle`; birincil CTA sayısı = 1 (glow sahibi); CTA dolgu `--accent`, hover `--accent-hover`, metin `--ac-tx`.
- **Teknik:** Yalnız bir birincil (glow sahibi) CTA. Kopya şiirsel iç-dil (Karot/közleşme/omurga) içermez; sade Türkçe. "Yatırım tavsiyesi değildir" görünürlüğü korunur.
- **DoD:** Hero'da 1 birincil CTA (glowlu) + üst cümle + dürüstlük satırı; ikinci glowlu CTA yok; kopyada iç-dil terimi yok.
- **Ölçüm:** hero içinde glow-CTA==1; üst cümle+CTA birebir; iç-dil sözlük taraması (Karot/közleşme/omurga/su-hattı)=0.
- **Migration (v1.1→v1.3):** v1.1 iki-CTA ("Ücretsiz Başla" + "Canlı sinyalleri gör") → tek birincil "Kendi sinyalini izle"; başlık → "9 motor. Tek yargı. Gizli değil."

### hero-scroll-canlı-muhakeme · Scroll = canlı AI muhakemesi, scrubber DEĞİL
- **Direktif:** Scroll ilerledikçe kanıt AÇILIR (AI düşünür → motorlar uzlaşır → konsensus → karar doğar); ancak scroll video-scrubber gibi kullanılamaz — geri alınca muhakeme geri SARILMAZ, olaylar birer kez olur.
- **Token/değer:** scroll-progress → canlı telemetriye bağlı; scrub geri-sarma YOK; scroll efektleri yalnız transform/opacity.
- **Teknik:** Scroll-progress yalnız kanıt katmanlarının görünürlüğünü/derinliğini açar (transform/opacity); zaman-eksenini ileri-geri sürmez. Doğum/settle telemetri geldiğinde bir kez, geri sarılmaz. Scroll yön/hız asla ele geçirilmez (scroll-jacking/wheel-intercept/zorunlu-snap/Lenis yasak, §06).
- **DoD:** Yukarı scroll doğmuş Karot'u geri bölmez (idempotent, tek-yön); scroll efektleri transform/opacity; scroll-jacking yok.
- **Ölçüm:** manuel: yukarı scroll doğmuş sinyali geri sarmaz; scroll handler yalnız opacity/transform yazar, `scrollTop`/`wheel-preventDefault`=fail.

### hero-ikinci-ziyaret · İkinci ziyaret çözümü
- **Direktif:** İkinci-ziyaret bayatlığını canlı açılış yapısal çözer (her ziyaret gerçek-veriyle taze); dönen ziyaretçiye localStorage ile kısa açılış; tez asıl olarak app içindeki Olay Defteri'nde yaşar — hero'da hapsedilmez.
- **Token/değer:** dönen-ziyaret bayrağı localStorage; dönene kısa açılış; app Olay Defteri = tezin kalıcı evi.
- **DoD/Ölçüm:** ilk ziyaret tam açılış; ikinci localStorage ile kısa; Olay Defteri kayıt tutar; ikinci yüklemede uzun koreografi tetiklenmez.

### hero-squint-testi-dod · Squint testi (hero DoD zorlayıcı fonksiyon)
- **Direktif:** Açılış/hero'da gözler kısılınca en parlak iki öge YALNIZ enstrüman (Karot) ve birincil CTA; parlaklık hiçbir şekilde öneri/dikkat itmez (legal). DoD zorlayıcı fonksiyonu.
- **⚠ v1.4.1 landing carve-out (C2, CHANGELOG):** LANDING-hero'da Karot marka-yüzeyi yasağı (bağlayıcı kullanıcı kararı) üstün olduğundan bu test landing'de "en parlak 2 = **H1 + birincil CTA**" olarak okunur; landing "Canlı Masa" teaser'ı read-only vitrindir ve "her sinyal yüzeyinde Karot zorunlu" kuralındaki *sinyal yüzeyi* tanımının DIŞINDADIR. Ürün-içi (app) yüzeylerde bu maddenin aslı ve Karot-zorunluluğu aynen geçerlidir.
- **Token/değer:** en parlak 2 öge = {Karot, birincil CTA}; dekoratif ışık daima loş/yönlü.
- **Teknik:** Hero'nun en yüksek luminanslı pikselleri veri (Karot omurgası/doğum nabzı) + birincil CTA; dekoratif ışık (anahtar/dolgu/bokeh) daima loş (VL§07 üç-ışık bütçesi).
- **Ölçüm:** hero screenshot Gaussian blur (~8px) + eşikleme sonrası en parlak iki bölge Karot ve CTA; dekoratif luminans ≤ veri luminans.

### Hero — atmosfer / ışık
Hero anahtar+dolgu ışığı owned-blue/cyan ufuk (kanonik plan VL§07). Her ışık gerçek bir olayı temsil eder; ambient dekoratif değildir.
- **⚠ v1.4.2 (K-C1, CHANGELOG):** LANDING'de yalnız **anahtar** ışık aktive edildi (`--light-key`: sol-üst kaynak, ΔL* ≤ +6, statik/drift'siz, sayfada 1); **dolgu (`--light-fill`, cyan) landing'de KULLANILMAZ** (gate-3 cyan-yüzey tekeli). Grain: tüm landing zemini, ≤%3, renksiz, metin üstünde asla. **App/dashboard'a atmosfer eklenmez** (idle-sessiz + "estetik ≯ veri"). Işık-envanteri kilidi: key×1 + kabin + olay-glow; final-yükseliş kompozisyonla.

| Token | Değer |
|---|---|
| `--light-key` | `radial-gradient(1200px 600px at 78% -10%, rgb(59 87 212 / .11), transparent 60%)` (owned-blue ufuk, sağ-üst) |
| `--light-fill` | `radial-gradient(800px 480px at -4% 30%, rgb(37 224 212 / .05), transparent 55%)` (owned cyan, sol-alt) |

- **Teknik:** Ambient tek animasyonlu = glow-drift (L1 0.92×); noise (toz) STATİK'tir (ambient-animasyon sayılmaz). Ambient-sayım (≤1) squint vurgu-sayımından (≤2) ayrı bütçedir; ambient daima loş/yönlü, vurgu bütçesine girmez.
- **Migration (v1.1→v1.3):** key ışık `130 246 → 87 212` (owned-blue); fill `34 211 238 → 37 224 212` (owned cyan).

### hero-3d-webgl-koşullu · *açık uç / DEFERRED*
- **Direktif:** 3D/WebGL yalnız bilgi taşıyorsa + tam perf/erişilebilirlik bütçesini karşılıyorsa hero'da kullanılabilir (gerektiğinde gerçek 3D — dekoratif değil, bilgi-taşıyan). Koşullar: bilgi-taşıyan-3D · DPR-cap≤2 · poster-fallback · reduced-motion statik · mobil fallback · lazy/code-split.
- **Teknik:** **Karot enstrümanı bu maddeden MUAF: her ölçekte 2D SVG (karot-08).** hero-3d-webgl-koşullu yalnız Karot-DIŞI atmosfer katmanına ait olabilir ve o da **ŞU AN 0 (DEFERRED, VL§11).** Tam stack VL§11 WebGL'siz revizyonunda netleşir. Vizyon korunur: gerektiğinde gerçek 3D bilgi taşıdığında açılır; sahte sinema değil.

### Hero — Kalıcı Yasaklar
**hero-sahte-sinematik-yasak.** Önceden-pişmiş 5-beat film · dekoratif kamera dolly/orbit (wow için) · dekoratif cyan-tarama · scroll-scrubbed WebGL hero · R3F/three/Bloom (kimlik-merkez) · ~190KB chunk = kalıcı YASAK. Yaşayan Hero KORUNUR (atılan yalnız sahte katman); her efekt gerçek veri-kaynağı gerekçesi taşır.
- **Ölçüm:** initial chunk'ta three/@react-three/postprocessing yok; dolly/orbit/scrub-timeline/scan-beat pattern=fail; her efekt veri-kaynağı gerekçesi taşır.

---

## 03 · Dashboard

Kullanıcı **3 saniyede** anlamalı: Bugün ne oldu? · Aktif sinyal var mı? · Portföy nasıl? · AI ne düşünüyor? · Risk ne? Yoğun veri + sakin chrome.

### dash-görev-durum-odası · Dashboard = Durum Odası (Executive Overview) · *(v1.5 CP-PIA)*
- **Direktif:** Dashboard'ın TEK görevi "3 saniyede: sistem ne durumda, kitap sağlıklı mı, dikkat gereken ne?". **Trading cockpit DEĞİLDİR** — icra/emir-benzeri hiçbir kontrol eklenmez (icrası olmayan kokpit sahte-premium'dur; hukuki ilke: auto-trade yok). 3-kuşak (dash-ia-üç-kuşak) korunur, keskinleşir: Üst=**Nabız** (yaşayan başlık) · Orta=**Şu-an** (aktif sinyaller top-N + Signal Center köprüsü) · Alt=**Sicil** (kahraman-rakam + dönem özeti). Derin sinyal analizi Signal Center'a, piyasa-tarama Markets'e, backtest Performance'a, arşiv History'ye aittir.
- **Token/değer:** görev = durum-özeti; cockpit = yasak; ekran başına kahraman-rakam = 1.
- **DoD/Ölçüm:** dashboard'da icra/emir kontrolü = 0; her viewport'ta ≤2 vurgu (dash-vurgu-bütçesi); tek kahraman-rakam + kanıt-makbuzu (n · dönem · win-rate) render.

### dash-nabız-bandı · App-içi yaşayan-Hero'nun tek formu · *(v1.5 CP-PIA)*
- **Direktif:** App içinde pazarlama-hero'su YOK. Yaşayan-Hero'nun (§02) app-içi tek meşru formu = Dashboard üst **Nabız bandı**: ≤~120px, canlı, olay-sürümlü (AI sistem-sesi tek TR cümle + bugünün çözüm-fotonları + rejim + aktif-sayı). Atmosfer ışığı (`--light-key`/`--light-fill`) app'te YALNIZ burada referanslanabilir (dash-ambient-yasak carve-out'u: band olay-bağlı + statik-ışık + scroll'suz; ambient-animasyon eklemez). Uygulama = CP-DASH.
- **Token/değer:** band-yükseklik ≤~120px; içerik = canlı-veri (mock=0); atmosfer app-referansı = yalnız Nabız.
- **Not:** AI Görüşü kart-formundan çıkar → Nabız'ın "sistem sesi" cümlesine döner (per-sinyal AI anlatısı Signal Center/IntelligencePanel'de kalır).
- **DoD/Ölçüm:** band canlı-veri taşır (sabit/mock=fail); band-dışı app yüzeyinde atmosfer-ışık = 0; scroll-tetikli band-motion = 0; band ≤~120px.

### dash-widget-taşıma-kilidi · CP-PIA widget-taşıma haritası (bağlayıcı) · *(v1.5 CP-PIA)*
Her taşıma **additive-first**; taşınan modülün analytics-event'i birlikte taşınır; **backend/API/DB değişmez**. Bilgi KAYBOLMAZ — sahibi olan ekrana gider.

| Modül (bugün Dashboard) | Karar | Hedef |
|---|---|---|
| Durum Bandı (DE-1) | terfi | Nabız bandı çekirdeği |
| AI Görüşü kartı (DE-3) | terfi + form değişimi | Nabız "sistem sesi" cümlesi |
| Risk Dağılımı (DE-3) | taşı + enstrümanlaş | **Signal Center**: dilime-tık → tablo o risk dilimine filtrelenir |
| 5 eşit stat-kart | kır | 1 kahraman (Dönem Net Getiri + makbuz) + 3 ikincil (Aktif · Kapanan · Win-Rate) |
| Fear & Greed | in | Piyasa-bağlamı satırı (stat-kart olmaktan çıkar) |
| BTC canlı grafik (TradingView) | kaldır | /markets/BTCUSDT köprüsü |
| Varlık Dağılımı (pie) | kaldır | Signal Center filtre-sayaçları (yön/TF/risk mini-dağılım) |
| En Çok Kazananlar | kaldır | /markets |
| Piyasa Genel Bakış (4-hücre) | in | tek kompakt piyasa-bağlamı satırı (mktcapΔ · BTC-dom · F&G) |

### dash-ekran-sorumluluk-sınırı · Ekran sorumluluk tablosu (cross-screen IA) · *(v1.5 CP-PIA)*
| Yüzey | Tek-cümle görev | Sahip OLMADIĞI (sınır) |
|---|---|---|
| **Dashboard** | 3-saniyede durum (Nabız · Şu-an · Sicil) | derin sinyal analizi · piyasa tarama · backtest · arşiv |
| **Signal Center** | sinyalle çalışma: tablo + Dock (Karot/konsensus/lifecycle/benzer/risk-enstrüman) | kitap-düzeyi özet · arşiv-döküm |
| **Landing** | ikna + dürüstlük (C/A hero) | ürün-içi veri derinliği · Karot-marka kullanımı |
| **Signal Detail / Dock** | tek sinyalin tam kanıtı | kitap-metrik · sayfa-olma iddiası |
| **Markets / Symbol** | piyasa tarama + tek-sembol analiz | sinyal-kitabı anlatısı |
| **Performance** | derin sicil + backtest | "şu an" durumu |
| **Signal History** | arşiv / döküm | aktif-durum anlatısı |

### dash-ia-guardrail · CP-PIA yasakları (test-edilebilir) · *(v1.5 CP-PIA)*
1. Dashboard'a icra/emir-benzeri kontrol yasak (cockpit yasağı).
2. App'te ≥240px statik pazarlama-hero bloğu yasak; Nabız ≤~120px + canlı-veri şart (§02 hero-app-içi-sınır).
3. App'te scroll-tetikli/parallax/scroll-scrub yasak (landing hariç; §02 hero-scroll + §06).
4. Eşit-ağırlık kart-grid yasak: bir viewport'ta aynı boyut/vurguda >3 eşdeğer kart = red (dash-vurgu-bütçesi ile uyumlu).
5. Risk Dağılımı hiçbir yüzeyde tık-etkisiz dekor olarak var olamaz (enstrüman-şartı).
6. Signal Center desktop'ta dock'suz (drawer-only) kalamaz; mobilde drawer meşru.
7. Dashboard'a üçüncü-taraf gömülü enstrüman (TradingView vb.) konmaz (evi Markets/Symbol).
8. Karot marka-yüzeyinde yasak (mevcut kilit, [[brand-identity-sprint-decision]]); ürün-içi Dock sahnelemesi serbest/teşvikli.

### dash-ia-üç-kuşak · Bilgi mimarisi — 3 kuşak (Şu an / Neden / Sicil)
- **Direktif:** Dashboard'u üç dikey kuşağa ayır: (1) ÜST "Şu an" = aktif sinyaller (Karot'larıyla) + TP'ye yaklaşanlar + bugün doğan/kapanan. (2) ORTA "Neden" = seçili sinyalin kanıt katmanı (9 motor dökümü + uzlaşmazlık + provenance). (3) ALT "Sicil" = kümülatif isabet + PF + drawdown, közleşmiş (kapanmış zarar) kayıplar DAHİL. Şiirsel adlar UI'a çıkmaz.
- **Token/değer:** 3 kuşak · Üst=Şu an · Orta=Neden · Alt=Sicil · her AI değeri 1 hover uzaklıkta provenance.
- **Teknik:** Üst kuşak canlı/değişen (aktif satır her biri Karot taşır, §05 zorunlu). Orta kuşak 9-motor dökümü (sabit sıra Teknik→Makro) + uzlaşmazlık + provenance. Alt kuşak dürüst track-record: közleşme dâhil (kapanan sinyal kül tonunda listede, §01).
- **DoD:** Üç kuşak okunur; Üst=canlı, Orta=kanıt, Alt=track-record; alt kuşakta közleşmiş kayıplar görünür; her AI değeri tek hover'da kaynak; iç-dil UI'da yok.
- **Ölçüm:** 3 kuşak DOM bölgesi; Sicil'de kapanan-zarar satırları render (0 gizleme); 10 AI değerinde hover→kaynak (10/10); UI'da iç-dil sözcüğü=0.
- **Migration (v1.1→v1.3):** v1.1 6-kart modeli (Durum bandı→Aktif→Portföy→AI→Risk→Piyasa) → 3-kuşak üst-çerçeve; 6-kart o kuşakların içeriğine yerleşir. "Sahte delta + sentetik market-cap + Forex/işlevsiz sekmeler" kaldırılır.

### dash-yoğunluk-sözleşmesi · Yoğunluk = Bloomberg verisi × Mercury çerçevesi
- **Direktif:** Veri yüzeylerini yoğun, chrome'unu sakin tasarla; yoğunluk ölçülebilir sözleşme. Veri satırında Mercury-boşluğunu reddet, cömert boşluğu YALNIZ chrome'a ver. Aynı ekranda iki ritim: veri satırı sıkı, chrome cömert.
- **Token/değer:** gövde 13px · satır-yükseklik 32px (kompakt) / 40px (rahat) · veri-satırı 4px iç, 8px arası · chrome 24px · `tabular-nums`.
- **Teknik:** Tablo gövde 13px tabular. Satır yüksekliği `--row-h` (32|40). Veri satırı 4px iç / 8px arası, chrome 24px. Ambient/paralaks/scroll-reveal veri yüzeyinde YASAK. "3 saniye kuralı": ilk 3 sn'de 5 çekirdek soru taranarak yanıtlanır.
- **DoD:** 1280×800 rahat modda ≥12 sinyal satırı; gövde 13px + tabular; veri yüzeyinde 0 ambient; chrome 24px nefes; 3-sn taraması 5 soruyu yanıtlar.
- **Ölçüm:** 1280×800 rahat(40px)'te görünür satır ≥12; computed row-height ∈{32,40}; gövde 13px; tabular lint; veri-yüzeyi ambient/transform animasyon=0.

### dash-yoğunluk-modu · İki mod — kompakt / rahat (kullanıcı-tıkla)
- **Direktif:** İki satır-yoğunluk modu (kompakt 32px / rahat 40px); mod kullanıcı-tıkla değişir ve kalıcıdır; otomatik/veri-tetikli değişim YASAK. Satır yüksekliği anında uygulanır, layout asla animasyonlanmaz.
- **Token/değer:** kompakt 32px · rahat 40px · `--row-h`; varsayılan öneri = rahat (erişilebilirlik).
- **Teknik:** Tek CSS değişkeni (`--row-h`); toggle 32↔40. Tercih persist. Satır yüksekliği (layout property) animasyonlanmaz — anlık. Toggle chrome'da yaşar.
- **Ölçüm:** computed `--row-h` ∈{32,40}; reload'da korunur; geçişte animated layout property=0; kompakt satır sayısı > rahat.

### dash-vurgu-bütçesi · Vurgu bütçesi — viewport başına ≤2
- **Direktif:** Aynı viewport'ta en çok 2 vurgu; parlaklık dikkat itmez, dikkat Karot şeklinden gelir. Tazelik/güncellik ışığı dikkat için KULLANILMAZ (yalnız yaşam-döngüsü olayına bağlı, legal).
- **Token/değer:** ≤2 vurgu/viewport; sahipler aktif-sinyal · CTA (glow üç-sahip ile ortak).
- **Teknik:** Squint testi dashboard'a uygulanır. Sıralama/dikkat Karot geometrisiyle taşınır, luminans/glow ile değil. Tazelik-ışığı kaldırıldı.
- **Ölçüm:** squint ≤2 parlak öge; hover-glow lint (kart/satır/ikon/başlıkta renkli box-shadow=0); luminans-histogram en parlak küme ≤2 bölge.

### dash-karar-akışı · Gör → Sorgula → Doğrula → Karar
- **Direktif:** Dört adımlı akış: Gör (Karot şekli) → Sorgula (provenance hover) → Doğrula (Sicil kuşağı) → Karar; her adım ≤1 hover/tık. Arayüz karar VERMEZ, BESLER: uzlaşmazlığı gizlemez, sicili saklamaz.
- **Token/değer:** 4 adım; Gör(Karot)→Sorgula(provenance)→Doğrula(sicil)→Karar; her adım ≤1 hover/tık; provenance giriş `--dur-warm` (140ms), anında çıkış.
- **Teknik:** Provenance 140ms giriş (`--dur-warm`), anında çıkış. Bölünmüş sinyalde Karot nötr/karışık-açılı kalır (yön-rengi yok). "AI emin değil" hali de gösterilir.
- **Ölçüm:** her adım ≤1 hover/tık; bölünmüş sinyalde yön-rengi yok; provenance açılış ≈140ms (`--dur-warm`).

### dash-ambient-yasak · Ambient/paralaks kalıcı yasağı
- **Direktif:** Dashboard (ve tüm app veri yüzeyleri) ambient/paralaks/scroll-reveal/autoplay/dekoratif hareket İÇERMEZ. Hareket yalnız gerçek telemetri olayına (tek sefer, ≤600ms, transform/opacity).
- **Token/değer:** app ambient=0 · paralaks=0 · scroll-reveal=0 · autoplay=0 · izinli motion ≤600ms transform/opacity.
- **Teknik:** §08 DoD H7 dashboard'da bağlayıcı. Paralaks yalnız landing. Durgun ekran özelliktir (sükûnet=güven). reduced-motion = zaten statik yüzeyde bilgi kaybı yok.
- **Ölçüm:** idle DOM aktif animation/transition=0; ambient element=0; scroll'da paralaks node=0; reduced-motion'da bilgi-kaybı=0.

### dash-40-karot-yoğunluk-kanıtı · *açık uç / FJ#4*
- **Direktif:** İlk ekranda ~40 Karot'un aynı anda okunabilirliğini KANITLA: 40 yan-yana Karot örüntü mü gürültü mü? Kanıtlanana dek "doğrulanmış" sayılmaz. Bu yüzey Hero canlı-konsensüs-masasıyla aynı açılış mekaniğini paylaşır.
- **Token/değer:** ~40 Karot / ilk ekran · 16px silüet (tablo) · yön+uzlaşma iki-hal okuması.
- **Teknik:** Tabloda Karot 16px silüet (yön+uzlaşma; kararsız yalnız detayda). 16px yoğunluk yüzeyinde glow KAPALI → squint ≤2 garantisi. Landing-hero (canlı settle+glow-drift) ile app-dashboard (idle-sessiz) AYRI motion bütçeli.
- **Ölçüm:** ölçüm sırası: önce squint vurgu ≤2 (geçemezse blok), sonra Karot-örüntü eşiği. Yabancı-kör: 16px silüet uzlaşan-vs-bölünmüş ≥%85 (48px ≥%90); örüntü kanıtlanamazsa yoğunluk hedefi revize.

### dash-göz-hareketi-folkloru-yasak
Dashboard IA'sını F/T göz-hareketi iddiasına dayandırma — **§00 G-00-17 dashboard'a uygulanır** (tek kanonik madde orada). Gerekçe = bilgi-önceliği (Şu an > Neden > Sicil) + kanıt-yoğunluğu.

### Navigation (INT-11)
Navigasyon konvansiyonel sidebar; radikal IA reddedilir (trader yeniden öğrenmez). Aktif öge = sol accent çubuğu (`--accent-ui` 2–3px, 1px-UI a11y) + tek luminans basamağı; ASLA glow. Özgünlük öz'de (Karot/provenance), iskelette değil.
- **Ölçüm:** aktif nav sol-border `--accent-ui` + bg +1 E-basamağı; nav'da box-shadow/glow===none.
- **Migration (v1.1→v1.3):** nav-accent iz `--accent → --accent-ui` (1px-UI E0–E3 hepsi ≥3; `--accent` iz/border olarak E2/E3'te FAIL 2.90/2.62 → yalnız dolgu).

---

## 04 · Markets

Amaç netlik + premium his; terminal derinliği değil.
- **Filtre bar:** segmented control (Tümü · Kripto · Hisse · N varlık — birimli) + arama + sıralama; BIST-kapalı rozeti "Son kapanış". Aktif segment iz/border `--accent-ui`; input-focus `--accent-ui` ring.
- **Market kartı (grid):** logo · sembol · fiyat (tabular) · 24s % (semantik renk `--bull`/`--bear`) · mini-sparkline (area-fill + vurgulu uç). Hover: kart-modu yüzey-ısınma (+1 luminans E1→E2, translateY(−2px), `--dur-warm` 140ms). Tıkla → analiz.
- **Tablo görünümü:** semantik `<table>` · sıralanabilir başlık · `md` altı → kart; satır hover +1 lümen, transform 0 (satır zıplamaz). 200 kart canlı-fiyatta batch-render; güncelleme yalnız foton flaşı (`--dur-photon` 150ms, konum sabit).
- **Heatmap (ops. · P2):** kategori/coin ısı haritası.
- **Loading:** kart-skeleton grid (grace-window <300ms; spinner yok). **Mobil:** grid tek kolon; filtre chip'leri yatay-scroll; tablo → kart; touch 44px.

### markets-widget-devir · Dashboard'dan devrolan piyasa-modülleri · *(v1.5 CP-PIA)*
- **Direktif:** Dashboard'dan CP-PIA ile devrolan piyasa-modülleri bu ekranın (ve /symbol-analysis'in) sorumluluğundadır: **BTC canlı grafik → /markets/BTCUSDT (symbol analiz)** · **En Çok Kazananlar → market grid** · **Varlık-Dağılımı bağlamı → Signal Center filtre-sayaçları**. Dashboard gömülü üçüncü-taraf enstrüman veya piyasa-tarama modülü taşımaz (§03 dash-ekran-sorumluluk-sınırı + guardrail-7).
- **Kapsam notu:** Bu revizyon yalnız widget-sahipliğini kilitler; **§04 filtre-bar'ının crypto-only sadeleştirmesi (Tümü/Kripto/Hisse segment + BIST-rozeti) AYRI track — CP-CO-3 — kapsamındadır ve bu doc-revizyonda değiştirilmedi.**

---

## 05 · Signals — Karot Konsensüs Enstrümanı

> ## ⚠️ DEPRECATED — Karot ürün-UI'dan kaldırılıyor · *(v1.7 · CP-KAROT-DOC · 2026-07-18)*
>
> **Bağlayıcı kullanıcı kararı (2026-07-18):** Karot artık TradeMinds **ürün arayüzünde KULLANILMAZ** — satır-içi glyph, kalite/confidence/risk yanı sembolü, Dock hero-objesi, consensus/lifecycle/proof objesi veya marka motifi olarak. Bu bölümdeki **tüm karot-* maddeleri (karot-01…karot-15) + karot-sahne-ölçekleri ürün-UI için SUPERSEDED'dir.** "Zorunlu merkez enstrüman" (karot-01), "kanonik silüet = marka-işareti / favicon-loader-logo" (karot-09), "Geometry Freeze" (karot-15) ve "sahne-ölçekleri" (satır/detay/kahraman) dahil hiçbiri artık ürün kimliğini bağlamaz. Aşağıdaki geometri/matematik/hal maddeleri **tarihsel kayıt** olarak bırakıldı — normatif değil.
>
> **Yeni kimlik tezi — Karot yerine (glyph/ikon/sembol İKAMESİ YOK):** TradeMinds premium kimliği artık bir işaret üzerine değil, **kompozisyon ve veri-hiyerarşisi** üzerine kurulur:
> - **typography** — sahipli tabular numeral + eyebrow→display grameri
> - **owned numerical hierarchy** — ekran-başına kahraman-rakam (§01-K craft-kahraman-rakam)
> - **instrument well** — E0-inset enstrüman-kuyusu (§01-K craft-veri-kuyusu)
> - **proof receipt** — kanıt-makbuzu (§01-K craft-makbuz-grameri); per-motor konsensüs artık METİNLE taşınır: `9 motor · 7 LONG · 2 nötr`
> - **data hierarchy + spacing** — kabin-imzası (yüzey-merdiveni / hairline / köşe-dili) + iki-ritim boşluk
> - **restrained dark terminal composition** — owned E0–E3 + terminal paleti (bull/bear/cyan yalnız çizgi/iz)
>
> Premium his **süs ile değil** kompozisyon / typography / spacing / veri-hiyerarşisi / makbuz ile kurulur. **Karot'un yerine yeni bir şekil KONMAZ** (konsensüs bilgisi makbuz-metnine iner). Logo-kapalı kimlik taşıyıcısı artık = kabin-imzası + tabular-numeral + owned-palet (§1124 güncellendi; §1131 zaten Karot-maskeli okumayı tanımlıyordu).
>
> **Kaldırma sırası (her biri AYRI CP + onay + görsel-QA):** CP-KAROT-DOC (bu) → CP-KAROT-UI1 (SignalTable satır+loading Karot; **Dashboard "Şu an" bandını da etkiler** — shared bileşen) → CP-KAROT-UI2 (Dock consensus sahnesi, `signals/page.tsx`) → CP-KAROT-UI3 (SignalDetailSection hero+motor; **AT-1 çapraz-vurgu + AT-2 tooltip dahil**) → CP-KAROT-CLEAN (`Karot.tsx` / `karot-geometry.ts` / `karot-adapter.ts` / `karot-selftest.mjs` ölü-kod). **favicon/icon.png/apple-icon.png = bu seride DEĞİL** — statik asset; Karot silüeti içeriyorsa ayrı CP-KAROT-ASSET / Brand Identity Sprint.
>
> *Aşağıdaki orijinal §05 içeriği tarihsel kayıt olarak korunur; ürün-UI için normatif DEĞİLdir.*

Sinyal kartı ürünün kalbi; merkez enstrüman = **Karot** (moat, Consensus Instrument). Karot 9 motorun yön×güven konsensusunu **dikey omurga + slot'a mıhlı açısal kanıt-fitilleri** ile görselleştirir (K17 görünüm + K02 matematik). AI-kimliği renkten forma taşınır; Karot yeniden-tasarlanmaz — geometri **karot-15 · Geometry Freeze** ile dondurulmuştur.

### karot-sahne-ölçekleri · Üç sahne boyu: satır / detay / kahraman · *(v1.6 CP-PV1-A)*
> **SUPERSEDED (v1.7 · CP-KAROT-DOC)** — ürün-UI için bağlayıcı DEĞİL; satır/detay/kahraman Karot sahneleri kaldırılıyor (CP-KAROT-UI1/2/3). Bkz §05 baş-banner.
- **Direktif:** Karot ürün-içi zekâ-objesi olarak ÜÇ sahne boyunda yaşar: **16–24px satır-silüeti** (SignalTable/dashboard-Şu-an; yön+uzlaşma iki-hal okuması; bu yüzeyde glow KAPALI — mevcut kural) · **32px detay-skoru** (SignalDetail/Dock skor-bloğu; etkileşimli, AT-1/AT-2) · **96–120px Dock kahraman-sahnesi (YENİ)** — kimliğin "ölçekte-okunduğu" an: seçili sinyalin Karot'u Signal-Center Dock'unda kuyu (craft-veri-kuyusu) içinde sahnelenir. Geometri değişmez (karot-15 Freeze); yalnız render ölçeği.
- **Token/değer:** satır 16–24 · detay 32 · kahraman 96–120; **<16px YASAK** (okunmaz); sahne-Karot'u well içinde.
- **Teknik:** Kahraman-sahne = aynı `<Karot>` primitifi (karot-01: tek render fonksiyonu, yalnız ölçek değişir). **Marka-yüzeyi yasağı AYNEN:** logo/favicon/navbar/landing-hero/splash'ta Karot KULLANILMAZ (bağlayıcı kullanıcı kararı, v1.4.1 carve-out). Dekoratif arka-plan deseni olarak Karot tekrarı = veri-dışı süs-render = yasak (G-00-07).
- **DoD:** Dock'ta seçili sinyalin ≥96px Karot'u well içinde; <16px render grep=0; marka-yüzeyi grep=0; süs-render=0.
- **Ölçüm:** sahne-boyu ∈ {16–24, 32, 96–120} dışı kullanım=fail; Dock kahraman-Karot'u + kahraman-rakam aynı viewport'ta vurgu-bütçesini (≤2) aşmaz (squint).

### karot-01 · Zorunlu konsensüs primitifi (merkez enstrüman)
> **SUPERSEDED (v1.7 · CP-KAROT-DOC)** — "zorunlu primitif / merkez enstrüman" ürün-UI için GEÇERSİZ; sinyal yüzeyleri artık Karot taşımaz (bilgi = bar/sayı/makbuz). Bkz §05 baş-banner.
- **Direktif:** Sinyal taşıyan HER kart Karot enstrümanını taşır (zorunlu primitif). Radar/örümcek, donut, bar gösterge tipleri sinyal-konsensüsü için ASLA kullanılmaz (kalıcı yasak).
- **Token/değer:** primitif `<Karot>` · gösterge tipi dikey-omurga fitil-demeti (radar/donut/bar DEĞİL).
- **Teknik:** SignalCard, tablo satırı, detay drawer, hero'daki her sinyal yüzeyi aynı Karot primitifini render eder (yalnız ölçek değişir). Radar/donut/bar "AI dashboard ortalaması" olduğu için reddedilir.
- **DoD:** Her sinyal yüzeyinde bir Karot render'ı; yasak gösterge tipi grep=0; DoD "Karot zorunluluğu" lint geçer.
- **Ölçüm:** sinyal-yüzeyi komponentlerinde Karot kullanımı=%100 (CI lint); radar/donut/bar (sinyal-konsensüs)=0.

### karot-02 · Geometri + fitil konum matematiği
- **Direktif:** Karot'u tek parametrik geometriden türet; hardcode edilmiş görsel şekil yazma.
- **Token/değer:** `W=96 · H=200 · PAD=20 · SPINE_X=24 · L=32 (fitil boyu, sabit) · θmax=34° · yön∈{+1 long,−1 short,0 nötr} · güven∈[0,1] · fitil=9 · step=(H−2·PAD)/8=20 · tip-len=18 · viewBox '0 0 96 200'`.
- **Teknik:** `fitil_i: taban=(SPINE_X, PAD+i·step), uç=(SPINE_X+L·cosθᵢ, yᵢ−L·sinθᵢ)`, `θᵢ=clamp(cᵢ,−1,1)·θmax` (c işaretli güven ∈[−1,1]; **boy L sabit** → güven yalnız açıya kodlanır: tek-değişkenli dürüst okuma, Lie Factor 1). Omurga = düz dikey çizgi `x=SPINE_X`, y aralığı PAD−8 → H−PAD+4. **Karar-ucu:** yalnız Uzlaşma; taban=(SPINE_X, PAD−8), `θ_tip=clamp(mean,−1,1)·θmax` (**büyütme çarpanı YOK**), uzunluk=tip-len 18, cyan, **en son çizilir** (AI en son konuşur). Tint-zarfı = omurga→fitil-uçları polygonu (slot sırasında; karşıt-yön fitil zarfı boğumlar → dürüstlük fiziği). **Çarpışma yasası:** `L·sin(θmax)=17.9 < step=20` (fitiller dönüşte çarpışmaz). Eksen-geçiş sayısı işaret dizisinden hesaplanır (karot-03) — projeksiyondan bağımsız, çatışma matematiğinin girdisi.
- **DoD:** Tek render fonksiyonu 9-değerli işaretli-güven dizisinden SVG üretir; W/H/PAD/SPINE_X/L/θmax tek kaynakta sabit; hiçbir şekil elle çizilmez.
- **Ölçüm:** unit test: `θᵢ=cᵢ·34°` ve uç-koordinat birebir; tint-zarfı + karar-ucu deterministik snapshot.
- **Migration (v1.3→v1.4):** merkez-eksenli spline (`x=AXIS+c·AMP`, Catmull-Rom→bezier, dashed merkez-eksen) → **tek-taraflı fitilli-omurga** (`θ=c·θmax`, düz omurga + açısal fitiller + karar-ucu). "K17 görünüm + K02 matematik": classify eşikleri (karot-03), 9-slot sıra (karot-04), rest-state dizisi (karot-09), dikey ritim (H/PAD/step) **korundu**; AXIS/AMP/spline/dashed-eksen **kaldırıldı**. Eksen hairline .12 → **slot-kılavuzu** (yalnız 200-ölçek).

### karot-03 · Hal-sınıflandırma eşikleri (implementasyon-bağlayıcı)
- **Direktif:** Hali şu sırayla ve tam bu eşiklerle sınıflandır: ortalama|güven|<0.30 → Kararsız; değilse eksen-geçiş≥2 → Bölünmüş; değilse → Uzlaşma. Yön tinti mean>0 bull, mean<0 bear.
- **Token/değer:** absMean eşiği=0.30 · eksen-geçiş eşiği=2 · işaret bandı c>0.08→+1, c<−0.08→−1, |c|≤0.08→0 · sıra weak→split→consensus.
- **Teknik:** `signs=confs.map(...)`, `cross`=ardışık sıfır-olmayan işaret değişimi, `absMean=Σ|c|/9`, `mean=Σc/9`. Öncelik zorunlu: önce weak, sonra split, aksi consensus. no-birth koşulu: cross≥2 OR absMean<0.30.
- **DoD:** `classify()` bu üç dalı bu sırayla; eşikler (0.30, 2, 0.08) tek kaynakta; sınır durumları test edilmiş.
- **Ölçüm:** consensusLong→consensus, split→split, weak→weak; sınır-değer testleri PASS.

### karot-04 · 9 motor sabit dikey sıra (öğrenilebilirlik)
- **Direktif:** 9 motoru omurgada daima bu sırayla (yukarıdan aşağı) diz; motor→slot eşlemesi asla değişmez.
- **Token/değer:** sıra (i=0→8): Teknik · Piyasa Yapısı · SMC · CRT · Hacim · Risk · Temel · On-Chain · Makro.
- **Teknik:** ENGINES dizisi sabit tek kaynak; slot-i (y=PAD+i·step) daima aynı motor (spatial memory); hover'da motor adı + fitil +1 lüminans (48px+). Sıra değişmezliği hem provenance okunabilirliğinin hem "hangi motor döndü" adreslemesinin ön koşulu.
- **Ölçüm:** ENGINES tek yerde; indeks→motor eşlemesi unit test.

### karot-05 · Üç dürüst hal + görsel imzaları
- **Direktif:** Üç hali ayrı imzayla render et: Uzlaşma (paralel fitiller + yön tinti zarfı + karar-ucu) / Bölünmüş (cyan omurga, tintsiz, karışık-açılı fitiller + eksen-üstü çift-nokta, karar-ucu YOK) / Kararsız (soluk, yataya-yapışık fitiller θ≈0). Tabloda (16px) YALNIZ 2 hal okunur (uzlaştı/bölündü); Kararsız yalnız 48px+.
- **Token/değer:** Uzlaşma: tint-zarfı fill-opacity 0.14 · fitiller `--tx2` (kanıt, nötr) · omurga+karar-ucu `--cyan` · stroke-width 1.9, opacity 0.95 · Bölünmüş: fitiller `--tx2`, omurga `--cyan`, karar-ucu YOK, tint=null, eksen-üstü çift-nokta `--cyan` · Kararsız: fitiller+omurga `--tx3`, stroke-width 1.3, opacity 0.6. **Cyan-bütçe:** bir Karot'ta cyan yalnız KARAR-İZİ öğelerinde — omurga + Uzlaşma'da karar-ucu + Bölünmüş'te eksen-üstü çift-nokta (üçü tek karar-izi konsepti; `micro-cyan-yoğunluk-bütçesi` "omurga + 1 provenance" tavanı içinde); fitiller ASLA cyan (kanıt=slate).
- **Teknik:** Uzlaşmada omurga→fitil-uçları zarfı yön tintiyle dolar (fill-opacity 0.14); karşıt-yön fitil zarfı boğumlar (dürüstlük fiziği). Bölünmüşte renk kazanılmaz (cyan-nötr) + eksen-üstü sabit çift-nokta imzası (1A-ii'de uygulandı; 16px silüette düşer). 16px silüette split ile aynı "uzlaşmadı" okuması yeterli.
- **DoD:** Üç hal 48px+'ta 1 sn'de ayrılır; çift-nokta imzası eklenmiş; 16px'te yalnız uzlaştı/bölündü; squint'te uzlaşma tinti en belirgin.
- **Ölçüm:** üç hal ayrı snapshot; yabancı-kör 3 hal @48px %90+; bölünmüş okuması @16px mevcut (tint-yok + cyan omurga; çift-nokta 48px+).

### karot-06 · Tek parametrik render fonksiyonu
- **Direktif:** Tüm haller ve tüm ölçekler (16/48/200px) tek fonksiyonun 9-değerli işaretli-güven dizisinden ürettiği SVG'den doğsun; ölçeğe/hale özel hardcode ASLA yazma.
- **Token/değer:** `svg(confs, scale, opt) → {html, cl}`; ölçekler 0.16→~16px silüet (3 küme-fitil), 1→~48px kart, büyük→~200px hero; fitil/omurga stroke-width: kararsız→1.3 · silüet(<32px, kararsız-dışı)→1.6 · tam-ölçek→1.9.
- **Teknik:** `svg()`: classify → slots → (consensus) tint-zarfı → fitiller → (consensus && scale≥1) glow underlay → omurga → (consensus) karar-ucu. 16px 3-küme-fitil silüeti (karar-ucu/glow düşer). Ölçek-değişmezliği (karot-08) bu fonksiyonun garantisi.
- **Ölçüm:** Karot render tek fonksiyona iner; statik Karot SVG asset=0 (kanonik rest-state hariç, karot-09).

### karot-07 · Omurga rengi (cyan istisna) + yön tinti kuralı
- **Direktif:** Omurga çizgisi daima cyan; yön tinti (bull/bear) YALNIZ Uzlaşma kazanınca gövdeye dolar; Bölünmüş/Kararsızda renk kazanılmaz (cyan-nötr / soluk).
- **Token/değer:** omurga cyan `--cyan #25E0D4`; uzlaşma tinti bull `--bull #2FBE9A` / bear `--bear #E14640`; kararsız omurga `--tx3 #5C6980`; tint area fill-opacity 0.14.
- **Teknik:** `classify()` consensus'ta stroke=cyan + tint=(mean>0?bull:bear); split stroke=cyan tint=null; weak stroke=faint tint=null. Renk "kazanılır" doktrini. Omurga cyan = §01 cyan-yalnız-çizgi kuralının bilinçli istisnası (çizgi, yüzey değil).
- **Ölçüm:** yön rengi yalnız state==='consensus'; hex literal (#22D3EE|#10B981|#F4556E) render kodunda=0.
- **Migration (v1.1→v1.3):** render literalleri `#22D3EE → --cyan #25E0D4`, `#10B981 → --bull #2FBE9A`, `#F4556E → --bear #E14640`.

### karot-08 · Ölçek-değişmezliği (tek okuma dili, 3 ölçek)
- **Direktif:** Aynı Karot'u üç ölçekte tek okuma diliyle render et: 16px silüet (tablo — 3 küme-fitil, yön+uzlaşma) / 48px kart (9 fitil, motor adları hover) / 200px hero-vitrin (etiketli, canlı settle, provenance). 200px hero dâhil TÜM ölçekler 2D SVG — WebGL/3D DEĞİL.
- **Token/değer:** 16px 3-küme-fitil glow-yok · 48px hover motor adları · 200px etiket+settle+provenance+slot-kılavuzu · malzeme 2D SVG (WebGL yasak).
- **Teknik:** Küçük ölçekte fitiller 3 kümeye iner + karar-ucu/glow düşer (glow yalnız scale≥1). 200px hero-vitrin dekoratif kamera/3D olmadan yalnız ışık+settle ile sinematiktir. Ölçek büyüdükçe bilgi eklenir, okuma dili değişmez.
- **Ölçüm:** hero Karot'ta three/R3F/webgl import=0; üç ölçek snapshot tek fonksiyondan; 16px silüet tablo satırında render.

### karot-09 · Kanonik rest-state silüet = marka-işareti (Consensus Instrument MILESTONE)
> **SUPERSEDED (v1.7 · CP-KAROT-DOC)** — Karot silüeti artık marka-işareti / favicon / loader / logo DEĞİL. Logo-kapalı kimlik = kabin-imzası + tabular-numeral + owned-palet (§1124). favicon/icon.png Karot içeriyorsa ayrı CP-KAROT-ASSET. Bkz §05 baş-banner.
- **Direktif:** Sabit kanonik rest-state Karot silüeti tanımla ve favicon/loader/logo olarak kullan; canlı render bu silüetin türevidir. AI-kimliği renkten forma taşınır. Kanonik rest-state = tek deterministik 9-motor yön×güven CONFS dizisi (hafif-bull-uzlaşma imzası); bu diziden tek parametrik render fonksiyonu → kanonik SVG (favicon/loader/logo). Bu bir MILESTONE'dur (K1b).
- **Token/değer — kanonik rest-state confs dizisi (i=0→8, Teknik→Makro), c∈[−1,1]:**
  `[ +0.42, +0.55, +0.38, +0.10, +0.48, +0.22, +0.60, +0.35, +0.18 ]`
  - Türetilen metrikler: `mean = +0.364`, `absMean = 0.364` (≥0.30 → Kararsız DEĞİL), işaret bandı sonrası tüm slotlar +1 (|c|>0.08), eksen-geçiş `cross = 0` (<2 → Bölünmüş DEĞİL) ⇒ hal = **Uzlaşma**, yön = **bull** (mean>0). İmza: hafif-bull-uzlaşma (9 fitil yukarı-sağa paralel, aşırı dik değil + karar-ucu yukarı — sakin/dürüst konsensus silüeti).
  - Kullanım: favicon · loader · logo. Render: `svg(confs, scale, {nodes:…})` tek parametrik fonksiyondan (karot-06); ayrı el-çizim asset yok.
- **Teknik:** Marka-işareti değişken render değil sabit silüet (retinaya kazınabilirlik). Form-tabanlı AI kimliği cyan hue bağımlılığını kaldırır (logo-kapalı tanınma kaldıracı, G-08-05). Bu dizi favicon/loader/logo için tek kaynaktır; canlı Karot render'ı aynı fonksiyonun değişken-veri türevidir. AI-kimliği formda taşınır.
- **DoD:** favicon+loader+logo tek kanonik silüet kaynağından (bu confs dizisi); statik el-çizim Karot asset=0; kanonik dizi `classify()` ile Uzlaşma/bull üretir (regresyon testi).
- **Ölçüm:** favicon+loader+logo tek kanonik silüet kaynağından; kanonik dizi → classify()==consensus/bull (unit test); logo-kapalı yabancı-kör testte silüet tanınırlığı (G-08-05).

### karot-10 · Malzeme/fizik: ışıkla çizilmiş ince metal tel, RADYUSSUZ
- **Direktif:** Karot'u "ışıkla çizilmiş ince metal tel" olarak render et; cam (glassmorphism) ve saf-glow (neon) ASLA; Karot RADYUSSUZ.
- **Token/değer:** fitil+omurga stroke-width uzlaşma/bölünmüş 1.9, kararsız 1.3 · linecap/linejoin round · uzlaşma glow underlay (yalnız scale≥1, omurga+karar-ucu üzerinde): stroke-width 3.4, opacity 0.14, blur 2px · radius yok.
- **Teknik:** İnce net vektör fitiller + omurga (1.3–1.9px). Uzlaşmada scale≥1'de düşük-opaklık blur underlay = **cyan omurga+karar-ucu çizgisinin AYNI-çizgi ışık-genişletmesi** (stroke-width 3.4 = omurga stroke kalınlaştırılmış kopyası), bağımsız dolgu-yüzey DEĞİL → cyan-yüzey tabusuna girmez; statik 2px blur backdrop değil enstrüman-blur (blur-yalnız-E3 lint'inden muaf), opaklık ≤.14 tavanına tabi. 16px yoğunluk yüzeyinde glow KAPALI. Radyussuzluk Karot'u jenerik radius-12 kartlardan ayıran imza.
- **Ölçüm:** Karot SVG'de radius/rx yok, cam/backdrop-filter yok; glow blur değeri sabit (animasyonlanmaz); stroke-width 1.3–3.4 bandında.
- **Migration (v1.1→v1.3):** underlay opacity **0.18 → 0.14** (tek glow tavanı).

### karot-11 · Karot ↔ Chart entegrasyonu (tek birleşik nesne) · *açık uç geometri / FJ#2*
- **Direktif:** Karot enstrümanı ile chart TEK BİRLEŞİK NESNE'dir (O8): ayrı widget değil; grafiğin üstünde yaşayan seviye çizgileri + ışık-maskeli grid ile tek görsel nesne olarak birleşir. Tam geometri spec'i açık uçtur; katman sırası ve omurga konumu KİLİTLİdir.
- **Token/değer:** katman sırası (alttan üste) = `grid < ışık-maske < yaşayan-seviye-çizgileri (TP/SL telemetriyle) < Karot-omurga < crosshair`; omurga konumu = chart sağ-kenarı (son-fiyat hizası) sabit; AI/aktif-eksen crosshair `--cyan`; ham fiyat-crosshair `--tx3`; grid hairline `--hl10`.
- **Teknik:**
  - **Katman düzeni (O8):** grid en altta; üstünde ışık-maske; üstünde yaşayan-seviye-çizgileri (TP `--bull` / Giriş `--accent` / SL `--bear`, telemetriyle canlanır — TP/SL yaklaştıkça parlaklık artar); üstünde Karot-omurga; en üstte crosshair. Bu sıra craft-depth ışık-sırasına uyar.
  - **Omurga konumu:** Karot omurgası chart'ın sağ-kenarına (son-fiyat hizası) SABİTlenir — konsensus okuması fiyatın "şimdi"siyle hizalanır.
  - **Crosshair ayrımı:** AI/aktif-eksen crosshair `--cyan` ("çizgi" rolü, cyan-tekeliyle uyumlu — yüzey değil); ham fiyat-crosshair `--tx3` (nötr UI-obje/iz). İki crosshair rolü karıştırılmaz.
  - **Geçici bağlayıcı elevation:** Karot+chart tek-nesnesi TEK elevation katmanı sayılır (craft-depth odak-2 kuralında 1); iç z-sıralama yeni z-scale token ÜRETMEZ (aynı stacking-context içi sıra).
- **DoD:** Karot chart-üstü tek nesne okunur; katman sırası (grid<ışık-maske<seviye<omurga<crosshair) uygulanmış; omurga son-fiyat hizasında; AI-crosshair cyan, ham-crosshair `--tx3`.
- **Ölçüm:** DOM/SVG katman-sırası assert (grid<ışık-maske<seviye<omurga<crosshair); omurga x-konumu = chart sağ-kenar/son-fiyat hizası; AI-crosshair computed stroke==`--cyan`, ham-crosshair==`--tx3`. Tam geometri spec'i FJ#2 sonrası kilitlenir.

### karot-12 · Bilgi-yükü netliği — donut/bar vs Karot rol ayrımı (O3-revize)
- **Direktif:** Karot YENİDEN-TASARLANMAZ; bilgi-yükü NETLEŞTİRİLİR. Donut/bar gibi toplam-göstergeler yalnızca TOPLAM'ı gösterir (skaler özet); Karot ise per-motor AYRIŞMA yapısını + zaman-eksenini (fikir-değiştirme) = SÜRECİ temsil eder. İki rol karıştırılmaz.
- **Token/değer:** donut/bar rolü = toplam/skaler özet (ör. "82/100") · Karot rolü = per-motor ayrışma (9 fitil) + süreç/zaman temsili · 48/200px ölçekte etkileşimde per-motor gerekçe açılır.
- **Teknik:** Sinyal-konsensüsü için donut/bar ASLA Karot yerine kullanılmaz (karot-01 yasağı korunur); donut/bar yalnızca bir skaler özet gerektiğinde ikincil rolde durabilir ve Karot'un taşıdığı per-motor ayrışma/süreç bilgisini üstlenmez. Bilgi-yükü: Karot = "hangi motor ne dedi + zamanla nasıl döndü"; donut/bar = "toplam kaç". 48px+ ölçekte etkileşimde (hover/tık) per-motor gerekçe açılır (provenance, AITL-03).
- **DoD:** Donut/bar hiçbir sinyal yüzeyinde Karot'un yerini almaz; per-motor ayrışma yalnız Karot'ta; 48/200px'te etkileşimde per-motor gerekçe açılır.
- **Ölçüm:** sinyal-konsensüs yüzeyinde donut/bar-yerine-Karot=%100; 48px+ Karot'ta etkileşim→per-motor gerekçe render; donut/bar toplam-dışı per-motor iddia taşımaz.

### karot-13 · Loading = boş-Karot (spinner/cyan-tarama yok)
- **Direktif:** Sinyal üretiminde loading Karot'un kendisi: 9 fitil yatay-nötr (θ=0) başlar, motor rapor verdikçe açısına döner. Skeleton = boş-Karot. Spinner, cyan-tarama beat'i, "durum-etiketli shimmer" kullanılmaz.
- **Token/değer:** başlangıç 9 fitil yatay-nötr (θ=0, kararsız hal) · fitil-dönüş stagger 50ms (izinli TEK stagger) · fitil easing `--dur-state` (180ms, `--ease-signal`) · cyan-tarama = YASAK.
- **Teknik:** Fitiller yatay-nötrden başlar; motor-önceliği sırasıyla (yukarıdan aşağı) açısına döner. Kaynak director-cut'taki "tek cyan tarama" beat'i KALDIRILDI (cyan-tarama AI-tropu ebedî yasak). Sinyal-Karot skeleton (boş-Karot = üretim başladı) grace'ten MUAF, her zaman gösterilir.
- **Ölçüm:** sinyal-loading'de spinner=0; cyan-tarama pattern=0; skeleton=boş-Karot render; fitil-dönüş süresi `--dur-state`.

### karot-14 · Lifecycle olayları omurgaya dokunmaz (durum katmanı)
- **Direktif:** Approaching/close olaylarını (TP-yaklaşma, invalidation) kartın DURUM KATMANINDA göster, omurgada DEĞİL. Omurga üretim anının kaydı; settle'dan sonra donar, statik kalır.
- **Token/değer:** omurga settle sonrası statik (idle 0 hareket) · lifecycle olayları kart durum katmanı (badge/şerit/durum), omurga dışı.
- **Teknik:** Karot omurgası sinyal doğum anının (9-motor konsensüs) sabit kaydıdır; doğduktan sonra oynamaz. approaching_tp/invalidating durum katmanında (lifecycle badge, közleşme, durum şeridi) gösterilir. Kapanış közleşmesi omurgaya dokunmaz (§01 micro-közleşme), durum katmanında yaşar; kayıp Sicil'de kalır.
- **Ölçüm:** lifecycle handler'ları omurga confs dizisine yazmaz; settle sonrası omurga statik (idle 0 animasyon).

### karot-15 · Geometry Freeze Rule (geometri dondurma)
> **SUPERSEDED (v1.7 · CP-KAROT-DOC)** — Geometry Freeze konusuz kaldı: Karot ürün-UI'dan kaldırılıyor. Dondurulacak yaşayan-varlık yok; geometri tarihsel kayıt. Bkz §05 baş-banner.
- **Direktif:** Bu revizyondan (v1.4) sonra Karot'un **geometrisi · slot sistemi · omurga · davranış kuralları DEĞİŞMEZ.** Geliştirme YALNIZ şu katmanlarda yapılır: Motion · Material · Rendering · Lighting · Interaction · Premium-Identity. Yeni geometri/davranış önerisi çıkarsa bu checkpoint kapsamında değil, gelecekte AYRI bir tasarım revizyonu olarak ele alınır.
- **Token/değer:** dondurulan = {fitil konum matematiği (karot-02) · 9-slot sıra (karot-04) · omurga+karar-ucu formu · classify eşikleri (karot-03) · hal imzaları (karot-05) · davranış yasaları}. Serbest katman = {motion · material · rendering · lighting · interaction · premium-identity}.
- **Teknik:** Y2 davranış yasası kilitli: **imleç kanıtı asla döndürmez** — hover yalnız lüminans (+1), fitil açısını değiştiremez (kanıt yalnız telemetriyle döner). Freeze, kimlik-kararlılığının (20-yıl) zorlayıcı fonksiyonudur; "daha iyi bir şekil buldum" gerekçesi bu checkpoint'te otomatik ertelenir.
- **Yeniden-açılma koşulu (TEK):** kritik kullanıcı-testi başarısızlığı — ölçülebilir tanım: karot-05/dash-40 yabancı-kör eşikleri (**16px silüet uzlaşan-vs-bölünmüş ≥%85 · 48px ≥%90**) ölçümle bu değerlerin ALTINA düşerse geometri yeniden açılabilir; başka hiçbir gerekçe (estetik/trend/tercih) geometriyi açmaz.
- **DoD:** v1.4 sonrası Karot geometri-değişikliği PR'ı yalnız "kritik-test-başarısızlığı" kanıtıyla kabul; aksi = red. Serbest-katman değişiklikleri (motion/render/…) freeze'e tabi değil.
- **Ölçüm:** geometri-token'ları (W/H/PAD/SPINE_X/L/θmax/step) değişiklik-PR'ında yabancı-kör test raporu zorunlu; rapor yoksa merge-blok.

### AI Thought Language (§05 · AI-Thought katmanı)

**AITL-01 · Renk tek kanal değil — durum çoklu-kodlanır (a11y).** Her lümen/durum/yön değerini renkten BAŞKA en az bir kanalla kodla: metin etiketi + ikon + konum (yön için +/− işaret ve ok ▲/▼). Renk tek ayırt edici değil; renk-körü/monokromda bilgi kaybı olmayacak.
- **Token/değer:** yön-glyph +/− + ok (▲/▼); `--bull #2FBE9A` / `--bear #E14640` (yalnız ikincil kanal); WCAG kanal-sayısı ≥2.
- **Ölçüm:** grayscale + 3 renk-körlüğü filtresi snapshot (her durum için metin/ikon/konum kanalı DOM'da assert); WCAG 1.4.1 PASS; kontrast ≥4.5:1 metin / ≥3:1 UI.
- **Migration (v1.1→v1.3):** `--bull #10B981 / --bear #F4556E → #2FBE9A / #E14640`.

**AITL-02 · AI sınırı görünür — cyan iz yoksa AI konuşmadı.** AI'nin dokunduğu her değere ve YALNIZ ona cyan iz (çizgi/nokta/omurga) eşdüşer; AI dokunmamış hiçbir değerde cyan görünmesin. Cyan yüzey/dolgu/zemin/buton/başlık olarak ASLA.
- **Token/değer:** `--cyan #25E0D4`; yalnız stroke/point/omurga.
- **Ölçüm:** CI-lint: cyan background/fill/surface = RED; cyan-taşıyan öge ↔ AI-alan eşlemesi 1:1.

**AITL-03 · Provenance her yerde — tek hover uzaklığında kaynak.** AI'nin dokunduğu her değer tek hover (veya `:focus-visible`) uzaklığında kaynağını gösterir: hangi motorlardan türedi, kaç motor hangi yönde. Çıplak sayı provenance'sız gösterilmez.
- **Token/değer:** provenance-hover payload `'{skor} ← {N} motor, {k}'i {yön}'` (ör. `skor 82 ← 9 motor, 3'ü SAT`); tetik hover + `:focus-visible`; giriş `--dur-warm` (140ms), anında çıkış.
- **Ölçüm:** AI-değer komponentlerinde provenance-tetik (hover+focus) assert; klavye-only provenance PASS; kaynak metni motor-dökümüne eşleşir.

**AITL-04 · AI muhakemesi dile taşınır — verbatim telemetri (design-paraphrase yasak, O1-revize).** Her motorun gerekçesini METİNLE ver; ancak provenance render'ı **motorun VERBATIM telemetri alanıdır** — design-layer paraphrase YASAK. AI hissini animasyon/efektten değil dilden üret. Cyan-tarama gibi soyut "AI düşünüyor" görseli KALICI YASAK.
- **Token/değer:** gerekçe = motorun verbatim telemetri alanı (ör. `SMC: FVG+likidite → SHORT .62`); güven [.00-1.00]; provenance kaynağı = stored `SignalSnapshot` alanı (snapshot-trace).
- **Teknik:** Provenance render'ı motorun ürettiği telemetri alanını olduğu gibi (verbatim) gösterir; tasarım katmanı bu metni yeniden-yazmaz/paraphrase etmez. Kaynak = stored `SignalSnapshot` alanına snapshot-trace (değer nereden geldi izlenebilir). **NOT:** ML-faithfulness (motorun gerçek muhakemesinin metne sadakati) tasarım-standardı DIŞIDIR → backend/model sorumluluğu; tasarım standardı yalnız "verbatim göster + snapshot-trace" garantisini kapsar.
- **Ölçüm:** cyan-tarama/idle-scan/radar-spin selektörleri CI-lint RED; motor-detay panelinde N-motor için N verbatim gerekçe sabit-sırada; provenance metni = stored snapshot alanı (design-layer string-transform=0).

**AITL-05 · AI fikir değiştirir — zaman ekseni (durum katmanında).** Bir motorun/konsensusun gün-gün dönüşünü görünür kıl (ör. `dün SHORT, 3 motor döndü → LONG bugün`). Dönüşüm kartın DURUM/ZAMAN katmanında; Karot omurgası üretim anının kaydıdır, statik.
- **Token/değer:** dönüş-metni `'dün {yön}, {N} motor döndü → {yön} bugün'`; zaman-çözünürlüğü gün; katman durum-katmanı (omurga DEĞİL).
- **Ölçüm:** dönüş senaryosunda durum-katmanı metni render + omurga geometrisi değişmez (üretim-anı snapshot'ına eşit) assert.

**AITL-06 · AI emin değil — no-birth / daima bölünmüş Karot.** Bazı sinyalde doğum OLMAZ — Karot bölünmüş kalır; belirsizliği galibiyet-yayına zorlama. İlk ekranda DAİMA ≥1 bölünmüş Karot. Sahte-kesinlik/temiz-galibiyet KALICI YASAK.
- **Token/değer:** no-birth koşulu eksen-geçiş≥2 OR absMean<0.30 → Bölünmüş (doğum yok); bölünmüş imza cyan omurga + tintsiz + karışık-açılı fitiller + eksen-üstü çift-nokta; ilk-ekran ≥1 bölünmüş.
- **Ölçüm:** eksen-geçiş≥2 (veya mean|conf|<0.3) girdide settle tetiklenmez + tint yok assert; ilk-ekran bölünmüş-Karot ≥1 assert.

### Signals — Kalıcı Yasaklar
Radar/örümcek/donut/bar (sinyal-konsensüs) · cyan-tarama AI-tropu · idle-tarama · dönen-radar · sahte-kesinlik/temiz-galibiyet-yayı = kalıcı YASAK. Şiirsel iç-dil (Karot/közleşme/omurga/su-hattı/kesim-dudağı) UI'a çıkmaz (G-08-13).

---

## 06 · Motion

App'te varsayılan **sükûnet**; hareket yalnız gerçek telemetri olayında. Her animasyon bir telemetri alanını isimlendirir. Süre rejimi **tek**: ayrık token seti (aralık yok); süre uydurmak, token setini aşmak lint-red'dir.

### MO-01 · Süre kilidi — tek rejim, ayrık token merdiveni
- **Direktif:** Her motion tipi kendi ayrık süre token'ını kullanır; aralık kullanma, ara-değer uydurma, token setini genişletme. Layout (width/height/top/left/margin) ASLA animasyonlanmaz. Uygulama katmanında hiçbir motion 600ms sert-tavanı aşamaz (overlay tavanı aşmaz).
- **Token/değer:**

| Token | Süre | Kullanım |
|---|---|---|
| `--dur-micro` | `140ms` | Hover ısınma + press-feedback (mikro etkileşim) |
| `--dur-state` | `180ms` | Aç/kapa/geçiş (dropdown/tooltip/panel state); Karot fitil-dönüşü bu banda oturur (`--ease-signal`) |
| `--dur-photon` | `150ms` | Sayı güncelleme (color/luminance flaşı; konum/scale sabit) |
| `--dur-warm` | `140ms` | Yüzey ısınma (kart/satır +1 luminans), ease-out |
| `--dur-settle` | `520ms` | Karot doğum omurga-oturması (spring; ≤600ms sert-tavan içinde) |
| `--dur-route` | `180ms` | Route ışık-devri (layout-anim yok) |
| `--dur-overlay` | `360ms` | Overlay spring settle wall-clock (stiffness ~300 / damping ~30; tekil değer, tavan aşmaz) |
| stagger | `50ms` | Liste-giriş + Karot motor-oyu (tek anlamlı stagger; nokta-değer) |
| press-scale | `.985` (lg) / `.96` (sm) | Süre = `--dur-micro` |
| follow-through | `--dur-photon` (150ms) | Foton takip-sönümü |

- **Teknik:** `--dur-micro` ve `--dur-warm` sayısal olarak eşittir (140ms) ama ayrı isimlendirilir (anlam ayrımı: etkileşim-geri-bildirimi vs. yüzey-ısınma) → migration ve review'da rol izlenebilir kalır. Overlay spring tek `--dur-overlay` (360ms) wall-clock ile ifade edilir; eski "≤~400ms" ifadesi 360ms tekil değere sabitlendi. Aralık YOK: her komponentin transition-duration'ı bu setin bir üyesine birebir eşit olmalı.
- **DoD:** Tüm `transition-duration`/`animation-duration` değerleri `{--dur-micro 140, --dur-state 180, --dur-photon 150, --dur-warm 140, --dur-settle 520, --dur-route 180, --dur-overlay 360, stagger 50}` setinden birine birebir eşit; set-dışı değer = lint-red; en uzun app-motion ≤600ms; layout-property animasyonu = 0.
- **Ölçüm:** CI-lint (§08 gate-5): computed `transition-duration ∈ {140,150,180,360,520}ms` + stagger 50ms; set-dışı süre build-red; en uzun app-motion wall-clock ≤600ms (DevTools perf-trace); layout-anim node=0.
- **Migration (v1.1→v1.3):** Süre-aralıkları (120–160 / 150–200 / ~500 / ~400 / ≤60) **kaldırıldı** → tek-rejim ayrık token. Overlay `≤~400ms → --dur-overlay 360ms` tekil. `dur-micro` alt-kalemleri (ısınma/press) tek 140ms'ye; `dur-route` 150–200 → 180ms; `dur-doğum` ~500 → `--dur-settle 520ms`.

### MO-02 · Easing imzası — sahipli `--ease-signal` + spring çifti
- **Direktif:** GPU-güvenli özelliklerle animasyonla; giren ease-out, çıkan ease-in; hazır ease-in-out ASLA; micro/stagger'da `--ease-signal`; Karot settle'da spring.
- **Token/değer:** `--ease-signal: cubic-bezier(.2,.8,.2,1)`; giriş ease-out / çıkış ease-in; Karot settle spring; overlay spring (stiffness ~300 / damping ~30, settle = `--dur-overlay` 360ms).
- **Teknik:** İki easing dili: (1) micro + liste-giriş stagger = `--ease-signal`; (2) Karot doğum omurga-oturması + overlay = spring. Yalnız `transform` + `opacity` animasyonlanır (foton için `color`/`opacity` 150ms tek istisna). Blur/filter ASLA animasyonlanmaz.
- **Ölçüm:** `grep 'ease-in-out'`=0 (CI-red); `cubic-bezier(.2,.8,.2,1)` yalnız `--ease-signal` tanımında; animasyonlanan property whitelist `{transform, opacity}` + foton `{color, opacity}`; @keyframes/transition içinde `blur`/`filter`=0.

### MO-03 · Karot doğum (settle) koreografisi — çift-easing tek atım
- **Direktif:** Son motor raporlanınca fitiller açısına dönsün + karar-ucu TEK yay ile otursun; fitil-dönüşü 50ms stagger, karar-ucu settle spring; bir kez oynat, ASLA geri sarma.
- **Token/değer:** fitil-dönüş stagger 50ms + `--ease-signal` · karar-ucu-settle spring `--dur-settle` (520ms, ≤600ms) · uzlaşma → yön tinti zarf-akışı + kalıcı cyan karar-ucu.
- **Teknik:** (1) 9 fitil yatay-nötrden açısına 50ms stagger (`--ease-signal`); (2) karar-ucu tek yay (spring, `--dur-settle`). Uzlaşmada yön tinti zarfa akar + kalıcı cyan karar-ucu; bölünmüş/kararsızda renk yok. Tek atım; sonra statik, geri sarılmaz.
- **Spring sayısal sınır (O11):** Spring damping ~30 rejiminde tepe-aşım (overshoot) **≤%8** (hedef konumun %8'inden fazla aşmaz); settle-toleransı **≤0.5px** (bu bandda "oturmuş" sayılır, animasyon durur). Overshoot >%8 veya salınım kuyruğu >0.5px = ayar-hatası (review-red).
- **Ölçüm:** settle ≤600ms; fitil stagger 50±10ms; `animation-iteration-count=1`; reduced-motion'da statik son-kare (doğum posteri); uzlaşma→karar-ucu var, bölünmüş→karar-ucu yok; karar-ucu açı-overshoot ölçülen ≤%8, settle-tolerans ≤0.5px.

### MO-03b · Eş-zamanlı settle bütçesi (40-Karot performans sözleşmesi) — *O11*
- **Direktif:** Hero/dashboard'da ~40 Karot eş-zamanlı doğsa bile settle'lar tek frame'de yığılmasın; transform/opacity-only GPU kompozisyonu + 50ms stagger ile settle'ları pencereye yay; dropped-frame üretme.
- **Token/değer:** eş-zamanlı-settle GPU property'leri = `{transform, opacity}` only · 50ms stagger penceresi · aynı frame'de aktif settle ≤~8 (16.67ms frame bütçesi) · hedef 60fps.
- **Teknik:** 50ms stagger, 40 doğumu zaman-eksenine yayar → herhangi bir 16.67ms frame'de aynı anda ≤~8 aktif settle kalır. Yalnız `transform`/`opacity` animasyonlandığı için her settle GPU-kompozit katmanında koşar (layout/paint yok). Reflow tetikleyen property (width/height/top) yasağı burada da geçerli.
- **Ölçüm (DoD):** DevTools performance-trace altında 40-Karot eş-zamanlı doğum senaryosunda **dropped-frame = 0**; herhangi bir frame'de aktif settle sayısı ≤~8; animasyonlanan property yalnız transform/opacity (paint/layout kaydı=0).

### MO-04 · App motion doktrini — idle sessizlik + event-only
- **Direktif:** App'te varsayılan sessizlik; yalnız gerçek telemetri olayında tek atım (≤600ms, transform/opacity-only, kaynağı backend); ambient/paralaks/scroll-reveal/autoplay/count-up/dekoratif-döngü app'te YASAK.
- **Token/değer:** olay atımı ≤600ms · transform/opacity-only · izinli tek anlamlı stagger = Karot sıralı motor oyu (50ms) · reduced-motion → statik (bilgi kaybı yok).
- **Teknik:** App idle'da sıfır ambient. İzinli: micro-etkileşim, foton, backend telemetri olayına kilitli tek atım (Karot doğum, approaching/invalidation durum-katmanı). Sahte olay üretilemez.
- **İdle-sessizlik kararı (D5-red):** App idle-SESSİZLİĞİ kanoniktir; **"her yüklemede settle-replay"** önerisi REDDEDİLDİ (dekoratiftir: gerçek telemetri olayı olmadan hareket üretir, MO-05'i ihlal eder). Settle YALNIZ ait olduğu yerde — gerçek doğum olayında — oynar. Hero canlı-konsensüs masası settle'ı gerçek-olay havuzundan (yeni doğan sinyaller) besler; app-route yeniden-yüklemesinde koreografi tetiklenmez. Yani "canlılık" sahte-replay ile değil, gerçek olay akışıyla gelir.
- **Ölçüm:** app-route'ta `animation-iteration-count:infinite`=0; scroll-linked animasyon=0 (Karot dışı); count-up=0; sayfa-yeniden-yüklemesinde settle-koreografisi tetiklenmez (yalnız gerçek doğum olayı tetikler); her app-motion bir telemetri kaynağına bağlı (isimsiz motion CI-red).

### MO-05 · Motion kaynağı isimlendirilir — anlamsız hareket yasağı
- **Direktif:** Her animasyon bir telemetri alanını isimlendirmeli; isimsiz/dekoratif motion kaldırılır. Her hareket üç sorudan birini yanıtlamalı: ne değişti / nereden geldi / ne yapabilirim.
- **Teknik:** Motion review turnusolü: (a) hangi telemetri alanı, (b) hangi soru — ikisi de yazılamıyorsa kaldırılır. "Güzel/canlı hissettiriyor" gerekçe değildir (MO-04 uygulama kapısı; §00 G-00-07 ile aynı ruh).
- **Ölçüm:** review checklist: her animasyon için `{kaynak-telemetri-alanı, yanıtladığı-soru}` zorunlu; boş = merge-blok.

### MO-07 · Frekans / sükûnet bütçesi (Rauno)
- **Direktif:** Yüksek-frekans güncellemeleri (canlı fiyat, cmdK) animasyonsuz bırak — foton yeter; hareketi düşük-frekans/yıkıcı olaylara sakla; kesilebilir jestte momentum koru; yaş>eşik → statik.
- **Token/değer:** viewport başına ≤1 ambient (yalnız landing) · yüksek-frekans → foton `--dur-photon` (150ms) · düşük-frekans olay → ayrılmış mikro-hareket ≤600ms · yaş>X → statik.
- **Teknik:** Sık güncellenen değerler yalnız foton (150ms, konum sabit). Nadir/yıkıcı olaylar ayrılmış mikro-hareket alır (hareket dikkat çeker çünkü nadirdir). Aynı satırda ≥2 canlı sayı foton'ları senkronize EDİLMEZ. **Noise (toz) STATİK'tir, ambient-animasyon sayılmaz;** landing tek animasyonlu ambient = glow-drift (L1 0.92×). Ambient-sayım (≤1) ile squint vurgu-sayım (≤2) AYRI bütçedir; ambient daima loş/yönlü, vurgu bütçesine girmez.
- **Ölçüm:** canlı fiyat güncellemesinde layout-shift=0, yalnız opacity/color (150ms); landing ambient ≤1; foton tetikleyicileri per-hücre bağımsız.

### MO-08 · Route geçişi — "ışık devri" (jenerik fade değil)
- **Direktif:** Sayfa geçişini jenerik fade ile YAPMA; "ışık devri": giden sayfa ease-in ile karar, gelen ease-out ile aydınlanır. Devir E-basamağı sayımıyla değil **min-ΔL kuralıyla** ölçülür (aşağıda). View Transitions API bu aşamada KULLANILMAZ.
- **Token/değer:** route geçişi `--dur-route` (180ms) · giden −%8 L (ease-in) · gelen +%6 L (ease-out) · layout-anim yok · View Transitions API → kullanılmaz.
- **Teknik (D1 — min-ΔL kuralı):** Işık-devri artık soyut "−1/+1 E-basamağı" ile değil, **computed-lightness delta** ile tanımlanır: giden yüzeyin ölçülen L (OKLCH lightness) değeri **≥%8 düşer**, gelen yüzeyin L değeri **≥%6 artar**. Bu deltalar algı-eşiğinin (just-noticeable difference) üzerindedir → devir gözle okunur, ölçülebilir ve E-basamağı merdiveninin ara-durumlarında da geçerlidir. Yalnız `opacity`/`transform` ile taşınır; layout yazılmaz.
- **Ölçüm:** `grep 'startViewTransition|view-transition-name'`=0; süre = `--dur-route` 180ms; CLS=0; **giden computed-L delta ≤ −%8, gelen computed-L delta ≥ +%6 (before/after DoD-assert)**.
- **Migration (v1.1→v1.3):** v1.1 "route geçişi fade/opacity" → ışık-devri; "−1/+1 E-basamağı" ifadesi → **min-ΔL kuralı (−%8 / +%6 computed-lightness)** ile netleştirildi; View Transitions API açık-uç (ileri tarayıcı-destek revizyonunda).

### MO-09 · Liste-giriş stagger — ≤50ms izin, tek anlamlı stagger istisnası
- **Direktif:** Liste-giriş stagger'ına 50ms izin ver; app'te izinli TEK anlamlı stagger = Karot sıralı motor oylaması (50ms); dışında app'te stagger yasağı sürer.
- **Token/değer:** liste-giriş stagger 50ms · Karot motor-oyu stagger 50ms (tek nokta-değer; eski ≤60ms aralığı kaldırıldı, süre-kilidiyle hizalı).
- **Ölçüm:** liste-giriş gecikmeleri 50ms bir kez (loop yok); Karot fitil-dönüş stagger 50±10ms; app-route stagger yalnız `{liste-giriş, Karot-fitil}`.

### MO-10 · Global scroll — smooth + reduced-motion auto (scroll-jacking yasağı)
- **Direktif:** `html scroll-behavior:smooth`; `prefers-reduced-motion:reduce → auto`. Scroll yön/hızını ASLA ele geçirme — scroll-jacking, wheel-intercept, zorunlu-snap, Lenis ebedî YASAK.
- **Token/değer:** `html{scroll-behavior:smooth}` · reduced-motion `auto` · scroll-jacking/wheel-intercept/zorunlu-snap/Lenis → kalıcı yasak.
- **Ölçüm:** `grep 'lenis|smooth-scroll'` import=0; wheel/touchmove `preventDefault` hız-hijack=review-red; `scroll-snap-type:*mandatory` pin-sahne ≤0 (landing tek pin istisnası hariç); reduced-motion'da bilgi kaybı=0.

### MO-11 · Parallax — yalnız landing, anlamlı analiz-katmanı temsili
- **Direktif:** Paralaksı yalnız landing'de ve yalnız analiz-katmanı temsili olarak kullan; maks 3 strata, hız farkı ≤0.06, transform-only; app'te paralaks YASAK.
- **Token/değer:** landing-only · maks 3 strata · hız farkı ≤0.06 · transform-only · L1 glow-drift 0.92× · app → yasak.
- **Ölçüm:** strata ≤3; katman hız oranı ≥0.94; app-route'ta scroll-linked transform (paralaks)=0; paralaks bileşeni yalnız landing tree'sinde.
- **Migration (v1.1→v1.3):** eski dekoratif hero-parallax taşıyıcısı atıldı; yaşayan-Hero rolü VL§11 WebGL'siz revizyonunda yeniden tanımlanır (açık uç).

### MO-12 · Karot idle — sessizlik (sıfır hareket) bir özelliktir
- **Direktif:** Idle'da son hesaplanan omurgayı dinlenme luminansında STATİK tut; sıfır hareket. Durgun ekran özelliktir (sükûnet=güven, panik-arayüzü reddi).
- **Token/değer:** idle → statik omurga · dinlenme luminansı · 0 hareket.
- **Teknik:** Settle sonrası omurga donar; idle'da pulse/shimmer/drift yok. Lifecycle olayları omurgaya DEĞİL durum-katmanına. **Uzlaşma glow underlay idle'da statik (0.14 sabit, animasyon yok) AMA yalnız scale≥1 VE tekil/seçili-odakta; 16px yoğunluk yüzeyinde KAPALI** → 40-Karot (16px) glow-suz, squint ≤2 korunur.
- **Ölçüm:** idle Karot'ta animasyon/transition=0; rAF idle'da çalışmıyor; 60sn idle'da piksel-değişimi 0 (foton/olay dışı).

### Motion — Kalıcı Yasaklar
**MO-06.** ASLA: sonsuz pulse · dönen radar · idle-tarama beat'i · sahte/gecikmeli progress · cyan-tarama AI tropu · autoplay dekoratif döngü · marquee · konfeti/particle-burst kutlama. Ebedî yasak.
- **Teknik:** AI-hissi renk/tarama animasyonundan DEĞİL, isimlendirilmiş telemetri zinciri + provenance dilinden gelir. Finans-ciddiyeti gereği kutlama = tek-bütçeli amber "gurur anı" (olay-bağlı, ≤600ms) yeter.
- **Ölçüm:** `animation-iteration-count:infinite` (Karot-dışı, izinli-liste dışı)=CI-red; 'scan'/'tarama' overlay=red; konfeti/confetti/particle kütüphanesi=red; kutlama ≤600ms tek atım.

### Interaction dili (§06/§01 · Interaction katmanı)

**INT-01 · Hover dili — tek lehçe, iki bağlam.** Tek hover lehçesi "ısınma"; iki bağlam: (a) YÜZEY-ISINMA (kart/panel/tile) = +1 luminans (E1→E2) + translateY(−2px), `--dur-warm` (140ms) ease-out; (b) SATIR-ISINMA (tablo/liste satırı) = YALNIZ +1 luminans, SIFIR transform (satır asla zıplamaz). Kart/ikon/başlık/panel hover'da ASLA glow; hover-glow yalnız birincil CTA.
- **Ölçüm:** tablo satırı hover computed transform===identity; kart hover translateY===−2px; `grep 'hover:bg-white|hover:bg-accent-secondary|hover:bg-indigo'`=0; hover-glow lint (kart/panel hover box-shadow yasağı); timing `--dur-warm` 140ms.
- **Migration (v1.1→v1.3):** eski 6 hover lehçesi (white/[.02–.10], cyan'a dönen primary, üç-ton border) emekli → tek "ısınma".

**INT-12 · Focus ring — 2px accent-ui ring her etkileşimlide (TEK kanonik).** TÜM etkileşimlide (buton, input, link, Dropdown, Modal, Karot dâhil) focus = 2px accent-ui ring; net (haze/blur değil). Klavye her yeri gezebilmeli.
- **Token/değer:** `outline: 2px solid var(--accent-ui) #4E6BE3; outline-offset: 2px`. YASAK: ring-3 / 3px jenerik.
- **Teknik:** Focus-ring 1px-UI rolüdür (metin/dolgu değil); bu yüzden `--accent` (#3B57D4, yalnız dolgu; E2/E3'te 1px-UI olarak 2.90/2.62 FAIL) DEĞİL, **a11y-türevi `--accent-ui` #4E6BE3** kullanılır (E0–E3 hepsi ≥3: 4.25/4.04/3.76/3.39). Bu kimlik değişikliği değil, erişilebilirlik-zorunlu accent türevidir (aynı owned-blue ailesi).
- **Ölçüm:** focus-visible computed outline-width===2px + color `--accent-ui`; `grep 'ring-3|outline.*3px'`(focus)=0; Karot tab-erişilebilirlik a11y testi; focus-ring'de `--accent` (#3B57D4) 1px-UI kullanımı=0 (accent-ui'ye migrate).
- **Not:** craft-v2 ve G-08-20 buna referans verir (drift yok).

**INT-08 · cmdK / klavye modeli — SPEC + güvenli varsayılan.** MVP/beta için cmdK affordance gösterilmez (rozet-kaldırma güvenli varsayılan): gerçek çalışan palette yoksa hiçbir yerde ⌘K rozeti/kısayol/yarı-durum (çizili ama handler yok) YOK. Tam-palette implementasyonu bir **milestone**'dur; seçildiğinde aşağıdaki spec bağlayıcıdır.
- **Palette IA (komut grupları):** komutlar anlamlı gruplara ayrılır (ör. Git/Ara · Sinyaller · Görünüm/Yoğunluk · Hesap); grup başlıkları uppercase mikro-etiket (`--tx2`, 500). AI-önerili sonuçlarda cyan iz (AITL-02'ye tabi; cyan yalnız iz, yüzey değil).
- **Gezinme:** `j`/`k` (ve ok tuşları) ile liste gezinme; `roving-tabindex` (tek tab-durağı, aktif öğe içeride ok'la gezilir); Enter=çalıştır.
- **ESC katman-sırası:** `overlay > palette > modal` — ESC en üstteki katmanı kapatır (overlay açıksa önce o, sonra palette, sonra modal); katman-sırası tek kaynakta sabit.
- **Yüzey/motion:** E3 cam + backdrop-blur (E3-only) + overlay spring (stiffness ~300 / damping ~30, `--dur-overlay` 360ms); `radius-panel`; focus-trap.
- **Kısayol keşfi:** `?` tuşu kısayol-cheatsheet'i açar (tüm klavye kısayollarının listesi); cheatsheet de aynı E3 overlay dilinde.
- **Ölçüm:** `grep '⌘K|cmd-k|Cmd\+K'` rozeti=0 (gerçek palette yoksa); tam-palette seçilirse ⌘K keydown→palette mount; `j`/`k` navigation + roving-tabindex (tek tab-durağı) assert; ESC katman-sırası (overlay>palette>modal) testi PASS; `?`→cheatsheet mount; AI-öneri satırında cyan yalnız iz (background/fill cyan=0).

---

## 07 · Öncelik · P0 / P1 / P2

**P0 — Beta öncesi zorunlu (dürüstlük + profesyonellik + hukuki hijyen):**
- Sahte veriyi sil (sabit delta'lar + sentetik market-cap grafiği). Dev-mesajlarını temizle.
- Ödeme hunisini beta'da kapat (pricing "yakında" · Yükselt gizle · checkout kapalı · waiver-consent yok).
- Legal placeholder'ları doldur + "taslak" kaldır + Help gerçek destek kanalı.
- İşlevsiz/yalancı sekmeler kaldır · error-state (`micro-error-state`) ekle · risk disclaimer dashboard'a.
- "BETA" kimliği · sayı chip'lerine birim · over-claim temizliği.

**P1 — Kalite sıçraması:**
- Tasarım-sistemi tek-kaynak: owned palet (E0–E3 + bull/bear/accent/accent-ui/accent-hover/cyan/amber) + hairline merdiveni + `tailwind-merge` + `next/font` + tabular-nums.
- Yaşayan Hero (canlı konsensüs masası) + tek CTA + SSR (spinner-gate kaldır).
- Karot enstrümanı (§05): parametrik render + 3 hal + 3 ölçek + provenance-hover.
- Mobil: tabloları kart-laştır + `sm:` katmanı + CTA/dropdown taşma.
- A11y: modalları dialog · ikon-buton aria-label · 2px accent-ui focus ring (INT-12) · dead butonlar.
- Kart/badge birleştirme · içerik-swap durdur · "PATLADI"→"STOP OLDU" · közleşme.
- Motion katmanı-1: micro (CSS ısınma/foton) + Karot settle (spring, `--dur-settle`); app idle-sessiz; süre-kilidi (ayrık token) uygulanır.

**P2 — Beta sonrası olgunlaşma:**
- Refactor: signals God-file + çift çeviri katmanı + api.ts böl.
- Performans: canlı-fiyat batch-render + WS churn + chart lib code-split + polling ayır; 40-Karot eş-zamanlı-settle bütçesi (MO-03b, dropped-frame=0) doğrulanır.
- Motion katmanı-2/3: route ışık-devri (`--dur-route` 180ms, MO-08, min-ΔL) + landing scroll-reveal; Markets heatmap.
- Paylaşılan primitifler: Dropdown (14 native select → INT-07) · Toast (INT-09) · Modal (INT-10) · Empty (Olay Defteri) · cmdK/klavye-modeli milestone (INT-08).

---

## 08 · Governance & Definition of Done

### Standart
Her yeni ekran bu Bible + VL'ye göre geliştirilir. Yeni renk/spacing/komponent gerekiyorsa **önce buraya token eklenir**, sonra kullanılır. Repo'da var olan doğru desen çoğaltılır, yeniden icat edilmez.

### Belge repo statüsü + kanoniklik (G-08-21 · C1/C2)
- **Direktif:** 5 strateji belgesini (director-cut/ruthless-correction/premium-extension vb.) YÜRÜRLÜKTE SAYMA; docs/design geçerlidir. Kanoniklik yalnız C1 (çift-ev) + C2 (sürümleme) ile.
- **C1 (çift-ev):** İki belge çeliştiğinde atmosfer/ışık/motion → **VL** kanonik; token/komponent/layout → **Bible** kanonik; aynı konuda çelişki → **daha kısıtlayıcı kural kazanır** ve her iki belgede aynı revizyonla giderilir.
- **C2 (sürümleme):** Revizyon = commit + sürüm artışı + CHANGELOG satırı; dosya adları sabit, sürüm başlıkta + CHANGELOG'da.
- **Ölçüm:** her normatif değişiklik için CHANGELOG satırı + sürüm artışı var; strateji-belgesi normatif-referans=0.

### Şiirsel adlar iç-dil (G-08-13)
Karot / közleşme / omurga / su-hattı / kesim-dudağı yalnız ekip iç-dilinde; UI metnine/etikete/tooltip'e ASLA çıkmaz.
- **Ölçüm:** UI string taraması: ('Karot','közleşme','omurga','su hattı','kesim dudağı') eşleşme=0.

### Jüri/Higgsfield süreci belgeye işlenmez (G-08-18 · *nitel-gate*)
K1 (Lümen Defteri kazanan konsept) ve Higgsfield süreci standarda madde olarak işlenmez; Higgsfield yalnız ref (konsept/storyboard/motion/3D/materyal), asla asset-kopya.
- **Ölçüm:** *Ölçüm-yok / nitel-gate.* Belgede süreç-kayıt maddesi=0; üründe Higgsfield-kopya asset=0.

### Dark-only; light-tema = kayıtlı bilinçli erteleme (G-08-19)
Ürün dark-only (E0–E3 near-black); light-tema üretilmez. Bu "unutuldu" değil **"bilinçli ertelendi"** — ileride sürüm revizyonuyla açılabilir.
- **Ölçüm:** §08'de light-tema erteleme notu var; kodda light-theme token seti=yok.

### Gerçek Lint Katmanı — 5 somut gate (K4)
Kimliği kod düzeyinde koruyan **beş fonksiyonel lint kuralı**; `stylelint` + custom-plugin ile **pre-commit + PR-gate** olarak koşar. Herhangi biri fail → build-red / merge-blok.

1. **token-dışı-hex.** Ham `#hex` YALNIZ `:root` (token tanımı) içinde; component/utility katmanında ham hex = RED. Renk yalnız `var(--token)` üzerinden.
   - *Ölçüm:* component/module dosyalarında `:root` dışı ham `#hex` eşleşmesi=0.
2. **renkli-glow-rgba.** `box-shadow`/`filter` içinde token-dışı renkli `rgba(...)` (accent/cyan/amber owned hue dışı, ör. `rgba(0,230,118,·)`/`rgba(255,82,82,·)`) = RED; parlaklık yalnız glow token ailesinden.
   - *Ölçüm:* `grep 'rgba(0,230,118|rgba(255,82,82'`=0; ham renkli box-shadow build-red.
3. **cyan-yüzey.** `background`/`fill` = cyan = RED; cyan YALNIZ `stroke`/1px iz (AITL-02). Karot omurga çizgisi cyan-stroke istisnası (yüzey değil).
   - *Ölçüm:* cyan `background`/`fill`/`surface`=0; cyan yalnız stroke/point/omurga.
4. **kırpılmış-eksen.** Chart baseline `min != 0` (dürüst-min dışı) = RED; kural chart config AST/schema düzeyinde denetlenir (Lie Factor=1).
   - *Ölçüm:* chart config'te kırpılmış-eksen (baseline min≠0/dürüst-min)=0.
5. **süre-kümesi.** `transition-duration`/`animation-duration` süre-token setinin (`{140,150,180,360,520}ms` + stagger 50ms) DIŞINDA = RED (MO-01).
   - *Ölçüm:* set-dışı süre=0; her süre token setine birebir eşleşir.

**Glow/blur muafiyeti — data-instrument kancası (K5):** Karot enstrümanının kendi ışık-underlay'i (statik ≤.14 blur, cyan-omurga ışık-genişletmesi) yukarıdaki gate-2/gate-3 ve blur-yalnız-E3 kuralından **muaftır** — ANCAK muafiyet YALNIZCA `data-instrument="karot"` özniteliği taşıyan SVG düğümünde geçerlidir. Lint muafiyeti bu öznitelikle sınırlıdır; hiçbir serbest node muaf değildir. Gelecekte yeni bir enstrüman muafiyet gerekirse `data-instrument="<ad>"` ile aynı tek-kurala girer (öznitelik-kapılı muafiyet; genişleme kontrollü).
- *Ölçüm:* enstrüman-muafiyeti uygulanan her düğümde `[data-instrument]` mevcut; öznitelik-siz muaf-görünümlü glow/blur node=0.

### Migration Map (v1.1 → v1.3)
Tam Migration Map AYRI belgede tutulur (tek kaynak: `docs/design/MIGRATION-MAP-v1.3.md`); burada yalnız tek-satır işaret. **Kapanış kriteri (özet):** `grep '#020817|#0A101C|#000000|#10B981|#F4556E|#F0564B|#3B82F6|#2563EB|indigo|#22D3EE|#FBBF24|#f97316'` (src+public) → **0**; `en-US` yalnız `lib/utils.ts`'te tr-TR'ye döner; focus-ring/nav/input-focus → `--accent-ui`; TradingView widget'ının tam tema eşlemesi (zemin dışı) bu haritanın dışıdır (Rev-2/M16).

### Logo-kapalı tanınırlık testi (G-08-05 · P2 zorlayıcı fonksiyon) · *açık uç: baseline "geçmez"*
- **Direktif:** Kimliği logo kapalıyken yalnız ekran görüntüsünden "bu TradeMinds" dedirtecek şekilde kur; taşıyıcılar **(v1.7 · CP-KAROT-DOC — Karot silüeti ÇIKARILDI):** kabin-imzası (yüzey-merdiveni / hairline / köşe-dili) + instrument-well + proof-receipt kompozisyonu + `--e0 #070B14` near-black + terminal-renk paleti (bull `#2FBE9A` / bear `#E14640` / cyan `#25E0D4`) + sahipli tabular numeral. Kimlik artık bir glyph/işaret'e değil **kompozisyon + veri-hiyerarşisine** dayanır; logo-kapalı tanınma sahipli-font + kabin-imzası yerleşene dek açık kimlik-borcu (release-blokaj değil).
- **DoD:** Çeyreklik denetimde logo maskelenmiş 3+ ekran dış gözlemciye "TradeMinds" olarak tanınabiliyor; tanınmıyorsa açık borç (release-blokaj değil, kimlik-borcu).
- **Ölçüm:** N gözlemciden doğru marka-atfı oranı; **şuanki baseline = "geçmez" (kayıtlı borç)**; ilk kilometre-taşı (font+silüet üretimi) sonrası hedef ≥%40, çeyreklik artan.

### Özgünlük ölçümü — sertleştirilmiş line-up protokolü (O10 · G-00-04 tek kapı)
Özgünlüğün TEK ölçüm kapısı G-00-04 screenshot line-up'tır (G-00-16/G-08-18 nitel-notları buna bağlanır). Protokol sertleştirildi:
- **Örneklem ≥5 ekran:** yalnız sinyal-yoğun ekran değil, **Karot-maskeli** ekranlar da dâhil (Sicil/Markets/Ayarlar dahil ≥5 farklı ekran). Karot maskelendiğinde ekranın özgünlüğü **kabin-imzası (yüzey merdiveni/hairline/köşe dili) + tipografi (tabular numeral kahraman) + renk (owned E0–E3 + terminal paleti)** üzerinden okunur.
- **Gözlemci-N ≥5:** en az beş bağımsız dış gözlemci.
- **Eşik ≥%60 ayırt-etme:** ekranın kategori/ürün olarak ayırt-edilme oranı ≥%60; altına düşerse release bloklanır.
- **Kıyas-seti iki-katmanlı:** hem **rakip-fintech** (TradingView/Matriks/Midas + genel SaaS-fintech) hem **genel bilgi-görsel kanonu** (jenerik dashboard/veri-görsel dili) ile karşılaştırılır — yalnız rakibe değil, tür-geneline karşı ayrışma aranır.
- **Ölçüm:** çeyreklik line-up log kaydı: ≥5 ekran (≥1'i Karot-maskeli) × ≥5 gözlemci; ayırt-etme oranı ≥%60; iki kıyas-katmanı da uygulandı (var/yok). Eşik-altı = release-blokaj.

### DoD korunma sözleşmesi — 5 zorlayıcı fonksiyon (G-08-20)
Kimliği aşındırmaya karşı 5 DoD kapısı istisnasız uygulanır. Herhangi biri fail → **release-blokaj**.

1. **Lümen/glow lint (CI-red).** Ham box-shadow / renkli glow-rgba (accent/cyan/amber token dışı hue) CI'da RED; parlaklık yalnız token ailesinden (K4 gate-1/2; Karot muafiyeti K5 `data-instrument`).
   - *Ölçüm:* CI-lint pass/fail; `grep 'rgba(0,230,118|rgba(255,82,82'`=0.
2. **Karot zorunluluğu.** Her sinyal yüzeyinde Karot primitifi.
   - *Ölçüm:* Karot-eksik sinyal-yüzeyi=0 (grep).
3. **Screenshot line-up (çeyreklik yabancı-kör).** Ekran rakiplerden (TradingView/Matriks/Midas) + genel görsel kanondan ayırt edilebilir (G-00-04 / O10 protokolü: ≥5 ekran, ≥5 gözlemci, ≥%60).
   - *Ölçüm:* çeyreklik line-up log kaydı; eşik-altı → release bloklanır.
4. **Squint testi.** En parlak iki öge yalnız enstrüman (Karot) + CTA.
   - *Ölçüm:* squint: en parlak 2 piksel-grubu = Karot+CTA (evet/hayır).
5. **WebAIM-kilit.** Tüm semantik hex E0–E3'e karşı rol-eşiğini geçer (metin ≥4.5:1 / UI ≥3:1); 20-hücre tablosu doldu → renk kilidi AÇIK (COL-11).
   - *Ölçüm:* WebAIM oranı: metin ≥4.5:1, UI ≥3:1; 20/20 hücre PASS.

### Definition of Done (görsel) — v1.3
Her ekran/komponent PR'ında:
1. **Token'dan türer** (hardcode renk/spacing yok; owned palet E0–E3 + semantik + `--accent`/`--accent-ui`/`--accent-hover` + hairline merdiveni); ham hex yalnız `:root` (K4 gate-1).
2. **3 state ayrı ve dürüst** (loading=boş-Karot skeleton · empty=Olay Defteri · error="—"+neden+tekrar-dene; asla 0/%0).
3. **Mobil doğrulandı** (`sm`+ · tablo→kart · touch 44px).
4. **A11y:** aria-label · dialog · 2px `--accent-ui` focus ring (INT-12) · kontrast AA (`--tx3` okunur metinde yasak) · renk tek kanal değil (AITL-01, WCAG 1.4.1).
5. **Motion doktrini:** app idle-sessiz; her animasyon telemetri-kaynağına bağlı (MO-05); süre ayrık-token setinden (MO-01, K4 gate-5); `reduced-motion` korumalı; ease-in-out yok; layout animasyonlanmaz; 40-Karot eş-zamanlı-settle dropped-frame=0 (MO-03b).
6. **Sahte/placeholder/dev-metni yok** (Lie Factor=1; kırpılmamış baseline K4 gate-4; közleşme görünür).
7. **App'te ambient/paralaks/scroll-efekti yok** (dash-ambient-yasak); viewport başına vurgu ≤2; landing ambient ≤1 (glow-drift), noise statik.
8. **Cyan yalnız çizgi/nokta/iz** (AI değeri); yüzey/dolgu/buton/başlık yasak (AITL-02, K4 gate-3).
9. **Squint testi:** en parlak pikseller = enstrüman (Karot) + CTA.
10. **Karot zorunlu** her sinyal yüzeyinde; şiirsel iç-dil UI'da yok (G-08-13); enstrüman glow/blur muafiyeti yalnız `data-instrument="karot"` (K5).
11. **10-katman tutarlılık satırı** işaretli (G-00-01) + karar 6-önerme turnusolüne (G-00-06) bağlı.
12. **5 zorlayıcı DoD kapısı** (G-08-20) + 5 somut lint gate (K4) geçti.

> **Özet:** beyin zaten güçlü (dürüstlük altyapısı, disclaimer, consent). v1.3 kimliği renkten forma taşır (Karot konsensüs enstrümanı), paleti tek-kaynağa çeker (owned E0–E3 + bull/bear/accent/accent-ui/accent-hover/cyan/amber, WCAG-kilitli), motion'ı telemetriye + tek-rejim ayrık süre-token'a bağlar (idle-sessiz app), ve dürüstlüğü fiziğe kodlar (Lie Factor=1, közleşme). Beş somut lint gate + `data-instrument` muafiyet-kancası kimliği kod düzeyinde korur. Bu belge o duruşun kalıcı sözleşmesidir.