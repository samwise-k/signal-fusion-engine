# SFE — Deferred Work

Tracked items from /plan-ceo-review on 2026-04-24.

---

## P0 — Agentic Portfolio Management Experiment

Pivot from signal experiment (2026-05-02). The engines stay; the meta-layer becomes an autonomous agent managing a simulated portfolio.

**Research question:** Can an LLM agent, given structured market signals and full discretion over a simulated book, manage a portfolio at a level of competence comparable to a human?

### Architecture

- **Pure simulation.** Paper portfolio with a starting balance, no broker integration. Prices from yfinance.
- **Daily cadence.** Agent runs pre-market, reviews engine outputs, makes allocation decisions.
- **Near-full autonomy.** Claude decides what to buy/sell, sizing, and timing. Minimal guardrails.
- **Agentic harness.** Custom tool-use loop — Claude calls tools like `get_portfolio_state`, `get_signals`, `open_position`, `close_position`, `resize_position`, etc.
- **Decision logging.** Every trade decision is logged with the agent's reasoning for post-hoc analysis.

### TODO

#### 1. Simulated portfolio engine
**What:** Portfolio state model (positions, cash, equity, P&L), trade execution against yfinance prices, persistent state in SQLite.
**Effort:** M

#### 2. Agent tool definitions
**What:** Define the tool schemas the agent can call: `get_portfolio_state`, `get_signals`, `get_ticker_detail`, `open_position`, `close_position`, `resize_position`, `get_trade_history`.
**Effort:** M

#### 3. Agentic harness
**What:** Tool-use loop that feeds engine outputs to Claude, lets it call portfolio tools, and logs the full decision trace. Uses Anthropic SDK directly.
**Effort:** L

#### 4. `sfe run-agent` CLI command
**What:** Entry point that runs engines for the watchlist, then hands off to the agentic harness for portfolio decisions.
**Effort:** S

#### 5. Performance tracker
**What:** Track portfolio value over time, compare vs. benchmarks (SPY), compute basic metrics (return, drawdown, Sharpe if enough data). `sfe agent-performance` CLI command.
**Effort:** M

#### 6. Daily automation
**What:** launchd job (or similar) to run `sfe run-agent` pre-market on weekdays.
**Effort:** S

---

## P2 — Brief-to-thread formatter
**What:** Auto-format earnings brief markdown into Twitter-thread segments (280-char numbered tweets with hook).
**Why:** Removes the most tedious publishing step (5-10 min manual formatting per brief).
**Effort:** S (human ~2 hrs / CC ~15 min)
**Depends on:** Publishing platform decision (week 1 of pilot).
**Context:** Deferred from CEO review cherry-pick ceremony. Build only after platform is chosen and formatting bottleneck is confirmed.

## P2 — "Explain this move" reactive trigger
**What:** Reactive mode where a large intraday move (>5%) on a watchlist ticker auto-generates a context brief.
**Why:** Natural Phase 2 after earnings-day trigger is validated. Higher viral potential, higher urgency.
**Effort:** L (human ~40 hrs / CC ~3 hrs)
**Depends on:** Earnings-day pilot validation (8-week checkpoint, ~2026-06-19). Only build if pilot shows demand.
**Context:** Requires real-time price monitoring, intraday news ingest, sub-hour latency. Significant infra gap.

## ~~P2 — Claude API error handling in CLI commands~~ DONE (2026-04-25)
Shipped with earnings engine PR. `run-meta` and `run-earnings-brief` now catch exceptions from `generate_briefing()`.

## ~~P3 — DRY refactor: extract _bootstrap_db() from pipeline.py~~ DONE (2026-04-25)
Shipped with earnings engine PR. `_bootstrap_db()`, `_parse_date()`, `_resolve_tickers()`, `_resolve_watchlist_entries()` extracted.

## P3 — Sector context block in earnings briefs
**What:** "Also reporting this week" section showing sector peers with upcoming earnings dates.
**Why:** Adds sector-level context that influences how a single name's earnings are interpreted.
**Effort:** S (human ~2 hrs / CC ~15 min)
**Depends on:** Earnings calendar widget + sector mapping from watchlist.yaml.
**Context:** Brief is already data-rich without it. Add after pilot cadence is established.

## ~~P3 — Insider/analyst windowing (30-day pre-print)~~ DONE (2026-04-25)
Enrichment aggregator now auto-detects `earnings_date` from the calendar and windows insider trades to 30 days before earnings. Analyst revisions filtered to pre-earnings periods.

---

## Improvement backlog

Captured from a whole-project review (2026-04-19); not yet scheduled. Ordered within each engine by rough signal-quality impact.

### Sentiment
- ~~Promote FinBERT to default scorer; retire TextBlob after spot-checking a week of rows.~~ DONE (2026-04-25). FinBERT is now default; TextBlob is fallback when sentiment-ml deps missing.
- Split `sec_filings` weight into `sec_8k` vs `sec_periodic` (8-Ks carry more event signal than 10-K/10-Q front matter). Cheaper than MD&A section parsing.
- ~~Dedup Finnhub + finlight articles before `weighted_rollup` so wire-service reprints don't double-count.~~ DONE (2026-04-25). Normalized-headline dedup in `_dedup_articles()` before rollup.
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

### Agent / meta layer
- Feed prior day's agent decisions into context so Claude can reference its own track record instead of cold-starting each session.
- Broad-market context block (SPY/QQQ/VIX + upcoming FOMC/CPI) — agent should factor macro regime into allocation decisions.

### Cross-cutting
- `config/sources.yaml` weights are currently guesses and are the most important tuning knob. Backtest weight variants against forward returns once a few weeks of rows accumulate.
- Add a response cache layer on Finnhub fetchers keyed by (ticker, date), mirroring the in-process EDGAR body cache.

### Deferred features
- GBT technical-health model (xgboost) — train once enough daily scorecards accumulate.
- Short interest (FINRA bimonthly file).
- Congressional trades (Quiver Quant free tier, 45-day lag).
- Options flow (Unusual Whales, paid).
- EDGAR MD&A section targeting for 10-K/10-Q.
- Backtesting framework.
- Email/Slack delivery.
- Historical comparison anchor in earnings briefs — needs prior outcome data first.

---

## CLI/TUI redesign

Captured from /plan-design-review on 2026-04-25. Transform the CLI from bare argparse into a Claude Code-inspired interactive TUI.

### P1 — Textual-based interactive TUI
**What:** Build an interactive TUI app using Textual. `sfe` with no args launches the session. Slash commands (`/earnings`, `/sentiment`, `/quant`, `/enrich`, `/meta`, `/calendar`, `/log`, `/status`, `/help`, `/quit`) with autocomplete dropdown. Formatted output via Rich renderables. Step-by-step progress with ✓/⚠/✗ markers. Scrollable output with command history persisted to `~/.sfe_history`.
**Why:** Current CLI is `uv run sfe run-earnings-brief --ticker NVDA` with raw log output. New TUI: type `sfe`, then `/earnings NVDA` with beautiful formatted output and progress feedback.
**Effort:** L (human ~1-2 weeks / CC ~2-3 hrs)
**Depends on:** Nothing. Existing `pipeline.py` functions are the backing layer — TUI calls the same engine functions.
**Design decisions (from review):**
- Framework: Textual (Python's closest analog to Ink/React, which powers Claude Code)
- Entry point: `sfe` = TUI, `sfe run-*` = non-interactive (backward compat preserved)
- Short command names: `/earnings`, `/sentiment`, `/quant`, `/enrich`, `/meta`, `/calendar`, `/log`, `/status`
- Bare ticker input (e.g. `NVDA`) triggers quick-look summary from DB
- API failures: inline ⚠ degradation markers in progress steps, brief still generates
- Min terminal width: 80 columns enforced with friendly message
- Colors: cyan headers, green positive, red negative, yellow warning, dim gray secondary
- Widgets: Header, Input+autocomplete, RichLog (scrollable), DataTable, ProgressBar, Footer
- Command history + scrollable output across commands
**New files:** `src/tui/app.py`, `src/tui/commands.py`, `src/tui/widgets.py`, `src/tui/renderer.py`
**New deps:** `textual` (add to pyproject.toml dependency group `tui`)

### P2 — Quick-look ticker summary
**What:** Bare ticker input (`NVDA` at prompt) shows compact card: last sentiment score, quant health, next earnings, enrichment summary from DB. No API calls — reads stored data only.
**Why:** Most natural trader interaction. Type ticker, see what's up.
**Effort:** S (human ~2 hrs / CC ~15 min)
**Depends on:** TUI implementation (P1).

### P3 — DESIGN.md terminal design system
**What:** Document terminal color palette, Textual widget vocabulary, output formatting conventions.
**Why:** Prevents design drift as new commands/views are added.
**Effort:** S (human ~1 hr / CC ~15 min)
**Depends on:** Nothing. Can be written before or during TUI implementation.

### P3 — Evaluate prompt_toolkit as lighter TUI alternative
**What:** After 2 weeks of Textual TUI usage, evaluate whether prompt_toolkit would be a simpler fit.
**Why:** Outside voice from /plan-eng-review flagged Textual as potentially overkill for a command-see-output REPL. prompt_toolkit gives autocomplete + colors without the widget framework overhead.
**Effort:** S (human ~2 hrs / CC ~30 min) for evaluation; M for migration if warranted.
**Depends on:** TUI P1 being used for at least 1-2 weeks.
**Context:** Textual is an innovation token. If widget layout features (DataTable, ProgressBar, multi-pane) prove valuable, stay. If it's just Input + RichLog, prompt_toolkit is lighter. Evaluate after 2026-05-09.
