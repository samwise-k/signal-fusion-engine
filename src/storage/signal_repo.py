"""Repository helpers for signal experiment data."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import SignalDaily


def upsert_signal_daily(session: Session, data: dict[str, Any]) -> SignalDaily:
    """Insert or update one ``signal_daily`` row."""
    ticker = data["ticker"]
    as_of = data["as_of"]
    if isinstance(as_of, str):
        as_of = Date.fromisoformat(as_of)

    fields = dict(
        ticker=ticker,
        as_of=as_of,
        direction=data["direction"],
        conviction=data["conviction"],
        dominant_component=data["dominant_component"],
        reasoning=data["reasoning"],
        entry_price=data.get("entry_price"),
        signal_components=data.get("signal_components") or {},
    )

    existing = session.execute(
        select(SignalDaily).where(
            SignalDaily.ticker == ticker,
            SignalDaily.as_of == as_of,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = SignalDaily(**fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        row = existing
    session.commit()
    return row
