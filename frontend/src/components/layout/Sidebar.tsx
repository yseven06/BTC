'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Zap, TrendingUp, Star, PieChart, Bell,
  BarChart3, BarChart2, Settings, ChevronLeft, ChevronRight,
  LogOut, User, Newspaper, Crown, Microscope, CreditCard,
  Globe, Shield, History,
} from 'lucide-react';
import { cn, formatDateTR } from '@/lib/utils';
import { Tooltip } from '@/components/ui/Tooltip';
import { PAYMENTS_ENABLED } from '@/lib/config';
import {
  fetchMySubscription, fetchActiveSignals,
  type SubscriptionResponse,
} from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { useAlerts } from '@/hooks/useAlerts';

interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  badge?: number;
}

const navItems: NavItem[] = [
  { id: 'dashboard',   label: 'Gösterge Paneli', icon: LayoutDashboard, href: '/dashboard' },
  { id: 'signals',     label: 'Sinyal Merkezi',  icon: Zap,             href: '/signals' },
  { id: 'signal-history', label: 'Sinyal Geçmişi', icon: History,       href: '/signal-history' },
  { id: 'markets',     label: 'Piyasalar',       icon: TrendingUp,      href: '/markets' },
  { id: 'portfolio',   label: 'Portföy',         icon: PieChart,        href: '/portfolio' },
  { id: 'performance',    label: 'Performans & Backtest', icon: BarChart3, href: '/performance' },
  { id: 'strategy-lab',   label: 'Strategy Lab',     icon: Microscope,    href: '/strategy-lab' },
  { id: 'symbol-analysis', label: 'Sembol Analizi',  icon: BarChart2,     href: '/symbol-analysis' },
  { id: 'macro',          label: 'Makro Görünüm',     icon: Globe,         href: '/macro' },
  { id: 'alerts',      label: 'Alarmlar',         icon: Bell,            href: '/alerts' },
  { id: 'watchlist',   label: 'İzleme Listesi',  icon: Star,            href: '/watchlist' },
  { id: 'news',        label: 'Haberler',         icon: Newspaper,       href: '/news' },
  { id: 'pricing',     label: 'Fiyatlandırma',    icon: CreditCard,      href: '/pricing' },
  { id: 'settings',    label: 'Ayarlar',          icon: Settings,        href: '/settings' },
];

const adminNavItem: NavItem = {
  id: 'admin', label: 'Yönetim Paneli', icon: Shield, href: '/admin',
};

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function Sidebar({ collapsed, onToggle, mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const { user: authUser, logout: doLogout } = useAuth();
  const [sub, setSub] = useState<SubscriptionResponse | null>(null);
  const [signalBadge, setSignalBadge] = useState(0);
  // Alerts come from the shared single-source hook (no duplicate /alerts fetch).
  const alerts = useAlerts();
  const alertBadge = alerts.filter((x) => !x.triggered_at).length;

  useEffect(() => {
    fetchMySubscription().then(setSub).catch(() => {});
    fetchActiveSignals({ only_actionable: true, page_size: 1 }).then((r) => setSignalBadge(r.total)).catch(() => {});
  }, []);

  const navBadges: Record<string, number> = { signals: signalBadge, alerts: alertBadge };

  // AuthContext is the single source of truth for the current user.
  const effectiveUser = authUser;

  const isAdmin = !!effectiveUser?.is_admin;
  const tier    = isAdmin ? 'admin' : (sub?.tier ?? 'free');
  const isFree  = tier === 'free';
  const planName  = isAdmin ? 'Kurucu (Admin)'
                  : tier === 'premium' ? 'Premium'
                  : tier === 'pro' ? 'Pro Plan'
                  : 'Ücretsiz Plan';
  const planColor = isAdmin ? 'text-accent-ui'
                  : tier === 'premium' ? 'text-amber'
                  : tier === 'pro' ? 'text-accent-primary'
                  : 'text-text-muted';
  const expiry = sub?.current_period_end
    ? formatDateTR(sub.current_period_end)
    : null;

  const displayName = effectiveUser?.full_name ?? effectiveUser?.email?.split('@')[0] ?? 'Trader';

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen flex flex-col',
        'glass-panel border-r border-border-subtle',
        'transition-all duration-[var(--dur-state)] ease-in-out',
        // Off-canvas drawer on mobile; always visible on desktop (lg+).
        '-translate-x-full lg:translate-x-0',
        mobileOpen && 'translate-x-0',
        collapsed ? 'w-[72px]' : 'w-[220px]'
      )}
    >
      {/* Logo */}
      <div className={cn('flex items-center h-16 px-4 border-b border-border-subtle', collapsed ? 'justify-center' : 'gap-3')}>
        <div className="relative flex items-center justify-center w-9 h-9 flex-shrink-0">
          <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-full h-full object-contain" />
        </div>
        {!collapsed && (
          <div className="animate-fade-in overflow-hidden">
            <div className="flex items-center gap-1.5">
              <h1 className="text-base font-display text-text-primary whitespace-nowrap">TradeMinds</h1>
              <span className="text-micro font-medium uppercase text-accent-primary bg-accent-primary/12 border border-accent-primary/30 px-1.5 py-0.5 rounded">BETA</span>
            </div>
            <p className="text-micro text-text-muted font-medium uppercase">AI Trading</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {[...navItems, ...(effectiveUser?.is_admin ? [adminNavItem] : [])].map((item) => {
          const isActive = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
          const Icon = item.icon;
          const badge = navBadges[item.id] ?? 0;
          return (
            <Link
              key={item.id}
              href={item.href}
              data-tour={item.id}
              onClick={onMobileClose}
              className={cn(
                'nav-item group relative',
                isActive && 'active',
                collapsed && 'justify-center px-0'
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={cn('w-4 h-4 flex-shrink-0 transition-colors', isActive ? 'text-accent-ui' : 'text-text-muted group-hover:text-text-primary')} />
              {!collapsed && (
                <span className="text-sm animate-fade-in whitespace-nowrap flex-1">{item.label}</span>
              )}
              {!collapsed && badge > 0 && (
                <span className="flex items-center justify-center min-w-[18px] h-4.5 px-1 text-micro font-medium font-mono rounded-full bg-accent-primary/20 text-accent-primary">
                  {badge}
                </span>
              )}
              {collapsed && badge > 0 && (
                <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-accent-primary" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Plan Section */}
      {!collapsed && (
        <div className="mx-2 mb-2 p-3 rounded-xl bg-gradient-to-br from-amber/10 to-accent-primary/10 border border-amber/20">
          <div className="flex items-center gap-2 mb-2">
            <Crown className={cn('w-4 h-4', tier === 'premium' ? 'text-amber' : 'text-amber')} />
            <span className={cn('text-xs font-display', planColor)}>{planName}</span>
            <span className={cn(
              'ml-auto text-micro px-1.5 py-0.5 rounded font-medium',
              isFree ? 'bg-text-muted/30 text-text-muted' : 'bg-amber text-e-0'
            )}>
              {isFree ? 'Pasif' : 'Aktif'}
            </span>
          </div>
          {isAdmin ? (
            <p className="text-micro text-text-muted">Sınırsız erişim · tüm özellikler aktif.</p>
          ) : isFree ? (
            <p className="text-micro text-text-muted">{PAYMENTS_ENABLED ? 'Sınırsız sinyal için yükselt.' : 'Ücretsiz plan.'}</p>
          ) : expiry ? (
            <p className="text-micro text-text-muted">Sona erme: {expiry}</p>
          ) : null}
          {/* Beta: hide the "Yükselt" upgrade CTA for free users while payments are off */}
          {(isAdmin || !isFree || PAYMENTS_ENABLED) && (
            <Link
              href={isAdmin ? '/admin' : '/pricing'}
              className="mt-2 block w-full text-micro font-medium text-e-0 bg-amber hover:bg-amber/90 rounded-lg py-1.5 transition-colors text-center"
            >
              {isAdmin ? 'Yönetim Paneli' : isFree ? 'Yükselt' : 'Planı Yönet'}
            </Link>
          )}
        </div>
      )}

      {/* Collapse Toggle (desktop only — mobile uses the drawer) */}
      <div className="hidden lg:block px-2 py-2 border-t border-border-subtle">
        <button
          onClick={onToggle}
          className={cn(
            'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-e-2 transition-all duration-[var(--dur-state)]',
            collapsed && 'justify-center'
          )}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span className="text-xs animate-fade-in">Daralt</span>
            </>
          )}
        </button>
      </div>

      {/* User Section */}
      <div className={cn('px-2 py-3 border-t border-border-subtle', collapsed ? 'flex justify-center' : '')}>
        <div className={cn('flex items-center gap-2.5 rounded-xl p-2 hover:bg-e-2 transition-all cursor-pointer', collapsed && 'justify-center')}>
          <div className="relative flex-shrink-0">
            <div className="w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-amber to-accent-primary flex items-center justify-center">
              {effectiveUser?.avatar_url ? (
                <img src={effectiveUser.avatar_url} alt="Avatar" className="w-full h-full object-cover" />
              ) : (
                <span className="text-xs font-display text-white">{displayName[0]?.toUpperCase() ?? 'T'}</span>
              )}
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-bullish border-2 border-bg-secondary" />
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0 animate-fade-in">
              <p className="text-xs font-display text-text-primary truncate">{displayName}</p>
              <p className="text-micro text-text-muted truncate">{effectiveUser?.email ?? ''}</p>
            </div>
          )}
          {!collapsed && (
            <Tooltip content="Çıkış">
              <button
                onClick={(e) => { e.stopPropagation(); doLogout(); }}
                aria-label="Çıkış"
                className="p-1 rounded-lg hover:bg-e-2 text-text-muted hover:text-bearish transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </Tooltip>
          )}
        </div>
      </div>
    </aside>
  );
}
