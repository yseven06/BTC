'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import MainLayout from './MainLayout';
import { Footer } from './Footer';
import { useAuth } from '@/lib/auth-context';

const PUBLIC_ROUTES = ['/', '/login', '/register'];

// Legal pages (/yasal, /yasal/<slug>) must be reachable without auth — they are
// linked from the footer, the register form, and need to be publicly viewable.
function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTES.includes(pathname) || pathname === '/yasal' || pathname.startsWith('/yasal/');
}

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router   = useRouter();
  const { user, loading } = useAuth();

  const isPublic = isPublicRoute(pathname);

  // Redirect unauthenticated users to /login (except on public routes).
  // If the session expired (a refresh attempt definitively failed), carry a
  // ?reason=expired so login can explain why — instead of a silent bounce.
  useEffect(() => {
    if (!loading && !user && !isPublic) {
      const params = new URLSearchParams({ redirect: pathname });
      if (typeof window !== 'undefined' && sessionStorage.getItem('session_expired') === '1') {
        params.set('reason', 'expired');
        sessionStorage.removeItem('session_expired');
      }
      router.replace('/login?' + params.toString());
    }
  }, [loading, user, isPublic, pathname, router]);

  if (isPublic) {
    return (
      <>
        {children}
        <Footer />
      </>
    );
  }

  // Initial auth probe still in flight → branded splash (P1-#1). Mirrors the
  // login page's brand block (same logo/typography) so splash→app or
  // splash→login feels visually continuous. Same `loading` condition — only
  // the visual changed; all classes/assets are existing (no new tokens).
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="flex flex-col items-center animate-fade-in">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-3">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-full h-full object-contain" />
          </div>
          <div className="text-h2 font-display gradient-text-brand">TradeMinds</div>
          <p className="text-sm text-text-secondary mt-1">AI Trading Intelligence</p>
          <div className="mt-6 w-5 h-5 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  // Probe finished but no user → useEffect above is redirecting to /login.
  // Render nothing so the user sees an immediate transition rather than a
  // spinner that never resolves while waiting for the redirect.
  if (!user) {
    return null;
  }

  const fullWidth = pathname.startsWith('/markets/');
  return <MainLayout fullWidth={fullWidth}>{children}</MainLayout>;
}
