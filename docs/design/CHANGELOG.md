# Design Standards — Changelog

Tasarım standardı belgelerinin (`DESIGN-BIBLE`, `VISUAL-LANGUAGE`) sürüm geçmişi.
Kural: **her revizyon = commit + sürüm artışı + bu dosyada bir satır.** Standart onaysız değişmez.

---

## v1.4.1 — Landing-hero vitrin istisnaları (C2 mini-revizyon) · 2026-07-12

> **Kapsam:** Design Constitution v1 / CP-5b (K-D=b1 kilitli kararı). Yalnız iki dar landing-istisnası; token/motion/renk/Karot-geometrisi **değişmedi**; app yüzeylerinde hiçbir kural değişmedi.
- **İstisna-1 (Karot-zorunluluğu):** Landing-hero'daki "Canlı Masa" teaser'ı **read-only pazarlama vitrinidir**; "her sinyal yüzeyinde Karot zorunlu" kuralındaki *sinyal yüzeyi* tanımının **dışındadır**. Gerekçe: Karot marka-yüzeyi yasağı (bağlayıcı kullanıcı kararı, landing-hero dahil) kanonik dokümanı geçer; ürün-içi tüm sinyal yüzeylerinde zorunluluk aynen sürer.
- **İstisna-2 (squint-gate landing carve-out):** `hero-squint-testi-dod` landing'de "en parlak 2 öge = **H1 + birincil CTA**" olarak okunur (Karot ürün-içi yüzeylerde kalır). Bible ilgili §'ine dipnot işlendi.

## v1.4 — Karot geometri revizyonu · 2026-07-09

> **Kapsam:** Karot konsensüs enstrümanının **geometrik projeksiyonu** revize edildi — "K17 görünüm + K02 matematik". Merkez-eksenli spline (v1.3) → **tek-taraflı fitilli-omurga** (dikey omurga + slot'a mıhlı açısal kanıt-fitilleri + karar-ucu). Değişen yalnız *forma projeksiyon*; K02'nin matematiksel rigor'u (classify eşikleri, 9-slot sıra, rest-state dizisi, dürüstlük fiziği, tüm süre/renk kilitleri, kalıcı yasaklar) **korundu**. Yalnız Bible §05 + ilgili §01/§06 satırları + VL §07/§09 motion-tablosu değişti; kod/CSS/component **bu commit'te değişmedi** (1A-ii ayrı commit). Dört-tur tarafsız tasarım süreci (10+6 konsept, 3-yol kıyas) sonrası kullanıcı kararı.

### Değişen standartlar (K17 formuna adapte)
- **karot-02 (Bible §05):** `W=120·AXIS=W/2·x=AXIS+c·AMP·Catmull-Rom spline` → `W=96·SPINE_X=24·θᵢ=cᵢ·θmax(34°)·L=32 sabit·karar-ucu`. Fitil boyu sabit → güven yalnız açıya kodlanır (Lie Factor 1). Çarpışma yasası `L·sin(θmax)<step`. Dikey ritim (H/PAD/step) korundu.
- **karot-05:** hal imzaları → Uzlaşma (paralel fitiller + tint-zarfı + karar-ucu) · Bölünmüş (karışık-açılı fitiller + çift-nokta, karar-ucu yok) · Kararsız (yataya-yapışık θ≈0). Token değerleri (fill .14 · stroke 1.9/1.3) aynen.
- **karot-06:** render sırası → classify → slots → tint-zarfı → fitiller → glow-underlay → omurga → karar-ucu.
- **karot-08:** 16px silüet → **3 küme-fitil** (motor aileleri ort.; hal/tint daima 9'lu classify'dan — ölçek-değişmezlik korunur).
- **karot-13 + micro-loading:** boş-Karot skeleton → 9 fitil yatay-nötr (θ=0) başlar, açısına **döner** (eskiden eksende düğüm).
- **MO-03 doğum:** düğüm-stagger → fitil-dönüş-stagger (50ms) + karar-ucu spring-oturması; overshoot açıya uygulanır. Süreler aynen.
- **Terim:** "düğüm/spline/merkez-eksen/zikzak" → "fitil/omurga/slot/karışık-açılı"; §01 `--hl12` "Karot-eksen" → "Karot slot-kılavuzu"; crosshair `x=W/2` → `x=SPINE_X`. VL §07/§09 motion-tablosu hizalandı.

### Eklenen
- **karot-15 · Geometry Freeze Rule:** v1.4 sonrası geometri · slot · omurga · davranış kuralları **DEĞİŞMEZ**; gelişme yalnız Motion/Material/Rendering/Lighting/Interaction/Premium-Identity katmanlarında. Y2 yasası: imleç kanıtı asla döndürmez (hover yalnız lüminans). Tek yeniden-açılma koşulu: kritik kullanıcı-testi başarısızlığı (16px ≥%85 / 48px ≥%90 yabancı-kör eşiğinin altına düşmek); estetik/trend/tercih geometriyi açmaz.

### Korunan (K02 rigor çekirdeği — 0 değişiklik)
- classify eşikleri (karot-03: absMean<.30 · eksen-geçiş≥2 · ±.08 bandı) · 9-slot sabit sıra (karot-04) · rest-state dizisi + K1b milestone (karot-09) · renk-kazanılır/tint .14 (karot-07/COL-09) · radyussuz/tel-malzeme/glow-underlay .14 (karot-10) · Karot↔Chart tek-nesne (karot-11) · lifecycle omurgaya dokunmaz (karot-14) · tüm süre/renk kilitleri · kalıcı yasaklar (radar/donut/bar · cyan-tarama · sahte-kesinlik) · iç-dil UI'a çıkmaz.

### Kararlar
- Tek kanonik sürüm ilkesi korunur; dosya adları sabit (v1.4 belge başlığında + bu changelog'da izlenir, yeniden-adlandırma yok).
- 1A-ii (Karot.tsx statik primitif) ayrı commit olarak bu revizyonun ardından uygulanır.

### Bakım (post-v1.4 · 2026-07-09)
- Bağımsız doğrulama (4-ajan audit) sonrası tek maintenance commit'i — **yeni kural/geometri YOK**, Geometry Freeze (karot-15) yürürlükte:
  - **(a)** §05↔§06 arasına önceki bir sürüm-fold'undan kalmış, normatif-olmayan İngilizce taslak-artığı metin ("I now have the complete draft… Key changes I'm applying:") **silindi** → kanonik gövde temizliği (Karot revizyonuyla ilgisiz pre-existing kusur).
  - **(b)** Doküman↔kod uzlaştırmaları: karot-06 stroke kuralına silüet=1.6 eklendi (kodla birebir); karot-05 cyan-bütçe cümlesi Bölünmüş eksen-üstü çift-noktayı da kapsayacak şekilde netleştirildi + stale "(bugün render'da YOK → eklenecek)" notu güncellendi; karot-05 Ölçüm 16px imza ifadesi düzeltildi.
  - **(c)** `karot-geometry.ts` + `Karot.tsx` sınır-guard'ı (geçersiz girdi zarif "kararsız/soluk"a düşer): 9-sonlu-değer ∈[−1,1] ve size>0 sözleşmesine uyan girdilerde render **byte-özdeş** (davranış-korur).

---

## v1.3 — KANONIK · 2026-07-06

> Design Standards tek kanonik sürümü. v1.3 taslakları (Bible + Visual Language) ile onaylı v1.3.1 revizyon planı (19 uygulanan / 3 revize / 1 reddedilen) tek gövdeye **fold** edildi. Bu sürüm, kalite denetimi referansındaki kritik boşlukları (64/100) kapatır. Kanonik kaynak: `docs/design/*.md`; Artifact yalnızca görsel aynadır.

### Eklenen standartlar

- **Renk — WebAIM kontrast kilidi:** `accent-ui`, `accent-hover`, `accent-text` token'ları WebAIM AA eşiklerine kilitlendi; kontrast oranları normatif tabloya bağlandı, serbest türetme yasak.
- **Hero — gerçek-olay havuzu:** Hero anlatısı sabit/uydurma senaryo yerine gerçek-olay havuzundan beslenir; önceki mantık-çelişkisi (statik iddia ↔ dinamik sinyal) giderildi.
- **Lint katmanı:** 5 zorunlu gate + "Karot" whitelist ile tasarım-token uyumu CI'da denetlenir; kaçış yalnız whitelist üzerinden.
- **Süre — tek rejim:** Tüm motion/geçiş süreleri tek normatif rejime bağlandı (çoklu/çelişen süre tanımları kaldırıldı).
- **Kabin imzası:** Ürün yüzeyi için tanımlı "kabin imzası" görsel kimlik kuralı — logo kapalıyken bile tanınırlık.
- **Bileşen matrisi + type-scale:** Component matrisi ve tipografi ölçeği normatif tabloya bağlandı; ad-hoc boyut/varyant üretimi yasak.
- **Provenance — verbatim:** Kaynak/atıf gösterimi verbatim zorunluluğuna bağlandı (özetleme/yeniden ifade yok).
- **Cyan bütçesi:** `cyan` vurgu kullanımına normatif bütçe/oran sınırı getirildi.
- **Kozlaşma (outcome) kuralı:** Sonuç/karar-durumu gösteriminin outcome-temelli normatif tanımı eklendi.
- **Reduced-transparency:** `prefers-reduced-transparency` için normatif fallback davranışı tanımlandı.
- **Özgünlük ölçümü:** Görsel özgünlük için ölçülebilir kriter/metronorm eklendi.
- **cmd+K spec:** Komut paleti (⌘K) için normatif etkileşim/erişilebilirlik spesifikasyonu eklendi.

### Çözülen (fold edilen v1.3.1 — 19 uygulanan)

- v1.3.1 revizyon planındaki 19 madde tek kanonik v1.3 gövdesine kaynaştırıldı; ayrı bir v1.3.1 sürümü **yayımlanmaz**.
- Kapatılan kritik boşluklar: renk WebAIM-kilidi, Hero mantık-çelişkisi, lint-katmanı (5 gate + Karot whitelist), süre tek-rejim, kabin-imzası, component-matris + type-scale, provenance-verbatim, cyan-bütçe, kozlaşma-outcome, reduced-transparency, özgünlük-ölçüm, cmd+K spec.

### Revize (3)

- **O1 — ML-faithfulness:** Ölçüt frontend'den backend'e taşındı; faithfulness backend katmanında doğrulanır (tasarım standardı yalnız gösterim tarafını bağlar).
- **O3 — Karot payload:** "Karot" whitelist payload tanımı netleştirildi (kapsam/format belirsizliği giderildi).
- **D4 — radius alias:** Radius token'ları alias'a bağlandı (doğrudan değer yerine tek-kaynak alias).

### Reddedilen (1)

- **D5:** Uygulama idle-sessizlik davranışı korunur; önerilen değişiklik reddedildi (mevcut idle davranışı kanonik kalır).

### Kararlar

- Tek kanonik sürüm ilkesi: v1.3.1 ayrı sürüm olarak tutulmaz; tüm onaylı revizyonlar v1.3'e fold edilir.
- Kalite hedefi: 64/100 referans denetimindeki kritik gap'ler bu sürümle kapatılır.
- Kanonik kaynak `docs/design/*.md`; Artifact görsel ayna olarak kalır, standart üretmez.
- Reddedilen ve revize edilen maddeler bu changelog'da izlenebilir tutulur (D5 reddi ve O1/O3/D4 revizyonları kalıcı kayıt).

---

## v1.2 — Rev-2/K1 · 2026-07-04

**Kapsam:** Design Standards Review'daki içerik-boşluğu High'larının K1 dilimi — P1.2 (Design system tek-kaynak) uygulamasının önkoşulu olan **eksik standartlar** tamamlandı. Yalnız Design Bible §01 + §08 değişti; **VL içeriği değişmedi** (sürüm senkron için v1.2). Kod/CSS/component'e dokunulmadı. Diğer Rev-2 Medium/Low (M8/M12/M13/M15/M16/M17…) hâlâ deferred.
**Sürümleme kararı (kullanıcı):** Dosya adları sabit tutulur (yeniden adlandırma yok); sürüm belge başlığında + bu changelog'da izlenir.

### Eklenen standartlar
- **H6 — Chart Tokens (Bible §01):** grafikler (recharts/lightweight/sparkline/equity) için tek token seti — mum bull/bear · çizgi/alan serisi (nötr=accent, sparkline=yön bull/bear) · eksen=--muted mono tnum (H11 uyumlu, --faint değil) · grid hairline .10 · tooltip E3 · grafik-üstü seviye çizgileri (TP/Giriş/SL) · **#f97316 kaldırılır** (warn'a eşitlenmez) · grafik ışık sırası (VL squint). TradingView embed tam-teması kapsam dışı (M16).
- **H7 — Locale & Format (Bible §01):** tek locale **tr-TR**; `Intl` zorunlu, elle ayraç yasak; fiyat ondalık-basamak tablosu; USD/kripto gösterim kuralı; tek-kaynak formatter (`lib/utils.ts`).
- **H8 — Migration Map (Bible §08):** eski→yeni eşleme (#020817→--bg · indigo→--accent · #f97316→chart token · en-US→formatter) + dosya-sınıfı envanteri (grep 2026-07-04) + kapanış kriteri; P1.2'nin kapanış ölçütü.

### Düzeltme
- **Bible §01 Table:** "kart deseni signal-history'de zaten var" iddiası kaldırıldı — kod doğrulaması (2026-07-04) desenin **olmadığını** gösterdi; P1.5'te yazılacağı belirtildi.

---

## v1.1 — Rev-1 · 2026-07-03

**Kapsam:** Design Standards Review'da doğrulanan 35 bulgunun **standart-bütünlüğünü** etkileyen kısmı (2 Critical + 8 High). İçerik-boşluğu tipi High'lar (chart teması, locale, migration haritası), tüm Medium ve Low maddeler **Rev-2**'ye ertelendi.
**Sınır:** Yalnız standart belgeleri değişti. Ürün koduna / CSS'e / component'lere / uygulama davranışına dokunulmadı.

### Critical
- **C1 — Belge-düzeyi kanoniklik tanımlandı.** Bible §08'e hiyerarşi maddesi eklendi: atmosfer/ışık/motion-bütçesi → VL kanonik; token/komponent/layout → Bible kanonik; çelişkide daha kısıtlayıcı kural kazanır ve düzeltme her iki belgede eşzamanlı yapılır. VL başlığına atıf konuldu. *(Belge: Her ikisi.)*
- **C2 — Belgeler repo'ya taşındı; sürümleme kuralı eklendi.** Kanonik kaynak artık `docs/design/*.md`; Artifact yalnız görsel ayna. "Revizyon = commit + sürüm artışı + changelog satırı" kuralı Bible §08'e işlendi. *(Belge: Her ikisi.)*

### High
- **H1 — Sticky header çelişkisi çözüldü.** Blur'suz opaklık çözümü kanonik: `background rgba(7,11,20,.72) + alt hairline .12`, `scroll>0`'da aktif, backdrop-blur YOK. Bible §01 glass listesinden "sticky header" çıkarıldı (glass = yalnız modal/dropdown/popover); tek sayısal reçete VL §08'de. *(Her ikisi.)*
- **H3 — Gölge tek tokene indirildi; glow adı ayrıldı.** `--shadow-e3: 0 16px 40px -20px rgba(0,0,0,.7)` yalnız E3 overlay; kartlar gölgesiz (derinlik border+lüminans). Eski `0 8px 24px -12px accent` değeri artık gölge değil, `--glow-cta` adıyla glow tokeni. *(Her ikisi.)*
- **H5 — Radius ölçeği gerçeğe hizalandı.** Yeni ölçek: `8 kontrol · 10 buton/input · 12 kart · 16 panel · 999 pill`. "Token tablosu kanoniktir; demo CSS normatif değildir" notu eklendi. *(Her ikisi.)*
- **H4 — Route-transition çelişkisi çözüldü.** VL §09 App satırına "route geçişi: 150-200ms fade/opacity, layout-anim yok" izni eklendi; liste stagger ve count-up yalnız landing. Bible §07 P2 "Framer page-transition" kalemi bu sınıra bağlandı. *(Her ikisi.)*
- **H9 — Motion araç-karar tablosu tek sahibe indi.** VL §11 tek kanonik kaynak ilan edildi; Bible §06 sayfa-eşlemeyi tutup verdict'ler için VL §11'e atıf yapıyor. Three.js → "Gereksiz", Spline/Video → "Hayır" iki belgede birebir hizalı. *(Her ikisi.)*
- **H10 — Definition of Done, VL kurallarıyla genişletildi.** Bible §08 DoD'a 4 madde: ≤1 ambient + app'te atmosfer yasağı (VL §09) · cyan yalnız AI (VL §01) · squint testi (VL §01) · noise ≤%3, veri üstünde yok (VL §04). *(Her ikisi — kural Bible'da, kaynak VL.)*
- **H11 — Kontrast kuralı eklendi (kendi ihlali kapandı).** `--faint` (#5C6980) koyu zeminde küçük metinde AA'yı (~3.6:1) geçmiyor → kural: `--faint` yalnız dekoratif/disabled; okunur mikro-etiket minimum `--muted`. Bible §01 + VL §11'e işlendi; DoD md.4 buna bağlandı. *(Her ikisi.)*
- **H2 — Sayfa taksonomisi + empty-state çelişkisi çözüldü.** VL §02'ye sayfa sınıflandırma tablosu (landing-tipi / auth / app-tipi → izinli katman seti) eklendi. Empty-state istisnası netleşti: app sayfa-geneli L0+L1; L2/L3 yalnız empty-state **kart sınırları içinde**, veri gelince kalkar. *(VL.)*

### Destekleyici netleştirmeler (Rev-1 kapsamında yapıldı)
- Kanonik ışık tokenı `--light-key` / `--light-fill` VL §02'de sabitlendi (dağınık %10-17 değerleri tek tokena bağlandı).
- Hero giriş koreografisi tek kanonik timeline tablosuna indirildi (VL §07); Bible §02 buna atıf yapıyor (600ms↔900ms çelişkisi giderildi).
- Bible §02'deki "gradient-mesh" ambient alternatifi kaldırıldı (VL sert-yasakla uyum); tek ambient = L4 sinyal tozu.
- Bokeh'in "tek anahtar ışık" bütçesine dahil olup olmadığı netleşti (yönsüz → dahil değil, yine ≤2).
- Auth "her tür animasyon yasak" → "ambient/koreografi yasak; micro-etkileşim serbest" olarak düzeltildi.

### Rev-2'ye ertelenenler (özet)
- **High (içerik-boşluğu):** H6 chart teması · H7 sayı/tarih locale standardı · H8 eski→yeni palet migration haritası. *(İlgili P0/P1 uygulama adımından önce eklenecek.)*
- **Medium (19):** glow bull/bear ifadesi · L1 statik/paralaks netleştirme · font ağırlık seti · tip ölçeği 72 · CTA glow rest/hover token ayrımı · dashboard count-up/tick (kısmen H4'te kapandı) · brand-grad/ufuk atfı (kapandı) · z-index ölçeği · focus-ring tokeni · disabled state · toast davranışı · TradingView embed teması · form-validation deseni · VL yeni tokenlarının Bible listesine resmî eklenmesi · input hairline 3:1 (WCAG 1.4.11) · vb.
- **Low (3):** bokeh ışık-bütçesi ifadesi (kapandı) · light-theme kararı · noise blend-mode maliyeti.

---

## v1.0 — İlk yayın · 2026-07-02
- **DESIGN-BIBLE v1** kabul edildi (resmî tek tasarım standardı): 9 bölüm — ilkeler, design system, hero, dashboard, markets, signals, motion, P0/P1/P2, governance.
- **VISUAL-LANGUAGE v1 "Gece Seansı"** kabul edildi (Annex A — Art Direction): ışık dili, background katmanları, glow/bokeh/noise, depth, section geçişleri, hero lighting, scroll/hover, motion bütçesi, kimlik, performans reçetesi.
