import React from "react";
import clsx from "clsx";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  className,
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled,
  ...props
}) => {
  // Renk migration (P9.4a/D9-04): focus=accent-ui (COL-04 1px-UI) · primary
  // dolgu=accent, hover=accent-hover (indigo-600 emekli) · danger/success ham
  // red/green-600 hover + rgba-glow KALDIRILDI (COL-12 semantik-glow=0).
  const baseStyle =
    "inline-flex items-center justify-center font-semibold rounded-lg transition-all duration-200 outline-none focus:ring-2 focus:ring-accent-ui/50 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]";

  const variants = {
    primary: "bg-accent hover:bg-accent-hover text-white hover:shadow-cta",
    secondary: "bg-bg-tertiary border border-border-medium hover:bg-e-2 text-text-primary",
    ghost: "bg-transparent hover:bg-bg-tertiary text-text-secondary hover:text-text-primary",
    danger: "bg-bear hover:bg-bear/90 text-white",
    success: "bg-bull hover:bg-bull/90 text-white",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button
      className={clsx(baseStyle, variants[variant], sizes[size], className)}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="flex items-center space-x-2">
          <svg className="animate-spin h-4 w-4 text-current" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>{children}</span>
        </span>
      ) : (
        children
      )}
    </button>
  );
};
export default Button;
