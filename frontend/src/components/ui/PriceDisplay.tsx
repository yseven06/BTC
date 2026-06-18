import React from "react";
import clsx from "clsx";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

interface PriceDisplayProps {
  price?: number;
  change24h?: number;
  changePct24h?: number;
  currency?: "USD" | "TRY";
  precision?: number;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export const PriceDisplay: React.FC<PriceDisplayProps> = ({
  price = 0,
  change24h = 0,
  changePct24h = 0,
  currency = "USD",
  precision,
  className,
  size = "md",
}) => {
  const isPositive = changePct24h >= 0;

  // Determine decimal precision based on price value
  const getPrecision = (val: number) => {
    if (precision !== undefined) return precision;
    if (val === 0) return 2;
    if (val < 0.1) return 6;
    if (val < 1.0) return 4;
    return 2;
  };

  const formattedPrice = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: getPrecision(price),
    maximumFractionDigits: getPrecision(price),
  }).format(price);

  const formattedPct = `${isPositive ? "+" : ""}${changePct24h.toFixed(2)}%`;

  return (
    <div className={clsx("flex flex-col", className)}>
      <span
        className={clsx(
          "font-bold font-mono tracking-tight text-text-primary",
          size === "sm" && "text-sm",
          size === "md" && "text-lg",
          size === "lg" && "text-2xl md:text-3xl"
        )}
      >
        {formattedPrice}
      </span>
      {changePct24h !== 0 && (
        <div
          className={clsx(
            "flex items-center space-x-1 mt-0.5 text-xs font-semibold",
            isPositive ? "text-bullish" : "text-bearish"
          )}
        >
          {isPositive ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
          <span>{formattedPct}</span>
        </div>
      )}
    </div>
  );
};
