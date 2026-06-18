'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import MainLayout from './MainLayout';
import { useAuth } from '@/lib/auth-context';

const PUBLIC_ROUTES = ['/login', '/register'];

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router   = useRouter();
  const { user, loading } = useAuth();

  const isPublic = PUBLIC_ROUTES.includes(pathname);

  // Redirect unauthenticated users to /login (except on public routes)
  useEffect(() => {
    if (!loading && !user && !isPublic) {
      router.replace('/login?redirect=' + encodeURIComponent(pathname));
    }
  }, [loading, user, isPublic, pathname, router]);

  if (isPublic) {
    return <>{children}</>;
  }

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return <MainLayout>{children}</MainLayout>;
}
