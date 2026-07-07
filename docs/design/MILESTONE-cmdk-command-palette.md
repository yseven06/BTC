# Milestone Spec — Komut Paleti (⌘K) · Bible §01 INT-08

> **Statü:** Faz-dışı milestone (Phase 7 Interaction'da KOD YAZILMAZ).
> Bu belge P7-D21'in çıktısıdır: (1) mevcut güvenli-varsayılan durumun doğrulama
> kaydı, (2) tam-palet uygulanınca uyulacak kanonik spec. Kaynak: Design Bible v1.3
> §01 INT-08 + Visual Language v1.3.

---

## 1. Güvenli-varsayılan doğrulama (P7-D21, regresyon-guard)

**Kural (INT-08):** Yarı-durum YASAK. Ya tam-kanonik komut paleti, ya da HİÇ
affordance. Çalışan palet olmadan `⌘K` rozeti / kısayol / "Cmd+K" ipucu
EKLENMEZ.

**Mevcut durum — 2026-07 doğrulaması (grep DoD):**
- `⌘K | cmd+k | cmd-k | command-palette | cmdk | useHotkeys | mousetrap` → **0 eşleşme**
- Cmd/Meta+K keydown dinleyicisi (fiili kısayol) → **yok**
- `Header.tsx` cmd/palette izi → **yok**

**Sonuç:** Kod tabanı güvenli-varsayılan (affordance yok) ile UYUMLU; ihlal yok.
Bu, INT-08 için bir regresyon-guard'dır — ileride bir palet-rozeti/kısayolu, çalışan
palet olmadan eklenirse (yarı-durum) bu DoD kırılır.

## 2. Tam-palet kanonik spec (uygulama milestone'u — henüz DEĞİL)

Palet gerçekten yapıldığında uyulacak kanonik davranış:

| Boyut | Kanonik kural |
|---|---|
| **Yüzey** | E3 cam overlay (`.glass-e3-overlay`: E3 %92 + blur 8–10px + `--hl22` + `--shadow-e3`), `--radius-panel` (16). |
| **Açılış/kapanış** | Spring giriş (`--dur-overlay`/`--dur-state`, `--ease-signal`); reduced-motion'da anlık. |
| **Klavye gezinme** | `j`/`k` (+ ok tuşları) ile satır gezinme; **roving-tabindex** (tek `tabindex=0` aktif satır, diğerleri `-1`). |
| **ESC katman-sırası** | `overlay > palette > modal` — en üstteki katman önce kapanır; ESC alt katmana sızmaz. |
| **`?` cheatsheet** | Kısayol referansı `?` ile açılır (aynı palette-katman disiplini). |
| **AI-öneri** | AI-önerilen komutlar `--cyan` iz (satır/nokta) ile işaretlenir (cyan yalnız iz, yüzey değil — COL-05/07). |
| **z-katmanı** | Palet, modal'ın üstünde ayrı bir katman-token'ı gerektirir (mevcut `--z-*` seti: dropdown 40 · modal 50 · toast 60 · tour 100; palet/blocking için token boşluğu var — bkz. P7 CP3 notu). |
| **Erişilebilirlik** | `role=dialog` + `aria-modal`, focus-trap, açılışta ilk-satır/arama-input odağı, kapanışta odak-iadesi (ui/Modal primitifi deseni yeniden kullanılabilir). |

## 3. Bağımlılıklar / notlar

- **Bağımsız değil:** AI-öneri iz'i (cyan) AI Thought Language (Phase 2) provenance
  verisine, spring/motion `--dur-*`/`--ease-signal` (Phase 6) token setine bağlı.
- **Primitif yeniden-kullanım:** ui/Modal (P7-D15) focus-trap/ESC/portal/scroll-lock
  altyapısı palet için temel alınabilir; palet, ek olarak liste-gezinme + arama +
  komut-registry gerektirir.
- **Yeni z-token:** Palet (ve blocking-modal) için `--z-*` setine ek token gerekir
  (P7 CP3'te not edildi; şimdilik ad-hoc `z-[110]` kullanılıyor).
