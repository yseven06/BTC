# TradeMinds Motion Doctrine v2 — KANONİK
**Tarih:** 2026-07-12 · **Statü:** Landing + Dashboard + Signal Center + tüm uygulama için TEK motion referansı (kanonik kaynak: bu dosya).
**Hiyerarşi:** Design Constitution v1'in altında, VL v1.5 kanonik değerlerine tabidir. K-J paketi 2026-07-12'de 7/7 ONAYLANDI (VL v1.5; bkz. CHANGELOG) — K-J-gated maddeler artık `[ONAYLI: VL v1.5]` etiketiyle YÜRÜRLÜKTEDİR (`[GATED: K-C2]` ayrı kapıdır, kapalı kalır). Bu doküman statik mimariyi (CP-5/6 sahnesi, Rezerv A/B/C) BOZMAZ — motion her zaman statik halin ÜZERİNE giydirilen, kaldırılabilir bir katmandır.
**Uygulama önkoşulu:** §8 M-0 borçları kapanmıştır (commit `e848674`).
**Revizyon (2026-07-18 · CP-PREMIUM-VISUAL-A, doc-only):** Yükleme reçetesi Karot'suz re-anchor edildi — §3 "Yükleme" satırı **Boş-Karot → hairline-iskelet** (kanonik reçete: Bible §03-K pv-yükleme-hairline-iskelet); §4 Global'deki Karot-motion cümlesi tarihsel işaretlendi (Karot ürün-UI'dan kaldırıldı, Bible v1.7). Davranış/süre-seti/yasaklar DEĞİŞMEDİ.
**Revizyon v2 (2026-07-18 · S0 REDESIGN-DOC, doc-only):** (a) **Sözlük ekleri** (§3): satır-seçimi tek-atım · Nabız olay-fotonu (Bible dash-nabız-v3) · bottom-sheet slide-up · landing scroll-driven mikro-koreografi (T3-genişletme, yalnız landing). (b) Sözlükte tanımlı-ama-implementasyonsuz üç olay (**sinyal-doğuşu · rozet-crossfade · toast-istifi**) **S2-BORÇ** statüsüne alındı — implement zorunlu (v3-sprint-sırası S2). (c) T2 "spring" spec'i **resmî indirgeme**: spring-karakteri hedef-tanımdır; uygulama CSS `--ease-signal` (el-yazımı JS-spring alınmaz; kütüphane-yasağı sürer). (d) **Kesintiye-açıklık** Yasa-4'e eklendi. (e) Route ışık-devrinin **tek-yön** uygulanışı resmîleşti (yalnız gelen +ΔL; View-Transitions yasağı). (f) §9'a S0 kapı-kayıtları eklendi (gated native-3D şeridi KAPALI · K-C2=S4-kapısı · bokeh emekli). **Süre-seti/yasaklar DEĞİŞMEDİ; runtime davranış yok.**

---

## 0. BEŞ YASA (felsefe — her kararın testi)

1. **Hareket olaydan doğar.** Bir şey kıpırdıyorsa, gerçek bir telemetri/kullanıcı olayı olmuştur. Dekoratif hareket yalandır (fake-data yasağının motion karşılığı).
2. **Frekans↑ = motion↓.** Günde yüz kez tetiklenen yüzey animasyonsuz açılır (cmdK, menüler, yüksek-frekans tablolar). Anlam↑ = tek-seferlik motion meşrulaşır (sinyal doğuşu).
3. **Tek atım, sonra sessizlik.** Hiçbir hareket kalıcı değildir: loop yok, pulse yok, idle-yaşam yok. "Emin olan enstrüman titremez."
4. **Simetri zorunlu.** Her giren öğe reverse-exit ile çıkar (PI-1a standardı); "pat diye kaybolma" yarım-kalmışlıktır. *(v2 ek: her motion **kesintiye açıktır** — kullanıcı aksiyonu animasyonu anında keser; hiçbir motion tamamlanmayı bekletmez, veri T0'da okunur.)*
5. **Statik hal = reduced-motion'ın nihai hali.** Her yüzey önce motion'sız kusursuz durur; motion eklenti, mimari değil. Bu, gelecekteki her motion değişikliğinin "yeniden kurulum" gerektirmemesinin garantisidir.

## 1. KATMAN SİSTEMİ (T0–T3)

| Katman | Amaç | Süre | Easing | Tetik | Yüzeyler |
|---|---|---|---|---|---|
| **T0 · State-feedback** | "Tepki anında" refleksi (hover/press/focus) | 140ms (`--dur-micro/warm`) | `--ease-signal` (Tailwind DEFAULT) | Yalnız kullanıcı girdisi | Her yerde |
| **T1 · Mikro-geçiş** | Küçük UI doğum/ölümü (tooltip/dropdown/toggle/badge) | giriş 180 (`--dur-state`) / çıkış ≤150 (`--dur-photon`) | giren ease-out, çıkan ease-in; `ease-in-out` YASAK | Kullanıcı eylemi VEYA tekil veri-olayı | Her yerde; yüksek-frekans yüzeyler HARİÇ (animasyonsuz) |
| **T2 · Yüzey** | Mekânsal süreklilik (modal/drawer/route/disclosure) | overlay 360 *(v2: "spring" hedef-karakter tanımıdır — stiffness~300/damping~30/overshoot ≤%8; **uygulama CSS `--ease-signal`**, JS-spring alınmaz)* · route 180 (ışık-devri; v2: tek-yön — yalnız gelen +ΔL) · disclosure 180 | `--ease-signal` | Navigasyon/aç-kapa; kesintiye uğratılabilir (ESC anında; deterministik timer, animationend'e güven YOK) | Her yerde |
| **T3 · Landing-özel tek-seferlik** | İlk izlenimde anlatı (reveal) | öğe ≤520 (`--dur-settle`) + 50ms stagger; **sekans ≤1.2s** `[ONAYLI: VL v1.5]` | ease-out | Sayfa/viewport-giriş; `once:true` + `sessionStorage`; IntersectionObserver (scroll-listener yok) | YALNIZ landing; **Karot içermez; ışık animate edilmez** |

**Kanonik süre seti (değişmez çekirdek):** {140, 150, 180, 300, 360, 520}ms + stagger 50ms · app sert-tavan 600ms · set-dışı = lint-red. `[ONAYLI: VL v1.5]` 300 = `--dur-flash` (veri-foton bg-tint; enforcement üçlüsü senkron).

## 2. YÜZEY MATRİSİ (hangi katman nerede yaşar)

| Yüzey | T0 | T1 | T2 | T3 | Olay-motion | Ambient |
|---|---|---|---|---|---|---|
| **Landing** | ✅ | ✅ | ✅ (route) | ✅ `[ONAYLI: VL v1.5]` | ❌ (ISR-statik; canlı-tick landing'e GELMEZ) | ❌ (ışık statik; drift v1 kapalı — K-C1 R6) |
| **Dashboard** | ✅ | ✅ | ✅ | ❌ | ✅ (foton `[ONAYLI: VL v1.5]`, doğuş, crossfade, tape alan-içi) | ❌ (idle-sessiz; "sakin krom") |
| **Signal Center** | ✅ | ✅ | ✅ (Drawer spring) | ❌ | ✅ (aynı sözlük; bileşen-seviyesinde — SignalTable nerede yaşarsa taşınır) | ❌ |
| **Diğer app** | ✅ | ✅ | ✅ | ❌ | olay varsa aynı sözlük | ❌ |

## 3. OLAY-MOTION SÖZLÜĞÜ *("Living Interface"in tek tanımı: yaşam = gerçek olay)*

| Olay | Motion | Kural |
|---|---|---|
| Fiyat/değer değişimi | Arka-plan foton-flash (yön renginde) → söner | `[ONAYLI: VL v1.5]` 300ms; **rakam ASLA tween'lenmez** (ara değer = var olmayan fiyat); konum oynamaz (tabular slot); **coalesced** (görünür değişim başına 1, satır-başı ≥~2s) |
| Sinyal doğuşu | Tek slide+fade giriş + sönen highlight | `data-lifecycle-event` enum zorunlu; loop'a dönüşemez · **(v2: S2-BORÇ — implementasyonsuz → zorunlu)** |
| Durum geçişi (Active→TP'ye-yaklaşıyor…) | Rozet crossfade (opacity+renk) | **SL/kayıpta ASLA alarm/kutlama** — sakinlik ciddiyettir (Robinhood dersi) · **(v2: S2-BORÇ)** |
| Kullanıcı kazancı (`user_win`) | Amber tek-atım toast | Mevcut kanonik; konfeti/havai-fişek kalıcı yasak |
| Route değişimi | Işık-devri (180ms) | View Transitions kullanılmaz; **v2: tek-yön resmî** — yalnız gelen +ΔL uygulanır (giden −%8 uygulanmaz) |
| Overlay aç/kapa | Giriş + reverse çıkış (`--ease-signal`) | Deterministik timer; focus-trap/ESC; kesintiye-açık |
| Toast istifi | Yeni girerken eskiler 8px translate | Hangisi yeni — hareketten okunur · **(v2: S2-BORÇ)** |
| Satır seçimi (tablo→Dock) *(v2)* | Tek-atım sönen seçim-tinti | Kullanıcı olayı; `--dur-state`; kalıcı vurgu = statik bg-tint; loop yok |
| Nabız olay-fotonu *(v2 · dash-nabız-v3)* | Band sayacı GÖRÜNÜR değişince tek-atım foton/flash | Yalnız Dashboard Nabız; idle'da sıfır; coalesced |
| Bottom-sheet aç/kapa *(v2 · S1)* | slide-up giriş + reverse çıkış | Mobil overlay; `--dur-overlay`; drag-handle statik |
| Landing scroll-driven mikro-koreografi *(v2 · S6)* | CSS `animation-timeline: scroll()/view()` + IO-fallback; bölüm-içi tek-atım | YALNIZ landing; pinning/scrub/Lenis yasak; reduce'ta atlanır |
| Landing ilk-görünüm | T3 reveal koreografisi: mikro-etiket→H1→alt-metin→dürüst-satır→CTA→panel; fold-altı bölümler fade+≤8px | `[ONAYLI: VL v1.5]`; bir kez; reduced'da tamamen atlanır; veri-fallback dalında CLS=0 sözleşmesi |
| Yükleme | **Hairline-iskelet statik** (app; Bible §03-K — Karot'suz) / hairline-çerçeve rezervi (landing paneli) | Spinner/shimmer/animasyonlu-skeleton/sahte-progress yasak; grace <300ms'te hiçbir şey gösterme; buton-içi işlem göstergesi yalnız yazılı istisna |
| Focus | **Anında görünür** — animasyonsuz | Klavye geri bildirimi geciktirilemez (a11y; INT-12) |

## 4. YÜZEY-ÖZEL KURALLAR

**Landing:** Statik sahne (E0→grain→key-light→içerik) dokunulmaz; T3 onun ÜZERİNDE oynar ("güneş doğmuş, sahne aydınlanmış" — ışık animate edilmez). Scroll daima serbest: yalnız scroll-TETİKLİ tek-atım (`once:true`); scrubbing/pinning/Lenis anayasal yasak. Parallax (VL: ≤3 strata, ışık=stratum-0) v1'de KAPALI — ayrı onayla açılır. *(v2/S6: scroll-driven mikro-koreografi — CSS `animation-timeline` + IO-fallback, tek-atım, yalnız landing — sözlüğe eklendi; parallax/drift KAPALI kalır.)* Canlı-tick yok (ISR-60 kararı); landing'in "yaşamı" = gerçek verinin tazeliği + tek-atım anlatı.

**Dashboard:** "Sakin krom" — hareket eden/parlayan tek şey anlam taşıyan veri. Tape: satır statik, güncelleme alan-içi foton, **marquee hiçbir koşulda yok**. Stat/tablo güncellemeleri layout-oynatmaz. Kuşak-bazlı izolasyon: bir bölümün verisi düşerse animasyon zinciri diğerlerini etkilemez.

**Signal Center:** Tablo olay-sözlüğüne tabi (doğuş/foton/crossfade); Drawer = T2 spring kanonik; sekme-içerik crossfade 150ms + indikatör 180ms, panel kaymaz. Shared-element (tablo→Drawer, sembol+fiyat bloğu) yalnız `[GATED: K-C2]` ve TEK geçişe sınırlı. Filtre-pill'leri set-içi (180ms).

**Global:** cmdK ve tüm yüksek-frekans menüler ANIMASYONSUZ açılır. `count-up` app'te yasak (landing'de de kullanılmaz — sayının kendisi değerli). `transition-all` yasak → property-explicit (lint adayı). *(Tarihsel — 2026-07-18: Karot ürün-UI'dan kaldırıldı; Karot-motion'ı artık YOKTUR.)* ~~Karot motion'ı (spring-settle, doğum-stagger) yalnız ürün-içi enstrüman bağlamında — marka/landing yüzeyinde asla.~~

## 5. YASAKLAR (konsolide — değişmez)
Scroll-jacking/scrubbing/Lenis · cursor-follow/magnetic/custom-cursor · ambient/idle motion (app HER YERDE; landing'de drift v1 kapalı) · particle-arkaplan/yıldız-tozu (dekoratif; landing sinyal-tozu YALNIZ diegetik/gerçek-olay-havuzu istisnası — VL §02 L4) · sonsuz loop/pulse/radar/cyan-tarama · shimmer/skeleton/sahte-progress · marquee · konfeti/kazanç-kutlaması · count-up · rakam-tween · layout-property animasyonu (width/height/margin/padding/blur) · `transition-all` · `ease-in-out` · girişli-çıkışsız asimetrik motion · yüksek-frekans yüzeye giriş-animasyonu · focus-geciktirme · Three/R3F/Spline/WebGL-kimlik/video-bg · her-tick'te flash (coalesce'siz) · Karot'un landing/marka yüzeyinde animasyonu · hover'da abartı (tavan: +1 lümen/−2px).

## 6. REDUCED-MOTION POLİTİKASI (tek karar)
**"Mekânsal hareket kalkar, bilgi kalır."** T0 aynen (vestibüler-güvenli) · T1/T2 → salt opacity-crossfade (aynı süre token'ları; spring devre-dışı) · T3/reveal **tamamen atlanır** (statik hal hazır) · foton'un renk-değişimi kalır (bilgi), hareket bileşeni yoktur zaten · uygulama: global `@media (prefers-reduced-motion: reduce)` + spring-JS'te `matchMedia` + motion-selftest'e reduce-assert'i. Bilgi kaybı sıfır.

## 7. PERFORMANS SÖZLEŞMESİ
Compositor-only: yalnız `transform`+`opacity` (foton istisnası: renk — `[ONAYLI: VL v1.5]` bg-color dar-tanımı, VL §Ölçüm) · eş-zamanlı animasyon ≤8, dropped-frame=0 · `will-change` yalnız animasyon-anı (kalıcı katman-şişmesi yasak) · timer=token (deterministik unmount) · tick-coalescing (rAF; her WS/poll mesajı DOM'a dokunmaz) · IntersectionObserver pasif (scroll-listener yok → INP temiz) · kütüphane eklenmez (Framer/GSAP yok) · **DoD her motion-CP'de:** DevTools 60fps + Layout/Recalc=0 + CLS 0 + düşük-güç throttle + reduced iki-yön + tek-oynatım kanıtı + 3-viewport + squint-değişmezliği.

## 8. UYGULAMA ÖNCÜLLERİ — ✅ KAPANDI (`e848674`)
- **M-0a (=CP-14/MO-01):** Sidebar `transition-all` → `transition-transform` (drawer-kayması kalır, genişlik snap); MainLayout padding-animasyonu kaldırıldı; sidebar hover'ları property-explicit.
- **M-0b:** Gate-5 TSX borçları sıfırlandı (signals-pili 300→`--dur-state` · dashboard F&G renkli-glow'u tamamen kaldırıldı · news 200→`--dur-state`); `transition-all` yasağının lint'e eklenmesi öneri olarak açık.

## 9. KAPILAR & SÜRÜM
- **K-J (VL v1.5 paketi) — ✅ ONAYLANDI (2026-07-12, 7/7):** `--dur-flash 300` + foton→bg-color (dar-tanım) + bull/bear geçici yüzey-alfa (mevcut `/10–/15` ailesi; COL-11 hex açılmadı) + T3 carve-out (sekans ≤1.2s, landing-mühürlü) + reduce-assert + M-L1 (H1 statik şartlı) + M-P1 (coalesced). Eski K-J-gated etiketler `[ONAYLI: VL v1.5]` oldu; enforcement üçlüsü (gates.cjs + design-gates.mjs + motion-selftest.mjs) aynı CP'de senkronlandı.
- **K-C2** — shared-element (tek geçiş, en son). *(v2/S0: **S4 karar-kapısı** — Signal Center Cockpit analizinde yeniden sunulur; öncesinde kapalı.)*
- **Kapalı-beklemede (kapısı yok, açmak ayrı onay):** parallax strata · ışık-drift · her tür yeni ambient.
- **S0 REDESIGN-DOC kayıtları (2026-07-18):** VL-MOTION-v3 gated native-3D/video/Spline şeridi **KAPATILDI** (kullanıcı kararı; 3D = gelecekte sıfırdan ayrı karar/sprint) · bokeh **EMEKLİ** (VL §03) · count-up/rakam-tween/sürekli-pulse/app-ambient/scroll-jack yasakları AYNEN · uygulama sırası = Bible §03-K **v3-sprint-sırası** (S1–S7; S2 = spinner-borcu [32 `animate-spin`/20 dosya] + landing `transition-all` borcu kapanış-DoD'u).
- **Sürümleme:** Doktrin değişikliği = onay + CHANGELOG satırı; sessiz revizyon yok. Kaynak üç belge (MP-v1/AD-v1/Anayasa) değişmez — doktrin onların motion-icrasıdır.
