import React from "react";
import clsx from "clsx";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "primary" | "secondary" | "success" | "danger" | "warning";
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  className,
  variant = "primary",
  ...props
}) => {
  const styles = {
    primary: "bg-accent-primary/10 text-accent-primary border-accent-primary/20",
    secondary: "bg-bg-tertiary text-text-secondary border-border-medium",
    success: "bg-bullish/10 text-bullish border-bullish/20",
    danger: "bg-bearish/10 text-bearish border-bearish/20",
    warning: "bg-amber/10 text-amber border-amber/20",
  };

  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 text-[10px] font-bold rounded-md border tracking-wide uppercase",
        styles[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
export default Badge;
