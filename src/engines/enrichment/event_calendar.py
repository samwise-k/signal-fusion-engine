"""Upcoming events via Finnhub ``/calendar/earnings``.

Phase 3 covers ticker-specific earnings. FOMC/CPI macro dates land in a
follow-up (hardcoded near-term calendar or FRED) — those aren't per-ticker
so they live at the payload/briefing level, not here.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import httpx

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 20.0
DEFAULT_LOOKAHEAD_DAYS = 30


def fetch_earnings(
    ticker: str,
    on_date: date,
    *,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
) -> list[dict[str, Any]]:
    """Return upcoming earnings rows for ``ticker`` in the lookahead window."""
    key = os.environ.get("FINNHUB_KEY")
    if not key:
        raise RuntimeError("FINNHUB_KEY not set in environment")

    end = on_date + timedelta(days=lookahead_days)
    params = {
        "symbol": ticker,
        "from": on_date.isoformat(),
        "to": end.isoformat(),
        "token": key,
    }
    response = httpx.get(
        f"{FINNHUB_BASE}/calendar/earnings", params=params, timeout=FINNHUB_TIMEOUT
    )
    response.raise_for_status()
    payload = response.json() or {}
    return payload.get("earningsCalendar") or []


def summarize(rows: list[dict[str, Any]], on_date: date) -> dict[str, Any]:
    """Pick the soonest upcoming earnings event and compute days until.

    Meta-layer uses ``days_until`` to flag "earnings within 5 trading days"
    per the planning doc — calendar days are a close-enough proxy at the
    briefing granularity.
    """
    upcoming: list[dict[str, Any]] = []
    for r in rows:
        d_str = r.get("date")
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if d < on_date:
            continue
        upcoming.append(
            {
                "date": d_str,
                "days_until": (d - on_date).days,
                "estimate_eps": r.get("epsEstimate"),
                "hour": r.get("hour"),
            }
        )

    upcoming.sort(key=lambda x: x["date"])
    next_event = upcoming[0] if upcoming else None
    return {
        "next_earnings": next_event,
        "upcoming_events": upcoming,
    }
