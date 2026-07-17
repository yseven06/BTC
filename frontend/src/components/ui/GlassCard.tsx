import React from "react";
import clsx from "clsx";

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  /** Lift + scale on hover. Defaults to off — most GlassCard usages are
   * pure info/layout cards (not click targets), and the lift effect both
   * implies clickability that isn't there and clips against any ancestor
   * with overflow:auto/hidden (e.g. a scrolling sidebar). Opt in explicitly
   * on cards that really are a click target (e.g. a row wrapped in a Link). */
  hoverEffect?: boolean;
  /** İki-ritim spacing (Bible §01 craft-spacing-two-rhythm, P10/D06):
   * varsayılan chrome-cömert p-6 (24px nefes); dense=true veri-yoğun sıkı
   * ritim p-4 (16px) — stat/veri kartları için. */
  dense?: boolean;
  /** Yüzey sınıfı (Bible §01-K craft-kap-hiyerarşisi / craft-veri-kuyusu, v1.6):
   * - "panel" (VARSAYILAN): mevcut GlassCard davranışı — E1 kap, kabin imzası,
   *   hover ısınma. BYTE-IDENTICAL (default değişmez).
   * - "well": enstrüman-kuyusu — içeriğinden bir basamak KARANLIK (E0-inset),
   *   iç-hairline (inset hl10), gölge/kabin YOK. Chart/tablo/Karot-sahnesi gibi
   *   ENSTRÜMANLARI barındırmak için opt-in. "Derinlik = kabın içine bakmak."
   *   Yeni glow/blur/token bütçesi AÇMAZ (bg-e-0 + hl10 mevcut token'lar).
   * Not: "chrome" (kapsız) bir varyant DEĞİLDİR — kompozisyon kuralıdır
   * (kap kullanmamak); komponentleştirilmez (Bible §01-K). */
  variant?: "panel" | "well";
}

// glowEffect/glowColor API'si SÖKÜLDÜ (P10/D03+D10, Bible §01 craft-glow-budget):
// kart glow taşımaz — glow yalnız birincil-CTA hover (--glow-cta) ve
// data-lifecycle-event'e bağlı anlardır; bull/bear ASLA glow almaz.
export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  style,
  hoverEffect = false,
  dense = false,
  variant = "panel",
  ...props
}) => {
  // Bible §01-K craft-veri-kuyusu (v1.6): "well" opt-in enstrüman-kuyusu.
  // variant="panel" (default) → clsx argümanları AYNEN eskisine çözülür
  // (!isWell=true ⇒ hover dalları eski koşullarla birebir aynı) → panel
  // çıktısı BYTE-IDENTICAL, mevcut 101 kullanım değişmez.
  const isWell = variant === "well";
  return (
    <div
      className={clsx(
        // PANEL (default): Gölgesizleştirme + kabin imzası (P10/D01+D05, Bible §01):
        //   drop-shadow YASAK — derinlik luminanstan (E1, hover E2). Kabin imzası
        //   = kart kimliğinin logo-kapalı taşıyıcısı: üst cut-lip highlight +
        //   dikey NET accent-ui-edge + yatay .06 soluk kenar. Hover = tek ısınma.
        // WELL: enstrüman-kuyusu — E0 (bir basamak karanlık) + iç-hairline (inset
        //   hl10); gölge/kabin/hover-lift YOK (statik kuyu; içindeki enstrüman
        //   tek parlak öge). Yeni glow/blur/token bütçesi açmaz.
        isWell
          ? "relative bg-e-0 rounded-card shadow-[inset_0_0_0_1px_var(--hl10)]"
          : "relative bg-e-1 border border-[var(--cabin-edge-h)] rounded-card shadow-cabin transition-[transform,background-color,border-color] duration-warm ease-signal",
        dense ? "p-4" : "p-6",
        // Panel-only hover (well statiktir). !isWell=false iken bu iki dal
        // otomatik kapanır → well'de hover-class yazılmaz.
        !isWell && !hoverEffect && "hover:border-[var(--hl16)] hover:bg-e-2",
        !isWell && hoverEffect && "motion-safe:hover:-translate-y-[2px] hover:bg-e-2 hover:border-[var(--hl16)]",
        className
      )}
      style={style}
      {...props}
    >
      {children}
    </div>
  );
};
