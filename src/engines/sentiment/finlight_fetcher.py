"""finlight.me news ingestion.

Finlight returns its own ``sentiment`` label per article. Phase 1 ignores
that and scores with TextBlob for consistency across sources; swapping to
Finlight's native label (or averaging) is a future knob.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

FINLIGHT_BASE = "https://api.finlight.me"
FINLIGHT_TIMEOUT = 20.0
DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_PAGE_SIZE = 100


def fetch_news(
    ticker: str,
    on_date: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict]:
    """Return raw finlight article dicts for ``ticker`` ending at ``on_date``.

    Each dict retains finlight's native shape (``title``, ``summary``,
    ``link``, ``source``, ``publishDate``, ``sentiment``, ``confidence``,
    ...); the aggregator extracts the fields it needs.
    """
    key = os.environ.get("FINLIGHT_KEY")
    if not key:
        raise RuntimeError("FINLIGHT_KEY not set in environment")

    start = on_date - timedelta(days=max(lookback_days - 1, 0))
    body = {
        "tickers": [ticker],
        "from": start.isoformat(),
        "to": on_date.isoformat(),
        "language": "en",
        "pageSize": DEFAULT_PAGE_SIZE,
    }
    response = httpx.post(
        f"{FINLIGHT_BASE}/v2/articles",
        json=body,
        headers={"X-API-KEY": key},
        timeout=FINLIGHT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    articles = payload.get("articles") if isinstance(payload, dict) else None
    return articles if isinstance(articles, list) else []
