export interface WatchlistEntry {
  ticker: string;
  sector: string | null;
}

export interface SentimentView {
  as_of: string;
  sentiment_score: number;
  sentiment_direction: string;
  sentiment_delta_7d: number | null;
  source_breakdown: Record<string, unknown>;
  key_topics: string[];
  notable_headlines: Array<Record<string, unknown>>;
}

export interface QuantView {
  as_of: string;
  close: number | null;
  change_1d: number | null;
  change_5d: number | null;
  change_20d: number | null;
  rsi_14: number | null;
  above_50sma: boolean | null;
  above_200sma: boolean | null;
  macd_signal: string | null;
  volume_vs_20d_avg: number | null;
  sector_etf: string | null;
  relative_return_5d: number | null;
  health_score: string;
}

export interface EnrichmentView {
  as_of: string;
  insider_trades: Record<string, unknown>;
  next_earnings: Record<string, unknown> | null;
  upcoming_events: Array<Record<string, unknown>>;
  analyst_activity: Record<string, unknown>;
}

export interface TickerSnapshot {
  ticker: string;
  sector: string | null;
  sentiment: SentimentView | null;
  quantitative: QuantView | null;
  enrichment: EnrichmentView | null;
}

export interface WatchlistSnapshot {
  as_of: string;
  entries: TickerSnapshot[];
}

export interface BriefingView {
  as_of: string;
  tickers: string[];
  markdown: string;
  model: string;
  created_at: string;
}

export interface PipelineRunResponse {
  status: string;
  command: string;
  tickers: string[];
  as_of: string;
  detail: string | null;
}

export interface TickerHistoryPoint {
  as_of: string;
  score?: number;
  direction?: string;
  close?: number | null;
  change_1d?: number | null;
  rsi_14?: number | null;
  health_score?: string;
}

export interface TickerHistory {
  sentiment: TickerHistoryPoint[];
  quant: TickerHistoryPoint[];
}
