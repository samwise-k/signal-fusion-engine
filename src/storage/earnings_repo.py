"""Repository helpers for EarningsBriefOutcome."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import EarningsBriefOutcome


def upsert_outcome(session: Session, data: dict[str, Any]) -> None:
    """Insert or update an earnings outcome row keyed on (ticker, earnings_date)."""
    stmt = select(EarningsBriefOutcome).where(
        EarningsBriefOutcome.ticker == data["ticker"],
        EarningsBriefOutcome.earnings_date == data["earnings_date"],
    )
    row = session.execute(stmt).scalar_one_or_none()

    if row is None:
        row = EarningsBriefOutcome(
            ticker=data["ticker"],
            earnings_date=data["earnings_date"],
        )
        session.add(row)

    row.brief_date = data.get("brief_date", date.today())
    row.predicted_dir = data["predicted_dir"]
    row.conviction = data["conviction"]
    row.actual_eps_surp = data.get("actual_eps_surp")
    row.actual_rev_surp = data.get("actual_rev_surp")
    row.stock_move_1d = data.get("stock_move_1d")
    row.outcome = data.get("outcome", "pending")
    row.notes = data.get("notes")

    session.commit()


def get_latest_outcome(
    session: Session, ticker: str
) -> EarningsBriefOutcome | None:
    """Return the most recent outcome row for a ticker."""
    stmt = (
        select(EarningsBriefOutcome)
        .where(EarningsBriefOutcome.ticker == ticker)
        .order_by(EarningsBriefOutcome.earnings_date.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()
