# Signal Fusion Engine (SFE)

Fuses sentiment, quantitative, and enrichment signals through a Claude-powered meta-layer to produce pre-earnings context briefs and daily market briefings. One command, 60 seconds, structured output with a directional read.

```
$ uv run sfe run-earnings-brief --ticker NVDA

## Earnings Brief — NVDA — 2026-05-28

### Setup
NVIDIA reports Q1 FY2027 on May 28. The stock is trading at $950, up 12% over
the past 20 days. Sentiment is positive (0.52) with bullish insider activity...

### Consensus
Street expects EPS of $0.88 (32 analysts). Revenue estimate: $43.2B...
```

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), a free [Finnhub API key](https://finnhub.io/register), and an [Anthropic API key](https://console.anthropic.com/).

```bash
# 1. Clone and install
git clone https://github.com/samwise-k/signal-fusion-engine.git
cd signal-fusion-engine
uv sync
uv sync --group quant    # yfinance (options-implied move)
uv sync --group llm      # anthropic SDK (Claude briefings)

# 2. Configure API keys
cp .env.example .env
# Edit .env and set at minimum:
#   FINNHUB_KEY=your_finnhub_key
#   ANTHROPIC_API_KEY=your_anthropic_key
#   SEC_EDGAR_USER_AGENT=sfe/0.1 (your-email@example.com)

# 3. Check what's reporting soon
uv run sfe earnings-calendar

# 4. Generate an earnings brief
uv run sfe run-earnings-brief --ticker MSFT

# 5. For a richer brief, run the signal engines first
uv run sfe run-sentiment --ticker MSFT
uv run sfe run-quant --ticker MSFT
uv run sfe run-enrichment --ticker MSFT
uv run sfe run-earnings-brief --ticker MSFT
```

## What it does

SFE pulls data from multiple free sources, scores it, and sends a structured payload to Claude for synthesis:

```
Finnhub (news, insider trades, analyst revisions, earnings calendar, consensus)
EDGAR (SEC filings: 8-K, 10-K, 10-Q)                                          → Sentiment
finlight (financial news)                                                         + Quant
yfinance (OHLCV, technicals, options chains)                                      + Enrichment
                                                                                     ↓
                                                                              Claude meta-layer
                                                                                     ↓
                                                                            Structured briefing
```

**Earnings briefs** are the primary workflow: per-ticker, pre-earnings context with consensus estimates, 8-quarter beat/miss history, options-implied move, multi-tier signal analysis, and a directional read with conviction tag.

**Daily briefings** cover the full watchlist: cross-ticker signal convergence/divergence ranking with conviction tags.

## CLI commands

| Command | What it does |
|---------|-------------|
| `sfe earnings-calendar` | Show watchlist tickers reporting in the next 14 days |
| `sfe run-earnings-brief --ticker SYM` | Generate a per-ticker pre-earnings context brief |
| `sfe log-outcome --ticker SYM ...` | Record prediction vs actual outcome after earnings |
| `sfe run-sentiment [--ticker SYM]` | Run sentiment engine (Finnhub + EDGAR + finlight) |
| `sfe run-quant [--ticker SYM]` | Run quantitative engine (technicals, sector-relative) |
| `sfe run-enrichment [--ticker SYM]` | Run enrichment engine (insider, analyst, calendar) |
| `sfe run-meta [--ticker SYM]` | Generate a daily watchlist briefing via Claude |

All commands accept `--date YYYY-MM-DD` (defaults to today). Commands without `--ticker` run against the full watchlist in `config/watchlist.yaml`.

### Tracking outcomes

After a company reports, log how the brief's call did:

```bash
uv run sfe log-outcome \
  --ticker MSFT \
  --earnings-date 2026-04-29 \
  --predicted-dir bullish \
  --conviction 0.7 \
  --actual-eps-surp 4.1 \
  --stock-move-1d 3.2 \
  --outcome correct
```

Next time you run `run-earnings-brief` for that ticker, Claude sees the prior call and can reference the track record.

## API keys

| Key | Required for | Free tier |
|-----|-------------|-----------|
| `FINNHUB_KEY` | Sentiment, enrichment, earnings | Yes (60 calls/min) |
| `ANTHROPIC_API_KEY` | `run-meta`, `run-earnings-brief` | Pay-per-use |
| `SEC_EDGAR_USER_AGENT` | SEC filing fetches | Keyless (requires email in UA) |
| `FINLIGHT_KEY` | Additional news sentiment | Yes |

Set these in `.env` (gitignored). Only `FINNHUB_KEY` and `ANTHROPIC_API_KEY` are needed to run earnings briefs.

## Setup (detailed)

```bash
# Core only (sentiment + storage + CLI)
uv sync

# Optional dependency groups, installed on demand:
uv sync --group sentiment-ml   # transformers + torch (FinBERT scorer)
uv sync --group quant          # scikit-learn, xgboost, yfinance
uv sync --group llm            # anthropic SDK (Claude briefings)
uv sync --group api            # fastapi + uvicorn (HTTP layer)
```

### Watchlist

Edit `config/watchlist.yaml` to set your tickers:

```yaml
tickers:
  - ticker: NVDA
    sector: technology
  - ticker: MSFT
    sector: technology
  - ticker: JPM
    sector: financials
```

The `sector` field maps to SPDR ETFs for sector-relative returns (XLK, XLF, etc.).

### Frontend (optional)

```bash
cd frontend
npm install
npm run dev       # Vite dev server on :5173, proxies /api to 127.0.0.1:8000
# Backend must be running in another shell: uv run sfe-api
```

### Tests

```bash
uv run pytest               # 137 tests, ~4 seconds
```

## Layout

```
config/      # watchlist.yaml, sources.yaml
src/
  engines/
    sentiment/     # news, social, SEC → score → aggregate
    quantitative/  # OHLCV, technicals, sector-relative, health score
    enrichment/    # insider trades, analyst revisions, earnings calendar
    earnings/      # consensus, beat/miss, options-implied, earnings payload
  meta/            # payload builder, Claude client, formatter, prompt templates
  api/             # FastAPI app, Pydantic schemas, `sfe-api` entry
  delivery/        # email, Slack (not yet wired)
  storage/         # SQLAlchemy models, repos, session
  pipeline.py      # CLI entry point (all `sfe` commands)
frontend/    # React + Vite + TS dashboard
tests/       # 137 tests
data/        # raw/ + processed/ (gitignored)
```

## Disclaimer

This is a personal research tool, not a financial product. It does not provide investment advice. The author may hold positions in securities discussed. Past framework outputs do not predict future results. See the auto-appended disclaimer on every earnings brief for the full text.

## Known limitations

- **EDGAR signal quality.** 10-K/10-Q filings are scored uniformly. Risk-factor boilerplate dilutes signal from MD&A sections. Targeting Item 7 specifically would improve this but requires section-anchor parsing that varies across filings.
- **Options data coverage.** yfinance options chain data is inconsistent across tickers. Some names return no expirations at all. The earnings brief gracefully omits the implied-move section when this happens.
- **Sentiment scorer.** FinBERT is the default for finance-domain accuracy. Requires `uv sync --group sentiment-ml` (torch + transformers). Falls back to TextBlob with a warning if those deps are missing. Force TextBlob with `SENTIMENT_SCORER=textblob` for lightweight dev/CI runs.
