'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  fetchCurrentUser, loginUser, registerUser, loginWithGoogle, logout as apiLogout,
  type UserProfile,
} from '@/lib/api';

interface AuthContextValue {
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
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
      const u = await fetchCurrentUser();
      setUser(u);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const storeTokens = (access: string, refreshTok: string) => {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refreshTok);
  };

  const login = async (email: string, password: string) => {
    const res = await loginUser(email, password);
    storeTokens(res.access_token, res.refresh_token);
    await refresh();
  };

  const register = async (email: string, password: string, full_name?: string) => {
    const res = await registerUser({ email, password, full_name });
    storeTokens(res.access_token, res.refresh_token);
    await refresh();
  };

  const googleLogin = async (idToken: string) => {
    const res = await loginWithGoogle(idToken);
    storeTokens(res.access_token, res.refresh_token);
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
