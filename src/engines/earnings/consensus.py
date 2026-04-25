"""Consensus estimates via Finnhub.

``/stock/metric`` for current forward estimates (EPS, revenue).
``/stock/earnings`` for historical actuals vs estimates (used by beat_miss too).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 20.0


def fetch_estimates(ticker: str) -> dict[str, Any]:
    """Return current consensus EPS/revenue estimates from Finnhub /stock/metric."""
    key = os.environ.get("FINNHUB_KEY")
    if not key:
        raise RuntimeError("FINNHUB_KEY not set in environment")

    params = {"symbol": ticker, "metric": "all", "token": key}
    resp = httpx.get(f"{FINNHUB_BASE}/stock/metric", params=params, timeout=FINNHUB_TIMEOUT)
    resp.raise_for_status()
    data = resp.json() or {}

    metric = data.get("metric") or {}
    estimates = data.get("estimates") or {}
    annual = (estimates.get("annual") or {}).get("revenue") or []
    quarterly_eps = (estimates.get("quarterly") or {}).get("eps") or []

    eps_estimate = None
    revenue_estimate = None
    num_analysts = None

    if quarterly_eps:
        latest_q = quarterly_eps[0]
        eps_estimate = latest_q.get("numberAnalysts") and latest_q.get("avg")
        num_analysts = latest_q.get("numberAnalysts")
        if eps_estimate is None:
            eps_estimate = metric.get("epsEstimate")

    if eps_estimate is None:
        eps_estimate = metric.get("epsEstimate")

    revenue_estimate = metric.get("revenueEstimate")
    if revenue_estimate is None and annual:
        revenue_estimate = annual[0].get("avg")

    if num_analysts is None:
        num_analysts = metric.get("numberOfAnalysts")

    return {
        "eps_estimate": _safe_float(eps_estimate),
        "revenue_estimate": _safe_float(revenue_estimate),
        "num_analysts": _safe_int(num_analysts),
    }


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
