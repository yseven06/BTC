'use client';

import React, { createContext, useContext, ReactNode } from 'react';
import { Language } from '@/types';
import { t, TranslationKey } from '@/lib/i18n';

// English support was half-built (only a handful of strings were ever
// wired up to the toggle, the rest of the app stayed Turkish) and confused
// more than it helped — the app is Turkish-only for now. `tr()` stays
// around since plenty of call sites use it for Turkish copy; `language`
// is just permanently 'tr'.
interface LanguageContextType {
  language: Language;
  tr: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language: Language = 'tr';
  const tr = (key: TranslationKey) => t(language, key);

  return (
    <LanguageContext.Provider value={{ language, tr }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}
