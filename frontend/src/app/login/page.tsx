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
    setError(null);
    setLoading(true);
    try {
      await login(email, password, remember);
      router.replace(redirect);
    } catch (err: any) {
      const msg = err?.message ?? '';
      if (msg.includes('401') || msg.includes('Invalid')) {
        setError('E-posta veya şifre hatalı.');
      } else if (msg.includes('Backend')) {
        setError('Backend kapalı. Lütfen start-backend.ps1 çalıştır.');
      } else {
        setError('Giriş yapılamadı: ' + msg);
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
          <h1 className="text-2xl font-extrabold gradient-text-brand">TradeMinds</h1>
          <p className="text-sm text-text-secondary mt-1">AI Trading Intelligence</p>
        </div>

        {/* Form */}
        <form onSubmit={submit} className="glass-panel border border-border-subtle rounded-2xl p-6 space-y-4">
          <h2 className="text-lg font-bold text-text-primary">Hoş Geldin</h2>

          {error && (
            <div className="bg-bearish/10 border border-bearish/30 rounded-xl px-3 py-2 text-xs text-bearish">
              {error}
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">E-posta</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
                placeholder="ornek@email.com"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">Şifre</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
                placeholder="••••••••"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="w-4 h-4 rounded border-border-medium bg-bg-secondary accent-accent-primary cursor-pointer"
            />
            <span className="text-xs text-text-secondary">Beni hatırla</span>
          </label>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-secondary text-white text-sm font-bold transition-colors disabled:opacity-50"
          >
            {loading ? 'Giriş yapılıyor...' : (<>Giriş Yap <ArrowRight className="w-4 h-4" /></>)}
          </button>

          <div className="text-center text-xs text-text-secondary pt-2 border-t border-border-subtle">
            Hesabın yok mu?{' '}
            <Link href="/register" className="text-accent-primary hover:underline font-semibold">
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
