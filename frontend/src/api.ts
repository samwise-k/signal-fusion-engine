import type {
  BriefingView,
  PipelineRunResponse,
  TickerHistory,
  TickerSnapshot,
  WatchlistEntry,
  WatchlistSnapshot,
} from "./types";

const BASE = import.meta.env.VITE_SFE_API_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  watchlist: () => request<WatchlistEntry[]>("/watchlist"),

  watchlistSnapshot: (date?: string) =>
    request<WatchlistSnapshot>(
      `/watchlist/snapshot${date ? `?date=${date}` : ""}`,
    ),

  tickerDetail: (symbol: string, date?: string) =>
    request<TickerSnapshot>(
      `/tickers/${encodeURIComponent(symbol)}${date ? `?date=${date}` : ""}`,
    ),

  tickerHistory: (symbol: string, limit = 30) =>
    request<TickerHistory>(
      `/tickers/${encodeURIComponent(symbol)}/history?limit=${limit}`,
    ),

  briefing: (date: string) =>
    request<BriefingView>(`/briefing/${date}`),

  runPipeline: (
    engine: "sentiment" | "quant" | "enrichment" | "meta",
    opts: { ticker?: string; date?: string; wait?: boolean } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.ticker) params.set("ticker", opts.ticker);
    if (opts.date) params.set("date", opts.date);
    if (opts.wait) params.set("wait", "true");
    const qs = params.toString();
    return request<PipelineRunResponse>(
      `/pipeline/${engine}${qs ? `?${qs}` : ""}`,
      { method: "POST" },
    );
  },
};
