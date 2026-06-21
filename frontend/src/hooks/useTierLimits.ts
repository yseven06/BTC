'use client';

import { useEffect, useState } from 'react';
import { fetchMyLimits, type TierLimits } from '@/lib/api';

const FREE_DEFAULT: TierLimits = {
  tier: 'free',
  label: 'Ücretsiz',
  daily_signal_limit: 3,
  can_view_engine_details: false,
  can_use_telegram: false,
  can_use_backtest: false,
  can_view_strategy_lab: false,
  can_view_symbol_analysis: false,
  can_use_api: false,
  backtest_runs_per_day: 0,
};

/**
 * Returns the current user's tier limits, defaulting to Free when the
 * request fails (e.g. no auth token, backend offline).
 *
 * `loading` starts true and the default is Free — callers that gate a
 * feature behind `can_use_*` must check `!loading` first, otherwise every
 * paying/admin user sees a false "upgrade required" lock flash for the
 * one render before the real tier comes back from the API.
 */
export function useTierLimits(): TierLimits & { loading: boolean } {
  const [limits, setLimits] = useState<TierLimits>(FREE_DEFAULT);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMyLimits()
      .then(setLimits)
      .catch(() => setLimits(FREE_DEFAULT))
      .finally(() => setLoading(false));
  }, []);

  return { ...limits, loading };
}
