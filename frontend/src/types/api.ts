export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  user_id: string;
  token_type: string;
}

export interface UserPreferences {
  alert_threshold: number;
  alert_enabled: boolean;
  bankroll: number;
  kelly_fraction: number;
  max_bet_pct: number;
  max_total_exposure: number;
  min_bet_size: number;
  whale_enabled: boolean;
  whale_min_trade_size: number;
  whale_extra_wallets: WalletEntry[];
}

export interface WalletEntry {
  address: string;
  label: string;
}

export interface Alert {
  id: string;
  debate_result_id: string | null;
  cycle_id: string;
  market_id: string;
  market_question: string;
  polymarket_probability: number;
  ai_probability: number;
  divergence: number;
  recommended_side: "YES" | "NO";
  bet_amount: number | null;
  sizing_details: SizingDetails | null;
  whale_signals: WhaleSignal[];
  notified: boolean;
  created_at: string;
}

export interface SizingDetails {
  kelly_raw: number;
  kelly_final: number;
  bet_amount: number;
  [key: string]: unknown;
}

export interface AlertStats {
  total_alerts: number;
  avg_divergence: number | null;
  total_bet_amount: number | null;
}

export interface Market {
  id: string;
  market_id: string;
  cycle_id: string;
  market_question: string;
  market_data: MarketData;
  consensus_probability: number;
  polymarket_price: number;
  created_at: string;
}

export interface MarketData {
  id: string;
  question: string;
  description: string;
  outcomes: string[];
  tokens: TokenInfo[];
}

export interface TokenInfo {
  token_id: string;
  outcome: string;
  price: number;
}

export interface DebateDetail {
  id: string;
  cycle_id: string;
  market_id: string;
  market_question: string;
  market_data: MarketData;
  opinions: AgentOpinion[];
  consensus_probability: number;
  synthesis_reasoning: string | null;
  polymarket_price: number;
  news_articles: NewsArticle[];
  created_at: string;
}

export interface AgentOpinion {
  agent_name: string;
  probability: number;
  confidence: number;
  reasoning: string;
}

export interface NewsArticle {
  title: string;
  url: string;
  source: string;
  published: string;
}

export interface WhaleSignal {
  wallet: string;
  side: string;
  size: number;
  label?: string;
}

export interface WhaleConfig {
  whale_enabled: boolean;
  whale_min_trade_size: number;
  whale_extra_wallets: WalletEntry[];
}

export interface WhaleLeaderboardEntry {
  wallet_address: string;
  wallet_label: string | null;
  wallet_stats: {
    roi: number;
    win_rate: number;
    total_volume: number;
    theme_expertise: string[];
    [key: string]: unknown;
  };
  new_trades: WhaleTrade[];
}

export interface WhaleTrade {
  market_id: string;
  side: string;
  size: number;
  timestamp: string;
}

export interface ApiKey {
  id: string;
  key_prefix: string;
  label: string;
  is_active: boolean;
  created_at: string;
  last_used: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  raw_key: string;
}

export interface HealthStatus {
  status: string;
  database: string;
  redis: string;
}
