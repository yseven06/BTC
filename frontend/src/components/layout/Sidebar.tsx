'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Zap, TrendingUp, Star, PieChart, Bell,
  BarChart3, BarChart2, Settings, ChevronLeft, ChevronRight, Brain,
  LogOut, User, Newspaper, FlaskConical, Crown, Microscope, CreditCard,
  Globe, Shield,
} from 'lucide-react';
import { useLanguage } from '@/lib/language-context';
import { cn } from '@/lib/utils';
import { fetchCurrentUser, fetchMySubscription, type UserProfile, type SubscriptionResponse } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  badge?: number;
}

const navItems: NavItem[] = [
  { id: 'dashboard',   label: 'Gösterge Paneli', icon: LayoutDashboard, href: '/' },
  { id: 'signals',     label: 'Sinyal Merkezi',  icon: Zap,             href: '/signals',     badge: 3 },
  { id: 'markets',     label: 'Piyasalar',       icon: TrendingUp,      href: '/markets' },
  { id: 'portfolio',   label: 'Portföy',         icon: PieChart,        href: '/portfolio' },
  { id: 'backtest',        label: 'Backtest',         icon: FlaskConical,  href: '/backtest' },
  { id: 'performance',    label: 'Performans',       icon: BarChart3,     href: '/performance' },
  { id: 'strategy-lab',   label: 'Strategy Lab',     icon: Microscope,    href: '/strategy-lab' },
  { id: 'symbol-analysis', label: 'Sembol Analizi',  icon: BarChart2,     href: '/symbol-analysis' },
  { id: 'macro',          label: 'Makro Görünüm',     icon: Globe,         href: '/macro' },
  { id: 'alerts',      label: 'Alarmlar',         icon: Bell,            href: '/alerts', badge: 5 },
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
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user: authUser, logout: doLogout } = useAuth();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [sub, setSub] = useState<SubscriptionResponse | null>(null);

  useEffect(() => {
    fetchCurrentUser().then(setUser).catch(() => {});
    fetchMySubscription().then(setSub).catch(() => {});
  }, []);

  // Prefer auth context (has is_admin) but fall back to direct fetch
  const effectiveUser = authUser ?? user;

  const isAdmin = !!effectiveUser?.is_admin;
  const tier    = isAdmin ? 'admin' : (sub?.tier ?? 'free');
  const isFree  = tier === 'free';
  const planName  = isAdmin ? 'Kurucu (Admin)'
                  : tier === 'premium' ? 'Premium'
                  : tier === 'pro' ? 'Pro Plan'
                  : 'Ücretsiz Plan';
  const planColor = isAdmin ? 'text-orange-400'
                  : tier === 'premium' ? 'text-yellow-400'
                  : tier === 'pro' ? 'text-accent-primary'
                  : 'text-text-muted';
  const expiry = sub?.current_period_end
    ? new Date(sub.current_period_end).toLocaleDateString('tr-TR')
    : null;

  const displayName = effectiveUser?.full_name ?? effectiveUser?.email?.split('@')[0] ?? 'Trader';

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen flex flex-col',
        'glass-panel border-r border-border-subtle',
        'transition-all duration-300 ease-in-out',
        collapsed ? 'w-[72px]' : 'w-[220px]'
      )}
    >
      {/* Logo */}
      <div className={cn('flex items-center h-16 px-4 border-b border-border-subtle', collapsed ? 'justify-center' : 'gap-3')}>
        <div className="relative flex items-center justify-center w-9 h-9 rounded-xl gradient-bg-brand shadow-glow-sm flex-shrink-0">
          <Brain className="w-5 h-5 text-white" />
        </div>
        {!collapsed && (
          <div className="animate-fade-in overflow-hidden">
            <h1 className="text-base font-bold gradient-text-brand whitespace-nowrap">TradeMinds</h1>
            <p className="text-[9px] text-text-muted font-medium tracking-wider uppercase">AI Trading</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {[...navItems, ...(effectiveUser?.is_admin ? [adminNavItem] : [])].map((item) => {
          const isActive = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.id}
              href={item.href}
              className={cn(
                'nav-item group relative',
                isActive && 'active',
                collapsed && 'justify-center px-0'
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={cn('w-4 h-4 flex-shrink-0 transition-colors', isActive ? 'text-accent-primary' : 'text-text-muted group-hover:text-text-primary')} />
              {!collapsed && (
                <span className="text-sm animate-fade-in whitespace-nowrap flex-1">{item.label}</span>
              )}
              {!collapsed && item.badge && item.badge > 0 && (
                <span className="flex items-center justify-center min-w-[18px] h-4.5 px-1 text-[10px] font-bold font-mono rounded-full bg-accent-primary/20 text-accent-primary">
                  {item.badge}
                </span>
              )}
              {collapsed && item.badge && item.badge > 0 && (
                <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-accent-primary" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Plan Section */}
      {!collapsed && (
        <div className="mx-2 mb-2 p-3 rounded-xl bg-gradient-to-br from-orange-500/10 to-accent-primary/10 border border-orange-500/20">
          <div className="flex items-center gap-2 mb-2">
            <Crown className={cn('w-4 h-4', tier === 'premium' ? 'text-yellow-400' : 'text-orange-500')} />
            <span className={cn('text-xs font-bold', planColor)}>{planName}</span>
            <span className={cn(
              'ml-auto text-[9px] px-1.5 py-0.5 rounded font-bold',
              isFree ? 'bg-text-muted/30 text-text-muted' : 'bg-orange-500 text-white'
            )}>
              {isFree ? 'Pasif' : 'Aktif'}
            </span>
          </div>
          {isAdmin ? (
            <p className="text-[10px] text-text-muted">Sınırsız erişim · tüm özellikler aktif.</p>
          ) : isFree ? (
            <p className="text-[10px] text-text-muted">Sınırsız sinyal için yükselt.</p>
          ) : expiry ? (
            <p className="text-[10px] text-text-muted">Sona erme: {expiry}</p>
          ) : null}
          <Link
            href={isAdmin ? '/admin' : '/pricing'}
            className="mt-2 block w-full text-[10px] font-bold text-white bg-orange-500 hover:bg-orange-600 rounded-lg py-1.5 transition-colors text-center"
          >
            {isAdmin ? 'Yönetim Paneli' : isFree ? 'Yükselt' : 'Planı Yönet'}
          </Link>
        </div>
      )}

      {/* Collapse Toggle */}
      <div className="px-2 py-2 border-t border-border-subtle">
        <button
          onClick={onToggle}
          className={cn(
            'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.03] transition-all duration-200',
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
        <div className={cn('flex items-center gap-2.5 rounded-xl p-2 hover:bg-white/[0.03] transition-all cursor-pointer', collapsed && 'justify-center')}>
          <div className="relative flex-shrink-0">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-orange-500 to-accent-primary flex items-center justify-center">
              <span className="text-xs font-bold text-white">{displayName[0]?.toUpperCase() ?? 'T'}</span>
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-bullish border-2 border-bg-secondary" />
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0 animate-fade-in">
              <p className="text-xs font-semibold text-text-primary truncate">{displayName}</p>
              <p className="text-[10px] text-text-muted truncate">{user?.email ?? ''}</p>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={(e) => { e.stopPropagation(); doLogout(); }}
              className="p-1 rounded-lg hover:bg-white/[0.06] text-text-muted hover:text-bearish transition-colors"
              title="Çıkış"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
