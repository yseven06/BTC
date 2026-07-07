"use client";

import React, { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Başlık — verilirse üst-şeritte + kapat düğmesi (aria-labelledby ile bağlanır). */
  title?: React.ReactNode;
  /** title yokken role=dialog için erişilebilir isim (WCAG 4.1.2). */
  ariaLabel?: string;
  children: React.ReactNode;
  /** Alt aksiyon şeridi (yalnız padded modunda). */
  footer?: React.ReactNode;
  /** Panel genişlik sınıfı (varsayılan max-w-lg). */
  size?: string;
  /** Backdrop tıklaması + ESC ile kapanma. Kritik/blocking onaylarda false ver. */
  dismissible?: boolean;
  /** Mobil hizalama: bottom = alttan sayfa (items-end), center = ortalı. */
  align?: "center" | "bottom";
  /** Panel className — cn/tailwind-merge ile max-h/size override edilebilir. */
  className?: string;
  /** Başlıkla birlikte kapat düğmesi (varsayılan true). */
  showClose?: boolean;
  /** z-index sınıfı (varsayılan z-modal=50; nested/blocking için override edilir). */
  zIndexClassName?: string;
  /** false → children doğrudan panele girer (başlık/scroll/padding yok); çok-bölgeli
   *  veya kenar-kenar (edge-to-edge) içerik kendi layout'unu kurar. */
  padded?: boolean;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

function isVisible(el: HTMLElement): boolean {
  // checkVisibility yeni tarayıcılarda kesin; yoksa offsetParent + rect fallback
  // (position:fixed focusable'ı yanlış elemesin diye rect kontrolü eklenir).
  const anyEl = el as HTMLElement & { checkVisibility?: () => boolean };
  if (typeof anyEl.checkVisibility === "function") return anyEl.checkVisibility();
  const r = el.getBoundingClientRect();
  return r.width > 0 || r.height > 0;
}

/**
 * Tek kanonik modal primitifi (Bible §01 INT-10 / G-00-09):
 * role=dialog + aria-modal + erişilebilir-isim (title→labelledby / ariaLabel),
 * panel-kapsamlı focus-trap + ESC (iç bileşen/yığın modal'ı bozmaz), gövde-scroll
 * kilidi, odak-iadesi, E3 yüzey (.glass-e3-overlay → reduced-transparency opak
 * fallback), z-modal named-token (nested/blocking için override), --dur-overlay/
 * --dur-state açılış animasyonu, body portalı (stacking-context bağımsız).
 * Kapanış animasyonu şimdilik anlık (çıkış-geçişi ayrı iş).
 */
export function Modal({
  open,
  onClose,
  title,
  ariaLabel,
  children,
  footer,
  size = "max-w-lg",
  dismissible = true,
  align = "center",
  className,
  showClose = true,
  zIndexClassName = "z-modal",
  padded = true,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const downOnBackdrop = useRef(false);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const getFocusables = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return [] as HTMLElement[];
    return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(isVisible);
  }, []);

  // Açılış: odak-noktasını sakla (bir kez), paneli odakla, gövdeyi kilitle;
  // kapanışta odağı iade et. deps yalnız [open] → open sürerken prop değişimi
  // odak-noktasını YENIDEN yakalamaz (lifecycle-review düzeltmesi).
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null;
    // İlk odak paneli hedefler (X düğmesine değil — a11y anti-pattern'den kaçınır;
    // SR başlığı duyurur, kullanıcı içeriğe Tab'lar).
    panelRef.current?.focus();

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
      restoreFocusRef.current?.focus?.();
      restoreFocusRef.current = null;
    };
  }, [open]);

  // ESC + focus-trap panelin KENDİ onKeyDown'ında (document capture DEĞİL):
  // iç dropdown/popover kendi ESC'ini stopPropagation ile önce yakalayabilir;
  // yığın modallarda yalnız odaklı (en üstteki) panel ESC alır.
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape" && dismissible) {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const f = getFocusables();
      const panel = panelRef.current;
      if (f.length === 0) {
        e.preventDefault();
        panel?.focus();
        return;
      }
      const first = f[0];
      const last = f[f.length - 1];
      const active = document.activeElement;
      // Odak panel dışına kaçtıysa sınıra geri çek (gerçek trap).
      if (panel && active instanceof Node && !panel.contains(active)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
        return;
      }
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [dismissible, getFocusables]
  );

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 flex justify-center p-4 bg-e-0/70 backdrop-blur-sm animate-in",
        zIndexClassName,
        align === "bottom" ? "items-end md:items-center" : "items-center"
      )}
      role="presentation"
      onMouseDown={(e) => {
        downOnBackdrop.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (dismissible && downOnBackdrop.current && e.target === e.currentTarget) onClose();
        downOnBackdrop.current = false;
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={!title ? ariaLabel : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={cn(
          "glass-e3-overlay rounded-panel w-full flex flex-col max-h-[90vh] outline-none animate-scale-in",
          size,
          className
        )}
      >
        {padded ? (
          <>
            {title && (
              <div className="flex items-center justify-between gap-4 px-5 pt-4 pb-3 border-b border-[var(--hl12)] shrink-0">
                <h2 id={titleId} className="text-h4 font-display text-text-primary min-w-0 truncate">
                  {title}
                </h2>
                {showClose && dismissible && (
                  <button
                    type="button"
                    onClick={onClose}
                    aria-label="Kapat"
                    className="focus-ring rounded-control p-1 text-text-secondary hover:text-text-primary hover:bg-e-2 transition-[background-color,color] duration-micro shrink-0"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}
            <div className="overflow-y-auto p-5 grow">{children}</div>
            {footer && (
              <div className="px-5 py-4 border-t border-[var(--hl12)] shrink-0">{footer}</div>
            )}
          </>
        ) : (
          children
        )}
      </div>
    </div>,
    document.body
  );
}

export default Modal;
