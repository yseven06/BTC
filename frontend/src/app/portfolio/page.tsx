'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  PieChart, Plus, Trash2, Search, X, TrendingUp, TrendingDown, Wallet, Share2, LogOut,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { ShareCardModal, type ShareCardData } from '@/components/ui/ShareCardModal';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { cn, formatPrice, formatUsd, formatPercentage } from '@/lib/utils';
import { useLivePrices } from '@/hooks/useLivePrices';
import {
  fetchPortfolios, fetchPortfolio, createPortfolio, deletePortfolio,
  addHolding, deleteHolding, closeHolding, searchAssets, fetchAssets,
  type ApiPortfolioListItem, type ApiPortfolio, type ApiAsset, type ApiHolding,
} from '@/lib/api';

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<ApiPortfolioListItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<ApiPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingActive, setLoadingActive] = useState(false);

  const [newName, setNewName] = useState('');
  const [newCapital, setNewCapital] = useState('10000');
  const [creating, setCreating] = useState(false);

  const [assetCache, setAssetCache] = useState<Record<string, ApiAsset>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<ApiAsset[]>([]);
  const [pickedAsset, setPickedAsset] = useState<ApiAsset | null>(null);
  const [qty, setQty] = useState('');
  const [entryPrice, setEntryPrice] = useState('');
  const [adding, setAdding] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [shareData, setShareData] = useState<ShareCardData | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchPortfolios();
      setPortfolios(res);
      if (res.length > 0) setActiveId((prev) => prev ?? res[0].id);
    } catch { /* keep empty */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const loadActive = useCallback(async (id: string) => {
    setLoadingActive(true);
    try { setActive(await fetchPortfolio(id)); } catch { setActive(null); } finally { setLoadingActive(false); }
  }, []);

  useEffect(() => { if (activeId) loadActive(activeId); }, [activeId, loadActive]);

  useEffect(() => {
    if (Object.keys(assetCache).length > 0) return;
    fetchAssets({ page_size: 200 }).then((r) => {
      const map: Record<string, ApiAsset> = {};
      for (const a of r.items) map[a.id] = a;
      setAssetCache(map);
    }).catch(() => {});
  }, [assetCache]);

  const symbols = (active?.holdings ?? [])
    .map((h) => (h.asset_id ? assetCache[h.asset_id]?.symbol : null))
    .filter((s): s is string => !!s);
  const livePrices = useLivePrices(symbols);

  const createNewPortfolio = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const pf = await createPortfolio({ name: newName.trim(), initial_capital: parseFloat(newCapital) || 0 });
      setNewName(''); setNewCapital('10000');
      await loadList();
      setActiveId(pf.id);
    } catch (e: any) {
      alert(e?.message ?? 'Portföy oluşturulamadı.');
    } finally { setCreating(false); }
  };

  // Onay diyaloğu durumu — native confirm() yerine ui/ConfirmModal (P7-D14).
  const [confirmState, setConfirmState] = useState<{ message: string; onConfirm: () => void } | null>(null);

  const removePortfolio = (id: string, name: string) => {
    setConfirmState({
      message: `"${name}" portföyü silinecek. Emin misin?`,
      onConfirm: async () => {
        try {
          await deletePortfolio(id);
          setPortfolios((prev) => prev.filter((p) => p.id !== id));
          if (activeId === id) { setActiveId(null); setActive(null); }
        } catch (e: any) {
          alert(e?.message ?? 'Silinemedi.');
        }
      },
    });
  };

  const runSearch = async (q: string) => {
    setSearch(q);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    try { setSearchResults(await searchAssets(q.trim())); } catch { setSearchResults([]); }
  };

  const submitHolding = async () => {
    if (!active || !pickedAsset || !qty || !entryPrice) return;
    setAdding(true);
    try {
      await addHolding(active.id, {
        asset_id: pickedAsset.id,
        quantity: parseFloat(qty),
        average_entry_price: parseFloat(entryPrice),
      });
      setAssetCache((prev) => ({ ...prev, [pickedAsset.id]: pickedAsset }));
      setShowAddForm(false); setPickedAsset(null); setQty(''); setEntryPrice(''); setSearch(''); setSearchResults([]);
      await loadActive(active.id);
    } catch (e: any) {
      alert(e?.message ?? 'Eklenemedi.');
    } finally { setAdding(false); }
  };

  const removeHolding = (holdingId: string) => {
    if (!active) return;
    const pf = active;
    setConfirmState({
      message: 'Bu pozisyon kaldırılacak. Emin misin?',
      onConfirm: async () => {
        try {
          await deleteHolding(pf.id, holdingId);
          await loadActive(pf.id);
        } catch (e: any) {
          alert(e?.message ?? 'Kaldırılamadı.');
        }
      },
    });
  };

  const closePosition = async (h: ApiHolding, suggestedExit: number) => {
    if (!active) return;
    const input = prompt('Çıkış fiyatını gir:', suggestedExit ? String(suggestedExit) : '');
    if (input === null) return;
    const exitPrice = parseFloat(input);
    if (!exitPrice || exitPrice <= 0) { alert('Geçerli bir fiyat gir.'); return; }
    setClosingId(h.id);
    try {
      await closeHolding(active.id, h.id, exitPrice);
      await loadActive(active.id);
    } catch (e: any) {
      alert(e?.message ?? 'Pozisyon kapatılamadı.');
    } finally {
      setClosingId(null);
    }
  };

  const openShareCard = (h: ApiHolding, refPrice: number, pnlPct: number, pnlAmount: number) => {
    const asset = h.asset_id ? assetCache[h.asset_id] : undefined;
    setShareData({
      symbol: asset?.symbol ?? '—',
      assetName: asset?.name ?? '',
      isClosed: h.is_closed,
      entryPrice: h.average_entry_price,
      refPrice,
      quantity: h.quantity,
      pnlPct,
      pnlAmount,
      closedAt: h.closed_at,
    });
  };

  const openHoldings = active?.holdings.filter((h) => !h.is_closed) ?? [];
  const closedHoldings = active?.holdings.filter((h) => h.is_closed) ?? [];

  // Compute live totals for currently open positions only
  const totals = (() => {
    let cost = 0, value = 0;
    for (const h of openHoldings) {
      const sym = h.asset_id ? assetCache[h.asset_id]?.symbol : undefined;
      const live = sym ? livePrices[sym]?.price : undefined;
      const c = h.quantity * h.average_entry_price;
      const v = h.quantity * (live ?? h.current_price ?? h.average_entry_price);
      cost += c; value += v;
    }
    const pnl = value - cost;
    return { cost, value, pnl, pnlPct: cost > 0 ? (pnl / cost) * 100 : 0 };
  })();

  // Realized total from closed positions
  const realizedTotal = closedHoldings.reduce((sum, h) => sum + (h.realized_pnl ?? 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h2 font-display text-text-primary flex items-center gap-2">
          <PieChart className="w-6 h-6 text-accent-primary" /> Portföy
        </h1>
        <p className="text-sm text-text-secondary mt-1">Pozisyonlarını takip et, anlık kâr/zararını gör</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <>
          {/* Portfolio selector */}
          <div className="flex items-center gap-2 flex-wrap">
            {portfolios.map((p) => (
              <button
                key={p.id}
                onClick={() => setActiveId(p.id)}
                className={cn(
                  'px-3.5 py-2 rounded-xl text-sm font-display transition-all border',
                  activeId === p.id
                    ? 'bg-accent-primary text-white border-accent-primary'
                    : 'bg-bg-secondary text-text-secondary border-border-subtle hover:text-text-primary'
                )}
              >
                {p.name}
              </button>
            ))}
            <div className="flex items-center gap-1.5">
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Portföy adı..."
                className="px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 w-32" />
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted pointer-events-none">$</span>
                <input value={newCapital} onChange={(e) => setNewCapital(e.target.value)} type="number" placeholder="Başlangıç bakiye"
                  className="pl-7 pr-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 w-36" />
              </div>
              <button onClick={createNewPortfolio} disabled={creating || !newName.trim()}
                className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent-primary/15 text-accent-primary hover:bg-accent-primary/25 transition-colors disabled:opacity-40">
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {portfolios.length === 0 ? (
            <GlassCard className="flex flex-col items-center justify-center p-16 text-center">
              <Wallet className="w-12 h-12 text-border-medium mb-3" />
              <h3 className="text-sm font-display text-text-secondary mb-1">Henüz portföyün yok</h3>
              <p className="text-xs text-text-muted max-w-sm">Yukarıdan bir isim ve başlangıç bakiyesi gir, ardından pozisyon ekle.</p>
            </GlassCard>
          ) : loadingActive || !active ? (
            <div className="flex justify-center py-16"><div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>
          ) : (
            <>
              {/* Summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <GlassCard className="p-4">
                  <span className="text-micro font-medium text-text-muted uppercase">Toplam Maliyet</span>
                  <div className="text-xl font-display font-mono mt-1 text-text-primary">{formatUsd(totals.cost)}</div>
                </GlassCard>
                <GlassCard className="p-4">
                  <span className="text-micro font-medium text-text-muted uppercase">Anlık Değer</span>
                  <div className="text-xl font-display font-mono mt-1 text-text-primary">{formatUsd(totals.value)}</div>
                </GlassCard>
                <GlassCard className="p-4">
                  <span className="text-micro font-medium text-text-muted uppercase">Kâr / Zarar</span>
                  <div className={cn('text-xl font-display font-mono mt-1', totals.pnl >= 0 ? 'text-bullish' : 'text-bearish')}>
                    {totals.pnl >= 0 ? '+' : ''}{formatUsd(totals.pnl)}
                  </div>
                </GlassCard>
                <GlassCard className="p-4">
                  <span className="text-micro font-medium text-text-muted uppercase">Getiri %</span>
                  <div className={cn('text-xl font-display font-mono mt-1', totals.pnlPct >= 0 ? 'text-bullish' : 'text-bearish')}>
                    {formatPercentage(totals.pnlPct)}
                  </div>
                </GlassCard>
              </div>

              <div className="flex items-center justify-between">
                <h2 className="text-base font-display text-text-primary">Açık Pozisyonlar</h2>
                <div className="flex items-center gap-3">
                  <button onClick={() => setShowAddForm(!showAddForm)}
                    className="flex items-center gap-1.5 text-xs font-display text-accent-primary hover:text-accent-ui border border-accent-primary/30 hover:border-accent-primary/60 px-3 py-1.5 rounded-lg transition-all">
                    <Plus className="w-3.5 h-3.5" /> Pozisyon Ekle
                  </button>
                  <button onClick={() => removePortfolio(active.id, active.name)}
                    className="flex items-center gap-1.5 text-xs font-display text-bearish hover:text-bearish/80 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" /> Portföyü Sil
                  </button>
                </div>
              </div>

              {showAddForm && (
                <GlassCard className="p-4 space-y-3">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <input
                      value={search}
                      onChange={(e) => { runSearch(e.target.value); setPickedAsset(null); }}
                      placeholder="Varlık ara (BTC, Bitcoin, THYAO...)..."
                      className="w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary outline-none focus:border-accent-primary/40"
                    />
                  </div>
                  {search.trim().length >= 2 && !pickedAsset && (
                    <div className="space-y-1 max-h-44 overflow-y-auto">
                      {searchResults.map((a) => (
                        <button key={a.id} onClick={() => { setPickedAsset(a); setSearch(`${a.symbol} · ${a.name}`); setSearchResults([]); }}
                          className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-bg-secondary text-left transition-colors">
                          <span className="text-sm font-display text-text-primary">{a.symbol} <span className="text-text-muted font-normal">· {a.name}</span></span>
                        </button>
                      ))}
                      {searchResults.length === 0 && <p className="text-xs text-text-muted text-center py-2">Sonuç yok.</p>}
                    </div>
                  )}
                  {pickedAsset && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <input value={qty} onChange={(e) => setQty(e.target.value)} type="number" step="any" placeholder="Miktar"
                        className="px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none w-28" />
                      <input value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} type="number" step="any" placeholder="Ortalama Giriş Fiyatı"
                        className="px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none w-44" />
                      <button onClick={submitHolding} disabled={adding || !qty || !entryPrice}
                        className="text-xs font-display bg-accent-primary/15 text-accent-primary px-3 py-2 rounded-lg hover:bg-accent-primary/25 transition-colors disabled:opacity-50">
                        {adding ? 'Ekleniyor...' : 'Pozisyonu Ekle'}
                      </button>
                      <button onClick={() => { setPickedAsset(null); setSearch(''); }} className="p-2 text-text-muted hover:text-bearish">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </GlassCard>
              )}

              {/* Open positions */}
              {openHoldings.length === 0 ? (
                <GlassCard>
                  <p className="text-text-muted text-sm text-center py-10">Henüz açık pozisyon yok.</p>
                </GlassCard>
              ) : (
                <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
                  <div className="grid grid-cols-[1.2fr_0.9fr_1fr_1fr_1fr_1fr_auto] gap-3 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
                    {['VARLIK', 'MİKTAR', 'GİRİŞ FİYATI', 'ANLIK FİYAT', 'DEĞER', 'K/Z %', ''].map((h) => (
                      <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
                    ))}
                  </div>
                  <div className="divide-y divide-border-subtle">
                    {openHoldings.map((h) => {
                      const asset = h.asset_id ? assetCache[h.asset_id] : undefined;
                      const live = asset ? livePrices[asset.symbol]?.price : undefined;
                      const currentPrice = live ?? h.current_price ?? h.average_entry_price;
                      const value = h.quantity * currentPrice;
                      const cost = h.quantity * h.average_entry_price;
                      const pnlPct = cost > 0 ? ((value - cost) / cost) * 100 : 0;
                      const pnlAmount = value - cost;
                      return (
                        <div key={h.id} className="grid grid-cols-[1.2fr_0.9fr_1fr_1fr_1fr_1fr_auto] gap-3 items-center px-5 py-3 text-xs hover:bg-e-2">
                          <span className="font-display text-text-primary">{asset?.symbol ?? '—'}</span>
                          <span className="font-mono text-text-secondary">{h.quantity}</span>
                          <span className="font-mono text-text-secondary">${formatPrice(h.average_entry_price)}</span>
                          <span className="font-mono text-text-primary">${formatPrice(currentPrice)}</span>
                          <span className="font-mono text-text-primary">{formatUsd(value)}</span>
                          <span className={cn('flex items-center gap-1 font-display font-mono', pnlPct >= 0 ? 'text-bullish' : 'text-bearish')}>
                            {pnlPct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                            {formatPercentage(pnlPct)}
                          </span>
                          <div className="flex items-center gap-1">
                            <button onClick={() => openShareCard(h, currentPrice, pnlPct, pnlAmount)} title="Paylaş"
                              className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-primary/10 transition-colors">
                              <Share2 className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => closePosition(h, currentPrice)} disabled={closingId === h.id} title="Pozisyonu Kapat"
                              className="p-1.5 rounded-lg text-text-muted hover:text-amber hover:bg-amber/10 transition-colors disabled:opacity-40">
                              <LogOut className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => removeHolding(h.id)} title="Sil"
                              className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Closed positions */}
              {closedHoldings.length > 0 && (
                <>
                  <div className="flex items-center justify-between pt-2">
                    <h2 className="text-base font-display text-text-primary">Kapanan Pozisyonlar</h2>
                    <span className={cn('text-sm font-display font-mono', realizedTotal >= 0 ? 'text-bullish' : 'text-bearish')}>
                      Gerçekleşen K/Z: {realizedTotal >= 0 ? '+' : ''}{formatUsd(realizedTotal)}
                    </span>
                  </div>
                  <div className="glass-panel border border-border-subtle rounded-2xl overflow-hidden">
                    <div className="grid grid-cols-[1.2fr_0.9fr_1fr_1fr_1fr_1fr_auto] gap-3 px-5 py-3 border-b border-border-subtle bg-bg-secondary/30">
                      {['VARLIK', 'MİKTAR', 'GİRİŞ', 'ÇIKIŞ', 'GERÇEKLEŞEN K/Z', 'K/Z %', ''].map((h) => (
                        <span key={h} className="text-micro font-medium text-text-muted uppercase">{h}</span>
                      ))}
                    </div>
                    <div className="divide-y divide-border-subtle">
                      {closedHoldings.map((h) => {
                        const asset = h.asset_id ? assetCache[h.asset_id] : undefined;
                        const pnlPct = h.realized_pnl_pct ?? 0;
                        return (
                          <div key={h.id} className="grid grid-cols-[1.2fr_0.9fr_1fr_1fr_1fr_1fr_auto] gap-3 items-center px-5 py-3 text-xs hover:bg-e-2 opacity-90">
                            <span className="font-display text-text-primary">{asset?.symbol ?? '—'}</span>
                            <span className="font-mono text-text-secondary">{h.quantity}</span>
                            <span className="font-mono text-text-secondary">${formatPrice(h.average_entry_price)}</span>
                            <span className="font-mono text-text-secondary">${formatPrice(h.exit_price ?? 0)}</span>
                            <span className={cn('font-mono font-display', (h.realized_pnl ?? 0) >= 0 ? 'text-bullish' : 'text-bearish')}>
                              {(h.realized_pnl ?? 0) >= 0 ? '+' : ''}{formatUsd(h.realized_pnl ?? 0)}
                            </span>
                            <span className={cn('flex items-center gap-1 font-display font-mono', pnlPct >= 0 ? 'text-bullish' : 'text-bearish')}>
                              {pnlPct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                              {formatPercentage(pnlPct)}
                            </span>
                            <div className="flex items-center gap-1">
                              <button onClick={() => openShareCard(h, h.exit_price ?? 0, pnlPct, h.realized_pnl ?? 0)} title="Paylaş"
                                className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-primary/10 transition-colors">
                                <Share2 className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => removeHolding(h.id)} title="Sil"
                                className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}

      {shareData && <ShareCardModal data={shareData} onClose={() => setShareData(null)} />}

      <ConfirmModal
        open={!!confirmState}
        message={confirmState?.message}
        variant="danger"
        onConfirm={() => {
          confirmState?.onConfirm();
          setConfirmState(null);
        }}
        onCancel={() => setConfirmState(null)}
      />
    </div>
  );
}
