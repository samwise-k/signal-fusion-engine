# Signal Fusion Engine (SFE)

Personal trading decision-support tool. Fuses sentiment, quantitative, and enrichment signals through a Claude-powered meta-layer into a daily pre-market briefing.

**Status:** Phase 1 feature-complete (bar deferred MD&A targeting) — Finnhub + finlight + SEC EDGAR wired end-to-end through the `run-sentiment` CLI into SQLite, 15-ticker S&P megacap watchlist seeded, FinBERT backend available via `SENTIMENT_SCORER=finbert` (TextBlob is the default).

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
  delivery/        # email, Slack, Streamlit
  storage/         # SQLAlchemy models + session
  pipeline.py      # CLI entry point
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
- [ ] Phase 1 — sentiment engine MVP _(in progress)_
- [ ] Phase 2 — quantitative engine MVP
- [ ] Phase 3 — enrichment signals
- [ ] Phase 4 — meta-synthesis layer
- [ ] Phase 5 — polish, dashboard, backtesting

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

### Phases 2–5
- [ ] Phase 2 — quantitative engine (yfinance, technicals, ML health score)
- [ ] Phase 3 — enrichment signals (insider trades, earnings calendar, short interest, FOMC/CPI dates)
- [ ] Phase 4 — meta-synthesis layer (payload builder, Claude API, briefing formatter, delivery)
- [ ] Phase 5 — polish, Streamlit dashboard, backtesting framework
