'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Mail, Lock, User, ArrowRight } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

export default function RegisterPage() {
  const router = useRouter();
  const { user, register } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace('/dashboard');
  }, [user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Şifre en az 8 karakter olmalı.');
      return;
    }
    setLoading(true);
    try {
      await register(email, password, fullName || undefined);
      router.replace('/dashboard');
    } catch (err: any) {
      const msg = err?.message ?? '';
      if (msg.includes('409')) setError('Bu e-posta zaten kayıtlı.');
      else setError('Kayıt yapılamadı. Tekrar deneyin.');
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
          <h1 className="text-2xl font-extrabold gradient-text-brand">TradeMinds</h1>
          <p className="text-sm text-text-secondary mt-1">Yeni Hesap Oluştur</p>
        </div>

        <form onSubmit={submit} className="glass-panel border border-border-subtle rounded-2xl p-6 space-y-4">
          <h2 className="text-lg font-bold text-text-primary">Kayıt Ol</h2>

          {error && (
            <div className="bg-bearish/10 border border-bearish/30 rounded-xl px-3 py-2 text-xs text-bearish">
              {error}
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">Ad Soyad</label>
            <div className="relative mt-1">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-bg-secondary border border-border-subtle rounded-xl text-sm text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
                placeholder="Mehmet Yılmaz (opsiyonel)"
              />
            </div>
          </div>

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
                placeholder="En az 8 karakter"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-primary hover:bg-accent-secondary text-white text-sm font-bold transition-colors disabled:opacity-50"
          >
            {loading ? 'Hesap oluşturuluyor...' : (<>Hesap Oluştur <ArrowRight className="w-4 h-4" /></>)}
          </button>

          <div className="text-center text-xs text-text-secondary pt-2 border-t border-border-subtle">
            Zaten hesabın var mı?{' '}
            <Link href="/login" className="text-accent-primary hover:underline font-semibold">
              Giriş yap
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
