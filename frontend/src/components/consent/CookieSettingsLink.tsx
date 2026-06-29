'use client';

import { openCookieSettings } from '@/lib/consent/cookie-consent';

/** Footer link that reopens the cookie preferences panel. */
export function CookieSettingsLink({ className = '' }: { className?: string }) {
  return (
    <button type="button" onClick={openCookieSettings} className={className}>
      Çerez Ayarları
    </button>
  );
}
