/** @type {import('next').NextConfig} */

// Security headers applied to every route. CSP is pragmatic (allows the inline
// styles/scripts Next + Tailwind emit) but blocks external injection sources and
// framing. Tighten to nonces later if needed.
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const isDev = process.env.NODE_ENV !== 'production';

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' https://fonts.gstatic.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://challenges.cloudflare.com https://s3.tradingview.com",
  `connect-src 'self' ${API} https://api.coingecko.com https://*.tradingview.com https://eu.i.posthog.com https://eu-assets.i.posthog.com https://*.posthog.com https://*.sentry.io https://*.ingest.sentry.io https://*.ingest.de.sentry.io${isDev ? ' ws: http://localhost:8000' : ''}`,
  "frame-src https://challenges.cloudflare.com https://*.tradingview.com",
  "worker-src 'self' blob:",
].join('; ');

const securityHeaders = [
  { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), browsing-topics=()' },
  { key: 'Content-Security-Policy', value: csp },
];

const nextConfig = {
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

module.exports = nextConfig;
