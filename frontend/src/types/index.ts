// ============================================
// TradeMinds AI - TypeScript Type Definitions
// ============================================

export type SignalType = 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
export type AssetType = 'crypto' | 'stock' | 'forex' | 'futures';
export type TimeFrame = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w';
export type RiskLevel = 'low' | 'medium' | 'high' | 'very_high';
export type Language = 'tr' | 'en';

export interface Asset {
  id: string;
  symbol: string;
  name: string;
  asset_type: AssetType;
  market: string;
  logo_url?: string;
  current_price?: number;
  price_change_24h?: number;
  price_change_percentage_24h?: number;
  market_cap?: number;
  volume_24h?: number;
}

export interface Signal {
  id: string;
  asset: Asset;
  signal_type: SignalType;
  confidence_score: number;
  probability_score: number;
  risk_score: number;
  risk_level: RiskLevel;
  direction: 'bullish' | 'bearish' | 'neutral';
  entry_zone: { low: number; high: number };
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  invalidation_conditions: string;
  explanation: string;
  engines: EngineResult[];
  timeframe: TimeFrame;
  generated_at: string;
  is_active: boolean;
}

export interface EngineResult {
  engine_name: string;
  score: number;
  bias: 'strong_bullish' | 'bullish' | 'neutral' | 'bearish' | 'strong_bearish';
  confidence: number;
  key_findings: string[];
  warnings: string[];
}

export interface SignalPerformance {
  id: string;
  signal_id: string;
  outcome: 'win' | 'loss' | 'breakeven' | 'active' | 'expired';
  actual_return: number;
  max_drawdown: number;
  hit_tp1: boolean;
  hit_tp2: boolean;
  hit_tp3: boolean;
  is_expired?: boolean;
}

export interface Watchlist {
  id: string;
  name: string;
  assets: Asset[];
  created_at: string;
}

export interface SweepEvent {
  direction: 'bullish' | 'bearish';
  sweep_price: number;
  reversal_price: number;
  sweep_index: number;
  reversal_index: number;
  detail: string;
  volume_confirmed: boolean;
  volume_ratio: number;
}

export interface Alert {
  id: string;
  asset: Asset;
  alert_type: 'price' | 'signal' | 'custom';
  conditions: Record<string, unknown>;
  is_active: boolean;
  triggered_at?: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string;
  language: Language;
  preferences: Record<string, unknown>;
}

export interface PlatformStats {
  total_signals: number;
  win_rate: number;
  avg_return: number;
  active_signals: number;
  total_assets_tracked: number;
}

export interface TickerItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

export interface NavItem {
  id: string;
  labelKey: string;
  icon: string;
  href: string;
  badge?: number;
}

export interface ChartDataPoint {
  timestamp: number;
  value: number;
  label?: string;
}

export interface PortfolioAsset {
  asset: Asset;
  quantity: number;
  avg_entry_price: number;
  current_value: number;
  pnl: number;
  pnl_percentage: number;
  allocation_percentage: number;
}

export interface Portfolio {
  id: string;
  name: string;
  total_value: number;
  total_pnl: number;
  total_pnl_percentage: number;
  assets: PortfolioAsset[];
  created_at: string;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'signal' | 'alert' | 'system' | 'achievement';
  is_read: boolean;
  created_at: string;
  action_url?: string;
}

export interface MarketOverview {
  asset: Asset;
  signal?: SignalType;
  trend: 'up' | 'down' | 'sideways';
  volatility: 'low' | 'medium' | 'high';
  volume_change: number;
  dominance?: number;
}
