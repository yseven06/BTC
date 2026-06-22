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

  const styleMap = {
    strong_buy: "bg-bullish/10 text-bullish border-bullish/40 shadow-[0_0_12px_rgba(0,230,118,0.25)] animate-pulse-slow",
    buy: "bg-bullish/5 text-bullish/90 border-bullish/20",
    hold: "bg-signal-hold/10 text-signal-hold border-signal-hold/30",
    sell: "bg-bearish/5 text-bearish/90 border-bearish/20",
    strong_sell: "bg-bearish/10 text-bearish border-bearish/40 shadow-[0_0_12px_rgba(255,82,82,0.25)] animate-pulse-slow",
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
