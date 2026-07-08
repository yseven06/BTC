# Design-System Backlog — katman-bazlı ertelenen maddeler

> Bu dosya, bir fazda **bilinçli olarak ertelenen** (o fazın kapsamı/kuralları
> gereği yapılamayan) maddeleri, hedef katmanlarıyla birlikte kaydeder. Kanonik
> standart: `docs/design/*.md` (Design Bible v1.1 / Visual Language). Bir madde
> ancak hedef katmanı açıkça ele alındığında uygulanır.

---

## Phase 7 — Interaction Language (kapanış: 2026-07-07)

Interaction Language fazı, **uygulanabilir tüm diff'ler** tamamlanarak kapatıldı
(bkz. kapanış raporu / commit geçmişi). Aşağıdaki 4 diff, **Color / Craft / Motion
/ Signal-Analysis** katmanlarına dokunmayı gerektirdiğinden Interaction fazında
uygulanmadı ve ilgili katmanların backlog'una taşındı.

### → Color System (Phase 9 / §09) backlog

- **P7-D17 — nav-active-accent-bar** · Bible §03 Navigation INT-11 — ✅ **TAMAMLANDI** (2026-07-08 · commit `6ec8e8e` · main `f7ad058`)
  - **Gerekli:** aktif nav = sol accent-çubuğu `--accent-ui` (2-3px) + `+1 luminans`
    basamağı (E1→E2), glow yok; ikon/aktif renk `--accent-primary → --accent-ui`;
    `.nav-item.active` reçetesini **globals.css'te** bu spec'e bağla.
  - **Neden ertelendi:** Color-token değişimi (`--accent`→`--accent-ui`, luminans) +
    `globals.css` düzenlemesi → Color katmanı.
  - **Dosyalar:** `src/components/layout/Sidebar.tsx`, `src/app/globals.css`
  - **Not:** `.nav-item.active` + `.active::before` (accent-çubuğu) globals.css'te
    zaten var; iş = reçeteyi `--accent-ui` + luminans'a çekmek.

- **P7-D20 — tooltip-static-glow (kalıntı)** · Bible §01 Tooltip / G-00-18 — ✅ **TAMAMLANDI** (2026-07-08 · commit `18b1fee` · main `f7ad058`)
  - **Gerekli:** `ui/Tooltip` Content `border-border-medium → --hl12` (+ `Arrow
    fill-border-medium → --hl12`).
  - **Neden ertelendi:** border-color token değişimi → Color katmanı.
  - **Dosyalar:** `src/components/ui/Tooltip.tsx`
  - **Not:** E3-yüzey + `shadow-e3` (glow değil) kısmı **zaten yapılmış** (plan'ın
    "current"ı bayattı); kalan tek boşluk border → `--hl12`.

- **P7-D22 — checkout-hover-cyan** · Bible §01 Button Migration / COL-04..10 — ✅ **TAMAMLANDI** (2026-07-08 · commit `f7ad058` · main `f7ad058`)
  - **Gerekli:** CTA `hover:bg-accent-secondary` (cyan) → `hover:bg-accent-hover`;
    `border-white/10-15` (ham beyaz-alfa) → `--hl12/--hl16` hairline.
  - **Neden ertelendi:** hover/border renk-token değişimi (cyan-tekeli COL-07) →
    Color katmanı.
  - **Dosyalar:** `src/components/billing/CheckoutConfirmModal.tsx`,
    `src/components/consent/CookieConsentBanner.tsx`,
    `src/components/consent/ReconsentGate.tsx`

### → Premium Craft (Phase 10 / §10) + Motion (Phase 6 / §06) + Signal-Analysis backlog

- **P7-D18 — hover-two-context** · Bible §01 INT-01
  - **Gerekli:** kart/panel hover = `+1 luminans (E1→E2) + translateY(-2px)`,
    `--dur-warm`, **glow kaldır** (kart-glow yasağı); tablo/liste satırı = **yalnız
    +1 luminans, transform 0**. GlassCard/SignalCard iki render-modu ayrımı.
  - **Neden ertelendi:** Craft/Motion (hover glow/transform/`--dur-warm`) **+
    `SignalDetailSection` (Signal Analysis, KORUNAN)** + `globals.css`. Çift-korumalı.
  - **Dosyalar:** `src/components/ui/GlassCard.tsx`,
    `src/components/ui/SignalDetailSection.tsx` (Signal-Analysis), `src/app/globals.css`
  - **Not:** `SignalDetailSection` dokunulduğu için, Color/Craft açılsa bile bu madde
    Signal-Analysis fazına (veya onunla eşgüdümlü) kalır.
