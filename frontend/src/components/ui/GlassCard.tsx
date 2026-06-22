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
  glowEffect?: boolean;
  glowColor?: "primary" | "bullish" | "bearish" | "none";
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  style,
  hoverEffect = false,
  glowEffect = false,
  glowColor = "none",
  ...props
}) => {
  // Edge-only glow: a tinted border + soft outer halo, same family as a
  // premium trading-terminal look. Earlier version filled the card's
  // interior with a blurred color wash (an absolute inset div) — that read
  // as a colored panel, not a glowing frame, so it's gone.
  //
  // Applied as inline style, not a Tailwind class: `border-border-subtle`
  // in the base className and a `border-{color}/NN` glow class both set
  // `border-color`, and Tailwind's generated stylesheet orders utilities
  // alphabetically by class name — not by where they appear in the
  // className string — so `border-border-subtle` (B-o-r-d-e-r-b...) was
  // silently winning over `border-accent-primary` (B-o-r-d-e-r-a...) every
  // time. Inline style has unconditional priority, so this can't happen.
  const glowStyles: Record<string, React.CSSProperties> = {
    none: {},
    primary: { borderColor: "rgba(59, 130, 246, 0.4)", boxShadow: "0 0 16px rgba(59, 130, 246, 0.25)" },
    bullish: { borderColor: "rgba(16, 185, 129, 0.4)", boxShadow: "0 0 16px rgba(16, 185, 129, 0.25)" },
    bearish: { borderColor: "rgba(239, 68, 68, 0.4)", boxShadow: "0 0 16px rgba(239, 68, 68, 0.25)" },
  };

  return (
    <div
      className={clsx(
        "relative backdrop-blur-md bg-bg-glass border border-border-subtle rounded-xl p-5 shadow-card transition-all duration-300",
        // Even cards that aren't click targets (hoverEffect=false) get a
        // faint border/glow lift on hover so the surface doesn't read as
        // completely static — no translate/scale here, so it never implies
        // clickability, just a quiet "alive" feel on an otherwise dark panel.
        !hoverEffect && "hover:border-border-medium hover:shadow-glow-sm",
        hoverEffect && "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-card-hover hover:border-border-medium",
        className
      )}
      style={glowEffect ? { ...glowStyles[glowColor], ...style } : style}
      {...props}
    >
      {children}
    </div>
  );
};
