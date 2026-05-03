"""Analyst revisions via Finnhub ``/stock/recommendation``.

Finnhub returns monthly aggregates of buy/hold/sell counts. We compare the
most recent month to the prior month to surface directional revision — the
mechanical-flow angle from the planning doc.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 20.0


def fetch_recommendations(ticker: str) -> list[dict[str, Any]]:
    """Return Finnhub recommendation-trend rows (most-recent-first)."""
    key = os.environ.get("FINNHUB_KEY")
    if not key:
        raise RuntimeError("FINNHUB_KEY not set in environment")

    params = {"symbol": ticker, "token": key}
    response = httpx.get(
        f"{FINNHUB_BASE}/stock/recommendation", params=params, timeout=FINNHUB_TIMEOUT
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    return sorted(payload, key=lambda r: r.get("period", ""), reverse=True)


def _bull_score(row: dict[str, Any]) -> int:
    return (
        int(row.get("strongBuy", 0) or 0)
        + int(row.get("buy", 0) or 0)
        - int(row.get("sell", 0) or 0)
        - int(row.get("strongSell", 0) or 0)
    )


def summarize(
    rows: list[dict[str, Any]],
    *,
    before_date: date | None = None,
) -> dict[str, Any]:
    """Compare latest month vs prior to label trend as upgrade/downgrade/stable.

    When ``before_date`` is given, only periods strictly before that date are
    considered — this focuses the signal on pre-earnings revisions rather than
    post-earnings noise.
    """
    if before_date is not None:
        rows = [r for r in rows if (r.get("period") or "") < before_date.isoformat()]
    if not rows:
        return {
            "latest_period": None,
            "strong_buy": 0,
            "buy": 0,
            "hold": 0,
            "sell": 0,
            "strong_sell": 0,
            "trend": "stable",
        }

    latest = rows[0]
    trend = "stable"
    if len(rows) >= 2:
        delta = _bull_score(latest) - _bull_score(rows[1])
        if delta >= 2:
            trend = "upgrade"
        elif delta <= -2:
            trend = "downgrade"

    return {
        "latest_period": latest.get("period"),
        "strong_buy": int(latest.get("strongBuy", 0) or 0),
        "buy": int(latest.get("buy", 0) or 0),
        "hold": int(latest.get("hold", 0) or 0),
        "sell": int(latest.get("sell", 0) or 0),
        "strong_sell": int(latest.get("strongSell", 0) or 0),
        "trend": trend,
    }
