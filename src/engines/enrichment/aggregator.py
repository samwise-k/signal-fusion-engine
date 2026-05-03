"""End-to-end enrichment rollup for one ticker on one day.

Phase 3 starting slice: insider trades, earnings calendar, analyst
revisions. Short interest / congressional / options flow / FOMC+CPI
macro events slot in later.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from src.engines.enrichment import analyst_revisions, event_calendar, insider_trades


def aggregate(
    ticker: str,
    on_date: date,
    *,
    earnings_date: date | None = None,
) -> dict[str, Any]:
    """Combine insider trades + earnings + analyst signals into one payload.

    When ``earnings_date`` is provided, insider trades are windowed to the
    30 days before earnings (more predictive than a generic lookback from
    today), and analyst revisions are filtered to periods before earnings.

    Per-source failures are logged and degrade to empty/neutral blocks, so
    one outage never blanks the enrichment row ��� same pattern as the
    sentiment aggregator.
    """
    # Fetch earnings calendar first so we can auto-detect earnings_date
    # for windowing insider trades and analyst revisions.
    events_block: dict[str, Any]
    try:
        events = event_calendar.fetch_earnings(ticker, on_date)
    except Exception as exc:
        logger.warning(f"{ticker}: earnings calendar fetch failed: {exc}")
        events_block = event_calendar.summarize([], on_date)
    else:
        events_block = event_calendar.summarize(events, on_date)

    if earnings_date is None and events_block["next_earnings"]:
        try:
            earnings_date = date.fromisoformat(events_block["next_earnings"]["date"])
        except (ValueError, KeyError):
            pass

    insider_block: dict[str, Any]
    try:
        insider_end = earnings_date if earnings_date else on_date
        txns = insider_trades.fetch_transactions(ticker, insider_end)
    except Exception as exc:
        logger.warning(f"{ticker}: insider fetch failed: {exc}")
        insider_block = insider_trades.summarize([])
    else:
        insider_block = insider_trades.summarize(txns)

    analyst_block: dict[str, Any]
    try:
        recs = analyst_revisions.fetch_recommendations(ticker)
    except Exception as exc:
        logger.warning(f"{ticker}: analyst fetch failed: {exc}")
        analyst_block = analyst_revisions.summarize([])
    else:
        analyst_block = analyst_revisions.summarize(recs, before_date=earnings_date)

    return {
        "ticker": ticker,
        "date": on_date.isoformat(),
        "insider_trades": insider_block,
        "next_earnings": events_block["next_earnings"],
        "upcoming_events": events_block["upcoming_events"],
        "analyst_activity": analyst_block,
    }
