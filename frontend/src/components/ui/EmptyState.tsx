import React from "react";
import clsx from "clsx";
import { FolderOpen } from "lucide-react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

// L3 grid kâğıdı — 1px ızgara (--hl10, katman opacity ile ~%5 efektif), radial-maskeyle
// eriyen (VL §02/§03). Statik. Gerçek içeriğin altında.
const GRID_LAYER: React.CSSProperties = {
  backgroundImage:
    "linear-gradient(var(--hl10) 1px, transparent 1px), linear-gradient(90deg, var(--hl10) 1px, transparent 1px)",
  backgroundSize: "22px 22px",
  WebkitMaskImage: "radial-gradient(ellipse 72% 68% at 50% 42%, black 24%, transparent 72%)",
  maskImage: "radial-gradient(ellipse 72% 68% at 50% 42%, black 24%, transparent 72%)",
};

// L2 noise — mono grain (feColorMatrix saturate 0), soft-light blend, α .045 (VL §04
// .02–.06 tavanı), 128px feTurbulence tek-tile data-URI (<2KB), banding-katili. Statik.
const NOISE_LAYER: React.CSSProperties = {
  backgroundImage:
    `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='128' height='128'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='128' height='128' filter='url(%23n)'/%3E%3C/svg%3E")`,
  backgroundSize: "128px 128px",
  mixBlendMode: "soft-light",
  opacity: 0.045,
};

/**
 * Boş-durum bileşeni. Atmosfer (VL §02/§04): app'in TEK noise istisnası, YALNIZ kart
 * sınırları içinde (overflow-hidden), STATİK (motion yok → reduced-motion nötr), gerçek
 * içeriğin ALTINDA ve hafif — veriyi gölgelemez. EmptyState yalnız veri-yokken render
 * olur → veri gelince (unmount) atmosfer de kalkar. İçerik (başlık/desc/CTA) çağırandan
 * gelir; ileride gerçek telemetry/event verisi bu bileşene aynı yapıyla beslenebilir.
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      className={clsx(
        "relative overflow-hidden flex flex-col items-center justify-center p-8 text-center rounded-xl border border-dashed border-border-medium bg-e-1",
        className
      )}
    >
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-50" style={GRID_LAYER} />
      <div aria-hidden className="pointer-events-none absolute inset-0" style={NOISE_LAYER} />

      <div className="relative flex flex-col items-center">
        <div className="flex items-center justify-center w-12 h-12 rounded-full bg-bg-tertiary border border-border-subtle text-text-muted mb-4">
          {icon || <FolderOpen className="w-6 h-6 text-accent-primary" />}
        </div>
        <h3 className="text-base font-display text-text-primary mb-1">{title}</h3>
        <p className="text-xs text-text-secondary max-w-[280px] mb-4">{description}</p>
        {action && <div className="flex justify-center">{action}</div>}
      </div>
    </div>
  );
};
export default EmptyState;
