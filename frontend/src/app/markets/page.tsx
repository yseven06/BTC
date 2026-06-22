'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { TrendingUp, TrendingDown, BarChart3, Bitcoin, Building2, Search } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { CoinIcon } from '@/components/ui/CoinIcon';
import { fetchAssets, type ApiAsset } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { cn } from '@/lib/utils';

type CategoryFilter = 'all' | 'crypto' | 'stock';

export default function MarketsPage() {
  const [assets, setAssets] = useState<ApiAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    fetchAssets({ page_size: 200 })
      .then((res) => { setAssets(res.items); setError(null); })
      .catch((e: any) => setError(e?.message ?? 'Varlıklar yüklenemedi.'))
      .finally(() => setLoading(false));
  }, []);

  // Counts per category
  const cryptoCount = assets.filter((a) => a.asset_type === 'crypto').length;
  const stockCount  = assets.filter((a) => a.asset_type === 'stock').length;

  // Apply filters
  const filtered = assets
    .filter((a) => category === 'all' || a.asset_type === category)
    .filter((a) => {
      if (!query.trim()) return true;
      const q = query.toLowerCase();
      // Word-prefix match on the name (not substring) — otherwise "eth"
      // matches "Bitcoin / Tether" because "Tether" contains "eth" midword.
      const nameWords = a.name.toLowerCase().split(/[\s/]+/);
      return a.symbol.toLowerCase().includes(q) || nameWords.some((w) => w.startsWith(q));
    });

  const symbols = filtered.map((a) => a.symbol);
  const prices = useLivePrices(symbols);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-accent-primary" /> Piyasalar
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Takip edilen kripto ve hisse varlıkları — grafik için tıkla
        </p>
      </div>

      {/* Category filter + search */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Category tabs */}
        <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl">
          {([
            { id: 'all',    label: 'TÜMÜ',   icon: BarChart3, count: assets.length },
            { id: 'crypto', label: 'KRİPTO', icon: Bitcoin,   count: cryptoCount },
            { id: 'stock',  label: 'HİSSE',  icon: Building2, count: stockCount },
          ] as const).map((c) => {
            const Icon = c.icon;
            return (
              <button
                key={c.id}
                onClick={() => setCategory(c.id)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                  category === c.id
                    ? 'bg-accent-primary text-white shadow-glow-sm'
                    : 'text-text-muted hover:text-text-primary'
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {c.label}
                <span className={cn(
                  'text-[10px] font-mono px-1.5 py-0.5 rounded',
                  category === c.id ? 'bg-white/20' : 'bg-bg-tertiary/60'
                )}>
                  {c.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Sembol veya isim ara..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary placeholder-text-muted outline-none focus:border-accent-primary/40 transition-colors"
          />
        </div>
      </div>

      {loading && <p className="text-text-muted text-sm">Yükleniyor...</p>}
      {error && (
        <div className="text-sm text-bearish bg-bearish/10 border border-bearish/20 rounded-xl px-4 py-3">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((asset) => {
          const live = prices[asset.symbol];
          const up = (live?.changePct24h ?? 0) >= 0;
          const isStock = asset.asset_type === 'stock';

          return (
            <Link key={asset.id} href={`/markets/${encodeURIComponent(asset.symbol)}`}>
              <GlassCard hoverEffect className="flex items-center gap-4 cursor-pointer group">
                <div className={cn(
                  'w-10 h-10 rounded-lg border flex items-center justify-center font-bold font-mono text-sm flex-shrink-0 overflow-hidden group-hover:border-accent-primary/40 transition-colors',
                  isStock
                    ? 'bg-purple-500/10 border-purple-500/30 text-purple-400'
                    : 'bg-bg-tertiary border-border-subtle text-accent-primary'
                )}>
                  <CoinIcon symbol={asset.symbol} assetType={asset.asset_type} />
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-text-primary text-sm flex items-center gap-1.5">
                    {asset.symbol}
                    <span className={cn(
                      'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded',
                      isStock
                        ? 'bg-purple-500/15 text-purple-400'
                        : 'bg-accent-primary/15 text-accent-primary'
                    )}>
                      {isStock ? 'BIST' : 'CRYPTO'}
                    </span>
                  </h4>
                  <p className="text-xs text-text-secondary truncate">{asset.name}</p>
                </div>
                <div className="text-right">
                  {live ? (
                    <>
                      <p className="text-sm font-bold font-mono text-text-primary">
                        {live.price.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}
                      </p>
                      <p className={cn('text-[11px] font-mono font-semibold flex items-center justify-end gap-0.5', up ? 'text-bullish' : 'text-bearish')}>
                        {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {up ? '+' : ''}{live.changePct24h?.toFixed(2)}%
                      </p>
                    </>
                  ) : (
                    <span className="text-[10px] text-text-muted animate-pulse">—</span>
                  )}
                </div>
              </GlassCard>
            </Link>
          );
        })}

        {!loading && filtered.length === 0 && (
          <div className="col-span-3 p-10 border border-dashed border-border-medium rounded-xl text-center text-text-muted">
            {query ? 'Eşleşen varlık yok.' : 'Bu kategoride varlık yok.'}
          </div>
        )}
      </div>
    </div>
  );
}
