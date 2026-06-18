/**
 * TradeMinds AI – Centralized API Client
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const COINGECKO = 'https://api.coingecko.com/api/v3';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

async function cgFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${COINGECKO}${path}`, {
    headers: { Accept: 'application/json' },
    next: { revalidate: 60 },
  });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Signals
// ---------------------------------------------------------------------------

export interface ApiSignal {
  id: string;
  asset_id: string;
  asset: {
    id: string;
    symbol: string;
    name: string;
    asset_type: string;
    market: string;
  };
  signal_type: string;
  direction: string;
  confidence_score: number;
  probability_score: number;
  risk_score: number;
  risk_level: string;
  entry_zone_low: number;
  entry_zone_high: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  invalidation_conditions: string;
  explanation_tr?: string;
  explanation_en?: string;
  engines_data?: Record<string, any>;
  timeframe: string;
  generated_at: string;
  expires_at?: string;
  is_active: boolean;
}

export interface SignalListResponse {
  items: ApiSignal[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PerformanceSummary {
  total_signals: number;
  win_count: number;
  loss_count: number;
  breakeven_count: number;
  active_count: number;
  expired_count: number;
  win_rate: number;
  average_return: number | null;
  average_drawdown: number | null;
  tp1_hit_rate: number;
  tp2_hit_rate: number;
  tp3_hit_rate: number;
  win_rate_by_direction: { bullish: number; bearish: number; neutral: number };
  win_rate_by_asset: Record<string, number>;
  performance_by_signal_type: Record<string, { total: number; win_rate: number; average_return: number }>;
  historical_equity_curve: Array<{ time: string; capital: number }>;
  drawdown_analysis: { max_drawdown: number; average_drawdown: number };
}

export async function fetchActiveSignals(params?: {
  direction?: string;
  signal_type?: string;
  timeframe?: string;
  page?: number;
  page_size?: number;
}): Promise<SignalListResponse> {
  const q = new URLSearchParams();
  if (params?.direction) q.set('direction', params.direction);
  if (params?.signal_type) q.set('signal_type', params.signal_type);
  if (params?.timeframe) q.set('timeframe', params.timeframe);
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch<SignalListResponse>(`/api/v1/signals${qs}`);
}

export async function fetchPerformanceSummary(): Promise<PerformanceSummary> {
  return apiFetch<PerformanceSummary>('/api/v1/signals/performance');
}

export async function triggerSignalGeneration(symbol: string, timeframe = '1h'): Promise<void> {
  await apiFetch(`/api/v1/signals/generate/${symbol}?timeframe=${timeframe}`, { method: 'POST' });
}

export async function triggerBatchGeneration(): Promise<void> {
  await apiFetch('/api/v1/signals/generate-batch', { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export interface ApiAsset {
  id: string;
  symbol: string;
  name: string;
  asset_type: string;
  market: string;
  is_active: boolean;
}

export interface AssetListResponse {
  items: ApiAsset[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchAssets(params?: {
  asset_type?: string;
  market?: string;
  page?: number;
  page_size?: number;
}): Promise<AssetListResponse> {
  const q = new URLSearchParams();
  if (params?.asset_type) q.set('asset_type', params.asset_type);
  if (params?.market) q.set('market', params.market);
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch<AssetListResponse>(`/api/v1/assets${qs}`);
}

export async function searchAssets(q: string): Promise<ApiAsset[]> {
  return apiFetch<ApiAsset[]>(`/api/v1/assets/search?q=${encodeURIComponent(q)}`);
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export interface ApiAlert {
  id: string;
  asset_id: string;
  alert_type: string;
  conditions: Record<string, unknown>;
  is_active: boolean;
  triggered_at?: string | null;
  created_at: string;
}

export async function fetchAlerts(): Promise<ApiAlert[]> {
  return apiFetch<ApiAlert[]>('/api/v1/alerts');
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
  avatar_url?: string;
  provider?: string;
  language?: string;
  is_active?: boolean;
  is_admin?: boolean;
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/v1/auth/me');
}

export async function updateProfile(payload: {
  full_name?: string; avatar_url?: string; language?: 'tr' | 'en';
}): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/v1/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function changePassword(
  current_password: string, new_password: string,
): Promise<{ status: string; message?: string }> {
  return apiFetch('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password }),
  });
}

// ---------------------------------------------------------------------------
// Notifications (Telegram)
// ---------------------------------------------------------------------------

export interface NotificationSettings {
  telegram_enabled: boolean;
  telegram_chat_id: string | null;
  has_bot_token: boolean;
  min_confidence: number;
  notify_hold: boolean;
}

export interface NotificationSettingsUpdate {
  telegram_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  min_confidence?: number;
  notify_hold?: boolean;
}

export async function fetchNotificationSettings(): Promise<NotificationSettings> {
  return apiFetch<NotificationSettings>('/api/v1/notifications/settings');
}

export async function updateNotificationSettings(
  payload: NotificationSettingsUpdate,
): Promise<NotificationSettings> {
  return apiFetch<NotificationSettings>('/api/v1/notifications/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function sendTelegramTest(): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>('/api/v1/notifications/test', { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Billing & Subscriptions
// ---------------------------------------------------------------------------

export type SubscriptionTier  = 'free' | 'pro' | 'premium';
export type BillingCycle      = 'monthly' | 'quarterly' | 'semi_annual' | 'yearly';
export type SubscriptionStatus = 'active' | 'canceled' | 'expired' | 'past_due' | 'trial';

export interface PlanPricing {
  cycle: BillingCycle;
  amount_usd: number;
  months: number;
  savings_pct: number;
}
export interface PlanFeature { label: string; included: boolean; }
export interface Plan {
  tier: SubscriptionTier;
  name: string;
  description: string;
  recommended: boolean;
  pricing: PlanPricing[];
  features: PlanFeature[];
}
export interface PlansResponse { plans: Plan[]; currency: string; }

export interface SubscriptionResponse {
  tier: SubscriptionTier;
  status: SubscriptionStatus;
  billing_cycle: BillingCycle | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

export async function fetchPlans(): Promise<PlansResponse> {
  return apiFetch<PlansResponse>('/api/v1/billing/plans');
}
export async function fetchMySubscription(): Promise<SubscriptionResponse> {
  return apiFetch<SubscriptionResponse>('/api/v1/billing/subscription');
}
export async function startCheckout(
  tier: SubscriptionTier,
  cycle: BillingCycle,
): Promise<{ url: string; session_id: string; mock: boolean }> {
  return apiFetch('/api/v1/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({ tier, cycle }),
  });
}
export async function cancelSubscription(): Promise<SubscriptionResponse> {
  return apiFetch<SubscriptionResponse>('/api/v1/billing/cancel', { method: 'POST' });
}

export interface TierLimits {
  tier: SubscriptionTier;
  label: string;
  daily_signal_limit: number;
  can_view_engine_details: boolean;
  can_use_telegram: boolean;
  can_use_backtest: boolean;
  can_view_strategy_lab: boolean;
  can_view_symbol_analysis: boolean;
  can_use_api: boolean;
  backtest_runs_per_day: number;
}
export async function fetchMyLimits(): Promise<TierLimits> {
  return apiFetch<TierLimits>('/api/v1/billing/limits');
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export async function registerUser(payload: {
  email: string; password: string; full_name?: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function loginUser(
  email: string, password: string,
): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function loginWithGoogle(idToken: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/google', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken }),
  });
}

export function logout(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }
}

export function isLoggedIn(): boolean {
  if (typeof window === 'undefined') return false;
  return !!localStorage.getItem('access_token');
}

// ---------------------------------------------------------------------------
// Macro
// ---------------------------------------------------------------------------

export interface MacroSnapshot {
  turkey: { usd_try: number | null; eur_try: number | null };
  united_states: {
    fed_funds_rate:  number | null;
    cpi:             number | null;
    ten_year_yield:  number | null;
    usd_broad_index: number | null;
    configured:      boolean;
  };
}
export async function fetchMacroSnapshot(): Promise<MacroSnapshot> {
  return apiFetch<MacroSnapshot>('/api/v1/macro/snapshot');
}

export interface KapDisclosure {
  title:     string;
  company:   string;
  published: string;
  category:  string;
  url:       string | null;
}
export async function fetchKapDisclosures(limit = 15): Promise<{ items: KapDisclosure[]; count: number }> {
  return apiFetch(`/api/v1/macro/kap-disclosures?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// OHLCV for charts
// ---------------------------------------------------------------------------

export interface OhlcvCandle {
  time:   number; open: number; high: number; low: number; close: number; volume: number;
}
export interface OhlcvResponse {
  symbol: string; timeframe: string; candles: OhlcvCandle[];
}
export async function fetchOhlcv(
  symbol: string, timeframe = '1h', limit = 200,
): Promise<OhlcvResponse> {
  return apiFetch<OhlcvResponse>(
    `/api/v1/prices/ohlcv/${encodeURIComponent(symbol)}?timeframe=${timeframe}&limit=${limit}`,
  );
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export interface AdminStats {
  total_users:        number;
  active_users:       number;
  admin_count:        number;
  paying_users:       number;
  total_signals:      number;
  active_signals:     number;
  total_assets:       number;
  total_revenue_usd:  number;
  win_rate:           number;
}
export interface AdminUserRow {
  id:              string;
  email:           string;
  full_name:       string | null;
  provider:        string;
  is_active:       boolean;
  is_admin:        boolean;
  created_at:      string;
  tier:            string;
  sub_status:      string | null;
  sub_period_end:  string | null;
}
export async function fetchAdminStats(): Promise<AdminStats> {
  return apiFetch<AdminStats>('/api/v1/admin/stats');
}
export async function fetchAdminUsers(
  page = 1, page_size = 50, q?: string,
): Promise<{ items: AdminUserRow[]; total: number; page: number; page_size: number }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(page_size) });
  if (q) params.set('q', q);
  return apiFetch(`/api/v1/admin/users?${params}`);
}
export async function updateAdminUser(
  user_id: string,
  payload: { is_admin?: boolean; is_active?: boolean; tier?: SubscriptionTier },
): Promise<void> {
  await apiFetch(`/api/v1/admin/users/${user_id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
export async function deleteAdminUser(user_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/users/${user_id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// PDF Reports
// ---------------------------------------------------------------------------

/** Download a PDF blob and trigger browser save dialog. */
async function downloadPdf(path: string, filename: string): Promise<void> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`PDF ${res.status}: ${txt}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadSignalPdf(signal_id: string, symbol = 'signal'): Promise<void> {
  await downloadPdf(
    `/api/v1/reports/signal/${signal_id}.pdf`,
    `trademinds-${symbol}-${signal_id.slice(0, 8)}.pdf`,
  );
}

export async function downloadPerformancePdf(): Promise<void> {
  await downloadPdf('/api/v1/reports/performance.pdf', 'trademinds-performance.pdf');
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export interface BacktestRequest {
  symbol: string;
  timeframe: string;
  initial_capital: number;
  risk_pct: number;
  max_age: number;
  execution_model?: string;
}

export interface BacktestTrade {
  trade_id: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  return_pct: number;
  capital_impact: number;
  entry_time: string;
  exit_time: string;
  outcome: string;
  max_drawdown: number;
  age: number;
}

export interface BacktestResult {
  total_trades: number;
  wins: number;
  losses: number;
  breakevens: number;
  expired: number;
  win_rate: number;
  loss_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  average_return_pct: number;
  average_rr: number;
  expectancy_pct: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  equity_curve: Array<{ time: string; capital: number }>;
  trades_log: BacktestTrade[];
}

export async function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  return apiFetch<BacktestResult>('/api/v1/signals/backtest', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// CoinGecko — Global Market
// ---------------------------------------------------------------------------

export interface GlobalMarketData {
  total_market_cap_usd: number;
  total_volume_usd: number;
  btc_dominance: number;
  eth_dominance: number;
  market_cap_change_24h: number;
  active_cryptocurrencies: number;
}

interface CgGlobalResponse {
  data: {
    active_cryptocurrencies: number;
    total_market_cap: Record<string, number>;
    total_volume: Record<string, number>;
    market_cap_percentage: Record<string, number>;
    market_cap_change_percentage_24h_usd: number;
  };
}

export async function fetchGlobalMarket(): Promise<GlobalMarketData> {
  const res = await cgFetch<CgGlobalResponse>('/global');
  const d = res.data;
  return {
    total_market_cap_usd: d.total_market_cap.usd ?? 0,
    total_volume_usd: d.total_volume.usd ?? 0,
    btc_dominance: d.market_cap_percentage.btc ?? 0,
    eth_dominance: d.market_cap_percentage.eth ?? 0,
    market_cap_change_24h: d.market_cap_change_percentage_24h_usd ?? 0,
    active_cryptocurrencies: d.active_cryptocurrencies ?? 0,
  };
}

// ---------------------------------------------------------------------------
// CoinGecko — Top Gainers / Market list
// ---------------------------------------------------------------------------

export interface CoinMarket {
  id: string;
  symbol: string;
  name: string;
  current_price: number;
  price_change_percentage_24h: number;
  market_cap: number;
  total_volume: number;
  image: string;
  sparkline_in_7d?: { price: number[] };
}

export async function fetchTopGainers(limit = 5): Promise<CoinMarket[]> {
  const coins = await cgFetch<CoinMarket[]>(
    `/coins/markets?vs_currency=usd&order=percent_change_24h_desc&per_page=${limit}&page=1&sparkline=false`
  );
  return coins;
}

export async function fetchTopCoins(limit = 10): Promise<CoinMarket[]> {
  return cgFetch<CoinMarket[]>(
    `/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=${limit}&page=1&sparkline=true`
  );
}

// ---------------------------------------------------------------------------
// Fear & Greed Index (alternative.me — free, no key)
// ---------------------------------------------------------------------------

export interface FearGreedData {
  value: number;
  value_classification: string;
}

export async function fetchFearGreed(): Promise<FearGreedData> {
  const res = await fetch('https://api.alternative.me/fng/?limit=1');
  if (!res.ok) throw new Error('FNG fetch failed');
  const json = await res.json();
  const item = json.data?.[0];
  return {
    value: parseInt(item?.value ?? '50', 10),
    value_classification: item?.value_classification ?? 'Neutral',
  };
}

// ---------------------------------------------------------------------------
// Market cap chart — synthesize realistic 24h data from live snapshot
// (CoinGecko Pro needed for historical global; this avoids that dependency)
// ---------------------------------------------------------------------------

export interface MarketCapPoint {
  time: string;
  cap: number;
  volume: number;
}

export function buildMarketCapChart(currentCap: number, changePercent: number): MarketCapPoint[] {
  const points: MarketCapPoint[] = [];
  const startCap = currentCap / (1 + changePercent / 100);
  const now = Date.now();
  const hoursBack = 24;
  for (let i = hoursBack; i >= 0; i--) {
    const t = new Date(now - i * 3600 * 1000);
    const progress = (hoursBack - i) / hoursBack;
    // smooth interpolation with slight noise
    const noise = (Math.sin(i * 2.5) * 0.008 + Math.cos(i * 1.3) * 0.005) * currentCap;
    const interpolated = startCap + (currentCap - startCap) * progress + noise;
    const label = t.getHours().toString().padStart(2, '0') + ':00';
    points.push({
      time: label,
      cap: Math.round(interpolated),
      volume: Math.round(interpolated * 0.04 * (0.9 + Math.random() * 0.2)),
    });
  }
  return points;
}
