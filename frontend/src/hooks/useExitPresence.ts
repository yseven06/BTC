"use client";

import { useEffect, useRef, useState } from "react";

/**
 * useExitPresence — PI-1a Modal çıkış-mekanizmasının yeniden-kullanılabilir çıkarımı
 * (PI-2c · disclosure enter+exit settle). `value != null` iken AÇIK; null olunca hemen
 * unmount ETMEZ, önce çıkış animasyonunu oynatır, DETERMİNİSTİK timer ile kaldırır
 * (animationend enter/exit yarışı YOK). Çıkış boyunca son non-null `value` önbelleklenir
 * → içerik kaybolmadan çıkış oynar.
 *
 * Süre, `ref`li elemanın computed `animation-duration`'ından (tek-kaynak `--dur-*`
 * token) okunur; reduced-motion global kuralı 0.01ms'ye indirir → timer ~anlık →
 * çıkış görünmeden kaldırılır (bilgi kaybı yok). Yalnız transform/opacity keyframe'leri
 * (fadeIn/scaleIn) çağıran taraf uygular; hook motion taşımaz.
 */
export function useExitPresence<T, E extends HTMLElement = HTMLDivElement>(
  value: T | null | undefined
): { rendered: boolean; closing: boolean; value: T; ref: React.RefObject<E | null> } {
  const open = value != null;
  const [rendered, setRendered] = useState(open);
  const [closing, setClosing] = useState(false);
  const last = useRef<T | null | undefined>(value);
  if (value != null) last.current = value;
  const ref = useRef<E>(null);

  // open → render/çıkış köprüsü (Modal.tsx deseni birebir): açılışta anında render;
  // kapanışta çıkış başlar (aşağıdaki timer unmount'u zamanlar).
  useEffect(() => {
    if (open) {
      setRendered(true);
      setClosing(false);
    } else if (rendered) {
      setClosing(true);
    }
  }, [open, rendered]);

  // Çıkış SÜRESİ kadar bekle → unmount. Süre ref'li elemanın computed
  // animation-duration'ından (tek-kaynak token) + küçük tampon.
  useEffect(() => {
    if (!closing) return;
    let ms = 400; // güvenli fallback (>--dur-overlay 360ms)
    const el = ref.current;
    if (el) {
      const raw = getComputedStyle(el).animationDuration.split(",")[0].trim();
      const parsed = raw.endsWith("ms") ? parseFloat(raw) : parseFloat(raw) * 1000;
      if (!Number.isNaN(parsed)) ms = parsed + 40;
    }
    const t = setTimeout(() => {
      setRendered(false);
      setClosing(false);
    }, ms);
    return () => clearTimeout(t);
  }, [closing]);

  return { rendered, closing, value: (value ?? last.current) as T, ref };
}
