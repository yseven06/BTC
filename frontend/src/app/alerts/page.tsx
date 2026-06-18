'use client';

import React, { useState, useEffect } from 'react';
import { Bell } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { fetchAlerts, type ApiAlert } from '@/lib/api';
import { formatRelativeTime } from '@/lib/utils';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<ApiAlert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAlerts()
      .then(setAlerts)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <Bell className="w-6 h-6 text-accent-primary" /> Alarmlar
        </h1>
        <p className="text-sm text-text-secondary mt-1">Fiyat ve sinyal alarmları</p>
      </div>

      {loading && <p className="text-text-muted text-sm">Yükleniyor...</p>}

      <div className="space-y-3">
        {alerts.map((alert) => (
          <GlassCard key={alert.id} className="flex items-center gap-4">
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${alert.triggered_at ? 'bg-text-muted' : 'bg-accent-primary animate-pulse'}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-text-primary">{alert.alert_type.toUpperCase()} Alarmı</p>
              <p className="text-xs text-text-muted">{formatRelativeTime(alert.created_at)}</p>
            </div>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${alert.triggered_at ? 'bg-bg-tertiary text-text-muted' : 'bg-accent-primary/10 text-accent-primary'}`}>
              {alert.triggered_at ? 'Tetiklendi' : 'Aktif'}
            </span>
          </GlassCard>
        ))}

        {!loading && alerts.length === 0 && (
          <GlassCard>
            <p className="text-text-muted text-sm text-center py-10">
              Henüz alarm oluşturulmamış.
            </p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
