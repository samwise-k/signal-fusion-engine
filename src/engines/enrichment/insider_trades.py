"""Insider trades via Finnhub ``/stock/insider-transactions``.

Finnhub pre-parses Form 4 filings into structured rows, which is why we
lean on it here rather than parsing EDGAR XML directly. Swapping to a
direct EDGAR Form 4 fetcher later is straightforward — only this module
would change.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import httpx

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 20.0
DEFAULT_LOOKBACK_DAYS = 30
RECENT_LIMIT = 5
# Transaction codes on Form 4: 'P' = open-market buy, 'S' = open-market sale.
# Other codes (A/M/F/G/...) are grants, exercises, gifts, etc. — much noisier
# signal — so we only count P/S toward net insider sentiment.
BUY_CODES = frozenset({"P"})
SELL_CODES = frozenset({"S"})


def fetch_transactions(
    ticker: str,
    on_date: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict[str, Any]]:
    """Return Finnhub insider-transaction dicts for ``ticker`` ending at ``on_date``."""
    key = os.environ.get("FINNHUB_KEY")
    if not key:
        raise RuntimeError("FINNHUB_KEY not set in environment")

    start = on_date - timedelta(days=max(lookback_days - 1, 0))
    params = {
        "symbol": ticker,
        "from": start.isoformat(),
        "to": on_date.isoformat(),
        "token": key,
    }
    response = httpx.get(
        f"{FINNHUB_BASE}/stock/insider-transactions", params=params, timeout=FINNHUB_TIMEOUT
    )
    response.raise_for_status()
    payload = response.json() or {}
    return payload.get("data") or []


def summarize(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll raw transactions into an enrichment-ready insider block.

    Net insider sentiment is a coarse label based on dollar value of P vs S
    codes (other codes ignored per module docstring). Ties or zero-activity
    collapse to ``"neutral"``.
    """
    buy_value = 0.0
    sell_value = 0.0
    recent: list[dict[str, Any]] = []

    for t in transactions:
        code = (t.get("transactionCode") or "").upper()
        change = t.get("change") or 0
        price = t.get("transactionPrice") or 0.0
        value = abs(float(change) * float(price))

        if code in BUY_CODES:
            buy_value += value
            txn_type = "purchase"
        elif code in SELL_CODES:
            sell_value += value
            txn_type = "sale"
        else:
            txn_type = "other"

        recent.append(
            {
                "name": t.get("name"),
                "type": txn_type,
                "code": code,
                "shares": int(change) if change is not None else None,
                "value": round(value, 2),
                "filing_date": t.get("filingDate"),
                "transaction_date": t.get("transactionDate"),
            }
        )

    if buy_value > sell_value * 1.1:
        net = "bullish"
    elif sell_value > buy_value * 1.1:
        net = "bearish"
    else:
        net = "neutral"

    recent.sort(key=lambda r: r.get("filing_date") or "", reverse=True)
    return {
        "net_insider_sentiment": net,
        "buy_value": round(buy_value, 2),
        "sell_value": round(sell_value, 2),
        "recent_filings": recent[:RECENT_LIMIT],
    }
