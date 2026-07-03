# Design Standards — Changelog

Tasarım standardı belgelerinin (`DESIGN-BIBLE`, `VISUAL-LANGUAGE`) sürüm geçmişi.
Kural: **her revizyon = commit + sürüm artışı + bu dosyada bir satır.** Standart onaysız değişmez.

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
