// TradeMinds AI service worker — conservative + safe.
// Navigations: network-first (users always get the freshest app; offline → cached
// shell). Static assets: stale-while-revalidate. API/auth: never cached. Bump
// CACHE_VERSION to invalidate. Registered ONLY in production (see PWARegister).

const CACHE_VERSION = 'tm-v1';
const SHELL_URL = '/dashboard';

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_VERSION).then((c) => c.add(SHELL_URL)).catch(() => {})
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // only same-origin
  if (url.pathname.startsWith('/api/')) return;     // never cache API/auth

  // Navigations → network-first, fallback to cached shell when offline.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(SHELL_URL, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(SHELL_URL).then((r) => r || caches.match(request)))
    );
    return;
  }

  // Static build output / images / fonts → stale-while-revalidate.
  if (url.pathname.startsWith('/_next/static/') || /\.(?:png|jpg|jpeg|svg|webp|ico|woff2?)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(CACHE_VERSION).then((c) => c.put(request, copy)).catch(() => {});
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
