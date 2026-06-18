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
 */
export function useTierLimits(): TierLimits {
  const [limits, setLimits] = useState<TierLimits>(FREE_DEFAULT);

  useEffect(() => {
    fetchMyLimits()
      .then(setLimits)
      .catch(() => setLimits(FREE_DEFAULT));
  }, []);

  return limits;
}
