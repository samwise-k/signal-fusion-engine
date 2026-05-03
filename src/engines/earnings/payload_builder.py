"""Assemble the earnings-specific payload for a single ticker.

Pulls existing engine data from DB (sentiment, quant, enrichment) and
combines with new earnings-specific fetches (consensus, beat/miss,
options-implied move). The prompt template receives this as JSON.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.engines.earnings import beat_miss, consensus, options_implied
from src.meta.payload_builder import _enrichment_view, _latest, _quant_view, _sentiment_view
from src.storage.models import EnrichmentDaily, QuantDaily, SentimentDaily


def build_earnings_payload(
    session: Session,
    ticker: str,
    on_date: date,
    earnings_date: date,
) -> dict[str, Any]:
    """Build the full earnings brief payload for one ticker."""
    sentiment = _sentiment_view(_latest(session, SentimentDaily, ticker, on_date))
    quant = _quant_view(_latest(session, QuantDaily, ticker, on_date))
    enrichment = _enrichment_view(_latest(session, EnrichmentDaily, ticker, on_date))

    consensus_data: dict[str, Any] | None = None
    try:
        consensus_data = consensus.fetch_estimates(ticker)
    except Exception as exc:
        logger.warning(f"{ticker}: consensus fetch failed: {exc}")

    beat_miss_data: list[dict[str, Any]] = []
    try:
        raw_history = beat_miss.fetch_history(ticker)
        beat_miss_data = beat_miss.summarize(raw_history)
    except Exception as exc:
        logger.warning(f"{ticker}: beat/miss fetch failed: {exc}")

    implied_move = options_implied.fetch_implied_move(ticker, earnings_date)

    prior_outcome = _get_prior_outcome(session, ticker)

    return {
        "ticker": ticker,
        "as_of": on_date.isoformat(),
        "earnings_date": earnings_date.isoformat(),
        "days_until_earnings": (earnings_date - on_date).days,
        "consensus": consensus_data,
        "beat_miss_history": beat_miss_data,
        "implied_move": implied_move,
        "sentiment": sentiment,
        "quant": quant,
        "enrichment": enrichment,
        "prior_outcome": prior_outcome,
    }


def _get_prior_outcome(session: Session, ticker: str) -> dict[str, Any] | None:
    """Return the most recent EarningsBriefOutcome for this ticker, if any."""
    from src.storage.models import EarningsBriefOutcome

    from sqlalchemy import select

    stmt = (
        select(EarningsBriefOutcome)
        .where(EarningsBriefOutcome.ticker == ticker)
        .order_by(EarningsBriefOutcome.earnings_date.desc())
        .limit(1)
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return {
        "predicted_dir": row.predicted_dir,
        "conviction": row.conviction,
        "actual_eps_surp": row.actual_eps_surp,
        "actual_rev_surp": row.actual_rev_surp,
        "stock_move_1d": row.stock_move_1d,
        "outcome": row.outcome,
    }
