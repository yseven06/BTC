// Next.js server instrumentation hook. Loads the Sentry server/edge config for
// the matching runtime (each is a no-op without NEXT_PUBLIC_SENTRY_DSN).
import * as Sentry from '@sentry/nextjs';

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config');
  }
}

// Captures errors thrown in nested React Server Components.
export const onRequestError = Sentry.captureRequestError;
