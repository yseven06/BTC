"use client";

import React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import clsx from "clsx";

interface TooltipProps {
  children: React.ReactNode;
  content: React.ReactNode;
  className?: string;
  delayDuration?: number;
}

export const Tooltip: React.FC<TooltipProps> = ({
  children,
  content,
  className,
  delayDuration = 200,
}) => {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          {children}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={4}
            className={clsx(
              // E3-materyal hizası (S1b2): z/radius/border token'a çekildi (z-toast =
              // modal-üstü görünürlük; rounded-control; E3-border hl22). Tooltip OPAK
              // kalır — yoğun-veri üstünde okunurluk için blur/glass/cut-lip EKLENMEZ;
              // bg-e-3 + shadow-e3 (S1a iki-katman) korunur. Giriş yalnız Radix'in açık
              // state'lerinde (delayed/instant-open); ÇIKIŞ animasyonu YOK (bilinçli —
              // CP-PRIMITIVE-CONTROLLED-EXIT'e ertelendi).
              "z-toast overflow-hidden rounded-control border border-border-hl22 bg-e-3 px-3 py-1.5 text-xs text-text-primary shadow-e3 motion-safe:data-[state=delayed-open]:animate-scale-in motion-safe:data-[state=instant-open]:animate-scale-in",
              className
            )}
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-border-hl22" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
};
export default Tooltip;

// ── ProvenanceReceipt (Bible §01-K craft-makbuz-grameri, v1.6 CP-PV1-B2) ──────
// Kanıt-makbuzu tek-biçimi: örneklem → dönem → era/sürüm, orta-nokta (·) ayraçlı,
// ikincil ton (tx2), mono/tabular sayı. "Fark efektte değil dürüstlük duruşunda"
// mikro-tipografisi. Saf presentational — Radix'e bağımlı DEĞİL → hem inline hem
// bir Tooltip içeriği olarak kullanılabilir. Mevcut Tooltip export'una dokunmaz.
// Yalnızca dolu segment'ler basılır (eksik alan uydurulmaz — no-backfill ruhu).
interface ProvenanceReceiptProps {
  /** Sırayla basılacak makbuz segment'leri, ör. ["n=5", "3G/2K", "v1"].
   *  null/undefined/boş segment atlanır. */
  segments: Array<React.ReactNode>;
  className?: string;
}
export const ProvenanceReceipt: React.FC<ProvenanceReceiptProps> = ({
  segments,
  className,
}) => {
  const parts = segments.filter((s) => s !== null && s !== undefined && s !== "");
  if (parts.length === 0) return null;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 text-micro text-text-secondary tabular-nums",
        className
      )}
    >
      {parts.map((p, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span aria-hidden className="text-text-muted">·</span>}
          <span>{p}</span>
        </React.Fragment>
      ))}
    </span>
  );
};
