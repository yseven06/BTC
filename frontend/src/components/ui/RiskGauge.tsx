import React from "react";
import clsx from "clsx";
import { RiskLevel } from "@/types";

interface RiskGaugeProps {
  level: RiskLevel;
  lang?: "tr" | "en";
  className?: string;
}

export const RiskGauge: React.FC<RiskGaugeProps> = ({
  level,
  lang = "tr",
  className,
}) => {
  const labels = {
    tr: {
      low: "Düşük",
      medium: "Orta",
      high: "Yüksek",
      very_high: "Çok Yüksek",
    },
    en: {
      low: "Low",
      medium: "Medium",
      high: "High",
      very_high: "Very High",
    },
  };

  const activeSegmentIdx = {
    low: 0,
    medium: 1,
    high: 2,
    very_high: 3,
  }[level.toLowerCase() as keyof typeof labels["tr"]] ?? 1;

  const segmentColors = [
    "bg-bullish shadow-[0_0_8px_rgba(0,230,118,0.3)]",
    "bg-signal-hold shadow-[0_0_8px_rgba(255,193,7,0.3)]",
    "bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.3)]",
    "bg-bearish shadow-[0_0_8px_rgba(255,82,82,0.3)]",
  ];

  const currentLabel = labels[lang][level.toLowerCase() as keyof typeof labels["tr"]] || level;

  return (
    <div className={clsx("flex flex-col items-center justify-center", className)}>
      <div className="flex space-x-1.5 items-end justify-center w-full max-w-[120px] h-6 mb-1.5">
        {[0, 1, 2, 3].map((idx) => {
          const isActive = idx === activeSegmentIdx;
          return (
            <div
              key={idx}
              className={clsx(
                "w-full rounded-sm transition-all duration-500",
                idx === 0 && "h-2",
                idx === 1 && "h-3",
                idx === 2 && "h-4",
                idx === 3 && "h-5",
                isActive ? segmentColors[idx] : "bg-bg-tertiary"
              )}
            />
          );
        })}
      </div>
      <span
        className={clsx(
          "text-xs font-bold uppercase tracking-wider",
          activeSegmentIdx === 0 && "text-bullish",
          activeSegmentIdx === 1 && "text-signal-hold",
          activeSegmentIdx === 2 && "text-orange-400",
          activeSegmentIdx === 3 && "text-bearish"
        )}
      >
        {currentLabel}
      </span>
    </div>
  );
};
