'use client';

import React, { Suspense, useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Mail, Lock, ArrowRight } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const { user, login } = useAuth();
  const redirect = search.get('redirect') ?? '/dashboard';
  const expiredNotice = search.get('reason') === 'expired'
    ? 'Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın.'
    : null;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace(redirect);
  }, [user, redirect, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      await login(email, password, remember);
      router.replace(redirect);
    } catch (err: any) {
      const msg = err?.message ?? '';
      if (msg.includes('401') || msg.includes('Invalid')) {
        setError('E-posta veya şifre hatalı.');
      } else if (msg.includes('403') || msg.includes('deactivated')) {
        setError('Hesabınız devre dışı bırakılmış. Lütfen destek ile iletişime geçin.');
      } else if (msg.includes('Backend') || msg.includes('bağlan') || msg.includes('yanıt')) {
        setError('Sunucuya şu anda ulaşılamıyor. Lütfen birazdan tekrar dene.');
      } else {
        setError('Giriş yapılamadı. Lütfen tekrar dene.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-4">
      <div className="w-full max-w-md space-y-6">
        {/* Logo */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-3">
            <img src="/logo-icon-square.png" alt="TradeMinds AI" className="w-full h-full object-contain" />
          </div>
          <div className="text-h2 font-display text-text-primary">TradeMinds</div>
          <p className="text-sm text-text-secondary mt-1">AI Trading Intelligence</p>
        </div>

        {/* Form */}
        <form onSubmit={submit} className="glass-panel border border-border-subtle rounded-2xl p-6 space-y-4">
          <h1 className="text-lg font-display text-text-primary">Hoş Geldin</h1>

          {expiredNotice && !error && (
            <div role="status" aria-live="polite" className="bg-accent-primary/10 border border-accent-primary/30 rounded-xl px-3 py-2 text-xs text-accent-primary">
              {expiredNotice}
            </div>
          )}

          {error && (
            <div id="login-error" role="alert" aria-live="assertive" className="bg-bearish/10 border border-bearish/30 rounded-xl px-3 py-2 text-xs text-bearish">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="login-email" className="text-xs font-display text-text-muted uppercase">E-posta</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                id="login-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!error}
                aria-describedby={error ? 'login-error' : undefined}
                className="focus-ring w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary focus:border-accent-primary/40 transition-colors"
                placeholder="ornek@email.com"
              />
            </div>
          </div>

          <div>
            <label htmlFor="login-password" className="text-xs font-display text-text-muted uppercase">Şifre</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                id="login-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!error}
                aria-describedby={error ? 'login-error' : undefined}
                className="focus-ring w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary focus:border-accent-primary/40 transition-colors"
                placeholder="••••••••"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="focus-ring w-4 h-4 rounded border-border-medium bg-bg-secondary accent-accent-primary cursor-pointer"
            />
            <span className="text-xs text-text-secondary">Beni hatırla</span>
          </label>

          <button
            type="submit"
            disabled={loading}
            className="focus-ring w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-hover text-white text-sm font-display transition-colors disabled:opacity-50"
          >
            {loading ? 'Giriş yapılıyor...' : (<>Giriş Yap <ArrowRight className="w-4 h-4" /></>)}
          </button>

          <div className="text-center text-xs text-text-secondary pt-2 border-t border-border-subtle">
            Hesabın yok mu?{' '}
            <Link href="/register" className="text-accent-primary hover:underline font-display">
              Kayıt ol
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-bg-primary" />}>
      <LoginForm />
    </Suspense>
  );
}
