'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  Search,
  Bell,
  Command,
  ChevronDown,
  User,
  Settings,
  LogOut,
  Moon,
  HelpCircle,
  Menu,
} from 'lucide-react';
import { useLanguage } from '@/lib/language-context';
import { cn } from '@/lib/utils';
import TickerBand from './TickerBand';
import { CoinIcon } from '@/components/ui/CoinIcon';
import { Tooltip } from '@/components/ui/Tooltip';
import { useToast } from '@/components/ui/Toast';
import { searchAssets, type ApiAsset } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { useAlerts } from '@/hooks/useAlerts';
import { formatRelativeTime } from '@/lib/utils';

export default function Header({ onMobileMenu }: { onMobileMenu?: () => void }) {
  const { tr } = useLanguage();
  const toast = useToast();
  // AuthContext is the single source of truth for the user; alerts come from
  // the shared useAlerts hook (fetched once app-wide) — no duplicate requests.
  const { user, logout: doLogout } = useAuth();
  const notifications = useAlerts();
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ApiAsset[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    searchTimer.current = setTimeout(async () => {
      try {
        const res = await searchAssets(searchQuery.trim());
        setSearchResults(res.slice(0, 8));
      } catch {
        setSearchResults([]);
      }
    }, 300);
  }, [searchQuery]);

  // An alert is "unread" if it has not been triggered yet (triggered_at is null)
  const unreadCount = notifications.filter((n) => !n.triggered_at).length;

  const displayName = user?.full_name ?? user?.email?.split('@')[0] ?? 'Trader';
  const displayEmail = user?.email ?? '';

  return (
    <header className="sticky top-0 z-30">
      {/* Ticker Band */}
      <TickerBand />

      {/* Main Header */}
      <div className="h-14 flex items-center justify-between px-4 lg:px-6 glass-panel border-b border-border-subtle">
        {/* Mobile menu (hamburger) — opens the sidebar drawer on < lg */}
        <button
          onClick={onMobileMenu}
          className="lg:hidden p-2 -ml-1 mr-1 rounded-lg text-text-secondary hover:text-text-primary hover:bg-e-2 flex-shrink-0"
          aria-label="Menüyü aç"
        >
          <Menu className="w-5 h-5" />
        </button>
        {/* Search Bar */}
        <div className="flex-1 max-w-xl relative">
          <div
            className={cn(
              'relative flex items-center gap-2 rounded-xl px-4 py-2',
              'bg-bg-primary/60 border transition-all duration-[var(--dur-state)]',
              searchFocused
                ? 'border-accent-primary/40'
                : 'border-border-subtle hover:border-border-medium'
            )}
          >
            <Search className="w-4 h-4 text-text-muted flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={tr('common.search_placeholder')}
              className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none"
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
            />
            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-bg-tertiary/50 border border-border-subtle">
              <Command className="w-3 h-3 text-text-muted" />
              <span className="text-micro font-mono text-text-muted">K</span>
            </div>
          </div>

          {/* Search results dropdown */}
          {searchFocused && searchResults.length > 0 && (
            <div className="absolute top-full mt-1 left-0 right-0 glass-e3-overlay rounded-panel z-dropdown overflow-hidden">
              {searchResults.map((asset) => (
                <div
                  key={asset.id}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-e-2 cursor-pointer border-b border-border-subtle last:border-none"
                >
                  <div className="w-7 h-7 rounded-md bg-bg-tertiary border border-border-subtle flex items-center justify-center text-micro font-medium font-mono text-accent-primary overflow-hidden">
                    <CoinIcon symbol={asset.symbol} assetType={asset.asset_type} />
                  </div>
                  <div>
                    <p className="text-sm font-display text-text-primary">{asset.symbol}</p>
                    <p className="text-xs text-text-muted">{asset.name} · {asset.market}</p>
                  </div>
                  <span className="ml-auto text-micro font-medium text-text-muted bg-bg-tertiary px-2 py-0.5 rounded">
                    {asset.asset_type}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 ml-4">

          {/* Notifications */}
          <div className="relative">
            <Tooltip content={tr('tooltip.notifications')}>
              <button
                onClick={() => {
                  setShowNotifications(!showNotifications);
                  setShowUserMenu(false);
                }}
                className={cn(
                  'relative p-2 rounded-lg',
                  'text-text-secondary hover:text-text-primary',
                  'hover:bg-e-2 transition-all duration-[var(--dur-state)] focus-ring',
                  showNotifications && 'bg-white/[0.04] text-text-primary'
                )}
              >
                <Bell className="w-5 h-5" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center w-4.5 h-4.5 min-w-[18px] text-micro font-medium font-mono text-white bg-bearish rounded-full shadow-lg">
                    {unreadCount}
                  </span>
                )}
              </button>
            </Tooltip>

            {/* Notifications Dropdown */}
            {showNotifications && (
              <div className="absolute right-0 top-full mt-2 w-96 glass-e3-overlay rounded-panel animate-scale-in overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
                  <h3 className="text-sm font-display text-text-primary">
                    {tr('notifications.title')}
                  </h3>
                  <button className="text-xs text-accent-primary hover:text-accent-ui transition-colors">
                    {tr('notifications.mark_all_read')}
                  </button>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {notifications.length === 0 ? (
                    <p className="text-xs text-text-muted text-center py-6">Bildirim yok</p>
                  ) : (
                    notifications.map((notif) => (
                      <div
                        key={notif.id}
                        className={cn(
                          'flex gap-3 px-4 py-3 hover:bg-e-2 transition-colors cursor-pointer border-b border-border-subtle last:border-b-0',
                          !notif.triggered_at && 'bg-accent-primary/[0.03]'
                        )}
                      >
                        <div className="mt-0.5 flex-shrink-0">
                          <div
                            className={cn(
                              'w-2 h-2 rounded-full mt-1.5',
                              !notif.triggered_at ? 'bg-accent-primary' : 'bg-transparent'
                            )}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">
                            {notif.alert_type.toUpperCase()} Alert
                          </p>
                          <p className="text-xs text-text-secondary mt-0.5">
                            {notif.triggered_at ? 'Triggered' : 'Watching'}
                            {' · '}{notif.alert_type}
                          </p>
                          <p className="text-micro text-text-muted mt-1">
                            {formatRelativeTime(notif.created_at)}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
                <div className="px-4 py-2.5 border-t border-border-subtle text-center">
                  <button className="text-xs text-accent-primary hover:text-accent-ui transition-colors font-medium">
                    {tr('common.view_all')}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* User Menu */}
          <div className="relative">
            <button
              onClick={() => {
                setShowUserMenu(!showUserMenu);
                setShowNotifications(false);
              }}
              className={cn(
                'flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-xl',
                'hover:bg-e-2 transition-all duration-[var(--dur-state)] focus-ring',
                showUserMenu && 'bg-white/[0.04]'
              )}
            >
              <div className="w-7 h-7 rounded-full overflow-hidden bg-gradient-to-br from-amber to-accent-primary flex items-center justify-center flex-shrink-0">
                {user?.avatar_url ? (
                  <img src={user.avatar_url} alt="Avatar" className="w-full h-full object-cover" />
                ) : (
                  <User className="w-3.5 h-3.5 text-white" />
                )}
              </div>
              <ChevronDown
                className={cn(
                  'w-3.5 h-3.5 text-text-muted transition-transform duration-[var(--dur-state)]',
                  showUserMenu && 'rotate-180'
                )}
              />
            </button>

            {/* User Dropdown */}
            {showUserMenu && (
              <div className="absolute right-0 top-full mt-2 w-56 glass-e3-overlay rounded-panel animate-scale-in overflow-hidden">
                <div className="px-4 py-3 border-b border-border-subtle">
                  <p className="text-sm font-display text-text-primary">{displayName}</p>
                  {displayEmail && <p className="text-xs text-text-muted">{displayEmail}</p>}
                </div>
                <div className="py-1">
                  <Link
                    href="/profile"
                    onClick={() => setShowUserMenu(false)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-text-primary hover:bg-e-2 transition-colors"
                  >
                    <User className="w-4 h-4" />
                    {tr('auth.profile')}
                  </Link>
                  <Link
                    href="/settings"
                    onClick={() => setShowUserMenu(false)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-text-primary hover:bg-e-2 transition-colors"
                  >
                    <Settings className="w-4 h-4" />
                    {tr('nav.settings')}
                  </Link>
                  <button
                    onClick={() => {
                      // Tema toggle — şu an sadece dark var, light yakında.
                      toast.info('Açık tema yakında. Şu an karanlık tema aktif.');
                      setShowUserMenu(false);
                    }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-text-primary hover:bg-e-2 transition-colors"
                  >
                    <Moon className="w-4 h-4" />
                    {tr('settings.theme')}
                  </button>
                  <Link
                    href="/help"
                    onClick={() => setShowUserMenu(false)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-text-primary hover:bg-e-2 transition-colors"
                  >
                    <HelpCircle className="w-4 h-4" />
                    Yardım
                  </Link>
                </div>
                <div className="py-1 border-t border-border-subtle">
                  <button
                    onClick={doLogout}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-bearish hover:bg-bearish/5 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    {tr('auth.logout')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
