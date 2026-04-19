# Signal Fusion Engine (SFE)

Personal trading decision-support tool. Fuses sentiment, quantitative, and enrichment signals through a Claude-powered meta-layer into a daily pre-market briefing.

**Status:** Phase 1 + Phase 2 + Phase 3 starting slices live. Phase 4 meta-synthesis starting slice live as of 2026-04-18 — payload builder queries the three engine tables, Anthropic Claude (`claude-opus-4-7`, adaptive thinking, cached system prompt) synthesizes a markdown briefing printed to stdout via `run-meta`. Phase 5 FastAPI layer live as of 2026-04-19 — `sfe-api` console script exposes read endpoints over the engine tables plus background-task pipeline triggers; briefings cached in `briefing_daily`. React + Vite + TS dashboard scaffolded under `frontend/` (watchlist table, ticker drill-down, briefing view with generate button) also as of 2026-04-19. Email/Slack delivery, short interest / congressional / options flow / FOMC macro events, and the GBT model still deferred within Phase 5.

Source of truth for architecture: `~/Documents/Obsidian Vault/Obsidian Vault/Project Ideas/Signal-Fusion-Tool.md`.

## Setup

```bash
# 1. Install dependencies (core only)
uv sync

# 2. Copy env template and fill in keys as you wire up each source
cp .env.example .env

# 3. Populate the watchlist
$EDITOR config/watchlist.yaml

# 4. Run the CLI
uv run sfe --help
```

### Optional dependency groups

Installed on demand to keep the base environment lean:

```bash
uv sync --group sentiment-ml   # transformers + torch (FinBERT)
uv sync --group quant          # scikit-learn, xgboost, yfinance
uv sync --group llm            # anthropic SDK (meta-layer)
uv sync --group api            # fastapi + uvicorn (Phase 5 HTTP layer)
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Vite dev server on :5173, proxies /api → 127.0.0.1:8000
# Backend must be running in another shell: uv run sfe-api
```

## Layout

```
config/      # watchlist.yaml, sources.yaml
src/
  engines/
    sentiment/     # Phase 1 — news, social, SEC → score → aggregate
    quantitative/  # Phase 2 — OHLCV, technicals, ML health score
    enrichment/    # Phase 3 — insider, options, short, events, ...
  meta/            # Phase 4 — payload builder, Claude client, formatter
  api/             # Phase 5 — FastAPI app, Pydantic schemas, `sfe-api` entry
  delivery/        # email, Slack, Streamlit
  storage/         # SQLAlchemy models + session
  pipeline.py      # CLI entry point
frontend/    # React + Vite + TS dashboard (Phase 5)
tests/
data/        # raw/ + processed/ (gitignored)
notebooks/
```

## Known limitations

- **EDGAR signal quality (Phase 1).** 8-K item codes are expanded to SEC
  English titles (`sec_item_codes.py`) and primary-document bodies are
  fetched, HTML-stripped, and truncated to 50k chars before scoring
  (`sec_fetcher.fetch_filing_body`). Bodies are cached in-process by URL.
  Remaining weakness: the entire front matter of a 10-K/10-Q is scored
  uniformly — risk-factor boilerplate dilutes signal from MD&A. Targeting
  Item 7 (MD&A) specifically would improve this but requires section-anchor
  parsing that varies across filings. Deferred until scores show it matters.

## Phase status

- [x] Phase 0 — skeleton
- [x] Phase 1 — sentiment engine MVP
- [ ] Phase 2 — quantitative engine MVP _(starting slice live; GBT deferred to Phase 5)_
- [ ] Phase 3 — enrichment signals _(starting slice live; short interest / congressional / options / macro deferred to Phase 5)_
- [ ] Phase 4 — meta-synthesis layer _(starting slice live; delivery deferred to Phase 5)_
- [ ] Phase 5 — polish, dashboard, backtesting, delivery, GBT, deferred enrichment _(FastAPI + React dashboard live; backtesting, delivery, GBT, deferred enrichment still pending)_

## Task tracker

### Phase 0 — skeleton
- [x] `pyproject.toml` + `uv` dependency groups (core / dev / sentiment-ml / quant / llm)
- [x] CLI entry point (`sfe` console script, argparse subcommands)
- [x] SQLAlchemy engine + session factory (`src/storage/db.py`)
- [x] `.env.example` aligned to the four chosen Phase-1 sources
- [x] `config/sources.yaml` weights for `sec_filings`, `news_finnhub`, `news_finlight`, `social_reddit`
- [x] `src/config.py` YAML loaders (`load_sentiment_weights`, `load_watchlist`)
- [x] `config/watchlist.yaml` populated (10–15 tickers across 2–3 sectors)

### Phase 1 — sentiment engine MVP
**Schema & scoring**
- [x] `SentimentDaily` schema with `(ticker, as_of)` uniqueness + JSON columns
- [x] TextBlob scorer (`score_text`), neutral on empty input
- [x] `weighted_rollup` pure aggregation (per-source averaging → weighted blend; drops unconfigured sources)

**Fetchers**
- [x] Finnhub `news_fetcher` (`/company-news`, configurable lookback, env-keyed, raises clearly without `FINNHUB_KEY`)
- [x] SEC EDGAR `sec_fetcher` (CIK lookup via `company_tickers.json`, 10-K/10-Q/8-K filter, 30-day default window, requires `SEC_EDGAR_USER_AGENT`)
- [x] finlight news fetcher (`POST /v2/articles`, `X-API-KEY` header, TextBlob-scored; native `sentiment` field left as future upgrade)
- [ ] ~~Reddit PRAW fetcher~~ _(deprioritized: TextBlob mangles Reddit finance-speak; revisit only after FinBERT upgrade, or build as a standalone project that pipes into SFE)_

**Orchestration & persistence**
- [x] `aggregate(ticker, on_date)` — combines Finnhub + EDGAR with per-source failure isolation
- [x] `upsert_sentiment_daily` repo helper (insert-or-update on `(ticker, as_of)`)
- [x] CLI: `run-sentiment --ticker SYM --date YYYY-MM-DD` creates DB on demand and persists rows
- [x] Test suite (52 passing): scorer, rollup, item-code expansion, HTML-to-text + body-fetch cache, both fetchers, end-to-end aggregate (incl. failure isolation + body-feed verification), upsert

**Open work**
- [x] EDGAR signal quality: 8-K item-code → English map wired into aggregator
- [x] EDGAR signal quality: filing-body fetch + HTML strip + 50k truncation + per-URL cache
- [ ] EDGAR signal quality: MD&A section targeting for 10-K/10-Q (see Known limitations)
- [x] `sentiment_direction` + `sentiment_delta_7d` computed from history (pipeline anchors against the closest prior row within a 7-day window)
- [x] Watchlist seed + multi-ticker run path exercised live
- [x] FinBERT upgrade path (`sentiment-ml` dep group) — `SENTIMENT_SCORER=finbert` switches scorer; TextBlob remains default

### Phase 2 — quantitative engine MVP
- [x] yfinance OHLCV fetcher (`price_fetcher.fetch_ohlcv`, 300-day default lookback)
- [x] Technicals (`compute_indicators`): RSI-14, SMA-50/200 position, MACD signal, 1/5/20-day returns, volume-vs-20d-avg
- [x] Sector-relative 5-day return vs SPDR ETF (mapping from `watchlist.yaml` sector field → XLK/XLC/...); degrades to null on ETF fetch failure
- [x] Rule-based `predict_health` (strong / neutral / weak) — placeholder until GBT trains
- [x] `QuantDaily` schema with `(ticker, as_of)` uniqueness + `upsert_quant_daily` repo helper
- [x] CLI: `run-quant --ticker SYM --date YYYY-MM-DD` (watchlist run when `--ticker` omitted)
- [x] Test suite: technicals (empty/short/rising/falling/volume/sort), rule-based model, aggregator (happy + degraded + no-data + unknown-sector), repo upsert
- [ ] GBT technical-health model (xgboost) — train once enough daily scorecards accumulate

### Phase 3 — enrichment signals
- [x] Insider trades via Finnhub `/stock/insider-transactions` — P/S codes drive net sentiment (bullish/bearish/neutral), other codes listed but not counted
- [x] Earnings calendar via Finnhub `/calendar/earnings` — soonest upcoming + `days_until`
- [x] Analyst revisions via Finnhub `/stock/recommendation` — month-over-month bull-score delta → upgrade/downgrade/stable
- [x] `EnrichmentDaily` schema + `upsert_enrichment_daily` repo helper
- [x] CLI: `run-enrichment --ticker SYM --date YYYY-MM-DD` (watchlist run when `--ticker` omitted)
- [x] Test suite: per-source summarizers (insider/earnings/analyst) + aggregator (happy / full failure / partial failure) + repo upsert
- [ ] Short interest (FINRA bimonthly file) — Phase 5
- [ ] Congressional trades (Quiver Quant free tier, 45-day lag) — Phase 5
- [ ] Options flow (Unusual Whales, paid) — Phase 5
- [ ] FOMC/CPI macro calendar (hardcoded near-term or FRED) — Phase 5

### Phase 4 — meta-synthesis layer
- [x] `payload_builder.build_payload` — pulls latest `SentimentDaily` + `QuantDaily` + `EnrichmentDaily` per watchlist ticker (rows with `as_of <= on_date`; null when missing)
- [x] `prompts/daily_briefing.txt` — static system prompt (per-tier signal thresholds, convergence/divergence rules, `[high|medium|low]` conviction tags, thin-data escape hatch, output markdown structure), cached via `cache_control: ephemeral`
- [x] `llm_client.generate_briefing` — Anthropic SDK, `claude-opus-4-7`, adaptive thinking, streamed via `messages.stream` + `get_final_message`, `max_tokens=16000`
- [x] `formatter.format_briefing` — strip + prepend header if model omitted it
- [x] CLI: `run-meta --ticker SYM --date YYYY-MM-DD` (watchlist run when `--ticker` omitted); prints briefing to stdout
- [x] Test suite (11 meta tests): payload builder (missing data, all-three-present, latest-prior, future excluded) + formatter + smoke imports
- [ ] Email/Slack delivery — Phase 5
- [ ] Broad market context block (SPY/QQQ/VIX, upcoming FOMC/CPI) — Phase 5

### Phase 5 — polish
- [x] FastAPI HTTP layer (`sfe-api` console script): `/health`, `/watchlist`, `/watchlist/snapshot`, `/tickers/{symbol}`, `/tickers/{symbol}/history`, `/briefing/{date}`, `POST /pipeline/{sentiment|quant|enrichment|meta}` (background tasks by default, `?wait=true` for sync); CORS locked to `http://localhost:5173` via `SFE_CORS_ORIGINS`
- [x] `BriefingDaily` table + cache: `run-meta` via API persists Claude output so `GET /briefing/{date}` serves without re-hitting the LLM
- [x] Test suite: 9 API tests (TestClient + in-memory SQLite via StaticPool); total suite now 108 passing
- [x] React + Vite + TypeScript dashboard under `frontend/` (watchlist table, ticker drill-down, briefing view with generate button; talks to `sfe-api` via Vite `/api` proxy to `127.0.0.1:8000`)
- [ ] Backtesting framework, GBT model, deferred enrichment sources (short interest / congressional / options / macro), email/Slack delivery
