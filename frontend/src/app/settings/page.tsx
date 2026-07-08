'use client';

import React, { useState, useEffect } from 'react';
import { Settings, Send, Check, X, HelpCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { LockedOverlay } from '@/components/ui/LockedOverlay';
import { useTierLimits } from '@/hooks/useTierLimits';
import {
  fetchNotificationSettings, updateNotificationSettings, sendTelegramTest,
  type NotificationSettings,
} from '@/lib/api';
import { cn, formatPercentage } from '@/lib/utils';

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={cn(
        'relative w-11 h-6 rounded-full transition-colors disabled:opacity-50',
        checked ? 'bg-accent-primary' : 'bg-bg-tertiary'
      )}
    >
      <span className={cn(
        'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform',
        checked && 'translate-x-5'
      )} />
    </button>
  );
}

export default function SettingsPage() {
  const limits = useTierLimits();
  const telegramLocked = !limits.loading && !limits.can_use_telegram;

  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [minConf, setMinConf] = useState(70);
  const [notifyHold, setNotifyHold] = useState(false);
  const [notifyLifecycle, setNotifyLifecycle] = useState(false);
  const [enabled, setEnabled] = useState(false);

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    fetchNotificationSettings()
      .then((s) => {
        setSettings(s);
        setEnabled(s.telegram_enabled);
        setChatId(s.telegram_chat_id ?? '');
        setMinConf(s.min_confidence);
        setNotifyHold(s.notify_hold);
        setNotifyLifecycle(s.notify_lifecycle);
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    setSavedMsg(false);
    try {
      const updated = await updateNotificationSettings({
        telegram_enabled: enabled,
        telegram_chat_id: chatId,
        min_confidence: minConf,
        notify_hold: notifyHold,
        notify_lifecycle: notifyLifecycle,
        // Only send token if user typed a new one
        ...(botToken ? { telegram_bot_token: botToken } : {}),
      });
      setSettings(updated);
      setBotToken(''); // clear input after save (token stored server-side)
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 3000);
    } catch {
      //
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await sendTelegramTest();
      setTestResult(r);
    } catch {
      setTestResult({ ok: false, error: 'İstek başarısız' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h2 font-display text-text-primary flex items-center gap-2">
          <Settings className="w-6 h-6 text-accent-primary" /> Ayarlar
        </h1>
        <p className="text-sm text-text-secondary mt-1">Uygulama tercihleri ve bildirimler</p>
      </div>

      {/* Telegram Notifications */}
      <GlassCard className="relative">
        {telegramLocked && (
          <LockedOverlay
            title="Telegram Bildirimleri — Pro Özellik"
            description="Yeni sinyal geldiğinde anında Telegram bildirimi almak için Pro plana yükselt."
          />
        )}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-display text-text-primary flex items-center gap-2">
            <Send className="w-4 h-4 text-accent-primary" /> Telegram Bildirimleri
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">{enabled ? 'Açık' : 'Kapalı'}</span>
            <Toggle checked={enabled} onChange={setEnabled} />
          </div>
        </div>

        {/* Setup help */}
        <div className="bg-bg-secondary/50 border border-border-subtle rounded-xl p-3 mb-4 text-xs text-text-secondary space-y-1">
          <p className="flex items-center gap-1.5 font-display text-text-primary">
            <HelpCircle className="w-3.5 h-3.5 text-accent-primary" /> Nasıl kurulur?
          </p>
          <p>1. Telegram'da <code className="text-accent-primary">@BotFather</code>'a yazıp <code className="text-accent-primary">/newbot</code> ile bot oluştur, <b>token</b>'ı al.</p>
          <p>2. <code className="text-accent-primary">@userinfobot</code>'a yazıp <b>chat ID</b>'ni öğren.</p>
          <p>3. İkisini aşağıya gir, kaydet, "Test Gönder" ile dene.</p>
        </div>

        <div className="space-y-4">
          {/* Bot Token */}
          <div>
            <label className="text-xs font-display text-text-muted uppercase">Bot Token</label>
            <input
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder={settings?.has_bot_token ? '•••••••• (kayıtlı — değiştirmek için yeni gir)' : '123456:ABC-DEF...'}
              className="w-full mt-1 px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary placeholder-text-muted outline-none focus:border-accent-primary/40 transition-colors font-mono"
            />
          </div>

          {/* Chat ID */}
          <div>
            <label className="text-xs font-display text-text-muted uppercase">Chat ID</label>
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="123456789"
              className="w-full mt-1 px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary placeholder-text-muted outline-none focus:border-accent-primary/40 transition-colors font-mono"
            />
          </div>

          {/* Min confidence */}
          <div>
            <div className="flex justify-between items-center">
              <label className="text-xs font-display text-text-muted uppercase">Minimum Güven</label>
              <span className="text-sm font-display font-mono text-accent-primary">{formatPercentage(minConf, 0, false)}</span>
            </div>
            <input
              type="range" min={0} max={100} step={5}
              value={minConf}
              onChange={(e) => setMinConf(Number(e.target.value))}
              className="w-full mt-2 accent-accent-primary"
            />
            <p className="text-micro text-text-muted mt-1">Sadece bu güven değerinin üzerindeki sinyaller bildirilir.</p>
          </div>

          {/* Notify HOLD */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-display text-text-primary">BEKLE sinyallerini de gönder</label>
              <p className="text-micro text-text-muted">Kapalıyken sadece AL/SAT sinyalleri bildirilir.</p>
            </div>
            <Toggle checked={notifyHold} onChange={setNotifyHold} />
          </div>

          {/* Notify LIFECYCLE (P1.2 — proaktif yaşam döngüsü uyarıları) */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-display text-text-primary">Sinyal yaşam döngüsü bildirimleri</label>
              <p className="text-micro text-text-muted">Sinyal geçersizleşince veya TP'ye yaklaşınca proaktif uyarı gönderilir.</p>
            </div>
            <Toggle checked={notifyLifecycle} onChange={setNotifyLifecycle} />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={save}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-accent-primary text-white text-sm font-display hover:bg-accent-hover transition-colors disabled:opacity-50"
            >
              {saving ? 'Kaydediliyor...' : 'Kaydet'}
            </button>
            <button
              onClick={test}
              disabled={testing}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-bg-tertiary border border-border-subtle text-text-primary text-sm font-display hover:border-accent-primary/40 transition-colors disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" /> {testing ? 'Gönderiliyor...' : 'Test Gönder'}
            </button>

            {savedMsg && <span className="text-xs text-bullish flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Kaydedildi</span>}
            {testResult && (
              <span className={cn('text-xs flex items-center gap-1', testResult.ok ? 'text-bullish' : 'text-bearish')}>
                {testResult.ok ? <><Check className="w-3.5 h-3.5" /> Mesaj gönderildi!</> : <><X className="w-3.5 h-3.5" /> {testResult.error}</>}
              </span>
            )}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
