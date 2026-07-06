import React from "react";
import clsx from "clsx";
import { SignalType } from "@/types";

interface SignalBadgeProps {
  type: SignalType;
  lang?: "tr" | "en";
  className?: string;
}

export const SignalBadge: React.FC<SignalBadgeProps> = ({
  type,
  lang = "tr",
  className,
}) => {
  const labels = {
    tr: {
      strong_buy: "Güçlü Long",
      buy: "Long",
      hold: "Bekle",
      sell: "Short",
      strong_sell: "Güçlü Short",
    },
    en: {
      strong_buy: "Strong Long",
      buy: "Long",
      hold: "Hold",
      sell: "Short",
      strong_sell: "Strong Short",
    },
  };

  // Renk migration (P9.4b/D9-05): owned bull/bear/amber; inline rgba-glow
  // KALDIRILDI (COL-12 semantik-glow=0). strong/normal ayrımı renk-dışı
  // kanallarla korunur: bg/border alfa (10/40 vs 5/20) + pulse (pulse→P6).
  const styleMap = {
    strong_buy: "bg-bull/10 text-bull border-bull/40 animate-pulse-slow",
    buy: "bg-bull/5 text-bull/90 border-bull/20",
    hold: "bg-amber/10 text-amber border-amber/30",
    sell: "bg-bear/5 text-bear/90 border-bear/20",
    strong_sell: "bg-bear/10 text-bear border-bear/40 animate-pulse-slow",
  };

  const currentLabel = labels[lang][type.toLowerCase() as keyof typeof labels["tr"]] || type;
  const currentStyle = styleMap[type.toLowerCase() as keyof typeof styleMap] || "bg-bg-tertiary text-text-secondary border-border-subtle";

  return (
    <span
      className={clsx(
        "inline-flex items-center justify-center px-3 py-1 text-xs font-semibold uppercase tracking-wider rounded-full border",
        currentStyle,
        className
      )}
    >
      {currentLabel}
    </span>
  );
};
