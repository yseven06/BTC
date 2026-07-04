import React, { useEffect, useState } from "react";
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
  // The ring's CSS transition only fires on a *change*, not on first paint —
  // rendering the real offset immediately means it shows up already full,
  // with no "filling in" feel. Starting from an empty ring and flipping to
  // the real value one frame later gives it something to animate from.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const offset = filled ? circumference - (score / 100) * circumference : circumference;

  // Determine indicator color based on score value
  const getStrokeColor = (val: number) => {
    if (val >= 75) return "stroke-bullish";
    if (val >= 50) return "stroke-accent-primary";
    if (val >= 35) return "stroke-signal-hold";
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
            className={clsx("transition-all duration-1000 ease-out", getStrokeColor(score))}
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
            className="font-bold text-text-primary font-mono leading-none"
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
