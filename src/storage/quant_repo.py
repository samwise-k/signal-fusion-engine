"""Repository helpers for quantitative data."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import QuantDaily

_FIELDS = (
    "close",
    "change_1d",
    "change_5d",
    "change_20d",
    "rsi_14",
    "above_50sma",
    "above_200sma",
    "macd_signal",
    "volume_vs_20d_avg",
    "sector_etf",
    "relative_return_5d",
    "health_score",
)


def upsert_quant_daily(session: Session, payload: dict[str, Any]) -> QuantDaily:
    """Insert or update one ``quant_daily`` row from an aggregator payload."""
    ticker = payload["ticker"]
    as_of = payload["date"]
    if isinstance(as_of, str):
        as_of = Date.fromisoformat(as_of)

    fields = {"ticker": ticker, "as_of": as_of}
    fields.update({k: payload.get(k) for k in _FIELDS})

    existing = session.execute(
        select(QuantDaily).where(
            QuantDaily.ticker == ticker,
            QuantDaily.as_of == as_of,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = QuantDaily(**fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        row = existing
    session.commit()
    return row
