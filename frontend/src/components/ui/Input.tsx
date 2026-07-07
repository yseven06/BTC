import React from "react";
import clsx from "clsx";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  wrapperClassName?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, wrapperClassName, type = "text", ...props }, ref) => {
    return (
      <div className={clsx("flex flex-col space-y-1.5 w-full", wrapperClassName)}>
        {label && (
          <label className="text-xs font-display text-text-secondary select-none">
            {label}
          </label>
        )}
        <input
          type={type}
          className={clsx(
            "w-full px-3.5 py-2.5 rounded-lg text-sm bg-bg-secondary border border-border-medium text-text-primary placeholder:text-text-muted focus:border-accent-primary/80 focus:ring-1 focus:ring-accent-primary/50 outline-none transition-all duration-150",
            error && "border-bearish focus:border-bearish focus:ring-bearish/30",
            className
          )}
          ref={ref}
          {...props}
        />
        {error && (
          <span className="text-xs font-medium text-bearish mt-0.5">
            {error}
          </span>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
export default Input;
