# TradeMinds Motion Doctrine v1 — KANONİK
**Tarih:** 2026-07-12 · **Statü:** Landing + Dashboard + Signal Center + tüm uygulama için TEK motion referansı (kanonik kaynak: bu dosya).
**Hiyerarşi:** Design Constitution v1'in altında, VL v1.4 kanonik değerlerine tabidir. `[GATED: K-J]` etiketli maddeler VL v1.5 paketi onaylanana dek YÜRÜRLÜKTE DEĞİLDİR — bu belge onları yasalaştırmaz, yalnız tanımlar. Bu doküman statik mimariyi (CP-5/6 sahnesi, Rezerv A/B/C) BOZMAZ — motion her zaman statik halin ÜZERİNE giydirilen, kaldırılabilir bir katmandır.
**Uygulama önkoşulu:** §8 M-0 borçları kapanmıştır (commit `e848674`).

---

## 0. BEŞ YASA (felsefe — her kararın testi)

1. **Hareket olaydan doğar.** Bir şey kıpırdıyorsa, gerçek bir telemetri/kullanıcı olayı olmuştur. Dekoratif hareket yalandır (fake-data yasağının motion karşılığı).
2. **Frekans↑ = motion↓.** Günde yüz kez tetiklenen yüzey animasyonsuz açılır (cmdK, menüler, yüksek-frekans tablolar). Anlam↑ = tek-seferlik motion meşrulaşır (sinyal doğuşu).
3. **Tek atım, sonra sessizlik.** Hiçbir hareket kalıcı değildir: loop yok, pulse yok, idle-yaşam yok. "Emin olan enstrüman titremez."
4. **Simetri zorunlu.** Her giren öğe reverse-exit ile çıkar (PI-1a standardı); "pat diye kaybolma" yarım-kalmışlıktır.
5. **Statik hal = reduced-motion'ın nihai hali.** Her yüzey önce motion'sız kusursuz durur; motion eklenti, mimari değil. Bu, gelecekteki her motion değişikliğinin "yeniden kurulum" gerektirmemesinin garantisidir.

## 1. KATMAN SİSTEMİ (T0–T3)

| Katman | Amaç | Süre | Easing | Tetik | Yüzeyler |
|---|---|---|---|---|---|
| **T0 · State-feedback** | "Tepki anında" refleksi (hover/press/focus) | 140ms (`--dur-micro/warm`) | `--ease-signal` (Tailwind DEFAULT) | Yalnız kullanıcı girdisi | Her yerde |
| **T1 · Mikro-geçiş** | Küçük UI doğum/ölümü (tooltip/dropdown/toggle/badge) | giriş 180 (`--dur-state`) / çıkış ≤150 (`--dur-photon`) | giren ease-out, çıkan ease-in; `ease-in-out` YASAK | Kullanıcı eylemi VEYA tekil veri-olayı | Her yerde; yüksek-frekans yüzeyler HARİÇ (animasyonsuz) |
| **T2 · Yüzey** | Mekânsal süreklilik (modal/drawer/route/disclosure) | overlay 360 (spring: stiffness~300/damping~30, overshoot ≤%8) · route 180 (ışık-devri −%8/+%6 ΔL) · disclosure 180 | spring / `--ease-signal` | Navigasyon/aç-kapa; kesintiye uğratılabilir (ESC anında; deterministik timer, animationend'e güven YOK) | Her yerde |
| **T3 · Landing-özel tek-seferlik** | İlk izlenimde anlatı (reveal) | öğe ≤520 (`--dur-settle`) + 50ms stagger; **sekans ≤1.2s** `[GATED: K-J]` | ease-out | Sayfa/viewport-giriş; `once:true` + `sessionStorage`; IntersectionObserver (scroll-listener yok) | YALNIZ landing; **Karot içermez; ışık animate edilmez** |

**Kanonik süre seti (değişmez çekirdek):** {140, 150, 180, 360, 520}ms + stagger 50ms · app sert-tavan 600ms · set-dışı = lint-red. `[GATED: K-J]` tek ekleme önerisi: `--dur-flash: 300ms` (veri-foton).

## 2. YÜZEY MATRİSİ (hangi katman nerede yaşar)

| Yüzey | T0 | T1 | T2 | T3 | Olay-motion | Ambient |
|---|---|---|---|---|---|---|
| **Landing** | ✅ | ✅ | ✅ (route) | ✅ `[GATED]` | ❌ (ISR-statik; canlı-tick landing'e GELMEZ) | ❌ (ışık statik; drift v1 kapalı — K-C1 R6) |
| **Dashboard** | ✅ | ✅ | ✅ | ❌ | ✅ (foton `[GATED]`, doğuş, crossfade, tape alan-içi) | ❌ (idle-sessiz; "sakin krom") |
| **Signal Center** | ✅ | ✅ | ✅ (Drawer spring) | ❌ | ✅ (aynı sözlük; bileşen-seviyesinde — SignalTable nerede yaşarsa taşınır) | ❌ |
| **Diğer app** | ✅ | ✅ | ✅ | ❌ | olay varsa aynı sözlük | ❌ |

## 3. OLAY-MOTION SÖZLÜĞÜ *("Living Interface"in tek tanımı: yaşam = gerçek olay)*

| Olay | Motion | Kural |
|---|---|---|
| Fiyat/değer değişimi | Arka-plan foton-flash (yön renginde) → söner | `[GATED: K-J]` 300ms; **rakam ASLA tween'lenmez** (ara değer = var olmayan fiyat); konum oynamaz (tabular slot); **coalesced** (görünür değişim başına 1, satır-başı ≥~2s) |
| Sinyal doğuşu | Tek slide+fade giriş + sönen highlight | `data-lifecycle-event` enum zorunlu; loop'a dönüşemez |
| Durum geçişi (Active→TP'ye-yaklaşıyor…) | Rozet crossfade (opacity+renk) | **SL/kayıpta ASLA alarm/kutlama** — sakinlik ciddiyettir (Robinhood dersi) |
| Kullanıcı kazancı (`user_win`) | Amber tek-atım toast | Mevcut kanonik; konfeti/havai-fişek kalıcı yasak |
| Route değişimi | Işık-devri (−%8/+%6 ΔL, 180ms) | View Transitions kullanılmaz |
| Overlay aç/kapa | Spring giriş + reverse çıkış | Deterministik timer; focus-trap/ESC |
| Toast istifi | Yeni girerken eskiler 8px translate (spring) | Hangisi yeni — hareketten okunur |
| Landing ilk-görünüm | T3 reveal koreografisi: mikro-etiket→H1→alt-metin→dürüst-satır→CTA→panel; fold-altı bölümler fade+≤8px | `[GATED: K-J]`; bir kez; reduced'da tamamen atlanır; veri-fallback dalında CLS=0 sözleşmesi |
| Yükleme | **Boş-Karot statik** (app) / hairline-çerçeve rezervi (landing paneli) | Spinner/skeleton/shimmer yasak; grace <300ms'te hiçbir şey gösterme; buton-içi işlem göstergesi yalnız yazılı istisna |
| Focus | **Anında görünür** — animasyonsuz | Klavye geri bildirimi geciktirilemez (a11y; INT-12) |

## 4. YÜZEY-ÖZEL KURALLAR

**Landing:** Statik sahne (E0→grain→key-light→içerik) dokunulmaz; T3 onun ÜZERİNDE oynar ("güneş doğmuş, sahne aydınlanmış" — ışık animate edilmez). Scroll daima serbest: yalnız scroll-TETİKLİ tek-atım (`once:true`); scrubbing/pinning/Lenis anayasal yasak. Parallax (VL: ≤3 strata, ışık=stratum-0) v1'de KAPALI — ayrı onayla açılır. Canlı-tick yok (ISR-60 kararı); landing'in "yaşamı" = gerçek verinin tazeliği + tek-atım anlatı.

**Dashboard:** "Sakin krom" — hareket eden/parlayan tek şey anlam taşıyan veri. Tape: satır statik, güncelleme alan-içi foton, **marquee hiçbir koşulda yok**. Stat/tablo güncellemeleri layout-oynatmaz. Kuşak-bazlı izolasyon: bir bölümün verisi düşerse animasyon zinciri diğerlerini etkilemez.

**Signal Center:** Tablo olay-sözlüğüne tabi (doğuş/foton/crossfade); Drawer = T2 spring kanonik; sekme-içerik crossfade 150ms + indikatör 180ms, panel kaymaz. Shared-element (tablo→Drawer, sembol+fiyat bloğu) yalnız `[GATED: K-C2]` ve TEK geçişe sınırlı. Filtre-pill'leri set-içi (180ms).

**Global:** cmdK ve tüm yüksek-frekans menüler ANIMASYONSUZ açılır. `count-up` app'te yasak (landing'de de kullanılmaz — sayının kendisi değerli). `transition-all` yasak → property-explicit (lint adayı). Karot motion'ı (spring-settle, doğum-stagger) yalnız ürün-içi enstrüman bağlamında — marka/landing yüzeyinde asla.

## 5. YASAKLAR (konsolide — değişmez)
Scroll-jacking/scrubbing/Lenis · cursor-follow/magnetic/custom-cursor · ambient/idle motion (app HER YERDE; landing'de drift v1 kapalı) · sonsuz loop/pulse/radar/cyan-tarama · shimmer/skeleton/sahte-progress · marquee · konfeti/kazanç-kutlaması · count-up · rakam-tween · layout-property animasyonu (width/height/margin/padding/blur) · `transition-all` · `ease-in-out` · girişli-çıkışsız asimetrik motion · yüksek-frekans yüzeye giriş-animasyonu · focus-geciktirme · Three/R3F/Spline/WebGL-kimlik/video-bg · her-tick'te flash (coalesce'siz) · Karot'un landing/marka yüzeyinde animasyonu · hover'da abartı (tavan: +1 lümen/−2px).

## 6. REDUCED-MOTION POLİTİKASI (tek karar)
**"Mekânsal hareket kalkar, bilgi kalır."** T0 aynen (vestibüler-güvenli) · T1/T2 → salt opacity-crossfade (aynı süre token'ları; spring devre-dışı) · T3/reveal **tamamen atlanır** (statik hal hazır) · foton'un renk-değişimi kalır (bilgi), hareket bileşeni yoktur zaten · uygulama: global `@media (prefers-reduced-motion: reduce)` + spring-JS'te `matchMedia` + motion-selftest'e reduce-assert'i. Bilgi kaybı sıfır.

## 7. PERFORMANS SÖZLEŞMESİ
Compositor-only: yalnız `transform`+`opacity` (foton istisnası: renk `[GATED: bg-color genişletmesi K-J]`) · eş-zamanlı animasyon ≤8, dropped-frame=0 · `will-change` yalnız animasyon-anı (kalıcı katman-şişmesi yasak) · timer=token (deterministik unmount) · tick-coalescing (rAF; her WS/poll mesajı DOM'a dokunmaz) · IntersectionObserver pasif (scroll-listener yok → INP temiz) · kütüphane eklenmez (Framer/GSAP yok) · **DoD her motion-CP'de:** DevTools 60fps + Layout/Recalc=0 + CLS 0 + düşük-güç throttle + reduced iki-yön + tek-oynatım kanıtı + 3-viewport + squint-değişmezliği.

## 8. UYGULAMA ÖNCÜLLERİ — ✅ KAPANDI (`e848674`)
- **M-0a (=CP-14/MO-01):** Sidebar `transition-all` → `transition-transform` (drawer-kayması kalır, genişlik snap); MainLayout padding-animasyonu kaldırıldı; sidebar hover'ları property-explicit.
- **M-0b:** Gate-5 TSX borçları sıfırlandı (signals-pili 300→`--dur-state` · dashboard F&G renkli-glow'u tamamen kaldırıldı · news 200→`--dur-state`); `transition-all` yasağının lint'e eklenmesi öneri olarak açık.

## 9. KAPILAR & SÜRÜM
- **K-J (VL v1.5 paketi)** — bu doktrindeki tüm `[GATED: K-J]` maddeleri yasalaştırır: `--dur-flash 300` + foton→bg-color + bull/bear yüzey-alfa (COL-11 hücre-doğrulaması) + T3 carve-out (≤1.2s) + gate-5/selftest/reduce-assert güncellemesi. Reddedilirse: flash 150ms'te, reveal 520-tavanlı tekil öğelerle — doktrin daralır, ölmez.
- **K-C2** — shared-element (tek geçiş, en son).
- **Kapalı-beklemede (kapısı yok, açmak ayrı onay):** parallax strata · ışık-drift · her tür yeni ambient.
- **Sürümleme:** Doktrin değişikliği = onay + CHANGELOG satırı; sessiz revizyon yok. Kaynak üç belge (MP-v1/AD-v1/Anayasa) değişmez — doktrin onların motion-icrasıdır.
