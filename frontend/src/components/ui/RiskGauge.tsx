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

  // Renk migration (P9.4b/D9-05): owned bull/amber/bear; inline rgba-glow
  // KALDIRILDI (COL-12). orange (palet-dışı) → amber: medium & high aynı
  // owned-sarı ailede — ayrım çubuk-yüksekliği (h-3/h-4) + etiket metniyle
  // korunur (renk-tek-kanal-değil, G-00-11); high, alfa ile koyulaştırıldı.
  const segmentColors = [
    "bg-bull",
    "bg-amber",
    "bg-amber/70",
    "bg-bear",
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
          "text-xs font-display uppercase tracking-wider",
          activeSegmentIdx === 0 && "text-bull",
          activeSegmentIdx === 1 && "text-amber",
          activeSegmentIdx === 2 && "text-amber/80",
          activeSegmentIdx === 3 && "text-bear"
        )}
      >
        {currentLabel}
      </span>
    </div>
  );
};
