'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Bell, Plus, Trash2, Search, X, Power } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { cn, formatRelativeTime } from '@/lib/utils';
import {
  fetchAlerts, createAlert, updateAlert, deleteAlert, searchAssets, fetchAssets,
  type ApiAlert, type ApiAsset,
} from '@/lib/api';

type AlertType = 'price' | 'signal' | 'custom';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<ApiAlert[]>([]);
  const [assetCache, setAssetCache] = useState<Record<string, ApiAsset>>({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Create-form state
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<ApiAsset[]>([]);
  const [pickedAsset, setPickedAsset] = useState<ApiAsset | null>(null);
  const [alertType, setAlertType] = useState<AlertType>('price');
  const [direction, setDirection] = useState<'above' | 'below'>('above');
  const [targetPrice, setTargetPrice] = useState('');
  const [minConfidence, setMinConfidence] = useState('70');
  const [signalTypes, setSignalTypes] = useState<string[]>(['strong_buy', 'buy']);
  const [indicator, setIndicator] = useState('RSI');
  const [customCondition, setCustomCondition] = useState<'above' | 'below'>('below');
  const [customValue, setCustomValue] = useState('30');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setAlerts(await fetchAlerts());
    } catch { /* keep empty */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetchAssets({ page_size: 200 }).then((r) => {
      const map: Record<string, ApiAsset> = {};
      for (const a of r.items) map[a.id] = a;
      setAssetCache(map);
    }).catch(() => {});
  }, []);

  const runSearch = async (q: string) => {
    setSearch(q);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    try { setSearchResults(await searchAssets(q.trim())); } catch { setSearchResults([]); }
  };

  const resetForm = () => {
    setPickedAsset(null); setSearch(''); setSearchResults([]);
    setAlertType('price'); setDirection('above'); setTargetPrice('');
    setMinConfidence('70'); setSignalTypes(['strong_buy', 'buy']);
    setIndicator('RSI'); setCustomCondition('below'); setCustomValue('30');
  };

  const submitCreate = async () => {
    if (!pickedAsset) return;
    let conditions: Record<string, unknown>;
    if (alertType === 'price') {
      if (!targetPrice) return;
      conditions = { direction, target_price: parseFloat(targetPrice) };
    } else if (alertType === 'signal') {
      if (signalTypes.length === 0) return;
      conditions = { signal_types: signalTypes, min_confidence: parseFloat(minConfidence) || 0 };
    } else {
      if (!customValue) return;
      conditions = { indicator, condition: customCondition, value: parseFloat(customValue) };
    }

    setCreating(true);
    try {
      await createAlert({ asset_id: pickedAsset.id, alert_type: alertType, conditions });
      setAssetCache((prev) => ({ ...prev, [pickedAsset.id]: pickedAsset }));
      resetForm();
      setShowForm(false);
      await load();
    } catch (e: any) {
      alert(e?.message ?? 'Alarm oluşturulamadı.');
    } finally { setCreating(false); }
  };

  const toggleActive = async (a: ApiAlert) => {
    try {
      await updateAlert(a.id, { is_active: !a.is_active });
      await load();
    } catch (e: any) {
      alert(e?.message ?? 'Güncellenemedi.');
    }
  };

  const removeAlert = async (a: ApiAlert) => {
    if (!confirm('Bu alarm silinecek. Emin misin?')) return;
    try {
      await deleteAlert(a.id);
      setAlerts((prev) => prev.filter((x) => x.id !== a.id));
    } catch (e: any) {
      alert(e?.message ?? 'Silinemedi.');
    }
  };

  const describeConditions = (a: ApiAlert): string => {
    const c = a.conditions as any;
    if (a.alert_type === 'price') {
      return `Fiyat ${c.direction === 'above' ? '≥' : '≤'} ${c.target_price}`;
    }
    if (a.alert_type === 'signal') {
      return `Sinyal: ${(c.signal_types ?? []).join(', ').toUpperCase()} · Güven ≥ %${c.min_confidence}`;
    }
    return `${c.indicator} ${c.condition === 'above' ? '≥' : '≤'} ${c.value}`;
  };

  const SIGNAL_TYPE_OPTIONS = ['strong_buy', 'buy', 'sell', 'strong_sell'];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
            <Bell className="w-6 h-6 text-accent-primary" /> Alarmlar
          </h1>
          <p className="text-sm text-text-secondary mt-1">Fiyat, sinyal ve özel koşul alarmları</p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 text-xs font-semibold text-accent-primary hover:text-accent-ui border border-accent-primary/30 hover:border-accent-primary/60 px-3 py-2 rounded-lg transition-all">
          <Plus className="w-3.5 h-3.5" /> Yeni Alarm
        </button>
      </div>

      {showForm && (
        <GlassCard className="p-5 space-y-4">
          {/* Asset picker */}
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
                  <span className="text-sm font-semibold text-text-primary">{a.symbol} <span className="text-text-muted font-normal">· {a.name}</span></span>
                </button>
              ))}
              {searchResults.length === 0 && <p className="text-xs text-text-muted text-center py-2">Sonuç yok.</p>}
            </div>
          )}

          {pickedAsset && (
            <div className="space-y-3 pt-1 border-t border-border-subtle">
              {/* Alert type tabs */}
              <div className="flex items-center gap-1 p-1 bg-bg-secondary border border-border-subtle rounded-xl w-fit">
                {([
                  { id: 'price', label: 'Fiyat' },
                  { id: 'signal', label: 'Sinyal' },
                  { id: 'custom', label: 'Özel (İndikatör)' },
                ] as { id: AlertType; label: string }[]).map((t) => (
                  <button key={t.id} onClick={() => setAlertType(t.id)}
                    className={cn('px-3 py-1.5 text-xs font-bold rounded-lg transition-all',
                      alertType === t.id ? 'bg-accent-primary text-white' : 'text-text-muted hover:text-text-primary')}>
                    {t.label}
                  </button>
                ))}
              </div>

              {alertType === 'price' && (
                <div className="flex items-center gap-2 flex-wrap">
                  <select value={direction} onChange={(e) => setDirection(e.target.value as any)}
                    className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary">
                    <option value="above">Fiyat üzerine çıkarsa</option>
                    <option value="below">Fiyat altına düşerse</option>
                  </select>
                  <input value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} type="number" step="any" placeholder="Hedef Fiyat"
                    className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary outline-none w-36" />
                </div>
              )}

              {alertType === 'signal' && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {SIGNAL_TYPE_OPTIONS.map((st) => (
                      <button key={st}
                        onClick={() => setSignalTypes((prev) => prev.includes(st) ? prev.filter((x) => x !== st) : [...prev, st])}
                        className={cn('px-2.5 py-1.5 text-[11px] font-bold uppercase rounded-lg border transition-all',
                          signalTypes.includes(st) ? 'bg-accent-primary/15 text-accent-primary border-accent-primary/40' : 'bg-bg-secondary text-text-muted border-border-subtle')}>
                        {st.replace('_', ' ')}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-text-muted">Min. Güven %</span>
                    <input value={minConfidence} onChange={(e) => setMinConfidence(e.target.value)} type="number" min={0} max={100}
                      className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary outline-none w-20" />
                  </div>
                </div>
              )}

              {alertType === 'custom' && (
                <div className="flex items-center gap-2 flex-wrap">
                  <select value={indicator} onChange={(e) => setIndicator(e.target.value)}
                    className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary">
                    <option value="RSI">RSI</option>
                    <option value="MACD">MACD</option>
                    <option value="Volume">Hacim</option>
                  </select>
                  <select value={customCondition} onChange={(e) => setCustomCondition(e.target.value as any)}
                    className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary">
                    <option value="above">Üzerine çıkarsa</option>
                    <option value="below">Altına düşerse</option>
                  </select>
                  <input value={customValue} onChange={(e) => setCustomValue(e.target.value)} type="number" step="any" placeholder="Değer"
                    className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary outline-none w-24" />
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <button onClick={submitCreate} disabled={creating}
                  className="text-xs font-semibold bg-accent-primary/15 text-accent-primary px-4 py-2 rounded-lg hover:bg-accent-primary/25 transition-colors disabled:opacity-50">
                  {creating ? 'Oluşturuluyor...' : 'Alarmı Oluştur'}
                </button>
                <button onClick={() => { resetForm(); setShowForm(false); }} className="p-2 text-text-muted hover:text-bearish">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </GlassCard>
      )}

      {loading && <p className="text-text-muted text-sm">Yükleniyor...</p>}

      <div className="space-y-3">
        {alerts.map((alert) => {
          const asset = assetCache[alert.asset_id];
          return (
            <GlassCard key={alert.id} className="flex items-center gap-4">
              <div className={cn('w-2 h-2 rounded-full flex-shrink-0', !alert.is_active ? 'bg-text-muted' : alert.triggered_at ? 'bg-amber' : 'bg-accent-primary animate-pulse')} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-text-primary">
                  {asset?.symbol ?? '—'} <span className="text-text-muted font-normal">· {describeConditions(alert)}</span>
                </p>
                <p className="text-xs text-text-muted">{formatRelativeTime(alert.created_at)}</p>
              </div>
              <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded', alert.triggered_at ? 'bg-amber/10 text-amber' : alert.is_active ? 'bg-accent-primary/10 text-accent-primary' : 'bg-bg-tertiary text-text-muted')}>
                {alert.triggered_at ? 'Tetiklendi' : alert.is_active ? 'Aktif' : 'Pasif'}
              </span>
              <button onClick={() => toggleActive(alert)} title={alert.is_active ? 'Devre dışı bırak' : 'Aktifleştir'}
                className={cn('p-1.5 rounded-lg transition-colors', alert.is_active ? 'text-accent-primary hover:bg-accent-primary/10' : 'text-text-muted hover:bg-bg-tertiary')}>
                <Power className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => removeAlert(alert)} className="p-1.5 rounded-lg text-text-muted hover:text-bearish hover:bg-bearish/10 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </GlassCard>
          );
        })}

        {!loading && alerts.length === 0 && (
          <GlassCard>
            <p className="text-text-muted text-sm text-center py-10">
              Henüz alarm oluşturulmamış. Yukarıdan "Yeni Alarm" ile ilkini oluştur.
            </p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
