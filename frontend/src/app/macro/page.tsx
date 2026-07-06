'use client';

import React, { useEffect, useState } from 'react';
import { Globe, DollarSign, TrendingUp, Building2, ExternalLink, AlertCircle, Activity } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import {
  fetchMacroSnapshot, fetchKapDisclosures, fetchBybitFunding,
  type MacroSnapshot, type KapDisclosure,
} from '@/lib/api';
import { formatRelativeTime, formatPercentage, formatNumber } from '@/lib/utils';

const FUNDING_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'] as const;

function MetricCard({
  label, value, sub, accent,
}: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <GlassCard className="text-center py-4">
      <p className="text-[10px] text-text-muted uppercase font-semibold">{label}</p>
      <p className={`text-2xl font-extrabold font-mono mt-1 ${accent ?? 'text-text-primary'}`}>{value}</p>
      {sub && <p className="text-[11px] text-text-secondary mt-1">{sub}</p>}
    </GlassCard>
  );
}

// Tek kaynak: lib/utils formatNumber (tr-TR). Yerel toFixed formatter'ı kaldırıldı.
const num = formatNumber;

export default function MacroPage() {
  const [snap, setSnap]   = useState<MacroSnapshot | null>(null);
  const [kap, setKap]     = useState<KapDisclosure[]>([]);
  const [funding, setFunding] = useState<Record<string, number | null>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchMacroSnapshot().catch(() => null),
      fetchKapDisclosures(15).catch(() => ({ items: [], count: 0 })),
      Promise.all(
        FUNDING_SYMBOLS.map((s) => fetchBybitFunding(s).then((r) => [s, r.funding_rate] as const).catch(() => [s, null] as const))
      ),
    ]).then(([m, k, f]) => {
      setSnap(m);
      setKap(k.items);
      setFunding(Object.fromEntries(f));
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <Globe className="w-6 h-6 text-accent-primary" /> Makro Görünüm
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          TCMB · FED · KAP — Piyasaları etkileyen makroekonomik veriler
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && snap && (
        <>
          {/* Turkey */}
          <div>
            <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-accent-primary" /> Türkiye (TCMB)
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="USD / TRY" value={num(snap.turkey.usd_try, 4)} accent="text-text-primary" />
              <MetricCard label="EUR / TRY" value={num(snap.turkey.eur_try, 4)} accent="text-text-primary" />
            </div>
          </div>

          {/* USA */}
          <div>
            <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-accent-primary" /> ABD Makro (FRED)
            </h2>
            {!snap.united_states.configured && (
              <GlassCard className="flex items-center gap-3 mb-3 bg-amber/5 border-amber/30">
                <AlertCircle className="w-4 h-4 text-amber flex-shrink-0" />
                <p className="text-xs text-tx">
                  ABD makro verileri şu an kullanılamıyor.
                </p>
              </GlassCard>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="FED Faiz" value={`${num(snap.united_states.fed_funds_rate)}%`} />
              <MetricCard label="10Y Tahvil" value={`${num(snap.united_states.ten_year_yield)}%`} />
              <MetricCard label="USD Endeksi" value={num(snap.united_states.usd_broad_index)} />
              <MetricCard label="CPI" value={num(snap.united_states.cpi, 1)} />
            </div>
          </div>
        </>
      )}

      {/* Funding rates */}
      <div>
        <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4 text-accent-primary" /> Vadeli İşlem Funding Oranı (Bybit)
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {FUNDING_SYMBOLS.map((s) => {
            const rate = funding[s];
            const pct = rate == null ? null : rate * 100;
            const accent = pct == null ? 'text-text-primary' : pct > 0 ? 'text-bullish' : pct < 0 ? 'text-bearish' : 'text-text-primary';
            return (
              <MetricCard
                key={s}
                label={s.replace('USDT', ' / USDT')}
                value={pct == null ? '—' : formatPercentage(pct, 4)}
                accent={accent}
              />
            );
          })}
        </div>
      </div>

      {/* KAP disclosures */}
      <div>
        <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-accent-primary" /> KAP Açıklamaları (BIST)
        </h2>
        {kap.length === 0 ? (
          <GlassCard>
            <p className="text-xs text-text-muted text-center py-6">KAP açıklamaları alınamadı.</p>
          </GlassCard>
        ) : (
          <div className="glass-panel border border-border-subtle rounded-2xl divide-y divide-border-subtle overflow-hidden">
            {kap.map((d, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 hover:bg-e-2 transition-colors">
                <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-bg-tertiary border border-border-subtle flex items-center justify-center text-[10px] font-bold font-mono text-accent-primary">
                  {(d.company ?? '?').slice(0, 3)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-text-primary truncate">{d.title}</p>
                  <p className="text-[11px] text-text-muted">
                    {d.company} · {d.category}
                    {d.published && ` · ${formatRelativeTime(d.published)}`}
                  </p>
                </div>
                {d.url && (
                  <a href={d.url} target="_blank" rel="noreferrer" className="flex-shrink-0 text-text-muted hover:text-accent-primary p-1">
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
