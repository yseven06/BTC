'use client';

import React, { useState, useEffect } from 'react';
import { Newspaper, ExternalLink, RefreshCw, Globe, Flag } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { formatRelativeTime } from '@/lib/utils';

interface NewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  published_at: string;
  summary: string;
}

interface NewsData {
  global: NewsItem[];
  turkish: NewsItem[];
  cached_at: string;
}

type Tab = 'turkish' | 'global';

function NewsList({ items, loading }: { items: NewsItem[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <GlassCard>
        <p className="text-text-muted text-sm text-center py-10">Haber yüklenemedi. Lütfen tekrar deneyin.</p>
      </GlassCard>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {items.map((item) => (
        <GlassCard key={item.id} className="flex flex-col gap-3">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-text-primary leading-snug line-clamp-2">
              {item.title}
            </h3>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 p-1 rounded-lg text-text-muted hover:text-accent-primary transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
          {item.summary && item.summary !== item.title && (
            <p className="text-[11px] text-text-secondary line-clamp-2">{item.summary}</p>
          )}
          <div className="flex items-center gap-2 mt-auto">
            <span className="text-[10px] font-semibold text-accent-primary">{item.source}</span>
            <span className="text-[10px] text-text-muted">·</span>
            <span className="text-[10px] text-text-muted">{formatRelativeTime(item.published_at)}</span>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

export default function NewsPage() {
  const [data, setData] = useState<NewsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('turkish');

  const load = () => {
    setLoading(true);
    // Cache-busting query param forces fresh fetch each time
    fetch(`/api/news?t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  // Auto-refresh every 5 minutes in the background
  useEffect(() => {
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const tabs: { id: Tab; label: string; icon: React.ReactNode; sources: string }[] = [
    {
      id: 'turkish',
      label: 'Türkçe',
      icon: <Flag className="w-3.5 h-3.5" />,
      sources: 'CoinTürk · BitcoinHaber · Coinkolik',
    },
    {
      id: 'global',
      label: 'Global',
      icon: <Globe className="w-3.5 h-3.5" />,
      sources: 'CoinDesk · CoinTelegraph · Decrypt',
    },
  ];

  const activeItems = data ? (tab === 'turkish' ? data.turkish : data.global) : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
            <Newspaper className="w-6 h-6 text-accent-primary" /> Kripto Haberler
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            {tabs.find((t) => t.id === tab)?.sources} — her 5 dakikada bir güncellenir
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Yenile
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-bg-tertiary/50 w-fit border border-border-subtle">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${
              tab === t.id
                ? 'bg-accent-primary text-white'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {data?.cached_at && (
        <p className="text-[10px] text-text-muted -mt-2">
          Son güncelleme: {formatRelativeTime(data.cached_at)}
        </p>
      )}

      <NewsList items={activeItems} loading={loading} />
    </div>
  );
}
