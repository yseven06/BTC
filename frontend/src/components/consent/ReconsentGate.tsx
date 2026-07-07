'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { LEGAL_META } from '@/lib/legal/registry';
import { needsReconsent } from '@/lib/legal/semver';
import { getConsentStatus, recordReconsent, type ConsentAcceptance } from '@/lib/api';

// The required, separately-acknowledged documents (consent_type → slug + label).
const REQUIRED = [
  { ctype: 'tos', slug: 'kullanim-kosullari', name: 'Kullanım Koşulları' },
  { ctype: 'privacy', slug: 'aydinlatma-metni', name: 'KVKK Aydınlatma Metni' },
  { ctype: 'risk', slug: 'risk-bildirimi', name: 'Risk Bildirimi' },
] as const;

type Doc = (typeof REQUIRED)[number];

/**
 * Re-consent gate. For a logged-in user, checks (via semver) whether any required
 * legal document changed in a way that requires fresh consent (MAJOR, or flagged
 * MINOR). Only then shows a blocking modal — trivial (PATCH / unflagged MINOR)
 * changes never disturb the user. Renders nothing otherwise.
 */
export function ReconsentGate() {
  const { user, logout } = useAuth();
  const [outdated, setOutdated] = useState<Doc[]>([]);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!user) {
      setOutdated([]);
      return;
    }
    let cancelled = false;
    getConsentStatus()
      .then((status) => {
        if (cancelled) return;
        const od = REQUIRED.filter((d) => {
          const meta = LEGAL_META[d.slug];
          if (!meta) return false;
          return needsReconsent(status[d.ctype], meta.version, meta.reconsentOnMinor);
        });
        setOutdated(od);
      })
      .catch(() => {
        /* status endpoint unavailable (pre-migration/restart) → no prompt */
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!user || outdated.length === 0) return null;

  const allChecked = outdated.every((d) => checked[d.ctype]);

  const submit = async () => {
    if (!allChecked || submitting) return;
    setSubmitting(true);
    try {
      const consents: ConsentAcceptance[] = outdated.map((d) => ({
        consent_type: d.ctype,
        slug: d.slug,
        version: LEGAL_META[d.slug]?.version ?? '0.0.0',
        hash: LEGAL_META[d.slug]?.hash ?? '',
      }));
      await recordReconsent(consents);
      setOutdated([]);
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-e-0/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-panel glass-e3-overlay p-5">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber" aria-hidden />
          <div>
            <h2 className="text-base font-display text-text-primary">Güncellenen Yasal Belgeler</h2>
            <p className="mt-1 text-xs leading-relaxed text-text-muted">
              Aşağıdaki belge(ler) güncellendi. Hizmeti kullanmaya devam etmek için lütfen
              gözden geçirip onaylayın.
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-2">
          {outdated.map((d) => (
            <label key={d.ctype} className="flex items-start gap-2 text-xs leading-relaxed text-text-secondary">
              <input
                type="checkbox"
                checked={!!checked[d.ctype]}
                onChange={(e) => setChecked((s) => ({ ...s, [d.ctype]: e.target.checked }))}
                className="mt-0.5 h-4 w-4 shrink-0 accent-accent-primary"
              />
              <span>
                Güncellenen <strong className="text-text-primary">{d.name}</strong>&apos;ni okudum ve
                kabul ediyorum.{' '}
                <Link
                  href={`/yasal/${d.slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="whitespace-nowrap text-accent-primary hover:underline"
                >
                  Oku ↗
                </Link>
              </span>
            </label>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={logout}
            className="text-xs text-text-muted hover:text-text-primary hover:underline"
          >
            Hesaptan çıkış yap
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!allChecked || submitting}
            className="rounded-lg bg-accent-primary px-4 py-2 text-xs font-display text-white transition-colors hover:bg-accent-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Kaydediliyor...' : 'Onayla ve Devam Et'}
          </button>
        </div>
      </div>
    </div>
  );
}
