/**
 * Centralized, VERSIONED analytics event names.
 *
 * Always reference events through this map (never inline strings) so the taxonomy
 * stays in one place. Bump the `_vN` suffix when an event's meaning or property
 * shape changes — old and new versions then coexist without silently mixing.
 */
export const AnalyticsEvent = {
  landing_cta_clicked: 'landing_cta_clicked_v1',
  signup_started: 'signup_started_v1',
  signup_completed: 'signup_completed_v1',
  login_completed: 'login_completed_v1',
  signal_viewed: 'signal_viewed_v1',
  signal_generation_clicked: 'signal_generation_clicked_v1',
  pricing_viewed: 'pricing_viewed_v1',
  checkout_started: 'checkout_started_v1',
  subscription_activated: 'subscription_activated_v1',
  watchlist_created: 'watchlist_created_v1',
  alert_created: 'alert_created_v1',
  portfolio_created: 'portfolio_created_v1',
  pdf_downloaded: 'pdf_downloaded_v1',
} as const;

export type AnalyticsEventName = (typeof AnalyticsEvent)[keyof typeof AnalyticsEvent];
