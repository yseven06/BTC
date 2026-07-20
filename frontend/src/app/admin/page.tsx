'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Shield, Users, DollarSign, Zap, TrendingUp, Database,
  Search, Crown, Trash2, RefreshCw, Activity, History,
  Plus, Play, AlertTriangle, CheckCircle, XCircle, Ban,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { Tooltip } from '@/components/ui/Tooltip';
import { useToast } from '@/components/ui/Toast';
import { Dropdown } from '@/components/ui/Dropdown';
import { useAuth } from '@/lib/auth-context';
import {
  fetchAdminStats, fetchAdminUsers, updateAdminUser, deleteAdminUser,
  fetchAdminSignals, invalidateAdminSignal, bulkCleanSignals, adminGenerateSignal,
  deleteAdminSignal, bulkDeleteClosedSignals,
  fetchAdminAssets, createAdminAsset, updateAdminAsset, deleteAdminAsset,
  fetchAdminJobStatus, triggerAdminJob,
  fetchAdminAuditLog,
  type AdminStats, type AdminUserRow, type SubscriptionTier, type UserRole,
  type AdminSignalRow, type AdminAssetRow, type AdminJobStatus, type AdminAuditLogRow,
} from '@/lib/api';
import { cn, formatAbsoluteTimeTR, formatPercentage, formatNumber } from '@/lib/utils';

const TIER_COLOR: Record<string, string> = {
  free:    'bg-bg-tertiary text-text-muted',
  pro:     'bg-accent-primary/20 text-accent-primary',
  premium: 'bg-amber/20 text-amber',
};

const ROLE_LABEL: Record<UserRole, string> = { user: 'Üye', admin: 'Admin', super_admin: 'Kurucu' };
const ROLE_COLOR: Record<UserRole, string> = {
  user: 'bg-bg-tertiary text-text-muted',
  admin: 'bg-accent-ui/15 text-accent-ui',
  super_admin: 'bg-amber/20 text-amber',
};

type Tab = 'overview' | 'users' | 'signals' | 'assets' | 'system' | 'audit';

function StatCard({
  label, value, icon: Icon, accent,
}: { label: string; value: string; icon: React.ComponentType<{ className?: string }>; accent: string }) {
  return (
    <GlassCard className="flex items-center gap-4">
      <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center', accent)}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-micro text-text-muted uppercase font-medium">{label}</p>
        <p className="text-h2 font-display font-mono text-text-primary mt-0.5">{value}</p>
      </div>
    </GlassCard>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>('overview');

  useEffect(() => {
    if (!loading && user && !user.is_admin) router.replace('/dashboard');
  }, [user, loading, router]);

  if (loading || !user) {
    return <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>;
  }
  if (!user.is_admin) return null;

  const isSuperAdmin = user.role === 'super_admin';

  const TABS: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'overview', label: 'Genel Bakış', icon: Activity },
    { id: 'users', label: 'Kullanıcılar', icon: Users },
    { id: 'signals', label: 'Sinyal Yönetimi', icon: Zap },
    { id: 'assets', label: 'Varlık Yönetimi', icon: Database },
    { id: 'system', label: 'Sistem & Scheduler', icon: RefreshCw },
    { id: 'audit', label: 'Audit Log', icon: History },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-h2 font-display text-text-primary flex items-center gap-2">
            <Shield className="w-6 h-6 text-accent-ui" /> Yönetim Paneli
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Platform yönetimi · kullanıcılar · sinyaller · sistem sağlığı
          </p>
        </div>
        <span className={cn('px-3 py-1.5 rounded-xl text-xs font-display uppercase', ROLE_COLOR[(user.role ?? 'admin') as UserRole])}>
          {ROLE_LABEL[(user.role ?? 'admin') as UserRole]}
        </span>
      </div>

      {/* Tab nav */}
      <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'flex items-center gap-1.5 px-3.5 py-2 text-xs font-display rounded-lg transition-colors whitespace-nowrap',
              tab === t.id ? 'bg-accent-primary text-white' : 'text-text-muted hover:text-text-primary'
            )}
          >
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'users' && <UsersTab isSuperAdmin={isSuperAdmin} selfId={user.id} />}
      {tab === 'signals' && <SignalsTab isSuperAdmin={isSuperAdmin} />}
      {tab === 'assets' && <AssetsTab isSuperAdmin={isSuperAdmin} />}
      {tab === 'system' && <SystemTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Genel Bakış
// ════════════════════════════════════════════════════════════════════════════

function OverviewTab() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setStats(await fetchAdminStats());
    } catch (e: any) {
      setError(e?.message ?? 'İstatistikler yüklenemedi.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={load} disabled={busy} className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary disabled:opacity-50">
          <RefreshCw className={cn('w-3.5 h-3.5', busy && 'animate-spin')} /> Yenile
        </button>
      </div>
      {busy && !stats && (
        <div role="status" aria-busy="true">
          <span className="sr-only">Yükleniyor</span>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4" aria-hidden="true">
            {Array.from({ length: 8 }).map((_, i) => (
              <GlassCard key={i} className="flex items-center gap-4">
                <Skeleton className="w-10 h-10" />
                <div>
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-8 w-12 mt-0.5" />
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}
      {error && (
        <div className="text-sm text-bearish bg-bearish/10 border border-bearish/20 rounded-xl px-4 py-3">
          {error}
        </div>
      )}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Toplam Kullanıcı" value={stats.total_users.toString()} icon={Users} accent="bg-accent-primary/15 text-accent-primary" />
          <StatCard label="Ödeyen Kullanıcı" value={stats.paying_users.toString()} icon={Crown} accent="bg-amber/15 text-amber" />
          <StatCard label="Toplam Gelir" value={`$${formatNumber(stats.total_revenue_usd, 0)}`} icon={DollarSign} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Aktif Sinyaller" value={stats.active_signals.toString()} icon={Zap} accent="bg-amber/15 text-amber" />
          <StatCard label="Kazanma Oranı" value={formatPercentage(stats.win_rate, 0, false)} icon={TrendingUp} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Toplam Sinyal" value={stats.total_signals.toString()} icon={Database} accent="bg-accent-ui/15 text-accent-ui" />
          <StatCard label="Aktif Kullanıcı" value={stats.active_users.toString()} icon={Users} accent="bg-bullish/15 text-bullish" />
          <StatCard label="Admin Sayısı" value={stats.admin_count.toString()} icon={Shield} accent="bg-bearish/15 text-bearish" />
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Kullanıcılar
// ════════════════════════════════════════════════════════════════════════════

function UsersTab({ isSuperAdmin, selfId }: { isSuperAdmin: boolean; selfId: string }) {
  const toast = useToast();
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  // Onay diyaloğu — native confirm() yerine ui/ConfirmModal (P7-D14). variant taşır
  // (rol değişimi=primary, silme=danger karışık).
  const [confirmState, setConfirmState] = useState<{ message: string; variant: 'danger' | 'primary'; onConfirm: () => void } | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const u = await fetchAdminUsers(1, 50, query || undefined);
      setUsers(u.items); setTotal(u.total);
    } finally { setBusy(false); }
  }, [query]);

  useEffect(() => { load(); }, [load]);

  const setRole = (u: AdminUserRow, role: UserRole) => {
    if (!isSuperAdmin) return;
    setConfirmState({
      message: `${u.email} kullanıcısının rolü "${ROLE_LABEL[role]}" olarak değiştirilecek. Onaylıyor musun?`,
      variant: 'primary',
      onConfirm: async () => {
        try { await updateAdminUser(u.id, { role }); load(); } catch (e: any) { toast.error(e?.message ?? 'İşlem başarısız.'); }
      },
    });
  };
  const toggleActive = async (u: AdminUserRow) => { await updateAdminUser(u.id, { is_active: !u.is_active }); load(); };
  const setTier = async (u: AdminUserRow, tier: SubscriptionTier) => { await updateAdminUser(u.id, { tier }); load(); };
  const removeUser = (u: AdminUserRow) => {
    setConfirmState({
      message: `${u.email} kalıcı olarak silinecek. Emin misin?`,
      variant: 'danger',
      onConfirm: async () => {
        try { await deleteAdminUser(u.id); load(); } catch (e: any) { toast.error(e?.message ?? 'Silinemedi.'); }
      },
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-display text-text-primary flex items-center gap-2">
          <Users className="w-4 h-4 text-accent-primary" /> Kullanıcılar <span className="text-xs text-text-muted font-normal">({total})</span>
        </h2>
        <div className="relative max-w-xs flex-1 ml-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="E-posta veya isim ara..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 transition-colors" />
        </div>
      </div>

      {!isSuperAdmin && (
        <p className="text-xs text-text-muted bg-bg-secondary border border-border-subtle rounded-xl px-4 py-2.5 mb-3">
          Rol değiştirme ve kullanıcı silme yalnızca kurucu hesabına açıktır.
        </p>
      )}

      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['KULLANICI', 'PROVIDER', 'TIER', 'DURUM', 'ROL', 'İŞLEMLER'].map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>
        {busy ? (
          <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : users.length === 0 ? (
          <p className="text-center text-text-muted text-sm py-12">Kullanıcı bulunamadı.</p>
        ) : (
          <div className="divide-y divide-border-subtle">
            {users.map((u) => (
              <div key={u.id} className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 items-center px-5 py-3 hover:bg-e-2 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber to-accent-primary flex items-center justify-center font-display text-xs text-white flex-shrink-0">
                    {(u.full_name ?? u.email)[0]?.toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-display text-text-primary truncate">{u.full_name ?? u.email.split('@')[0]}</p>
                    <p className="text-micro text-text-muted truncate">{u.email}</p>
                  </div>
                </div>
                <span className="text-xs text-text-secondary capitalize">{u.provider}</span>
                <Dropdown
                  value={u.tier}
                  onValueChange={(v) => setTier(u, v as SubscriptionTier)}
                  ariaLabel="Kullanıcı tier"
                  showChevron={false}
                  contentClassName="uppercase"
                  className={cn('text-base h-[31px] rounded! font-medium uppercase px-2 py-1 border-0 cursor-pointer', TIER_COLOR[u.tier] ?? TIER_COLOR.free)}
                  options={[
                    { value: 'free', label: 'Free' },
                    { value: 'pro', label: 'Pro' },
                    { value: 'premium', label: 'Premium' },
                  ]}
                />
                <button onClick={() => toggleActive(u)}
                  className={cn('text-micro font-medium uppercase px-2 py-1 rounded', u.is_active ? 'bg-bullish/15 text-bullish' : 'bg-bearish/15 text-bearish')}>
                  {u.is_active ? 'Aktif' : 'Pasif'}
                </button>
                <span title={u.id === selfId ? 'Kendi rolünü değiştiremezsin' : undefined}>
                  <Dropdown
                    value={u.role}
                    onValueChange={(v) => setRole(u, v as UserRole)}
                    disabled={!isSuperAdmin || u.id === selfId}
                    ariaLabel="Kullanıcı rolü"
                    showChevron={false}
                    contentClassName="uppercase"
                    className={cn('text-base h-[31px] rounded! font-medium uppercase px-2 py-1 border-0 cursor-pointer disabled:opacity-60', ROLE_COLOR[u.role])}
                    options={[
                      { value: 'user', label: 'Üye' },
                      { value: 'admin', label: 'Admin' },
                      { value: 'super_admin', label: 'Kurucu' },
                    ]}
                  />
                </span>
                <button onClick={() => removeUser(u)} disabled={!isSuperAdmin || u.id === selfId}
                  className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  title="Kullanıcıyı sil">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmModal
        open={!!confirmState}
        message={confirmState?.message}
        variant={confirmState?.variant}
        onConfirm={() => {
          confirmState?.onConfirm();
          setConfirmState(null);
        }}
        onCancel={() => setConfirmState(null)}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Sinyal Yönetimi
// ════════════════════════════════════════════════════════════════════════════

function SignalsTab({ isSuperAdmin }: { isSuperAdmin: boolean }) {
  const toast = useToast();
  const [signals, setSignals] = useState<AdminSignalRow[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [onlyActive, setOnlyActive] = useState(true);

  const [cleanThreshold, setCleanThreshold] = useState(40);
  const [cleaning, setCleaning] = useState(false);
  const [cleanMsg, setCleanMsg] = useState<string | null>(null);

  const [genSymbol, setGenSymbol] = useState('');
  const [genTf, setGenTf] = useState('1h');
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState<string | null>(null);

  const [delOutcome, setDelOutcome] = useState('');
  const [delSignalType, setDelSignalType] = useState('hold');
  const [delOlderDays, setDelOlderDays] = useState<string>('');
  const [deletingBulk, setDeletingBulk] = useState(false);
  const [delMsg, setDelMsg] = useState<string | null>(null);

  // Onay diyaloğu — native confirm() yerine ui/ConfirmModal (P7-D14). variant taşır
  // (gizleme=primary, silme=danger karışık).
  const [confirmState, setConfirmState] = useState<{ message: string; variant: 'danger' | 'primary'; onConfirm: () => void } | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetchAdminSignals({ q: q || undefined, only_active: onlyActive, page_size: 100 });
      setSignals(res.items); setTotal(res.total);
    } finally { setBusy(false); }
  }, [q, onlyActive]);

  useEffect(() => { load(); }, [load]);

  const invalidate = (s: AdminSignalRow) => {
    setConfirmState({
      message: `${s.symbol} (${s.timeframe}) sinyali kullanıcılardan gizlenecek. Onaylıyor musun?`,
      variant: 'primary',
      onConfirm: async () => {
        await invalidateAdminSignal(s.id);
        load();
      },
    });
  };

  const deleteOne = (s: AdminSignalRow) => {
    setConfirmState({
      message: `${s.symbol} (${s.timeframe}) sinyali kalıcı olarak silinecek. Bu işlem geri alınamaz. Emin misin?`,
      variant: 'danger',
      onConfirm: async () => {
        try { await deleteAdminSignal(s.id); load(); } catch (e: any) { toast.error(e?.message ?? 'Silinemedi.'); }
      },
    });
  };

  const runBulkDeleteClosed = () => {
    const olderDays = delOlderDays.trim() ? Number(delOlderDays) : undefined;
    const parts = [
      delSignalType && `tip=${delSignalType.toUpperCase()}`,
      delOutcome && `sonuç=${delOutcome}`,
      olderDays && `${olderDays} günden eski`,
    ].filter(Boolean).join(', ');
    setConfirmState({
      message: `Eşleşen TÜM kapanan sinyaller kalıcı olarak silinecek (${parts || 'filtre yok — tüm kapananlar'}). Bu işlem geri alınamaz. Emin misin?`,
      variant: 'danger',
      onConfirm: async () => {
        setDeletingBulk(true); setDelMsg(null);
        try {
          const res = await bulkDeleteClosedSignals({
            outcome: delOutcome || undefined,
            signal_type: delSignalType || undefined,
            older_than_days: olderDays,
          });
          setDelMsg(`${res.deleted_count} sinyal kalıcı olarak silindi.`);
          load();
        } catch (e: any) {
          setDelMsg(e?.message ?? 'Silme başarısız.');
        } finally {
          setDeletingBulk(false);
          setTimeout(() => setDelMsg(null), 6000);
        }
      },
    });
  };

  const runBulkClean = async () => {
    setCleaning(true); setCleanMsg(null);
    try {
      const res = await bulkCleanSignals({ min_confidence: cleanThreshold });
      setCleanMsg(`${res.invalidated_count} düşük kaliteli sinyal kaldırıldı.`);
      load();
    } catch (e: any) {
      setCleanMsg(e?.message ?? 'Temizlik başarısız.');
    } finally {
      setCleaning(false);
      setTimeout(() => setCleanMsg(null), 6000);
    }
  };

  const runGenerate = async () => {
    if (!genSymbol.trim()) return;
    setGenerating(true); setGenMsg(null);
    try {
      await adminGenerateSignal(genSymbol.trim().toUpperCase(), genTf);
      setGenMsg(`${genSymbol.toUpperCase()} (${genTf}) için sinyal üretildi.`);
      load();
    } catch (e: any) {
      setGenMsg(e?.message ?? 'Üretim başarısız.');
    } finally {
      setGenerating(false);
      setTimeout(() => setGenMsg(null), 6000);
    }
  };

  return (
    <div className="space-y-4">
      {/* Tools */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {isSuperAdmin && (
          <GlassCard className="p-4 space-y-2 md:col-span-2 border-bearish/20">
            <h3 className="text-sm font-display text-text-primary flex items-center gap-1.5"><Trash2 className="w-4 h-4 text-bearish" /> Kapanan Sinyalleri Kalıcı Sil</h3>
            <p className="text-micro text-text-muted">
              Geçmişe düşmüş, gereksiz birikmiş sinyalleri (örn. binlerce HOLD kaydı) kalıcı olarak siler. Aktif sinyallere dokunmaz, geri alınamaz.
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              <Dropdown
                value={delSignalType}
                onValueChange={setDelSignalType}
                ariaLabel="Sinyal tipi filtresi"
                className="text-xs px-2 py-1.5"
                options={[
                  { value: '', label: 'Tüm Tipler' },
                  { value: 'hold', label: 'Sadece HOLD' },
                  { value: 'buy', label: 'Sadece BUY' },
                  { value: 'sell', label: 'Sadece SELL' },
                  { value: 'strong_buy', label: 'Sadece STRONG BUY' },
                  { value: 'strong_sell', label: 'Sadece STRONG SELL' },
                ]}
              />
              <Dropdown
                value={delOutcome}
                onValueChange={setDelOutcome}
                ariaLabel="Sonuç filtresi"
                className="text-xs px-2 py-1.5"
                options={[
                  { value: '', label: 'Tüm Sonuçlar' },
                  { value: 'win', label: 'TP — Kazandı' },
                  { value: 'loss', label: 'Stop Oldu' },
                  { value: 'breakeven', label: 'Başabaş' },
                  { value: 'expired', label: 'Süresi Doldu' },
                ]}
              />
              <input value={delOlderDays} onChange={(e) => setDelOlderDays(e.target.value)} placeholder="X günden eski (ops.)" type="number" min={0}
                className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none w-44" />
              <button onClick={runBulkDeleteClosed} disabled={deletingBulk}
                className="text-xs font-display bg-bearish/15 text-bearish px-3 py-1.5 rounded-lg hover:bg-bearish/25 transition-colors disabled:opacity-50 whitespace-nowrap">
                {deletingBulk ? 'Siliniyor...' : 'Kalıcı Sil'}
              </button>
            </div>
            {delMsg && <p className="text-micro text-bullish">{delMsg}</p>}
          </GlassCard>
        )}

        <GlassCard className="p-4 space-y-2">
          <h3 className="text-sm font-display text-text-primary flex items-center gap-1.5"><Ban className="w-4 h-4 text-bearish" /> Toplu Temizlik</h3>
          <p className="text-micro text-text-muted">Belirtilen güven skorunun altındaki aktif sinyalleri kullanıcılardan gizler.</p>
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={100} step={5} value={cleanThreshold} onChange={(e) => setCleanThreshold(Number(e.target.value))} className="flex-1 accent-bearish" />
            <span className="text-xs font-display font-mono w-10 text-center">{formatPercentage(cleanThreshold, 0, false)}</span>
            <button onClick={runBulkClean} disabled={cleaning}
              className="text-xs font-display bg-bearish/15 text-bearish px-3 py-1.5 rounded-lg hover:bg-bearish/25 transition-colors disabled:opacity-50 whitespace-nowrap">
              {cleaning ? 'Temizleniyor...' : 'Temizle'}
            </button>
          </div>
          {cleanMsg && <p className="text-micro text-bullish">{cleanMsg}</p>}
        </GlassCard>

        <GlassCard className="p-4 space-y-2">
          <h3 className="text-sm font-display text-text-primary flex items-center gap-1.5"><Play className="w-4 h-4 text-accent-primary" /> Zorla Sinyal Üret</h3>
          <p className="text-micro text-text-muted">Belirli bir sembol + zaman dilimi için anında sinyal üretimini tetikler.</p>
          <div className="flex items-center gap-2">
            <input value={genSymbol} onChange={(e) => setGenSymbol(e.target.value)} placeholder="BTCUSDT"
              className="flex-1 bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none focus:border-accent-primary/40" />
            <Dropdown
              value={genTf}
              onValueChange={setGenTf}
              ariaLabel="Zaman dilimi"
              className="text-xs px-2 py-1.5"
              options={[
                { value: '15m', label: '15m' },
                { value: '1h', label: '1h' },
                { value: '4h', label: '4h' },
                { value: '1d', label: '1d' },
              ]}
            />
            <button onClick={runGenerate} disabled={generating}
              className="text-xs font-display bg-accent-primary/15 text-accent-primary px-3 py-1.5 rounded-lg hover:bg-accent-primary/25 transition-colors disabled:opacity-50 whitespace-nowrap">
              {generating ? 'Üretiliyor...' : 'Üret'}
            </button>
          </div>
          {genMsg && <p className="text-micro text-bullish">{genMsg}</p>}
        </GlassCard>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sembol ara..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40" />
        </div>
        <button onClick={() => setOnlyActive(!onlyActive)}
          className={cn('px-3 py-2 text-xs font-display rounded-xl border transition-colors',
            onlyActive ? 'bg-bullish/15 text-bullish border-bullish/30' : 'bg-bg-secondary text-text-muted border-border-subtle')}>
          {onlyActive ? '✓ SADECE AKTİF' : 'TÜMÜ'}
        </button>
      </div>

      {/* Table */}
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr_1.3fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL', 'TİP', 'GÜVEN', 'TF', 'DURUM', 'ÜRETİLDİ', 'İŞLEM'].map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>
        {busy ? (
          <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : signals.length === 0 ? (
          <p className="text-center text-text-muted text-sm py-12">Sinyal bulunamadı.</p>
        ) : (
          <div className="divide-y divide-border-subtle max-h-[600px] overflow-y-auto">
            {signals.map((s) => (
              <div key={s.id} className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr_1.3fr_auto] gap-4 items-center px-5 py-2.5 hover:bg-e-2 transition-colors text-xs">
                <span className="font-display text-text-primary">{s.symbol}</span>
                <span className="uppercase text-text-secondary">{s.signal_type.replace('_', ' ')}</span>
                <span className="font-mono text-text-primary">{formatPercentage(s.confidence_score, 0, false)}</span>
                <span className="uppercase text-text-muted">{s.timeframe}</span>
                <span className={cn('font-display uppercase', s.is_active ? 'text-bullish' : s.admin_invalidated ? 'text-bearish' : 'text-text-muted')}>
                  {s.admin_invalidated ? 'Kaldırıldı' : s.is_active ? 'Aktif' : s.outcome}
                </span>
                <span className="font-mono text-text-muted">{formatAbsoluteTimeTR(s.generated_at)}</span>
                {s.is_active ? (
                  <Tooltip content="Geçersiz kıl (kullanıcılardan gizle)">
                    <button onClick={() => invalidate(s)}
                      className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors">
                      <Ban className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                ) : (
                  <button onClick={() => deleteOne(s)} disabled={!isSuperAdmin}
                    className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title={isSuperAdmin ? 'Kalıcı olarak sil' : 'Sadece kurucu silebilir'}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="text-micro text-text-muted">{total} sinyal listeleniyor.</p>

      <ConfirmModal
        open={!!confirmState}
        message={confirmState?.message}
        variant={confirmState?.variant}
        onConfirm={() => {
          confirmState?.onConfirm();
          setConfirmState(null);
        }}
        onCancel={() => setConfirmState(null)}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Varlık Yönetimi
// ════════════════════════════════════════════════════════════════════════════

function AssetsTab({ isSuperAdmin }: { isSuperAdmin: boolean }) {
  const toast = useToast();
  const [assets, setAssets] = useState<AdminAssetRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);

  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('crypto');
  const [newMarket, setNewMarket] = useState('');
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  // Onay diyaloğu — native confirm() yerine ui/ConfirmModal (P7-D14). variant taşır
  // (SignalsTab/UsersTab ile aynı biçim; burada yalnız danger).
  const [confirmState, setConfirmState] = useState<{ message: string; variant: 'danger' | 'primary'; onConfirm: () => void } | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetchAdminAssets({ q: q || undefined, page_size: 200 });
      setAssets(res.items); setTotal(res.total);
    } finally { setBusy(false); }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const toggleActive = async (a: AdminAssetRow) => { await updateAdminAsset(a.id, { is_active: !a.is_active }); load(); };
  const removeAsset = (a: AdminAssetRow) => {
    setConfirmState({
      message: `${a.symbol} ve ona bağlı tüm sinyaller silinecek. Emin misin?`,
      variant: 'danger',
      onConfirm: async () => {
        try { await deleteAdminAsset(a.id); load(); } catch (e: any) { toast.error(e?.message ?? 'Silinemedi.'); }
      },
    });
  };

  const createAsset = async () => {
    if (!newSymbol.trim() || !newName.trim()) return;
    setCreating(true); setCreateMsg(null);
    try {
      await createAdminAsset({ symbol: newSymbol.trim(), name: newName.trim(), asset_type: newType, market: newMarket || undefined });
      setCreateMsg(`${newSymbol.toUpperCase()} eklendi.`);
      setNewSymbol(''); setNewName(''); setNewMarket('');
      load();
    } catch (e: any) {
      setCreateMsg(e?.message ?? 'Eklenemedi.');
    } finally {
      setCreating(false);
      setTimeout(() => setCreateMsg(null), 6000);
    }
  };

  return (
    <div className="space-y-4">
      <GlassCard className="p-4 space-y-2">
        <h3 className="text-sm font-display text-text-primary flex items-center gap-1.5"><Plus className="w-4 h-4 text-accent-primary" /> Yeni Varlık Ekle</h3>
        <div className="flex items-center gap-2 flex-wrap">
          <input value={newSymbol} onChange={(e) => setNewSymbol(e.target.value)} placeholder="Sembol (BTCUSDT)"
            className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none w-36" />
          <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Ad (Bitcoin)"
            className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none w-40" />
          <Dropdown
            value={newType}
            onValueChange={setNewType}
            ariaLabel="Varlık tipi"
            className="text-xs px-2 py-1.5"
            options={[
              { value: 'crypto', label: 'Kripto' },
            ]}
          />
          <input value={newMarket} onChange={(e) => setNewMarket(e.target.value)} placeholder="Market (binance)"
            className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none w-32" />
          <button onClick={createAsset} disabled={creating}
            className="text-xs font-display bg-accent-primary/15 text-accent-primary px-3 py-1.5 rounded-lg hover:bg-accent-primary/25 transition-colors disabled:opacity-50">
            {creating ? 'Ekleniyor...' : 'Ekle'}
          </button>
        </div>
        {createMsg && <p className="text-micro text-bullish">{createMsg}</p>}
      </GlassCard>

      <div className="relative max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sembol ara..."
          className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40" />
      </div>

      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        <div className="grid grid-cols-[1fr_2fr_1fr_1fr_1fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['SEMBOL', 'AD', 'TİP', 'MARKET', 'DURUM', 'İŞLEM'].map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>
        {busy ? (
          <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <div className="divide-y divide-border-subtle max-h-[600px] overflow-y-auto">
            {assets.map((a) => (
              <div key={a.id} className="grid grid-cols-[1fr_2fr_1fr_1fr_1fr_auto] gap-4 items-center px-5 py-2.5 hover:bg-e-2 transition-colors text-xs">
                <span className="font-display text-text-primary">{a.symbol}</span>
                <span className="text-text-secondary truncate">{a.name}</span>
                <span className="uppercase text-text-muted">{a.asset_type}</span>
                <span className="text-text-muted">{a.market ?? '—'}</span>
                <button onClick={() => toggleActive(a)}
                  className={cn('text-micro font-medium uppercase px-2 py-1 rounded w-fit', a.is_active ? 'bg-bullish/15 text-bullish' : 'bg-bearish/15 text-bearish')}>
                  {a.is_active ? 'Aktif' : 'Pasif'}
                </button>
                <button onClick={() => removeAsset(a)} disabled={!isSuperAdmin} aria-label="Varlığı sil"
                  className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="text-micro text-text-muted">{total} varlık listeleniyor.</p>

      <ConfirmModal
        open={!!confirmState}
        message={confirmState?.message}
        variant={confirmState?.variant}
        onConfirm={() => {
          confirmState?.onConfirm();
          setConfirmState(null);
        }}
        onCancel={() => setConfirmState(null)}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Sistem & Scheduler
// ════════════════════════════════════════════════════════════════════════════

function SystemTab() {
  const toast = useToast();
  const [jobs, setJobs] = useState<Record<string, AdminJobStatus>>({});
  const [busy, setBusy] = useState(false);
  const [triggering, setTriggering] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try { setJobs((await fetchAdminJobStatus()).jobs); } finally { setBusy(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  const trigger = async (jobId: string) => {
    setTriggering(jobId);
    try {
      await triggerAdminJob(jobId);
      setTimeout(load, 2000);
    } catch (e: any) {
      toast.error(e?.message ?? 'İş tetiklenemedi.');
    } finally {
      setTimeout(() => setTriggering(null), 2000);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={load} disabled={busy} className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary disabled:opacity-50">
          <RefreshCw className={cn('w-3.5 h-3.5', busy && 'animate-spin')} /> Yenile
        </button>
      </div>
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        <div className="grid grid-cols-[1.5fr_1fr_1.5fr_2fr_auto] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['İŞ', 'DURUM', 'SON ÇALIŞMA', 'HATA', 'İŞLEM'].map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>
        <div className="divide-y divide-border-subtle">
          {Object.entries(jobs).map(([jobId, j]) => (
            <div key={jobId} className="grid grid-cols-[1.5fr_1fr_1.5fr_2fr_auto] gap-4 items-center px-5 py-3 text-xs">
              <span className="font-display text-text-primary">{j.label}</span>
              <span className="flex items-center gap-1.5 font-display uppercase">
                {j.running ? (
                  <><div className="w-3 h-3 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /> Çalışıyor</>
                ) : j.last_status === 'ok' ? (
                  <><CheckCircle className="w-3.5 h-3.5 text-bullish" /> <span className="text-bullish">Başarılı</span></>
                ) : j.last_status === 'error' ? (
                  <><XCircle className="w-3.5 h-3.5 text-bearish" /> <span className="text-bearish">Hata</span></>
                ) : (
                  <span className="text-text-muted">Henüz çalışmadı</span>
                )}
              </span>
              <span className="font-mono text-text-muted">{j.last_run_at ? formatAbsoluteTimeTR(j.last_run_at) : '—'}</span>
              <span className="text-bearish truncate" title={j.last_error ?? ''}>{j.last_error ?? '—'}</span>
              <button onClick={() => trigger(jobId)} disabled={triggering === jobId || j.running}
                className="flex items-center gap-1 text-micro font-medium text-accent-primary hover:text-accent-ui border border-accent-primary/30 hover:border-accent-primary/60 px-2.5 py-1 rounded-lg transition-[color,border-color,opacity] disabled:opacity-50">
                <Play className="w-3 h-3" /> {triggering === jobId ? 'Tetiklendi' : 'Şimdi Çalıştır'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Audit Log
// ════════════════════════════════════════════════════════════════════════════

function AuditTab() {
  const [rows, setRows] = useState<AdminAuditLogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetchAdminAuditLog({ page_size: 100 });
      setRows(res.items); setTotal(res.total);
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-display text-text-primary flex items-center gap-2">
          <History className="w-4 h-4 text-accent-primary" /> Admin İşlem Geçmişi <span className="text-xs text-text-muted font-normal">({total})</span>
        </h2>
        <button onClick={load} disabled={busy} className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary disabled:opacity-50">
          <RefreshCw className={cn('w-3.5 h-3.5', busy && 'animate-spin')} /> Yenile
        </button>
      </div>
      <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
        <div className="grid grid-cols-[1.3fr_1.2fr_1.5fr_1.5fr_2fr] gap-4 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
          {['ZAMAN', 'KİM', 'AKSİYON', 'HEDEF', 'DETAY'].map((h) => (
            <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
          ))}
        </div>
        {busy ? (
          <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : rows.length === 0 ? (
          <p className="text-center text-text-muted text-sm py-12">Henüz kayıt yok.</p>
        ) : (
          <div className="divide-y divide-border-subtle max-h-[600px] overflow-y-auto">
            {rows.map((r) => (
              <div key={r.id} className="grid grid-cols-[1.3fr_1.2fr_1.5fr_1.5fr_2fr] gap-4 items-center px-5 py-2.5 text-xs">
                <span className="font-mono text-text-muted">{formatAbsoluteTimeTR(r.created_at)}</span>
                <span className="text-text-primary truncate">{r.actor_email}</span>
                <span className="font-display text-accent-primary">{r.action}</span>
                <span className="text-text-secondary">{r.target_type ? `${r.target_type}${r.target_id ? ` · ${r.target_id.slice(0, 8)}` : ''}` : '—'}</span>
                <span className="text-text-muted truncate font-mono text-micro">{JSON.stringify(r.detail)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
