// Sentry (browser). Loaded automatically by Next.js on the client. Env-gated:
// a no-op unless NEXT_PUBLIC_SENTRY_DSN is set, so local/dev sends nothing.
import * as Sentry from '@sentry/nextjs';

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

// Instruments client-side navigations for tracing.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
