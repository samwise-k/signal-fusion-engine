# Signal Fusion Engine (SFE)

Agentic portfolio management experiment. Sentiment, quantitative, and enrichment engines feed a Claude-powered agent that autonomously manages a simulated portfolio — making allocation decisions, sizing positions, and reacting to new signals daily.

**Research question:** Can an LLM agent, given structured market signals and full discretion over a simulated book, manage a portfolio at a level of competence comparable to a human?

```
$ uv run sfe run-agent

[agent] Reviewing pre-market signals for 2026-05-02...
[agent] Opening position: NVDA long 5% of portfolio @ $950 — sentiment 0.52,
        bullish insider activity, earnings catalyst May 28
[agent] Trimming JPM from 8% → 4% — quant health deteriorating, sector-relative
        underperformance
[agent] Portfolio: 12 positions, $98,420 equity, +1.8% since inception
```

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), a free [Finnhub API key](https://finnhub.io/register), and an [Anthropic API key](https://console.anthropic.com/).

```bash
# 1. Clone and install
git clone https://github.com/samwise-k/signal-fusion-engine.git
cd signal-fusion-engine
uv sync
uv sync --group quant       # yfinance (options-implied move)
uv sync --group llm         # anthropic SDK (Claude agent)
uv sync --group dashboard   # streamlit + plotly (agent dashboard)

# 2. Configure API keys
cp .env.example .env
# Edit .env and set at minimum:
#   FINNHUB_KEY=your_finnhub_key
#   ANTHROPIC_API_KEY=your_anthropic_key
#   SEC_EDGAR_USER_AGENT=sfe/0.1 (your-email@example.com)

# 3. Run all signal engines for the watchlist
uv run sfe run-signals

# 4. Let the agent manage the portfolio
uv run sfe run-agent

# 5. View the dashboard
uv run sfe-dashboard
```

## What it does

SFE pulls data from multiple free sources, scores it, and hands a structured payload to a Claude agent that manages a simulated portfolio:

```
Finnhub (news, insider trades, analyst revisions, earnings calendar, consensus)
EDGAR (SEC filings: 8-K, 10-K, 10-Q)                                          → Sentiment
finlight (financial news)                                                         + Quant
yfinance (OHLCV, technicals, options chains)                                      + Enrichment
                                                                                     ↓
                                                                            Claude agent harness
                                                                              (agentic tool loop)
                                                                                     ↓
                                                                          Simulated portfolio mgmt
                                                                         (positions, P&L, decisions)
```

**Agentic portfolio management** is the primary workflow. Each day (pre-market), the agent:
1. Reads the latest engine outputs for every watchlist ticker
2. Reviews current portfolio state (positions, cash, P&L)
3. Makes autonomous allocation decisions — open, close, resize positions
4. Logs its reasoning for every trade decision

The agent has near-full discretion. There are minimal guardrails — the experiment tests whether Claude can manage a book competently, not whether it can follow rules.

**Earnings briefs** remain available as a secondary workflow for per-ticker, pre-earnings context.

## CLI commands

### Agent (primary workflow)

| Command | What it does |
|---------|-------------|
| `sfe run-agent` | Run the agent — reviews signals, makes portfolio decisions |
| `sfe run-signals` | Run all 3 engines for the full watchlist (no Claude call) |
| `sfe-dashboard` | Launch the Streamlit portfolio dashboard |

`run-agent` accepts `--date`, `--model` (default: claude-sonnet-4-6), `--portfolio` (default: default), and `--starting-equity` (default: 100000).

### Engines

| Command | What it does |
|---------|-------------|
| `sfe run-sentiment [--ticker SYM]` | Run sentiment engine (Finnhub + EDGAR + finlight) |
| `sfe run-quant [--ticker SYM]` | Run quantitative engine (technicals, sector-relative) |
| `sfe run-enrichment [--ticker SYM]` | Run enrichment engine (insider, analyst, calendar) |

### Earnings briefs (secondary)

| Command | What it does |
|---------|-------------|
| `sfe earnings-calendar` | Show watchlist tickers reporting in the next 14 days |
| `sfe run-earnings-brief --ticker SYM` | Generate a per-ticker pre-earnings context brief |
| `sfe run-meta [--ticker SYM]` | Generate a daily watchlist briefing via Claude |

All commands accept `--date YYYY-MM-DD` (defaults to today). Commands without `--ticker` run against the full watchlist in `config/watchlist.yaml`.

## API keys

| Key | Required for | Free tier |
|-----|-------------|-----------|
| `FINNHUB_KEY` | Sentiment, enrichment, earnings | Yes (60 calls/min) |
| `ANTHROPIC_API_KEY` | `run-agent`, `run-meta`, `run-earnings-brief` | Pay-per-use |
| `SEC_EDGAR_USER_AGENT` | SEC filing fetches | Keyless (requires email in UA) |
| `FINLIGHT_KEY` | Additional news sentiment | Yes |

Set these in `.env` (gitignored). `FINNHUB_KEY` and `ANTHROPIC_API_KEY` are required.

## Setup (detailed)

```bash
# Core only (sentiment + storage + CLI)
uv sync

# Optional dependency groups, installed on demand:
uv sync --group sentiment-ml   # transformers + torch (FinBERT scorer)
uv sync --group quant          # scikit-learn, xgboost, yfinance
uv sync --group llm            # anthropic SDK (Claude agent + briefings)
uv sync --group dashboard      # streamlit + plotly (agent dashboard)
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
uv run pytest               # 199 tests, ~4 seconds
```

## Layout

```
config/      # watchlist.yaml, sources.yaml
src/
  agent/           # agentic harness, tools, system prompt, Streamlit dashboard
  engines/
    sentiment/     # news, SEC → score → aggregate
    quantitative/  # OHLCV, technicals, sector-relative, health score
    enrichment/    # insider trades, analyst revisions, earnings calendar
    earnings/      # consensus, beat/miss, options-implied, earnings payload
  meta/            # payload builder, Claude client, formatter, prompt templates
  api/             # FastAPI app, Pydantic schemas, `sfe-api` entry
  storage/         # SQLAlchemy models, repos, session (portfolio, positions, trades)
  pipeline.py      # CLI entry point (all `sfe` commands)
frontend/    # React + Vite + TS dashboard (secondary)
tests/       # 199 tests
data/        # raw/ + processed/ (gitignored)
```

## Disclaimer

This is a personal research tool, not a financial product. It does not provide investment advice. The author may hold positions in securities discussed. Past framework outputs do not predict future results. See the auto-appended disclaimer on every earnings brief for the full text.

## Known limitations

- **EDGAR signal quality.** 10-K/10-Q filings are scored uniformly. Risk-factor boilerplate dilutes signal from MD&A sections. Targeting Item 7 specifically would improve this but requires section-anchor parsing that varies across filings.
- **Options data coverage.** yfinance options chain data is inconsistent across tickers. Some names return no expirations at all. The earnings brief gracefully omits the implied-move section when this happens.
- **Sentiment scorer.** FinBERT is the default for finance-domain accuracy. Requires `uv sync --group sentiment-ml` (torch + transformers). Falls back to TextBlob with a warning if those deps are missing. Force TextBlob with `SENTIMENT_SCORER=textblob` for lightweight dev/CI runs.
