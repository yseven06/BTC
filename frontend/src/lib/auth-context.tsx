'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  fetchCurrentUser, loginUser, registerUser, loginWithGoogle, logout as apiLogout,
  storeAuthTokens, isLoggedIn,
  type UserProfile,
} from '@/lib/api';

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
    // Hard timeout so we never get stuck in spinner if backend hangs
    const timeoutId = setTimeout(() => setLoading(false), 4000);
    refresh().finally(() => {
      clearTimeout(timeoutId);
      setLoading(false);
    });
  }, [refresh]);

  const login = async (email: string, password: string, remember = true) => {
    const res = await loginUser(email, password);
    storeAuthTokens(res.access_token, res.refresh_token, remember);
    await refresh();
  };

  const register = async (email: string, password: string, full_name?: string) => {
    const res = await registerUser({ email, password, full_name });
    storeAuthTokens(res.access_token, res.refresh_token, true);
    await refresh();
  };

  const googleLogin = async (idToken: string) => {
    const res = await loginWithGoogle(idToken);
    storeAuthTokens(res.access_token, res.refresh_token, true);
    await refresh();
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
