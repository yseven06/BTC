# TradeMinds REDESIGN v3 — «Enstrüman Odası» Sprint Planı

**Sürüm:** v1 · **Tarih:** 2026-07-18 · **Statü:** NON-NORMATİF yol haritası (normatif kurallar: [DESIGN-BIBLE](./DESIGN-BIBLE-v1.1.md) v3.0 · [VISUAL-LANGUAGE](./VISUAL-LANGUAGE-v1.1.md) v3.0 · [MOTION-DOCTRINE](./MOTION-DOCTRINE-v1.md) v2). Çelişkide kanonik üçlü kazanır.

> **Final hedef (kullanıcı, bağlayıcı):** Landing Hero + Dashboard Nabız Bandı + Signal Center Cockpit + Popup/Modal/Drawer sistemi + Scroll/Scrollytelling + Motion + Visual Effects **bütün olarak ultra-premium**. Plan panel/table düzeltmesine indirgenemez; S5-S6 (landing/hero/scroll) roadmap'te KİLİTLİdir.

---

## 1 · Vizyon özeti

«Enstrüman Odası»: dışarısı rasathane (landing — atmosfer · ışık · anlatı), içerisi hassas alet (app — steril · yoğun · anında). Premium kimlik YALNIZ gerçek ürün yüzeylerinden kurulur: gerçek dashboard yüzeyleri · Signal Center intelligence cockpit · proof-surface/receipt sistemi · data panels · key-light · depth · hairline grid · controlled glow · premium overlay sistemi · landing scroll-reveal · Nabız bandı · gerçek veri/kanıt hissi. **Karot / soyut-3D obje / kristal / orb / brand-object / generic-3D hero YOK — gelecek kapı da YOK** (Bible §00-V3 v3-karot-kapanış).

## 2 · Karar-kapısı sicili (S0'da kilitlendi)

| Kapı | Karar | Kaynak |
|---|---|---|
| K-GATE (Karot/soyut-3D) | **KAPALI — KALICI**; gelecek kapı olarak da tutulmaz; creative-asset planında yer almaz | Bible §00-V3 |
| VL gated native-3D/video/Spline şeridi | **KAPATILDI**; landing derinliği yalnız CSS/Canvas-2D; 3D=gelecekte sıfırdan ayrı karar+sprint | VL "VL-MOTION-v3" S0-banner |
| PV-D3b (satır yoğunluğu) | **Seçenek-A**: padding-trim + avatar 28px; bilgi-kaybı=fail; 32px-literal yok; mobil/desktop kırılmaz | Bible §03-K v3-sprint-sırası S4 |
| Bokeh | **EMEKLİ** (landing dahil rastgele bokeh yok) | VL §03 |
| K-C2 shared-element | Şimdi kapalı; **S4'te karar-kapısı olarak yeniden sunulur** | Doctrine §9 |
| IA-GATE (AI-Overview / Risk-Distribution) | Mevcut yerleşim varsayılan; **S3/S4 analizinde yeniden sunulur**; onaysız geri-taşıma yok | Bible §03 |
| Rejim (Nabız bileşeni) | **VERİ-KAPILI** — frontend endpoint'i yok; sahnelemesi ayrı-onaylı read-only backend CP'si | Bible dash-nabız-v3 |
| Spring spec | CSS `--ease-signal`'e resmî indirgeme (JS-spring alınmaz) | Doctrine v2 |

## 3 · Sprint kartları (S1–S7)

Her sprint: **salt-okuma kapsam-analizi → kullanıcı onayı → küçük commit'ler → canlı görsel-QA → commit-öncesi DUR → ayrı commit onayı → ayrı push onayı.** `.claude/` asla stage'lenmez.

### S1 · Material & Overlay Foundation
- **Kapsam:** e3-materyal-v2 (VL §05): `--shadow-e3` iki-katman + cut-lip'in cam-reçetesine eklenmesi + standart scrim; 4 ad-hoc modal kabuğunun (`SignalDrawer` · `ClosedSignalChartModal` · `EngineDetailModal` · `ShareCardModal`) kanonik `ui/Modal`'a göçü; PI-1b (Dropdown/Tooltip reverse-exit); Header'ın 3 ad-hoc dropdown'u; mobil bottom-sheet (`align="bottom"`+slideUp+drag-handle); z-token göçü; Tooltip materyal-yükseltme; LockedOverlay blur-bandı; OKLCH basamak-kalibrasyon denetimi.
- **Dokunulmaz:** veri/davranış mantığı · backend · SignalTable satır-yapısı.
- **DoD:** ad-hoc modal kabuğu=0 · exit'siz overlay=0 · scrim-sapması=0 · hardcoded-z=0 · 6-mikro-durum tamlığı · a11y (focus-trap/aria) tüm overlay'lerde.

### S2 · Motion-Core *(≈eski CP-MOTION-A)*
- **Kapsam:** 32 `animate-spin` (20 dosya) → hairline-iskelet/statik gösterge; landing `transition-all` borcu (page.tsx CTA'ları) + lint'e ekleme; S2-BORÇ sözlük implementleri (sinyal-doğuşu · rozet-crossfade · toast-istifi); row-selection tek-atım; hairline-grid empty-state craft'ı.
- **DoD:** `animate-spin`=0 (buton-içi yazılı istisna hariç) · `transition-all`=0 · sözlük-borcu=0 · motion-selftest güncel+yeşil.

### S3 · Dashboard Pulse
- **Kapsam:** dash-nabız-v3 (statik key-light carve-out + olay-bağlı tek-atım foton + zengin sistem-sesi: lifecycle-census + "bugün doğan N"); Sicil tam-makbuz; ölü `AIGorusu.tsx`/`RiskDagilimi.tsx` CLEAN-mini; IA-GATE sunumu.
- **Sınır:** ≤120px · squint'te Nabız üçüncü parlak bölge OLMAZ · rejim YAZILMAZ (veri-kapılı) · F&G taşınmaz.
- **DoD:** band-dışı atmosfer=0 · idle-motion=0 · mock=0 · dış-kaynak (CoinGecko/F&G) dürüst-boş fallback.

### S4 · Signal Center Cockpit
- **Kapsam:** PV-D4 receipt-recompose (seviye-well · on-chain-well · LONG/SHORT nötr-yüzey · census `ProvenanceReceipt` tek-biçim); PV-D3b Seçenek-A (hedef rahat ~40–44 / kompakt ~50–54px; baseline-kırar → before/after zorunlu); Dock proof-surface materyali (e3-v2); K-C2 karar-kapısı sunumu.
- **DoD:** bilgi-kaybı=0 · well ≤2/ekran · kahraman=1 · satır-states tam (doğuş/crossfade/selection/foton) · mobil kart-görünümü kırılmaz.

### S5 · Landing Hero Cinematic *(KİLİTLİ)*
- **Kapsam:** hero-v3-kanıt-rasathanesi — katmanlı proof-surface derinliği (yalnız CSS/Canvas-2D) + key-light sahne + diegetik sinyal-tozu (gerçek-olay-havuzu; rAF+IO-pause+DPR-cap+reduce-kapalı) + Canlı Masa derinleştirme.
- **Yasak:** Karot/soyut-3D/orb/kristal/video-bg/mock; 3D şeridi kapalı.
- **DoD:** H1 LCP-statik · squint={H1,CTA} · CLS=0 · hero asset-bütçesi (~≤300KB görsel toplamı) · mobil tek-kolon fallback.

### S6 · Landing Scrollytelling *(KİLİTLİ)*
- **Kapsam:** anlatı-kavisi **Hero → Proof (Kanıt-Bandı+Sicil) → Signal-Lifecycle (Motorlar) → Trust (Şeffaflık+Güvenlik) → CTA**; CSS `animation-timeline` scroll-driven + IO-fallback; bölüm-içi tek-atım mikro-koreografi (makbuz satırları sırayla, hairline'lar çizilir); mobil = basit IO `rv-in`.
- **Yasak:** pinning/scrub/Lenis/wheel-intercept; app'te scroll-animasyonu=0; parallax/drift kapalı.
- **DoD:** reduce'ta tamamen statik+bilgi-kaybı=0 · LCP etkilenmez · legal/trust envanteri piksel-korunur.

### S7 · Polish & Perf Sweep
- **Kapsam:** optik-hiza denetimi (ondalık/ikon/baseline) · Lighthouse (LCP/CLS/INP) · reduce iki-yön · 3-viewport · düşük-uç fallback doğrulaması · "amatör-detay av listesi" (bulunan her şey raporlanır; görsel-QA kapısı: amatör/hizasız → commit atılmaz).

## 4 · Canlı görsel-QA protokolü (her sprint, bağlayıcı)

Gerçek render kontrolü: desktop (1280/1400) + mobil/dar-viewport (375/390 — kimlikli-tarayıcı viewport-kısıtı nedeniyle in-app preview+test-login veya gerçek cihaz) + scroll davranışı + popup/modal davranışı + animation-timing + console (app-kaynaklı hata=0) + premium-kalite kontrolü + amatör-görünen-detay listesi. Regresyon → DUR + raporla (oto-fix yok).

## 5 · Performans & mobil bütçeler

LCP: H1-statik kilidi; hero görsel-bütçe ~≤300KB; Canvas gecikmeli-mount. CLS=0 her yüzeyde. Bundle: Framer/GSAP/Three eklenmez. blur yalnız E3 (8-10px). Canvas-toz: parçacık-tavanı + IO-pause + DPR-cap ≤2 + düşük-uç/mobilde kapalı-veya-düşük. Eş-zamanlı animasyon ≤8; compositor-only. Dış-kaynak fallback'leri dürüst-boş (mock=fail).

## 6 · Scope-dışı (değişmez)

Gerçek veri semantiği · signal generation/scoring/risk/outcome/tracking/lifecycle · backend/API/DB/scheduler · legal/disclaimer çizgisi · filtre/sıralama/persist. Her sprint salt-sunum; davranış değişikliği ancak açık kullanıcı-onaylı ayrı CP.
