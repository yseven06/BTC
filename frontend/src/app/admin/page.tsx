'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Shield, Users, DollarSign, Zap, TrendingUp, Database,
  Search, Crown, Trash2, RefreshCw,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/lib/auth-context';
import {
  fetchAdminStats, fetchAdminUsers, updateAdminUser, deleteAdminUser,
  type AdminStats, type AdminUserRow, type SubscriptionTier,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const TIER_COLOR: Record<string, string> = {
  free:    'bg-bg-tertiary text-text-muted',
  pro:     'bg-accent-primary/20 text-accent-primary',
  premium: 'bg-yellow-500/20 text-yellow-400',
};

function StatCard({
  label, value, icon: Icon, accent,
}: { label: string; value: string; icon: React.ComponentType<{ className?: string }>; accent: string }) {
  return (
    <GlassCard className="flex items-center gap-4">
      <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center', accent)}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-[10px] text-text-muted uppercase font-semibold tracking-wide">{label}</p>
        <p className="text-2xl font-extrabold font-mono text-text-primary mt-0.5">{value}</p>
      </div>
    </GlassCard>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);

  // Block non-admins
  useEffect(() => {
    if (!loading && user && !user.is_admin) {
      router.replace('/');
    }
  }, [user, loading, router]);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [s, u] = await Promise.all([
        fetchAdminStats(),
        fetchAdminUsers(1, 50, query || undefined),
      ]);
      setStats(s);
      setUsers(u.items);
      setTotal(u.total);
    } finally {
      setBusy(false);
    }
  }, [query]);

  useEffect(() => {
    if (user?.is_admin) load();
  }, [user, load]);

  const toggleAdmin = async (u: AdminUserRow) => {
    if (!confirm(`${u.email} kullanıcısının admin yetkisi ${u.is_admin ? 'kaldırılacak' : 'verilecek'}. Onaylıyor musun?`)) return;
    await updateAdminUser(u.id, { is_admin: !u.is_admin });
    load();
  };

  const toggleActive = async (u: AdminUserRow) => {
    await updateAdminUser(u.id, { is_active: !u.is_active });
    load();
  };

  const setTier = async (u: AdminUserRow, tier: SubscriptionTier) => {
    await updateAdminUser(u.id, { tier });
    load();
  };

  const removeUser = async (u: AdminUserRow) => {
    if (!confirm(`${u.email} kalıcı olarak silinecek. Emin misin?`)) return;
    await deleteAdminUser(u.id);
    load();
  };

  if (loading || !user) {
    return <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>;
  }

  if (!user.is_admin) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
            <Shield className="w-6 h-6 text-orange-400" /> Yönetim Paneli
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Platform yönetimi · kullanıcılar · gelir · sistem istatistikleri
          </p>
        </div>
        <button
          onClick={load}
          disabled={busy}
          className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary disabled:opacity-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', busy && 'animate-spin')} /> Yenile
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Toplam Kullanıcı" value={stats.total_users.toString()}
                    icon={Users} accent="bg-accent-primary/15 text-accent-primary" />
          <StatCard label="Ödeyen Kullanıcı" value={stats.paying_users.toString()}
                    icon={Crown} accent="bg-yellow-500/15 text-yellow-400" />
          <StatCard label="Toplam Gelir" value={`$${stats.total_revenue_usd.toFixed(0)}`}
                    icon={DollarSign} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Aktif Sinyaller" value={stats.active_signals.toString()}
                    icon={Zap} accent="bg-orange-500/15 text-orange-400" />
          <StatCard label="Kazanma Oranı" value={`${stats.win_rate}%`}
                    icon={TrendingUp} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Toplam Sinyal" value={stats.total_signals.toString()}
                    icon={Database} accent="bg-accent-secondary/15 text-accent-secondary" />
          <StatCard label="Aktif Kullanıcı" value={stats.active_users.toString()}
                    icon={Users} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Admin Sayısı" value={stats.admin_count.toString()}
                    icon={Shield} accent="bg-bearish/15 text-bearish" />
        </div>
      )}

      {/* Users table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Users className="w-4 h-4 text-accent-primary" />
            Kullanıcılar <span className="text-xs text-text-muted font-normal">({total})</span>
          </h2>
          <div className="relative max-w-xs flex-1 ml-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="E-posta veya isim ara..."
              className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
            />
          </div>
        </div>

        <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
          {/* Head */}
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
            {['KULLANICI', 'PROVIDER', 'TIER', 'DURUM', 'ROL', 'İŞLEMLER'].map((h) => (
              <span key={h} className="text-[10px] font-bold text-text-muted uppercase tracking-wider">{h}</span>
            ))}
          </div>

          {users.length === 0 ? (
            <p className="text-center text-text-muted text-sm py-12">Kullanıcı bulunamadı.</p>
          ) : (
            <div className="divide-y divide-border-subtle">
              {users.map((u) => (
                <div key={u.id} className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 items-center px-5 py-3 hover:bg-white/[0.02] transition-colors">
                  {/* User */}
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-orange-500 to-accent-primary flex items-center justify-center font-bold text-xs text-white flex-shrink-0">
                      {(u.full_name ?? u.email)[0]?.toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-text-primary truncate">{u.full_name ?? u.email.split('@')[0]}</p>
                      <p className="text-[10px] text-text-muted truncate">{u.email}</p>
                    </div>
                  </div>

                  {/* Provider */}
                  <span className="text-xs text-text-secondary capitalize">{u.provider}</span>

                  {/* Tier (clickable) */}
                  <select
                    value={u.tier}
                    onChange={(e) => setTier(u, e.target.value as SubscriptionTier)}
                    className={cn(
                      'text-[11px] font-bold uppercase px-2 py-1 rounded cursor-pointer border-0 outline-none',
                      TIER_COLOR[u.tier] ?? TIER_COLOR.free
                    )}
                  >
                    <option value="free">Free</option>
                    <option value="pro">Pro</option>
                    <option value="premium">Premium</option>
                  </select>

                  {/* Active toggle */}
                  <button
                    onClick={() => toggleActive(u)}
                    className={cn(
                      'text-[11px] font-bold uppercase px-2 py-1 rounded',
                      u.is_active ? 'bg-bullish/15 text-bullish' : 'bg-bearish/15 text-bearish'
                    )}
                  >
                    {u.is_active ? 'Aktif' : 'Pasif'}
                  </button>

                  {/* Admin toggle */}
                  <button
                    onClick={() => toggleAdmin(u)}
                    className={cn(
                      'flex items-center gap-1 text-[11px] font-bold uppercase px-2 py-1 rounded',
                      u.is_admin ? 'bg-orange-500/15 text-orange-400' : 'bg-bg-tertiary text-text-muted'
                    )}
                  >
                    <Shield className="w-3 h-3" />
                    {u.is_admin ? 'Admin' : 'Üye'}
                  </button>

                  {/* Delete */}
                  <button
                    onClick={() => removeUser(u)}
                    className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors"
                    title="Kullanıcıyı sil"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
