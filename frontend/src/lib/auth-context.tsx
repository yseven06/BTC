'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  fetchCurrentUser, loginUser, registerUser, loginWithGoogle, logout as apiLogout,
  storeAuthTokens, isLoggedIn,
  type UserProfile,
} from '@/lib/api';
import { track } from '@/lib/analytics';
import { AnalyticsEvent } from '@/lib/analytics-events';

interface AuthContextValue {
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string, remember?: boolean) => Promise<void>;
  register: (email: string, password: string, full_name?: string) => Promise<void>;
  googleLogin: (idToken: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      // If no token, don't even try (avoid useless network round-trip)
      if (!isLoggedIn()) {
        setUser(null);
        return;
      }
      const u = await fetchCurrentUser();
      setUser(u);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    // If there's no token at all, we already know the answer — don't wait.
    // If a token DOES exist, the user must stay "logged in" (loading=true)
    // until refresh() actually resolves, however long that takes — forcing
    // loading=false early via a short fixed timer caused false "you got
    // logged out" redirects whenever /auth/me was merely slow (cold backend,
    // brief network hiccup), even though the token in storage was still
    // perfectly valid. apiFetch's own 8s abort + tryRefreshToken already
    // bound how long this can take; this is just a generous last-resort
    // safety net so a truly hung backend can't freeze the UI forever.
    const timeoutId = setTimeout(() => setLoading(false), 20000);
    refresh().finally(() => {
      clearTimeout(timeoutId);
      setLoading(false);
    });
  }, [refresh]);

  const login = async (email: string, password: string, remember = true) => {
    const res = await loginUser(email, password);
    storeAuthTokens(res.access_token, res.refresh_token, remember);
    await refresh();
    track(AnalyticsEvent.login_completed, { method: 'password' });
  };

  const register = async (email: string, password: string, full_name?: string) => {
    const res = await registerUser({ email, password, full_name });
    storeAuthTokens(res.access_token, res.refresh_token, true);
    await refresh();
    track(AnalyticsEvent.signup_completed, { method: 'password' });
  };

  const googleLogin = async (idToken: string) => {
    const res = await loginWithGoogle(idToken);
    storeAuthTokens(res.access_token, res.refresh_token, true);
    await refresh();
    track(AnalyticsEvent.login_completed, { method: 'google' });
  };

  const logout = () => {
    apiLogout();
    setUser(null);
    router.push('/login');
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, googleLogin, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
