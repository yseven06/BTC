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
  // Interaction (P7-D04/D05, INT-03): radius-button 10 · transition whitelist'i
  // (transform/bg/shadow) + --dur-micro · press-scale boyut-bağlı ve motion-safe
  // (reduced-motion'da scale hiç üretilmez, sizes map'inde). font-display (650,
  // Phase8) KORUNUR — D07 (weight 500) typography olduğundan uygulanmaz.
  const baseStyle =
    "inline-flex items-center justify-center font-display rounded-button transition-[transform,background-color,box-shadow] duration-micro focus-ring disabled:opacity-50 disabled:cursor-not-allowed";

  const variants = {
    primary: "bg-accent hover:bg-accent-hover text-white hover:shadow-cta",
    secondary: "bg-bg-tertiary border border-border-medium hover:bg-e-2 text-text-primary",
    ghost: "bg-transparent hover:bg-bg-tertiary text-text-secondary hover:text-text-primary",
    danger: "bg-bear hover:bg-bear/90 text-white",
    success: "bg-bull hover:bg-bull/90 text-white",
  };

  // Press-scale boyuta bağlı (INT-03): küçük buton daha derin (.96), md/lg daha ince
  // (.985). motion-safe: → reduced-motion'da hiç üretilmez (scale iptal).
  const sizes = {
    sm: "px-3 py-1.5 text-xs motion-safe:active:scale-[0.96]",
    md: "px-4 py-2 text-sm motion-safe:active:scale-[0.985]",
    lg: "px-6 py-3 text-base motion-safe:active:scale-[0.985]",
  };

  return (
    <button
      // Loading (P7-D06, INT-03/MO-06): sürekli-dönen spinner KALDIRILDI. Genişlik
      // sabit kalsın diye children her zaman render edilir; yükleme durumu
      // disabled (opacity-50 sönük) + aria-busy ile taşınır. Karot mikro-skeleton
      // Phase 3'te; bu ara-çözüm spinner-siz genişlik-kilitli disabled durumdur.
      className={clsx(baseStyle, variants[variant], sizes[size], className)}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...props}
    >
      {children}
    </button>
  );
};
export default Button;
