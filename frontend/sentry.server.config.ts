// Sentry (server runtime). Env-gated: a no-op unless NEXT_PUBLIC_SENTRY_DSN is set,
// so local/dev is unaffected. Loaded by instrumentation.ts on the Node runtime.
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
