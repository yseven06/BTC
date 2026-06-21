import React from "react";
import clsx from "clsx";

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  hoverEffect?: boolean;
  glowEffect?: boolean;
  glowColor?: "primary" | "bullish" | "bearish" | "none";
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  hoverEffect = true,
  glowEffect = false,
  glowColor = "none",
  ...props
}) => {
  const glowClasses = {
    none: "",
    primary: "shadow-glow-md border-accent-primary/20",
    bullish: "shadow-glow-bullish border-bullish/20",
    bearish: "shadow-glow-bearish border-bearish/20",
  };

  return (
    <div
      className={clsx(
        "relative backdrop-blur-md bg-bg-glass border border-border-subtle rounded-xl p-5 shadow-card transition-all duration-300",
        hoverEffect && "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-card-hover hover:border-border-medium",
        glowEffect && glowClasses[glowColor],
        className
      )}
      {...props}
    >
      {/* Background radial glow */}
      {glowEffect && glowColor !== "none" && (
        <div
          className={clsx(
            "absolute -inset-[1px] -z-10 rounded-xl blur-sm opacity-30 transition-opacity duration-300",
            glowColor === "primary" && "bg-gradient-to-r from-accent-primary to-accent-secondary",
            glowColor === "bullish" && "bg-bullish",
            glowColor === "bearish" && "bg-bearish"
          )}
        />
      )}
      {children}
    </div>
  );
};
