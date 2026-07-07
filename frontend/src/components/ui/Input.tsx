import React from "react";
import clsx from "clsx";
import { AlertCircle, Check } from "lucide-react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  /** Olay-bağlı doğrulama-başarısı: kısa --bull hairline + check ikonu (INT-05). */
  success?: boolean;
  wrapperClassName?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    { className, label, error, success, wrapperClassName, type = "text", readOnly, ...props },
    ref
  ) => {
    // Durum matrisi (Bible §01 INT-05/06, P7-D08..D12): dinlenme kenarı --hl12,
    // focus'ta --hl22 kenar + accent-ui outline halka (.focus-ring, INT-12); hata
    // ve başarı ÜÇ-KANAL (kenar rengi + ikon + metin/aria, salt-renk değil); salt-okur
    // sessiz --hl10 (odak-halkası yok). Geçiş whitelist border-color/box-shadow +
    // --dur-micro. Placeholder --tx2 (okunur ton; tx3 metin-dışıydı). radius 10 (INT-05).
    const stateBorder = error
      ? "border-bear focus:border-bear"
      : success
      ? "border-bull focus:border-bull"
      : readOnly
      ? "border-[var(--hl10)]"
      : "border-[var(--hl12)] focus:border-[var(--hl22)]";
    const hasIcon = Boolean(error) || Boolean(success && !error);

    return (
      <div className={clsx("flex flex-col space-y-1.5 w-full", wrapperClassName)}>
        {label && (
          <label className="text-xs font-display text-text-secondary select-none">
            {label}
          </label>
        )}
        <div className="relative">
          <input
            type={type}
            readOnly={readOnly}
            aria-invalid={error ? true : undefined}
            className={clsx(
              "w-full px-3.5 py-2.5 rounded-input text-sm bg-bg-secondary border text-text-primary placeholder:text-text-secondary transition-[border-color,box-shadow] duration-micro",
              hasIcon && "pr-10",
              readOnly ? "cursor-default" : "focus-ring",
              stateBorder,
              className
            )}
            ref={ref}
            {...props}
          />
          {error ? (
            <AlertCircle
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-bear"
              aria-hidden
            />
          ) : success ? (
            <Check
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-bull"
              aria-hidden
            />
          ) : null}
        </div>
        {error && (
          <span className="text-xs font-medium text-text-secondary mt-0.5">{error}</span>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
export default Input;
