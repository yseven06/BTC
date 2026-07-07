import React from "react";
import clsx from "clsx";
import { formatPercentage } from '@/lib/utils';

interface ScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  className?: string;
}

export const ScoreRing: React.FC<ScoreRingProps> = ({
  score,
  size = 70,
  strokeWidth = 6,
  label,
  className,
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  // Statik render (P6/M09, Bible §06 MO-04): halka gerçek değerinde doğar —
  // mount'ta rAF+state ile "dolum" (count-up-benzeri, olaysız dekoratif) KALDIRILDI.
  const offset = circumference - (score / 100) * circumference;

  // Determine indicator color based on score value
  const getStrokeColor = (val: number) => {
    if (val >= 75) return "stroke-bullish";
    if (val >= 50) return "stroke-accent-primary";
    if (val >= 35) return "stroke-amber";
    return "stroke-bearish";
  };

  return (
    <div className={clsx("flex flex-col items-center justify-center", className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg className="w-full h-full -rotate-90">
          {/* Background circle */}
          <circle
            className="stroke-bg-tertiary"
            strokeWidth={strokeWidth}
            fill="transparent"
            r={radius}
            cx={size / 2}
            cy={size / 2}
          />
          {/* Progress circle */}
          <circle
            className={getStrokeColor(score)}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            fill="transparent"
            r={radius}
            cx={size / 2}
            cy={size / 2}
          />
        </svg>
        {/* Central percentage text */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className="font-display text-text-primary font-mono leading-none"
            style={{ fontSize: Math.max(8, size * 0.21) }}
          >
            {formatPercentage(score, 0, false)}
          </span>
        </div>
      </div>
      {label && <span className="mt-2 text-xs text-text-secondary font-medium">{label}</span>}
    </div>
  );
};
