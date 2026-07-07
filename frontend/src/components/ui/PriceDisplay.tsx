import React from "react";
import clsx from "clsx";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { formatCurrency, formatPercentage } from "@/lib/utils";

interface PriceDisplayProps {
  price?: number;
  change24h?: number;
  changePct24h?: number;
  currency?: "USD" | "TRY";
  className?: string;
  size?: "sm" | "md" | "lg";
}

export const PriceDisplay: React.FC<PriceDisplayProps> = ({
  price = 0,
  change24h = 0,
  changePct24h = 0,
  currency = "USD",
  className,
  size = "md",
}) => {
  const isPositive = changePct24h >= 0;

  // Single-source formatting (Bible §01 H7 · lib/utils).
  const formattedPrice = formatCurrency(price, currency);
  const formattedPct = formatPercentage(changePct24h);

  return (
    <div className={clsx("flex flex-col", className)}>
      <span
        className={clsx(
          "num font-num-560 text-text-primary" /* sahipli-numeral: Inter+tnum, agirlik 560; tracking govde-0 (P8/D3+D4) */,
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
            "flex items-center space-x-1 mt-0.5 text-xs num font-num-520",
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
