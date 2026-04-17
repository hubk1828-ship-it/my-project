// API Types matching backend schemas

export interface User {
  id: string;
  username: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Wallet {
  id: string;
  exchange: string;
  label: string | null;
  is_active: boolean;
  created_at: string;
}

export interface BalanceItem {
  asset: string;
  free_balance: number;
  locked_balance: number;
  usd_value: number | null;
}

export interface WalletBalance {
  wallet_id: string;
  exchange: string;
  total_usd: number;
  assets: BalanceItem[];
}

export interface Analysis {
  id: string;
  symbol: string;
  timeframe: string;
  news_source: string | null;
  news_title: string | null;
  is_momentum_real: boolean | null;
  price_confirmed_news: boolean | null;
  decision: "buy" | "sell" | "no_opportunity";
  confidence_score: number | null;
  reasoning: string;
  technical_indicators: Record<string, any> | null;
  created_at: string;
}

export interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: string;
  quantity: number;
  price: number;
  total_value: number;
  fee: number;
  status: string;
  executed_by: "bot" | "manual";
  created_at: string;
  executed_at: string | null;
}

export interface BotSettings {
  is_auto_trade_enabled: boolean;
  is_admin_approved: boolean;
  max_trades_per_day: number;
  max_trade_amount: number;
  max_portfolio_percentage: number;
  max_daily_loss: number;
  min_loss_limit: number;
  max_loss_limit: number;
  updated_at: string;
}

export interface NotificationPrefs {
  telegram_enabled: boolean;
  telegram_chat_id: string | null;
  email_enabled: boolean;
  web_enabled: boolean;
  notify_opportunities: boolean;
  notify_trades: boolean;
  notify_daily_summary: boolean;
}

export interface Notification {
  id: string;
  type: string;
  category: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

// Market types
export interface NewsSource {
  id: string;
  name: string;
  url: string | null;
  is_active: boolean;
  is_suggested: boolean;
  created_at: string;
}

export interface SupportedSymbol {
  id: string;
  symbol: string;
  base_asset: string;
  quote_asset: string;
  is_default: boolean;
  is_active: boolean;
  min_trade_amount: number | null;
  created_at: string;
}

export interface SuggestedCoin {
  symbol: string;
  name: string;
  current_price: number;
  market_cap: number;
  price_change_24h: number;
  volume_24h: number;
}

// Live data types
export interface LiveCoin {
  symbol: string;
  base_asset: string;
  price: number;
  change_24h: number;
  volume_24h: number;
  high_24h: number;
  low_24h: number;
  analysis: {
    decision: string;
    confidence: number;
    reasoning: string;
    technical_indicators: Record<string, any>;
    created_at: string | null;
  } | null;
}

export interface LiveUpdate {
  type: "live_update";
  timestamp: number;
  coins: LiveCoin[];
}

export interface TradeEvent {
  type: "trade_event";
  symbol: string;
  side: string;
  success: boolean;
  price: number;
  quantity: number;
  total_value: number;
}

// SMC types
export interface SMCStructureBreak {
  type: "BOS" | "CHoCH";
  bias: "bullish" | "bearish";
  level: number;
  index: number;
}

export interface SMCOrderBlock {
  high: number;
  low: number;
  index: number;
  bias: "bullish" | "bearish";
  mitigated: boolean;
}

export interface SMCFairValueGap {
  top: number;
  bottom: number;
  index: number;
  bias: "bullish" | "bearish";
  mitigated: boolean;
}

export interface SMCEqualLevel {
  price: number;
  type: "EQH" | "EQL";
  index1: number;
  index2: number;
}

export interface SMCData {
  trend: "bullish" | "bearish" | "neutral";
  internal_trend: "bullish" | "bearish" | "neutral";
  swing_points: { price: number; index: number; type: string }[];
  structure_breaks: SMCStructureBreak[];
  order_blocks: SMCOrderBlock[];
  fair_value_gaps: SMCFairValueGap[];
  equal_levels: SMCEqualLevel[];
  strong_high: number | null;
  weak_high: number | null;
  strong_low: number | null;
  weak_low: number | null;
  premium_zone: [number, number] | null;
  discount_zone: [number, number] | null;
  equilibrium: number | null;
}
