"""Repository helpers for sentiment data."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import SentimentDaily


def upsert_sentiment_daily(session: Session, payload: dict[str, Any]) -> SentimentDaily:
    """Insert or update one ``sentiment_daily`` row from an aggregator payload."""
    ticker = payload["ticker"]
    as_of = payload["date"]
    if isinstance(as_of, str):
        as_of = Date.fromisoformat(as_of)

    fields = dict(
        ticker=ticker,
        as_of=as_of,
        sentiment_score=payload["sentiment_score"],
        sentiment_direction=payload["sentiment_direction"],
        sentiment_delta_7d=payload.get("sentiment_delta_7d"),
        source_breakdown=payload.get("source_breakdown") or {},
        key_topics=payload.get("key_topics") or [],
        notable_headlines=payload.get("notable_headlines") or [],
    )

    existing = session.execute(
        select(SentimentDaily).where(
            SentimentDaily.ticker == ticker,
            SentimentDaily.as_of == as_of,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = SentimentDaily(**fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        row = existing
    session.commit()
    return row
