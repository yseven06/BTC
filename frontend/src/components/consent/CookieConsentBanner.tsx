'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Cookie } from 'lucide-react';
import {
  getStoredConsent,
  saveConsent,
  applyConsent,
  OPEN_COOKIE_SETTINGS_EVENT,
} from '@/lib/consent/cookie-consent';

/**
 * KVKK-compliant cookie consent banner. Simple by default (three clear choices),
 * with a "manage" panel that separates necessary vs analytics cookies. Analytics
 * stays OFF until the user explicitly opts in. Reopened anytime from the footer's
 * "Çerez Ayarları" link (via a window event).
 */
export function CookieConsentBanner() {
  const [open, setOpen] = useState(false);
  const [manage, setManage] = useState(false);
  const [analytics, setAnalytics] = useState(false);

  // On mount: apply any stored consent; if none, show the banner (first visit).
  useEffect(() => {
    const stored = getStoredConsent();
    applyConsent(stored);
    if (stored) setAnalytics(stored.analytics);
    else setOpen(true);
  }, []);

  // Footer "Çerez Ayarları" → reopen in manage mode with current values.
  useEffect(() => {
    const handler = () => {
      const stored = getStoredConsent();
      setAnalytics(stored?.analytics ?? false);
      setManage(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_COOKIE_SETTINGS_EVENT, handler);
    return () => window.removeEventListener(OPEN_COOKIE_SETTINGS_EVENT, handler);
  }, []);

  if (!open) return null;

  const acceptAll = () => {
    saveConsent(true);
    setOpen(false);
    setManage(false);
  };
  const onlyNecessary = () => {
    saveConsent(false);
    setOpen(false);
    setManage(false);
  };
  const savePrefs = () => {
    saveConsent(analytics);
    setOpen(false);
    setManage(false);
  };

  return (
    <div className="fixed inset-x-0 bottom-0 z-[100] px-3 pb-3 sm:px-4 sm:pb-4">
      <div className="mx-auto w-full max-w-3xl rounded-xl border border-border-hl12 bg-e-3 p-4 shadow-e3 sm:p-5">
        <div className="flex items-start gap-3">
          <Cookie className="mt-0.5 h-5 w-5 shrink-0 text-accent-primary" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-display text-text-primary">Çerez Tercihleri</p>
            <p className="mt-1 text-xs leading-relaxed text-text-muted">
              Zorunlu çerezler hizmetin çalışması için gereklidir. Analitik çerezler
              yalnızca onayınızla çalışır. Ayrıntılar için{' '}
              <Link href="/yasal/cerez-politikasi" className="text-accent-primary hover:underline">
                Çerez Politikası
              </Link>
              .
            </p>

            {manage && (
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between rounded-lg border border-border-hl12 bg-bg-primary/40 px-3 py-2">
                  <div>
                    <p className="text-xs font-medium text-text-primary">Zorunlu Çerezler</p>
                    <p className="text-micro text-text-muted">Oturum ve güvenlik — devre dışı bırakılamaz.</p>
                  </div>
                  <span className="shrink-0 rounded-md bg-white/5 px-2 py-1 text-micro font-medium text-text-muted">
                    Her zaman aktif
                  </span>
                </div>

                <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border-hl12 bg-bg-primary/40 px-3 py-2">
                  <div>
                    <p className="text-xs font-medium text-text-primary">Analitik Çerezler</p>
                    <p className="text-micro text-text-muted">Ürün kullanımının ölçümü (PostHog) — isteğe bağlı.</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={analytics}
                    onChange={(e) => setAnalytics(e.target.checked)}
                    className="h-4 w-4 shrink-0 accent-accent-primary"
                    aria-label="Analitik çerezlere izin ver"
                  />
                </label>
              </div>
            )}

            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <button
                onClick={acceptAll}
                className="rounded-lg bg-accent-primary px-3 py-2 text-xs font-display text-white transition-colors hover:bg-accent-hover"
              >
                Tümünü Kabul Et
              </button>
              <button
                onClick={onlyNecessary}
                className="rounded-lg border border-border-hl16 px-3 py-2 text-xs font-display text-text-secondary transition-colors hover:bg-e-2"
              >
                Yalnızca Zorunlu Çerezler
              </button>
              {manage ? (
                <button
                  onClick={savePrefs}
                  className="rounded-lg border border-accent-primary/40 px-3 py-2 text-xs font-display text-accent-primary transition-colors hover:bg-accent-primary/10"
                >
                  Tercihleri Kaydet
                </button>
              ) : (
                <button
                  onClick={() => setManage(true)}
                  className="rounded-lg border border-border-hl16 px-3 py-2 text-xs font-display text-text-secondary transition-colors hover:bg-e-2"
                >
                  Tercihleri Yönet
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
