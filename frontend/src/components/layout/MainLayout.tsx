'use client';

import React, { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { Footer } from "./Footer";
import { cn } from "@/lib/utils";

interface MainLayoutProps {
  children: React.ReactNode;
  /** Chart-heavy pages (e.g. markets/[symbol]) need the full viewport width
   * to lay a chart out beside a sidebar — the usual 1280px reading-width
   * cap leaves a large empty gutter on either side on wide monitors. */
  fullWidth?: boolean;
}

export default function MainLayout({ children, fullWidth = false }: MainLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // Mobile (< lg) the sidebar is an off-canvas drawer toggled by the header
  // hamburger; on desktop it stays as the fixed, collapsible rail.
  const [mobileOpen, setMobileOpen] = useState(false);

  // Route ışık-devri (P6/M12, Bible §06 MO-08): navigasyonda gelen içerik kısa
  // +lightness ile oturur (.route-cycle, opacity 0.92→1, --dur-route). REMOUNT YOK
  // (key kullanılmaz) → children state korunur; animasyonu class remove→reflow→add
  // ile yeniden oynatırız. Tüm DOM erişimi useEffect içinde → SSR-güvenli.
  const pathname = usePathname();
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    el.classList.remove("route-cycle");
    void el.offsetWidth; // reflow → animasyonu baştan tetikle
    el.classList.add("route-cycle");
  }, [pathname]);

  return (
    <div className="flex min-h-screen bg-bg-primary text-text-primary overflow-hidden">
      {/* Left Sidebar — fixed rail on desktop, slide-in drawer on mobile */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* Mobile drawer backdrop — S1d2: koşullu mount KALDIRILDI. Panel (Sidebar)
          transform ile 180ms kayarken scrim eskiden anında belirip anında yok
          oluyordu (iki yönde de desenkron, Doctrine §simetri ihlali). Artık scrim
          sürekli render edilir ve panelin BİREBİR aynı süre/easing'iyle
          (--dur-state + ease-signal) opaklık geçişi yapar → ikisi aynı anda
          başlar, aynı anda biter. Kapalıyken pointer-events-none (görünmez ama
          tıklanabilir yüzey BIRAKILMAZ); lg+ da display:none (lg:hidden).
          Scrim yoğunluğu kanonik Modal reçetesine hizalandı (/60 → /70). */}
      <div
        className={cn(
          "lg:hidden fixed inset-0 z-30 bg-e-0/70 backdrop-blur-sm",
          "transition-opacity duration-[var(--dur-state)] ease-signal",
          mobileOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        )}
        onClick={() => setMobileOpen(false)}
        aria-hidden
      />

      {/* Main Right Area — no left padding on mobile (drawer overlays), padded for
          the fixed rail on desktop. */}
      {/* M-0a (MO-01): padding-left animasyonu = layout-anim → transition KALDIRILDI (anlık snap). */}
      <div className={cn(
        "flex-1 flex flex-col min-w-0 relative pl-0",
        sidebarCollapsed ? "lg:pl-[72px]" : "lg:pl-[260px]"
      )}>
        {/* Top Header (includes TickerBand internally) */}
        <Header onMobileMenu={() => setMobileOpen(true)} />

        {/* Scrollable Content Container */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 space-y-6">
          <div ref={contentRef} className={fullWidth ? 'w-full' : 'max-w-7xl mx-auto w-full'}>
            {children}
          </div>
          <Footer />
        </main>
      </div>
    </div>
  );
}
