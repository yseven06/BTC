'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { TrendingUp, TrendingDown, BarChart3 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { fetchAssets, type ApiAsset } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { cn } from '@/lib/utils';

export default function MarketsPage() {
  const [assets, setAssets] = useState<ApiAsset[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAssets({ page_size: 50 })
      .then((res) => setAssets(res.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const symbols = assets.map((a) => a.symbol);
  const prices = useLivePrices(symbols);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-accent-primary" /> Piyasalar
        </h1>
        <p className="text-sm text-text-secondary mt-1">Takip edilen varlıklar — grafik için tıklayın</p>
      </div>

      {loading && <p className="text-text-muted text-sm">Yükleniyor...</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {assets.map((asset) => {
          const live = prices[asset.symbol];
          const up = (live?.changePct24h ?? 0) >= 0;

          return (
            <Link key={asset.id} href={`/markets/${encodeURIComponent(asset.symbol)}`}>
              <GlassCard className="flex items-center gap-4 cursor-pointer group">
                <div className="w-10 h-10 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center font-bold font-mono text-sm text-accent-primary flex-shrink-0 group-hover:border-accent-primary/40 transition-colors">
                  {asset.symbol.slice(0, 2)}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-text-primary text-sm flex items-center gap-1.5">
                    {asset.symbol}
                    <BarChart3 className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
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
                    <span className="text-[10px] font-medium text-text-muted bg-bg-tertiary px-2 py-0.5 rounded uppercase">
                      {asset.asset_type}
                    </span>
                  )}
                </div>
              </GlassCard>
            </Link>
          );
        })}

        {!loading && assets.length === 0 && (
          <div className="col-span-3 p-10 border border-dashed border-border-medium rounded-xl text-center text-text-muted">
            Varlık bulunamadı.
          </div>
        )}
      </div>
    </div>
  );
}
