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
}

// glowEffect/glowColor API'si SÖKÜLDÜ (P10/D03+D10, Bible §01 craft-glow-budget):
// kart glow taşımaz — glow yalnız birincil-CTA hover (--glow-cta) ve
// data-lifecycle-event'e bağlı anlardır; bull/bear ASLA glow almaz.
export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  style,
  hoverEffect = false,
  ...props
}) => {
  return (
    <div
      className={clsx(
        // Gölgesizleştirme + kabin imzası (P10/D01+D05, Bible §01):
        // drop-shadow YASAK — derinlik luminanstan (E1, hover E2). Kabin imzası
        // = kart kimliğinin logo-kapalı taşıyıcısı: üst cut-lip highlight +
        // dikey NET accent-ui-edge + yatay .06 soluk kenar (shadow-cabin bileşiği).
        "relative bg-e-1 border border-[var(--cabin-edge-h)] rounded-card p-5 shadow-cabin transition-all duration-300",
        // Even cards that aren't click targets (hoverEffect=false) get a
        // faint border/luminance lift on hover so the surface doesn't read as
        // completely static — no translate/scale here, so it never implies
        // clickability, just a quiet "alive" feel on an otherwise dark panel.
        !hoverEffect && "hover:border-[var(--hl16)] hover:bg-e-2",
        hoverEffect && "hover:-translate-y-1 hover:scale-[1.01] hover:border-[var(--hl16)]",
        className
      )}
      style={style}
      {...props}
    >
      {children}
    </div>
  );
};
