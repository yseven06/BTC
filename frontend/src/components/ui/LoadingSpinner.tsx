import React from "react";
import clsx from "clsx";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  className,
  label,
}) => {
  const sizeClasses = {
    sm: "w-5 h-5 border-2",
    md: "w-8 h-8 border-[3px]",
    lg: "w-12 h-12 border-4",
  };

  return (
    <div className={clsx("flex flex-col items-center justify-center space-y-3", className)}>
      <div
        className={clsx(
          "rounded-full border-t-accent-primary border-r-accent-primary/20 border-b-accent-primary/20 border-l-accent-primary/20 animate-spin",
          sizeClasses[size]
        )}
      />
      {label && (
        <span className="text-xs font-semibold text-text-secondary animate-pulse-slow">
          {label}
        </span>
      )}
    </div>
  );
};
export default LoadingSpinner;
