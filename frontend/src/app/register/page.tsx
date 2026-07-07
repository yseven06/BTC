'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Mail, Lock, User, ArrowRight } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { LEGAL_META } from '@/lib/legal/registry';
import { track } from '@/lib/analytics';
import { AnalyticsEvent } from '@/lib/analytics-events';

// Required, separately-acknowledged legal documents at signup.
const REQUIRED = [
  { key: 'tos', slug: 'kullanim-kosullari', ctype: 'tos', name: 'Kullanım Koşulları',
    rest: '’nı okudum ve kabul ediyorum.' },
  { key: 'privacy', slug: 'aydinlatma-metni', ctype: 'privacy', name: 'KVKK Aydınlatma Metni',
    rest: '’ni okudum.' },
  { key: 'risk', slug: 'risk-bildirimi', ctype: 'risk', name: 'Risk Bildirimi',
    rest: '’ni okudum; içeriklerin yatırım tavsiyesi olmadığını ve işlemlerin sorumluluğunun bana ait olduğunu kabul ediyorum.' },
] as const;

export default function RegisterPage() {
  const router = useRouter();
  const { user, register } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState({ tos: false, privacy: false, risk: false });
  const allRequiredAccepted = accepted.tos && accepted.privacy && accepted.risk;

  // Consent-gated, anonymous "document viewed" event (no-op until analytics consent).
  const onReadDoc = (slug: string) => track(AnalyticsEvent.legal_document_viewed, { slug });

  useEffect(() => {
    if (user) router.replace('/dashboard');
  }, [user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    if (password.length < 8) {
      setError('Şifre en az 8 karakter olmalı.');
      return;
    }
    if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
      setError('Şifre en az bir harf ve bir rakam içermeli.');
      return;
    }
    if (!allRequiredAccepted) {
      setError('Devam etmek için zorunlu onay kutularını işaretlemelisin.');
      return;
    }
    setLoading(true);
    try {
      const consents = REQUIRED.map((d) => ({
        consent_type: d.ctype,
        slug: d.slug,
        version: LEGAL_META[d.slug]?.version ?? '0.0.0',
        hash: LEGAL_META[d.slug]?.hash ?? '',
      }));
      await register(email, password, fullName || undefined, consents);
      router.replace('/dashboard');
    } catch (err: any) {
      const msg = err?.message ?? '';
      if (msg.includes('409')) setError('Bu e-posta zaten kayıtlı.');
      else if (msg.includes('422')) setError('Bilgileri kontrol et: geçerli bir e-posta ve en az 8 karakter, harf + rakam içeren bir şifre gerekli.');
      else if (msg.includes('Backend') || msg.includes('bağlan') || msg.includes('yanıt')) setError('Sunucuya şu anda ulaşılamıyor. Lütfen birazdan tekrar dene.');
      else setError('Kayıt yapılamadı. Lütfen tekrar dene.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-3">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-full h-full object-contain" />
          </div>
          <div className="flex items-center justify-center gap-2">
            <div className="text-h2 font-display text-text-primary">TradeMinds</div>
            <span className="text-micro font-medium uppercase text-accent-primary bg-accent-primary/12 border border-accent-primary/30 px-1.5 py-0.5 rounded">BETA</span>
          </div>
          <p className="text-sm text-text-secondary mt-1">Yeni Hesap Oluştur</p>
          <p className="text-xs text-text-muted mt-2">
            Erken erişim beta sürümü — özellikler geliştirilmeye devam ediyor.
          </p>
        </div>

        <form onSubmit={submit} className="glass-panel border border-border-subtle rounded-2xl p-6 space-y-4">
          <h1 className="text-lg font-display text-text-primary">Kayıt Ol</h1>

          {error && (
            <div id="register-error" role="alert" aria-live="assertive" className="bg-bearish/10 border border-bearish/30 rounded-xl px-3 py-2 text-xs text-bearish">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="register-name" className="text-xs font-display text-text-muted uppercase">Ad Soyad</label>
            <div className="relative mt-1">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                id="register-name"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="focus-ring w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary focus:border-accent-primary/40 transition-colors"
                placeholder="Mehmet Yılmaz (opsiyonel)"
              />
            </div>
          </div>

          <div>
            <label htmlFor="register-email" className="text-xs font-display text-text-muted uppercase">E-posta</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                id="register-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!error}
                aria-describedby={error ? 'register-error' : undefined}
                className="focus-ring w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary focus:border-accent-primary/40 transition-colors"
                placeholder="ornek@email.com"
              />
            </div>
          </div>

          <div>
            <label htmlFor="register-password" className="text-xs font-display text-text-muted uppercase">Şifre</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                id="register-password"
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!error}
                aria-describedby={error ? 'register-error' : undefined}
                className="focus-ring w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary focus:border-accent-primary/40 transition-colors"
                placeholder="En az 8 karakter, harf + rakam"
              />
            </div>
          </div>

          <div className="space-y-2 pt-1">
            {REQUIRED.map((d) => (
              <label key={d.key} className="flex items-start gap-2 text-xs leading-relaxed text-text-secondary">
                <input
                  type="checkbox"
                  checked={accepted[d.key]}
                  onChange={(e) => setAccepted((s) => ({ ...s, [d.key]: e.target.checked }))}
                  className="mt-0.5 h-4 w-4 shrink-0 accent-accent-primary"
                />
                <span>
                  <strong className="text-text-primary">{d.name}</strong>{d.rest}{' '}
                  <Link
                    href={`/yasal/${d.slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => onReadDoc(d.slug)}
                    className="whitespace-nowrap text-accent-primary hover:underline"
                  >
                    Oku ↗
                  </Link>
                </span>
              </label>
            ))}
          </div>

          <button
            type="submit"
            disabled={loading || !allRequiredAccepted}
            className="focus-ring w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-hover text-white text-sm font-display transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Hesap oluşturuluyor...' : (<>Hesap Oluştur <ArrowRight className="w-4 h-4" /></>)}
          </button>

          <div className="text-center text-xs text-text-secondary pt-2 border-t border-border-subtle">
            Zaten hesabın var mı?{' '}
            <Link href="/login" className="text-accent-primary hover:underline font-display">
              Giriş yap
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
