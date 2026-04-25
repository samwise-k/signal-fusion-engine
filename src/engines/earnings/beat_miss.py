"""Historical beat/miss via Finnhub ``/stock/earnings``.

Returns actual vs estimated EPS for the last N quarters, plus a stock
reaction field (1-day move post-print) when available.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 20.0
DEFAULT_QUARTERS = 8


def fetch_history(ticker: str, *, limit: int = DEFAULT_QUARTERS) -> list[dict[str, Any]]:
    """Return last ``limit`` quarters of earnings actuals vs estimates."""
    key = os.environ.get("FINNHUB_KEY")
    if not key:
        raise RuntimeError("FINNHUB_KEY not set in environment")

    params = {"symbol": ticker, "limit": limit, "token": key}
    resp = httpx.get(f"{FINNHUB_BASE}/stock/earnings", params=params, timeout=FINNHUB_TIMEOUT)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape raw Finnhub earnings rows into the payload format the prompt expects."""
    result: list[dict[str, Any]] = []
    for r in rows:
        actual = r.get("actual")
        estimate = r.get("estimate")

        surprise_pct = None
        if actual is not None and estimate is not None and estimate != 0:
            surprise_pct = round(((actual - estimate) / abs(estimate)) * 100, 2)

        result.append({
            "quarter": r.get("period"),
            "eps_actual": actual,
            "eps_estimate": estimate,
            "surprise_pct": surprise_pct,
            "stock_reaction_1d": r.get("surprisePercent"),
        })
    return result
