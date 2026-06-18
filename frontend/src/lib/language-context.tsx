'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { Language } from '@/types';
import { t, TranslationKey } from '@/lib/i18n';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  toggleLanguage: () => void;
  tr: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>('tr');

  const toggleLanguage = useCallback(() => {
    setLanguage((prev) => (prev === 'tr' ? 'en' : 'tr'));
  }, []);

  const tr = useCallback(
    (key: TranslationKey) => t(language, key),
    [language]
  );

  return (
    <LanguageContext.Provider value={{ language, setLanguage, toggleLanguage, tr }}>
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
