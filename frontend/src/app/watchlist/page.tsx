'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Star, Plus, Trash2, Search, X, TrendingUp, TrendingDown } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn, formatPrice } from '@/lib/utils';
import { useLivePrices } from '@/hooks/useLivePrices';
import {
  fetchWatchlists, createWatchlist, updateWatchlist, deleteWatchlist,
  searchAssets, fetchAssets, type ApiWatchlist, type ApiAsset,
} from '@/lib/api';

export default function WatchlistPage() {
  const [lists, setLists] = useState<ApiWatchlist[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [newListName, setNewListName] = useState('');
  const [creating, setCreating] = useState(false);

  // Asset metadata cache (id -> asset) so we can render symbol/name from asset_ids
  const [assetCache, setAssetCache] = useState<Record<string, ApiAsset>>({});
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<ApiAsset[]>([]);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWatchlists();
      setLists(res);
      if (res.length > 0) setActiveId((prev) => prev ?? res[0].id);
    } catch { /* keep empty state */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const active = lists.find((l) => l.id === activeId) ?? null;

  // Resolve asset metadata for everything currently shown
  useEffect(() => {
    const missing = (active?.asset_ids ?? []).filter((id) => !assetCache[id]);
    if (missing.length === 0) return;
    // assets/search endpoint only does text search; fall back to fetching all
    // and filtering client-side since there's no batch-by-id endpoint.
    // page_size is capped at 200 server-side (le=200) — 300 returned 422 and
    // left assetCache empty, so watchlist items never rendered. Total assets
    // (~97) fit well under 200.
    fetchAssets({ page_size: 200 }).then((r) => {
      const map: Record<string, ApiAsset> = {};
      for (const a of r.items) map[a.id] = a;
      setAssetCache((prev) => ({ ...prev, ...map }));
    }).catch(() => {});
  }, [active, assetCache]);

  const symbolsInActive = (active?.asset_ids ?? [])
    .map((id) => assetCache[id]?.symbol)
    .filter((s): s is string => !!s);
  const livePrices = useLivePrices(symbolsInActive);

  const runSearch = async (q: string) => {
    setSearch(q);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    setSearching(true);
    try { setSearchResults(await searchAssets(q.trim())); } finally { setSearching(false); }
  };

  const createList = async () => {
    if (!newListName.trim()) return;
    setCreating(true);
    try {
      const wl = await createWatchlist(newListName.trim());
      setNewListName('');
      setLists((prev) => [wl, ...prev]);
      setActiveId(wl.id);
    } catch (e: any) {
      alert(e?.message ?? 'Liste oluşturulamadı.');
    } finally { setCreating(false); }
  };

  const removeList = async (l: ApiWatchlist) => {
    if (!confirm(`"${l.name}" listesi silinecek. Emin misin?`)) return;
    try {
      await deleteWatchlist(l.id);
      setLists((prev) => prev.filter((x) => x.id !== l.id));
      if (activeId === l.id) setActiveId(null);
    } catch (e: any) {
      alert(e?.message ?? 'Silinemedi.');
    }
  };

  const addAsset = async (asset: ApiAsset) => {
    if (!active) return;
    if (active.asset_ids.includes(asset.id)) return;
    const updatedIds = [...active.asset_ids, asset.id];
    try {
      const updated = await updateWatchlist(active.id, { asset_ids: updatedIds });
      setAssetCache((prev) => ({ ...prev, [asset.id]: asset }));
      setLists((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
      setSearch(''); setSearchResults([]);
    } catch (e: any) {
      alert(e?.message ?? 'Eklenemedi.');
    }
  };

  const removeAsset = async (assetId: string) => {
    if (!active) return;
    const updatedIds = active.asset_ids.filter((id) => id !== assetId);
    try {
      const updated = await updateWatchlist(active.id, { asset_ids: updatedIds });
      setLists((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
    } catch (e: any) {
      alert(e?.message ?? 'Kaldırılamadı.');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <Star className="w-6 h-6 text-accent-primary" /> İzleme Listesi
        </h1>
        <p className="text-sm text-text-secondary mt-1">Kaydettiğin varlıkları tek yerden takip et</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <>
          {/* List selector */}
          <div className="flex items-center gap-2 flex-wrap">
            {lists.map((l) => (
              <button
                key={l.id}
                onClick={() => setActiveId(l.id)}
                className={cn(
                  'flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold transition-all border',
                  activeId === l.id
                    ? 'bg-accent-primary text-white border-accent-primary shadow-glow-sm'
                    : 'bg-bg-secondary text-text-secondary border-border-subtle hover:text-text-primary'
                )}
              >
                {l.name}
                <span className={cn('text-[10px] font-mono px-1.5 py-0.5 rounded', activeId === l.id ? 'bg-white/20' : 'bg-bg-tertiary')}>
                  {l.asset_ids.length}
                </span>
              </button>
            ))}
            <div className="flex items-center gap-1.5">
              <input
                value={newListName}
                onChange={(e) => setNewListName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createList()}
                placeholder="Yeni liste adı..."
                className="px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 w-36"
              />
              <button onClick={createList} disabled={creating || !newListName.trim()}
                className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent-primary/15 text-accent-primary hover:bg-accent-primary/25 transition-colors disabled:opacity-40">
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {lists.length === 0 ? (
            <GlassCard className="flex flex-col items-center justify-center p-16 text-center">
              <Star className="w-12 h-12 text-border-medium mb-3" />
              <h3 className="text-sm font-bold text-text-secondary mb-1">Henüz izleme listen yok</h3>
              <p className="text-xs text-text-muted max-w-sm">Yukarıdan bir isim yazıp "+" ile ilk listeni oluştur, ardından varlık aramasıyla içine sembol ekle.</p>
            </GlassCard>
          ) : active ? (
            <>
              {/* Header row: list name + delete */}
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-text-primary">{active.name}</h2>
                <button onClick={() => removeList(active)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-bearish hover:text-bearish/80 transition-colors">
                  <Trash2 className="w-3.5 h-3.5" /> Listeyi Sil
                </button>
              </div>

              {/* Asset search to add */}
              <GlassCard className="p-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                  <input
                    value={search}
                    onChange={(e) => runSearch(e.target.value)}
                    placeholder="Sembol veya isim ara (örn. BTC, Bitcoin, THYAO)..."
                    className="w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary outline-none focus:border-accent-primary/40"
                  />
                </div>
                {search.trim().length >= 2 && (
                  <div className="mt-2 space-y-1 max-h-56 overflow-y-auto">
                    {searching ? (
                      <p className="text-xs text-text-muted text-center py-3">Aranıyor...</p>
                    ) : searchResults.length === 0 ? (
                      <p className="text-xs text-text-muted text-center py-3">Sonuç bulunamadı.</p>
                    ) : (
                      searchResults.map((a) => (
                        <button
                          key={a.id}
                          onClick={() => addAsset(a)}
                          disabled={active.asset_ids.includes(a.id)}
                          className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-bg-secondary text-left transition-colors disabled:opacity-40"
                        >
                          <span className="text-sm font-semibold text-text-primary">{a.symbol} <span className="text-text-muted font-normal">· {a.name}</span></span>
                          {active.asset_ids.includes(a.id) ? (
                            <span className="text-[10px] text-text-muted">Listede</span>
                          ) : (
                            <Plus className="w-3.5 h-3.5 text-accent-primary" />
                          )}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </GlassCard>

              {/* Asset grid */}
              {active.asset_ids.length === 0 ? (
                <GlassCard>
                  <p className="text-text-muted text-sm text-center py-10">Bu liste boş — yukarıdan varlık ekle.</p>
                </GlassCard>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {active.asset_ids.map((id) => {
                    const asset = assetCache[id];
                    if (!asset) return null;
                    const live = livePrices[asset.symbol];
                    const up = (live?.changePct24h ?? 0) >= 0;
                    return (
                      <GlassCard key={id} className="p-4 flex items-center justify-between gap-3">
                        <Link href={`/markets/${asset.symbol}`} className="flex-1 min-w-0 group">
                          <p className="text-sm font-bold text-text-primary group-hover:text-accent-primary transition-colors truncate">{asset.symbol}</p>
                          <p className="text-[11px] text-text-muted truncate">{asset.name}</p>
                          {live ? (
                            <div className="flex items-center gap-2 mt-1.5">
                              <span className="text-sm font-mono font-bold text-text-primary">
                                {formatPrice(live.price)}
                              </span>
                              <span className={cn('flex items-center gap-0.5 text-[11px] font-mono font-semibold', up ? 'text-bullish' : 'text-bearish')}>
                                {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                {up ? '+' : ''}{live.changePct24h?.toFixed(2)}%
                              </span>
                            </div>
                          ) : (
                            <span className="text-[11px] text-text-muted">—</span>
                          )}
                        </Link>
                        <button onClick={() => removeAsset(id)}
                          className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors flex-shrink-0">
                          <X className="w-4 h-4" />
                        </button>
                      </GlassCard>
                    );
                  })}
                </div>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
