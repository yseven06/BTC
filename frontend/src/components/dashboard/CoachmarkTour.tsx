'use client';

import React, { useCallback, useEffect, useLayoutEffect, useState } from 'react';

// One-time welcome tour (frontend-only, localStorage). Spotlights the 4 most
// important areas in the sidebar. Skippable in one click; ~30-45s.
const KEY = 'tm_tour_v1';

interface TourStep { sel: string; title: string; desc: string; }

const STEPS: TourStep[] = [
  { sel: '[data-tour="dashboard"]',       title: 'Gösterge Paneli',  desc: 'Piyasanın ve performansının tek ekranda özeti.' },
  { sel: '[data-tour="signals"]',         title: 'Sinyal Merkezi',   desc: 'AI motorlarının ürettiği canlı AL/SAT sinyalleri.' },
  { sel: '[data-tour="markets"]',         title: 'Piyasalar',        desc: 'Tüm coinleri keşfet; canlı grafik ve AI sinyallerini incele.' },
  { sel: '[data-tour="signal-history"]',  title: 'Sinyal Geçmişi',   desc: 'Geçmiş sinyaller ve gerçekleşen sonuçları.' },
];

interface Rect { top: number; left: number; width: number; height: number; }

export default function CoachmarkTour() {
  const [step, setStep] = useState(-1); // -1 = inactive
  const [rect, setRect] = useState<Rect | null>(null);

  // Start once, shortly after mount (so the sidebar is in the DOM).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    let done = false;
    try { done = localStorage.getItem(KEY) === 'done'; } catch { /* ignore */ }
    if (done) return;
    const t = setTimeout(() => setStep(0), 700);
    return () => clearTimeout(t);
  }, []);

  const measure = useCallback(() => {
    if (step < 0) return;
    const el = document.querySelector(STEPS[step].sel) as HTMLElement | null;
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [step]);

  useLayoutEffect(() => { measure(); }, [measure]);

  useEffect(() => {
    if (step < 0) return;
    const onResize = () => measure();
    window.addEventListener('resize', onResize);
    window.addEventListener('scroll', onResize, true);
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onResize, true);
    };
  }, [step, measure]);

  const finish = useCallback(() => {
    try { localStorage.setItem(KEY, 'done'); } catch { /* ignore */ }
    setStep(-1);
  }, []);

  if (step < 0) return null;

  const cur = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const pad = 8;

  const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
  const tipTop = rect ? Math.min(Math.max(12, rect.top - 4), vh - 200) : 96;
  const tipLeft = rect ? rect.left + rect.width + 14 : 96;

  return (
    <div className="fixed inset-0 z-[100]">
      {/* Click blocker — clicking the dimmed area does nothing (no accidental skip) */}
      <div className="absolute inset-0" />

      {/* Spotlight (also dims everything else via large box-shadow) */}
      {rect && (
        <div
          className="absolute rounded-xl pointer-events-none transition-all duration-[var(--dur-state)]"
          style={{
            top: rect.top - pad,
            left: rect.left - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            boxShadow: '0 0 0 9999px color-mix(in oklab, var(--e0) 72%, transparent)' /* #020817 emekli -> e0 (D9-12) */,
            border: '2px solid var(--accent-primary)',
          }}
        />
      )}

      {/* Tooltip card */}
      <div
        className="absolute w-[280px] max-w-[80vw] glass-panel border border-accent-primary/40 rounded-2xl p-4"
        style={{ top: tipTop, left: tipLeft }}
        role="dialog"
        aria-label="Tanıtım turu"
      >
        <div className="flex items-center justify-between">
          <span className="text-micro font-medium uppercase text-accent-primary">
            Tanıtım · {step + 1}/{STEPS.length}
          </span>
          <button onClick={finish} className="focus-ring rounded text-xs font-display text-text-muted hover:text-text-primary transition-colors">
            Turu atla
          </button>
        </div>
        <h3 className="text-sm font-display text-text-primary mt-2">{cur.title}</h3>
        <p className="text-xs text-text-secondary mt-1 leading-relaxed">{cur.desc}</p>
        <div className="flex items-center justify-between mt-3">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="focus-ring rounded text-xs font-display text-text-secondary hover:text-text-primary disabled:opacity-40 disabled:cursor-default transition-colors"
          >
            Geri
          </button>
          <button
            onClick={() => (isLast ? finish() : setStep((s) => s + 1))}
            className="focus-ring inline-flex items-center text-xs font-display bg-accent-primary hover:bg-accent-hover text-white px-4 py-1.5 rounded-xl transition-colors"
          >
            {isLast ? 'Bitir' : 'İleri'}
          </button>
        </div>
      </div>
    </div>
  );
}
