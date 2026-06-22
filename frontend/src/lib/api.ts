/**
 * TradeMinds AI – Centralized API Client
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const COINGECKO = 'https://api.coingecko.com/api/v3';

// ---------------------------------------------------------------------------
// Token storage — "Beni Hatırla" determines which storage survives a closed
// browser. localStorage persists across restarts (remembered); sessionStorage
// clears when the tab/browser closes (not remembered). Access tokens expire
// after 30 minutes either way — apiFetch transparently refreshes them below
// so the user is never bounced to /login just because 30 minutes passed.
// ---------------------------------------------------------------------------

function getStoredToken(name: string): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(name) ?? sessionStorage.getItem(name);
}

export function storeAuthTokens(access: string, refresh: string, remember: boolean): void {
  if (typeof window === 'undefined') return;
  const store = remember ? localStorage : sessionStorage;
  const other = remember ? sessionStorage : localStorage;
  store.setItem('access_token', access);
  store.setItem('refresh_token', refresh);
  other.removeItem('access_token');
  other.removeItem('refresh_token');
}

function clearAuthTokens(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  sessionStorage.removeItem('access_token');
  sessionStorage.removeItem('refresh_token');
}

// Dedupe concurrent refresh attempts — if 3 requests 401 at the same moment,
// only one POST /auth/refresh fires; the rest await the same promise.
let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refreshToken = getStoredToken('refresh_token');
    if (!refreshToken) return false;
    try {
      const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      // Preserve whichever storage tier was already in use (remember-me choice).
      const remembered = typeof window !== 'undefined' && !!localStorage.getItem('refresh_token');
      storeAuthTokens(data.access_token, data.refresh_token, remembered);
      return true;
    } catch {
      return false;
    }
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit, _isRetry = false): Promise<T> {
  const token = getStoredToken('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };
  // Abort after 8s so a dead backend doesn't make the UI hang for 30+s
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    // Access token expired mid-session — silently refresh and retry once
    // instead of surfacing a 401 that would bounce the user to /login.
    if (res.status === 401 && !_isRetry && !path.includes('/auth/refresh') && !path.includes('/auth/login')) {
      const refreshed = await tryRefreshToken();
      if (refreshed) return apiFetch<T>(path, init, true);
      clearAuthTokens();
    }
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API ${res.status}: ${body}`);
    }
    // 204 No Content (and any other empty body) has nothing for res.json()
    // to parse — it throws "Unexpected end of JSON input" otherwise.
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new Error('Backend yanıt vermiyor. Lütfen backend\'in çalıştığından emin ol (localhost:8000).');
    }
    if (err?.message?.includes('Failed to fetch') || err?.message?.includes('NetworkError')) {
      throw new Error('Backend\'e bağlanılamıyor. localhost:8000 çalışıyor mu?');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
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
  outcome?: 'active' | 'win' | 'loss' | 'breakeven' | 'expired' | 'invalidated';
  actual_return?: number | null;
  max_drawdown?: number | null;
  hit_tp1?: boolean;
  hit_tp2?: boolean;
  hit_tp3?: boolean;
  tp1_hit_at?: string | null;
  tp2_hit_at?: string | null;
  tp3_hit_at?: string | null;
  closed_at?: string | null;
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
  only_actionable?: boolean;
  page?: number;
  page_size?: number;
}): Promise<SignalListResponse> {
  const q = new URLSearchParams();
  if (params?.direction) q.set('direction', params.direction);
  if (params?.signal_type) q.set('signal_type', params.signal_type);
  if (params?.timeframe) q.set('timeframe', params.timeframe);
  if (params?.only_actionable !== undefined) q.set('only_actionable', String(params.only_actionable));
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch<SignalListResponse>(`/api/v1/signals${qs}`);
}

export async function fetchPerformanceSummary(): Promise<PerformanceSummary> {
  return apiFetch<PerformanceSummary>('/api/v1/signals/performance');
}

export interface SignalHistoryFilters {
  asset_id?: string;
  symbol?: string;
  market?: 'crypto' | 'stock';
  signal_type?: string;
  outcome?: 'active' | 'win' | 'loss' | 'breakeven' | 'expired' | 'invalidated';
  min_confidence?: number;
  max_confidence?: number;
  date_from?: string;
  date_to?: string;
  only_resolved?: boolean;
  page?: number;
  page_size?: number;
}

export async function fetchSignalHistory(params?: SignalHistoryFilters): Promise<SignalListResponse> {
  const q = new URLSearchParams();
  if (params?.asset_id) q.set('asset_id', params.asset_id);
  if (params?.symbol) q.set('symbol', params.symbol);
  if (params?.market) q.set('market', params.market);
  if (params?.signal_type) q.set('signal_type', params.signal_type);
  if (params?.outcome) q.set('outcome', params.outcome);
  if (params?.min_confidence !== undefined) q.set('min_confidence', String(params.min_confidence));
  if (params?.max_confidence !== undefined) q.set('max_confidence', String(params.max_confidence));
  if (params?.date_from) q.set('date_from', params.date_from);
  if (params?.date_to) q.set('date_to', params.date_to);
  if (params?.only_resolved !== undefined) q.set('only_resolved', String(params.only_resolved));
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch<SignalListResponse>(`/api/v1/signals/history${qs}`);
}

export interface SignalHistoryStats {
  total_signals: number;
  closed_count: number;
  win_count: number;
  loss_count: number;
  breakeven_count: number;
  expired_count: number;
  invalidated_count: number;
  active_count: number;
  win_rate: number;
  tp_hit_rate: number;
  sl_rate: number;
  average_return: number | null;
  profit_factor: number | null;
  best_signal: { symbol: string; return: number; outcome: string; closed_at: string | null } | null;
  worst_signal: { symbol: string; return: number; outcome: string; closed_at: string | null } | null;
}

export async function fetchSignalHistoryStats(params?: {
  market?: 'crypto' | 'stock';
  date_from?: string;
  date_to?: string;
}): Promise<SignalHistoryStats> {
  const q = new URLSearchParams();
  if (params?.market) q.set('market', params.market);
  if (params?.date_from) q.set('date_from', params.date_from);
  if (params?.date_to) q.set('date_to', params.date_to);
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch<SignalHistoryStats>(`/api/v1/signals/history/stats${qs}`);
}

export async function triggerSignalGeneration(symbol: string, timeframe = '1h'): Promise<void> {
  await apiFetch(`/api/v1/signals/generate/${symbol}?timeframe=${timeframe}`, { method: 'POST' });
}

export async function triggerBatchGeneration(): Promise<void> {
  await apiFetch('/api/v1/signals/generate-batch', { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Adaptive Signal Intelligence — "is this signal still valid?" panel data
// ---------------------------------------------------------------------------

export interface EngineScoreSnapshot {
  score: number;
  bias: string;
  confidence: number;
}

export interface CoinMemoryInfo {
  has_memory: boolean;
  total_signals?: number;
  wins?: number;
  losses?: number;
  win_rate?: number | null;
  avg_bars_to_outcome?: number | null;
  adaptive_active?: boolean;
}

export interface SignalIntelligence {
  signal_id: string;
  symbol: string | null;
  timeframe: string;
  is_active: boolean;
  generated_at: string | null;
  live_status: string | null;
  live_status_tr: string | null;
  status_reason: string | null;
  status_updated_at: string | null;
  birth_confidence: number | null;
  regime: string | null;
  regime_win_rate: number | null;
  atr_pct: number | null;
  volatility_ratio: number | null;
  fear_greed: number | null;
  engine_scores_at_signal: Record<string, EngineScoreSnapshot> | null;
  coin_memory: CoinMemoryInfo;
  similar_setups: {
    has_data: boolean;
    match_count: number;
    needed?: number;
    wins?: number;
    losses?: number;
    win_rate?: number | null;
    most_common_outcome?: string | null;
  };
  outcome: string | null;
  detail_label: string | null;
  detail_label_tr: string | null;
  mfe_pct: number | null;
  max_drawdown: number | null;
  bars_to_outcome: number | null;
}

export async function fetchSignalIntelligence(signalId: string): Promise<SignalIntelligence> {
  return apiFetch<SignalIntelligence>(`/api/v1/signals/${signalId}/intelligence`);
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

export async function fetchAlerts(isActive?: boolean): Promise<ApiAlert[]> {
  const qs = isActive === undefined ? '' : `?is_active=${isActive}`;
  return apiFetch<ApiAlert[]>(`/api/v1/alerts${qs}`);
}

export async function createAlert(payload: {
  asset_id: string; alert_type: 'price' | 'signal' | 'custom'; conditions: Record<string, unknown>;
}): Promise<ApiAlert> {
  return apiFetch<ApiAlert>('/api/v1/alerts', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateAlert(alert_id: string, payload: {
  conditions?: Record<string, unknown>; is_active?: boolean;
}): Promise<ApiAlert> {
  return apiFetch<ApiAlert>(`/api/v1/alerts/${alert_id}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteAlert(alert_id: string): Promise<void> {
  await apiFetch(`/api/v1/alerts/${alert_id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Watchlists
// ---------------------------------------------------------------------------

export interface ApiWatchlist {
  id: string;
  user_id: string;
  name: string;
  asset_ids: string[];
  created_at: string;
}

export async function fetchWatchlists(): Promise<ApiWatchlist[]> {
  return apiFetch<ApiWatchlist[]>('/api/v1/watchlists');
}

export async function createWatchlist(name: string, asset_ids: string[] = []): Promise<ApiWatchlist> {
  return apiFetch<ApiWatchlist>('/api/v1/watchlists', { method: 'POST', body: JSON.stringify({ name, asset_ids }) });
}

export async function updateWatchlist(id: string, payload: { name?: string; asset_ids?: string[] }): Promise<ApiWatchlist> {
  return apiFetch<ApiWatchlist>(`/api/v1/watchlists/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteWatchlist(id: string): Promise<void> {
  await apiFetch(`/api/v1/watchlists/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Portfolios
// ---------------------------------------------------------------------------

export interface ApiHolding {
  id: string;
  portfolio_id: string;
  asset_id: string | null;
  quantity: number;
  average_entry_price: number;
  current_price: number | null;
  total_cost: number | null;
  current_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  notes: string | null;
  is_closed: boolean;
  exit_price: number | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  closed_at: string | null;
}

export interface ApiPortfolioListItem {
  id: string; user_id: string; name: string; description: string | null;
  initial_capital: number; currency: string;
}

export interface ApiPortfolio extends ApiPortfolioListItem {
  holdings: ApiHolding[];
}

export async function fetchPortfolios(): Promise<ApiPortfolioListItem[]> {
  return apiFetch<ApiPortfolioListItem[]>('/api/v1/portfolios');
}

export async function fetchPortfolio(id: string): Promise<ApiPortfolio> {
  return apiFetch<ApiPortfolio>(`/api/v1/portfolios/${id}`);
}

export async function createPortfolio(payload: {
  name: string; description?: string; initial_capital?: number; currency?: string;
}): Promise<ApiPortfolio> {
  return apiFetch<ApiPortfolio>('/api/v1/portfolios', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updatePortfolio(id: string, payload: {
  name?: string; description?: string; initial_capital?: number; currency?: string;
}): Promise<ApiPortfolio> {
  return apiFetch<ApiPortfolio>(`/api/v1/portfolios/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deletePortfolio(id: string): Promise<void> {
  await apiFetch(`/api/v1/portfolios/${id}`, { method: 'DELETE' });
}

export async function addHolding(portfolioId: string, payload: {
  asset_id: string; quantity: number; average_entry_price: number; notes?: string;
}): Promise<ApiHolding> {
  return apiFetch<ApiHolding>(`/api/v1/portfolios/${portfolioId}/holdings`, { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateHolding(portfolioId: string, holdingId: string, payload: {
  quantity?: number; average_entry_price?: number; current_price?: number; notes?: string;
}): Promise<ApiHolding> {
  return apiFetch<ApiHolding>(`/api/v1/portfolios/${portfolioId}/holdings/${holdingId}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteHolding(portfolioId: string, holdingId: string): Promise<void> {
  await apiFetch(`/api/v1/portfolios/${portfolioId}/holdings/${holdingId}`, { method: 'DELETE' });
}

export async function closeHolding(portfolioId: string, holdingId: string, exit_price: number): Promise<ApiHolding> {
  return apiFetch<ApiHolding>(`/api/v1/portfolios/${portfolioId}/holdings/${holdingId}/close`, {
    method: 'POST', body: JSON.stringify({ exit_price }),
  });
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
  role?: 'user' | 'admin' | 'super_admin';
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

export async function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const token = getStoredToken('access_token');
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/v1/auth/upload-avatar`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed: ${body}`);
  }

  return res.json() as Promise<{ avatar_url: string }>;
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
  return apiFetch<TokenResponse>('/api/v1/auth/google-login', {
    method: 'POST',
    body: JSON.stringify({ token: idToken }),
  });
}

export function logout(): void {
  clearAuthTokens();
}

export function isLoggedIn(): boolean {
  return !!getStoredToken('access_token');
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

export async function fetchBybitFunding(symbol: string): Promise<{ funding_rate: number | null }> {
  return apiFetch(`/api/v1/macro/bybit-funding/${symbol}`);
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
  symbol: string, timeframe = '1h', limit = 200, endTime?: number,
): Promise<OhlcvResponse> {
  const endParam = endTime != null ? `&end_time=${endTime}` : '';
  return apiFetch<OhlcvResponse>(
    `/api/v1/prices/ohlcv/${encodeURIComponent(symbol)}?timeframe=${timeframe}&limit=${limit}${endParam}`,
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
export type UserRole = 'user' | 'admin' | 'super_admin';

export interface AdminUserRow {
  id:              string;
  email:           string;
  full_name:       string | null;
  provider:        string;
  is_active:       boolean;
  is_admin:        boolean;
  role:            UserRole;
  created_at:      string;
  tier:            string;
  sub_status:      string | null;
  sub_period_end:  string | null;
}
export async function fetchAdminStats(): Promise<AdminStats> {
  return apiFetch<AdminStats>('/api/v1/admin/stats');
}

export interface SymbolAnalysisData {
  symbols: Array<{
    symbol: string; name: string; asset_type: string;
    total: number; wins: number; losses: number; breakeven: number; active: number;
    win_rate: number; avg_confidence: number; quality_score: number;
    directions: Record<string, number>;
    htf_types: Record<string, number>;
  }>;
  total_symbols: number;
  locked?: boolean;
}
export async function fetchSymbolAnalysis(): Promise<SymbolAnalysisData> {
  return apiFetch<SymbolAnalysisData>('/api/v1/analytics/symbol-analysis');
}

export interface StrategyLabData {
  by_hour: Array<{ hour: number; label: string; total: number; wins: number; losses: number; win_rate: number; avg_confidence: number }>;
  by_day: Array<{ day: number; label: string; total: number; wins: number; losses: number; win_rate: number; avg_confidence: number }>;
  by_direction: Array<{ direction: string; total: number; wins: number; win_rate: number; avg_confidence: number }>;
  by_risk: Array<{ risk_level: string; total: number; wins: number; win_rate: number }>;
  total_signals: number;
  locked?: boolean;
}
export async function fetchStrategyLab(): Promise<StrategyLabData> {
  return apiFetch<StrategyLabData>('/api/v1/analytics/strategy-lab');
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
  payload: { role?: UserRole; is_active?: boolean; tier?: SubscriptionTier },
): Promise<void> {
  await apiFetch(`/api/v1/admin/users/${user_id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
export async function deleteAdminUser(user_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/users/${user_id}`, { method: 'DELETE' });
}

// ── Admin: signal moderation ──────────────────────────────────────────────

export interface AdminSignalRow {
  id: string;
  symbol: string;
  signal_type: string;
  confidence_score: number;
  timeframe: string;
  is_active: boolean;
  admin_invalidated: boolean;
  generated_at: string;
  outcome: string;
}

export async function fetchAdminSignals(params?: {
  q?: string; only_active?: boolean; min_confidence?: number; max_confidence?: number;
  page?: number; page_size?: number;
}): Promise<{ items: AdminSignalRow[]; total: number; page: number; page_size: number }> {
  const q = new URLSearchParams();
  if (params?.q) q.set('q', params.q);
  if (params?.only_active !== undefined) q.set('only_active', String(params.only_active));
  if (params?.min_confidence !== undefined) q.set('min_confidence', String(params.min_confidence));
  if (params?.max_confidence !== undefined) q.set('max_confidence', String(params.max_confidence));
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch(`/api/v1/admin/signals${qs}`);
}

export async function invalidateAdminSignal(signal_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/signals/${signal_id}/invalidate`, { method: 'POST' });
}

export async function bulkCleanSignals(payload: { min_confidence: number; market?: string }): Promise<{ invalidated_count: number }> {
  return apiFetch(`/api/v1/admin/signals/bulk-clean`, { method: 'POST', body: JSON.stringify(payload) });
}

export async function adminGenerateSignal(symbol: string, timeframe = '1h'): Promise<void> {
  await apiFetch(`/api/v1/admin/signals/generate`, {
    method: 'POST', body: JSON.stringify({ symbol, timeframe }),
  });
}

export async function deleteAdminSignal(signal_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/signals/${signal_id}`, { method: 'DELETE' });
}

export async function bulkDeleteClosedSignals(payload: {
  outcome?: string; signal_type?: string; older_than_days?: number; market?: string;
}): Promise<{ deleted_count: number }> {
  return apiFetch(`/api/v1/admin/signals/bulk-delete-closed`, { method: 'POST', body: JSON.stringify(payload) });
}

// ── Admin: asset management ───────────────────────────────────────────────

export interface AdminAssetRow {
  id: string; symbol: string; name: string; asset_type: string;
  market: string | null; is_active: boolean;
}

export async function fetchAdminAssets(params?: { q?: string; page?: number; page_size?: number }):
  Promise<{ items: AdminAssetRow[]; total: number; page: number; page_size: number }> {
  const q = new URLSearchParams();
  if (params?.q) q.set('q', params.q);
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch(`/api/v1/admin/assets${qs}`);
}

export async function createAdminAsset(payload: { symbol: string; name: string; asset_type: string; market?: string }): Promise<void> {
  await apiFetch(`/api/v1/admin/assets`, { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateAdminAsset(asset_id: string, payload: { name?: string; market?: string; is_active?: boolean }): Promise<void> {
  await apiFetch(`/api/v1/admin/assets/${asset_id}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteAdminAsset(asset_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/assets/${asset_id}`, { method: 'DELETE' });
}

// ── Admin: system & scheduler ─────────────────────────────────────────────

export interface AdminJobStatus {
  label: string; running: boolean; last_run_at: string | null;
  last_status: 'ok' | 'error' | null; last_error: string | null; last_result: any;
}

export async function fetchAdminJobStatus(): Promise<{ jobs: Record<string, AdminJobStatus> }> {
  return apiFetch(`/api/v1/admin/system/jobs`);
}

export async function triggerAdminJob(job_id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/system/jobs/${job_id}/trigger`, { method: 'POST' });
}

// ── Admin: audit log ───────────────────────────────────────────────────────

export interface AdminAuditLogRow {
  id: string; actor_email: string; action: string;
  target_type: string | null; target_id: string | null;
  detail: Record<string, any>; created_at: string;
}

export async function fetchAdminAuditLog(params?: { action?: string; page?: number; page_size?: number }):
  Promise<{ items: AdminAuditLogRow[]; total: number; page: number; page_size: number }> {
  const q = new URLSearchParams();
  if (params?.action) q.set('action', params.action);
  if (params?.page) q.set('page', String(params.page));
  if (params?.page_size) q.set('page_size', String(params.page_size));
  const qs = q.toString() ? `?${q}` : '';
  return apiFetch(`/api/v1/admin/audit-log${qs}`);
}

// ---------------------------------------------------------------------------
// PDF Reports
// ---------------------------------------------------------------------------

/** Download a PDF blob and trigger browser save dialog. */
async function downloadPdf(path: string, filename: string): Promise<void> {
  const token = getStoredToken('access_token');
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
