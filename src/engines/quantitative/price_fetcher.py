"""OHLCV ingestion via yfinance."""

from __future__ import annotations

from datetime import date, timedelta

import yfinance as yf

DEFAULT_LOOKBACK_DAYS = 300


def fetch_ohlcv(ticker: str, end_date: date, days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict]:
    """Return daily OHLCV rows for ``ticker`` ending on/before ``end_date``.

    Pulls ``days`` calendar days back so a 200-session SMA has enough history
    after weekends and holidays are removed. yfinance's ``end`` is exclusive,
    so we nudge it forward by one day to include ``end_date`` itself.
    """
    start = end_date - timedelta(days=days)
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        return []

    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df = df.droplevel(1, axis=1)

    rows: list[dict] = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "date": idx.date() if hasattr(idx, "date") else idx,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
        )
    return rows
