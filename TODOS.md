# SFE — Deferred Work

Tracked items from /plan-ceo-review on 2026-04-24.

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

## P3 — Insider/analyst windowing (30-day pre-print)
**What:** Window insider trades and analyst revisions to 30 days before earnings_date instead of using whatever's in the DB.
**Why:** Focuses the signal on pre-print activity, which is more predictive than a generic 30-day lookback from today.
**Effort:** S (human ~2 hrs / CC ~15 min)
**Depends on:** Nothing. Existing enrichment data works for week 1.
**Context:** Accepted scope from CEO review, deferred from Sunday must-have. Build when first briefs expose the gap.

---

## Improvement backlog

Captured from a whole-project review (2026-04-19); not yet scheduled. Ordered within each engine by rough signal-quality impact.

### Sentiment
- ~~Promote FinBERT to default scorer; retire TextBlob after spot-checking a week of rows.~~ DONE (2026-04-25). FinBERT is now default; TextBlob is fallback when sentiment-ml deps missing.
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
- Feed yesterday's briefing (or a tier-change diff) into the prompt so Claude can reference prior calls instead of cold-starting each morning.
- Add a `briefing_outcomes` table for manual post-hoc right/wrong marking. Unblocks threshold tuning and eventually provides GBT labels.
- Broad-market context block (SPY/QQQ/VIX + upcoming FOMC/CPI) — worth prioritizing because high-conviction calls on risk-off days should be downgraded.

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
