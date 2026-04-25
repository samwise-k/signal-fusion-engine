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
