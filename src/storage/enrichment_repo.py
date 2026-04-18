"""Repository helpers for enrichment data."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import EnrichmentDaily


def upsert_enrichment_daily(session: Session, payload: dict[str, Any]) -> EnrichmentDaily:
    """Insert or update one ``enrichment_daily`` row from an aggregator payload."""
    ticker = payload["ticker"]
    as_of = payload["date"]
    if isinstance(as_of, str):
        as_of = Date.fromisoformat(as_of)

    fields = dict(
        ticker=ticker,
        as_of=as_of,
        insider_trades=payload.get("insider_trades") or {},
        next_earnings=payload.get("next_earnings"),
        upcoming_events=payload.get("upcoming_events") or [],
        analyst_activity=payload.get("analyst_activity") or {},
    )

    existing = session.execute(
        select(EnrichmentDaily).where(
            EnrichmentDaily.ticker == ticker,
            EnrichmentDaily.as_of == as_of,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = EnrichmentDaily(**fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        row = existing
    session.commit()
    return row
