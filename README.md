# Signal Fusion Engine (SFE)

Personal trading decision-support tool. Fuses sentiment, quantitative, and enrichment signals through a Claude-powered meta-layer into a daily pre-market briefing.

**Status:** Phase 1-5 base live. Earnings engine live as of 2026-04-25: `run-earnings-brief` generates per-ticker pre-earnings context briefs (consensus estimates, 8-quarter beat/miss history, options-implied move via yfinance, multi-tier signal analysis, auto-disclaimer). `log-outcome` tracks predictions vs actuals. `earnings-calendar` shows upcoming reports for the watchlist. Pipeline DRY-refactored (shared `_bootstrap_db`/`_resolve_tickers`). Claude API error handling added to `run-meta` and `run-earnings-brief`. 137 tests passing.

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

## Improvement backlog (2026-04-19 review)

Captured from a whole-project review; not yet scheduled. Use this as the
menu when picking what to zoom in on next. Ordered within each engine by
rough signal-quality impact.

### Sentiment
- Promote FinBERT to default scorer; retire TextBlob after spot-checking a week of rows. Single biggest quality lever.
- Split `sec_filings` weight into `sec_8k` vs `sec_periodic` (8-Ks carry more event signal than 10-K/10-Q front matter). Cheaper than MD&A section parsing.
- Dedup Finnhub + finlight articles before `weighted_rollup` (hash on normalized title + publisher) so wire-service reprints don't double-count.
- Either populate `key_topics` (top TF-IDF tokens across the day's headlines) or remove the field from the schema and prompt.

### Quantitative
- Replace binary-vote `predict_health` with a z-score composite per indicator so magnitude/regime matter (no ML required).
- Pin the GBT label definition now (forward 5d return vs sector? Sharpe over N days?) so accumulated scorecards are trainable later.
- Add SPY-relative return alongside sector-relative; divergence between the two is itself a signal.
- Add a volatility feature (ATR or realized vol) so the meta-layer can weight a 5% move by the name's typical range.

### Enrichment
- Insider summary: weight by net dollar value and insider role (CEO/CFO vs 10%-holder), not just P/S code counts.
- Analyst revisions: weight the latest revision heavier than MoM aggregate; use firm name if exposed.
- Add a post-earnings-drift flag ("earnings N days ago, stock ±X%") to the payload.
- Pull FRED FOMC/CPI macro calendar forward from the deferred list — free, low-effort, meta-layer currently has no macro context.

### Meta layer
- Feed yesterday's briefing (or a tier-change diff) into the prompt so Claude can reference prior calls instead of cold-starting each morning. `BriefingDaily` already persists — cheap add.
- Add a `briefing_outcomes` table for manual post-hoc right/wrong marking. Unblocks threshold tuning and eventually provides GBT labels.
- Broad-market context block (SPY/QQQ/VIX + upcoming FOMC/CPI) — already on the Phase 5 list; worth prioritizing because high-conviction calls on risk-off days should be downgraded.

### Cross-cutting
- `config/sources.yaml` weights are currently guesses and are the most important tuning knob. Backtest weight variants against forward returns once a few weeks of rows accumulate.
- Add a response cache layer on Finnhub fetchers keyed by (ticker, date), mirroring the in-process EDGAR body cache. Helps tests too.

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

### Earnings engine
- [x] Consensus estimates fetcher (Finnhub `/stock/metric` for forward EPS/revenue/analyst count)
- [x] Beat/miss history fetcher (Finnhub `/stock/earnings`, last 8 quarters, surprise % with div-by-zero guard)
- [x] Options-implied move fetcher (yfinance ATM straddle, graceful degradation when chain data unavailable)
- [x] Earnings payload builder (merges new fetchers + existing engine DB rows per ticker)
- [x] Earnings-specific prompt template (`prompts/earnings_briefing.txt`, 9-section structure)
- [x] `EarningsBriefOutcome` schema + repo (upsert on `(ticker, earnings_date)`, tracks predictions vs actuals)
- [x] CLI: `run-earnings-brief --ticker SYM` (auto-detects earnings date from Finnhub, `--earnings-date` override)
- [x] CLI: `log-outcome --ticker SYM --earnings-date ... --predicted-dir bullish --conviction 0.7 [--actual-eps-surp ...] [--outcome correct]`
- [x] CLI: `earnings-calendar` (watchlist tickers reporting in next 14 days, with consensus EPS)
- [x] Auto-disclaimer appended to all earnings briefs
- [x] Claude API error handling in `run-meta` and `run-earnings-brief`
- [x] DRY refactor: `_bootstrap_db()`, `_parse_date()`, `_resolve_tickers()` shared helpers in pipeline.py
- [x] Test suite: 28 earnings tests (beat/miss summarize + edge cases, consensus fetch, options helpers, payload builder with mocked fetchers, outcome repo CRUD + upsert + uniqueness, disclaimer formatting)
- [ ] Insider/analyst windowing (30-day pre-print lookback) — existing data acceptable for week 1
- [ ] Historical comparison anchor in briefs — needs prior outcome data first

### Phase 5 — polish
- [x] FastAPI HTTP layer (`sfe-api` console script): `/health`, `/watchlist`, `/watchlist/snapshot`, `/tickers/{symbol}`, `/tickers/{symbol}/history`, `/briefing/{date}`, `POST /pipeline/{sentiment|quant|enrichment|meta}` (background tasks by default, `?wait=true` for sync); CORS locked to `http://localhost:5173` via `SFE_CORS_ORIGINS`
- [x] `BriefingDaily` table + cache: `run-meta` via API persists Claude output so `GET /briefing/{date}` serves without re-hitting the LLM
- [x] Test suite: 9 API tests (TestClient + in-memory SQLite via StaticPool); total suite now 137 passing
- [x] React + Vite + TypeScript dashboard under `frontend/` (watchlist table, ticker drill-down, briefing view with generate button; talks to `sfe-api` via Vite `/api` proxy to `127.0.0.1:8000`)
- [ ] Backtesting framework, GBT model, deferred enrichment sources (short interest / congressional / options / macro), email/Slack delivery
