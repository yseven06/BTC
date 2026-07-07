"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Kanonik Toast primitifi (Bible §01 INT-09) — native window.alert() yerine.
 * "Üstten düşen E3 kesit": E3 cam yüzey (.glass-e3-overlay) + üstten-düşüş girişi
 * (animate-slide-down / slideDown, --dur-overlay) + z-toast (60). Dismiss "yukarı
 * çıkış + fade" = aynı slideDown keyframe'inin TERS oynatımı (reverse, yeni keyframe
 * yok — yalnız mevcut token/keyframe tüketimi). States: success (--amber tek-atım
 * → mevcut .tp-pulse-badge + data-lifecycle-event="user_win") · error (neden --tx2)
 * · info (nötr). a11y/zamanlayıcı/swipe @radix-ui/react-toast'tan.
 */

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  variant: ToastVariant;
  title: string;
  description?: string;
}

interface ToastApi {
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast, <ToastProvider> içinde kullanılmalı.");
  return ctx;
}

const VARIANT_ICON: Record<ToastVariant, React.ComponentType<{ className?: string }>> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

// İkon tonu: success = amber (olay-bağlı kazanç); error/info = luminans-only nötr
// (kırmızı YOK — INT-09 hata = "lümen düşüşü + neden", alarm-rengi değil).
const ICON_TONE: Record<ToastVariant, string> = {
  success: "text-amber",
  error: "text-text-secondary",
  info: "text-text-muted",
};

const AUTO_DISMISS_MS = 5000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const push = useCallback((variant: ToastVariant, title: string, description?: string) => {
    counter.current += 1;
    const id = counter.current;
    setToasts((prev) => [...prev, { id, variant, title, description }]);
  }, []);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (title, description) => push("success", title, description),
      error: (title, description) => push("error", title, description),
      info: (title, description) => push("info", title, description),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={api}>
      <ToastPrimitive.Provider swipeDirection="up" duration={AUTO_DISMISS_MS}>
        {children}

        {toasts.map((t) => {
          const Icon = VARIANT_ICON[t.variant];
          return (
            <ToastPrimitive.Root
              key={t.id}
              duration={AUTO_DISMISS_MS}
              onOpenChange={(open) => {
                if (!open) remove(t.id);
              }}
              data-lifecycle-event={t.variant === "success" ? "user_win" : undefined}
              className={cn(
                // E3 cam yüzey + panel yarıçapı (Modal ile aynı reçete).
                "glass-e3-overlay rounded-panel w-full p-4 flex items-start gap-3 outline-none",
                // Giriş: üstten-düşüş (mevcut slideDown @ --dur-overlay). motion-safe:
                // reduced-motion'da animasyon yok → anlık görünür (globals'a dokunulmaz).
                "motion-safe:data-[state=open]:animate-slide-down",
                // Dismiss: aynı slideDown'ın TERS oynatımı = yukarı çıkış + fade
                // (yeni keyframe yok; --dur-overlay tüketilir). forwards → biter, gizli kalır.
                // reduced-motion'da animasyon yok → Radix anlık kaldırır.
                "motion-safe:data-[state=closed]:[animation:slideDown_var(--dur-overlay)_ease-out_reverse_forwards]",
                // Swipe-up ile kapat (Radix değişkenleri).
                "data-[swipe=move]:translate-y-[var(--radix-toast-swipe-move-y)]",
                "data-[swipe=cancel]:translate-y-0 data-[swipe=cancel]:transition-transform",
                // success = --amber tek-atım foton (mevcut reçete).
                t.variant === "success" && "tp-pulse-badge"
              )}
            >
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", ICON_TONE[t.variant])} aria-hidden />
              <div className="min-w-0 flex-1">
                <ToastPrimitive.Title className="text-sm font-display text-text-primary">
                  {t.title}
                </ToastPrimitive.Title>
                {t.description && (
                  <ToastPrimitive.Description className="mt-0.5 text-xs leading-relaxed text-text-secondary">
                    {t.description}
                  </ToastPrimitive.Description>
                )}
              </div>
              <ToastPrimitive.Close
                aria-label="Kapat"
                className="focus-ring shrink-0 rounded-control p-0.5 text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          );
        })}

        {/* Tek Viewport: üstten-ortadan düşen yığın; z-toast (60). Boşken görünmez. */}
        <ToastPrimitive.Viewport className="fixed left-1/2 top-0 z-toast flex max-h-screen w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 flex-col gap-2 p-4 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export default ToastProvider;
