"""Assemble per-ticker engine outputs into the meta-layer JSON payload.

Pulls the latest ``SentimentDaily`` / ``QuantDaily`` / ``EnrichmentDaily``
row for each watchlist ticker (as of ``on_date`` or earlier) and folds
them into the planning-doc payload shape the LLM prompt expects.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import load_watchlist
from src.storage.models import EnrichmentDaily, QuantDaily, SentimentDaily


def _latest(session: Session, model, ticker: str, on_date: date):
    stmt = (
        select(model)
        .where(model.ticker == ticker, model.as_of <= on_date)
        .order_by(model.as_of.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _sentiment_view(row: SentimentDaily | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "as_of": row.as_of.isoformat(),
        "score": row.sentiment_score,
        "direction": row.sentiment_direction,
        "delta_7d": row.sentiment_delta_7d,
        "source_breakdown": row.source_breakdown,
        "key_topics": row.key_topics,
        "notable_headlines": row.notable_headlines,
    }


def _quant_view(row: QuantDaily | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "as_of": row.as_of.isoformat(),
        "close": row.close,
        "change_1d": row.change_1d,
        "change_5d": row.change_5d,
        "change_20d": row.change_20d,
        "rsi_14": row.rsi_14,
        "above_50sma": row.above_50sma,
        "above_200sma": row.above_200sma,
        "macd_signal": row.macd_signal,
        "volume_vs_20d_avg": row.volume_vs_20d_avg,
        "sector_etf": row.sector_etf,
        "relative_return_5d": row.relative_return_5d,
        "health_score": row.health_score,
    }


def _enrichment_view(row: EnrichmentDaily | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "as_of": row.as_of.isoformat(),
        "insider_trades": row.insider_trades,
        "next_earnings": row.next_earnings,
        "upcoming_events": row.upcoming_events,
        "analyst_activity": row.analyst_activity,
    }


def build_payload(
    session: Session,
    on_date: date,
    *,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Return the meta-layer JSON payload for ``on_date``.

    Pass ``tickers`` to override the watchlist (single-ticker runs, tests).
    """
    if tickers is None:
        tickers = [t["ticker"].upper() for t in load_watchlist()]

    entries: list[dict[str, Any]] = []
    for ticker in tickers:
        sym = ticker.upper()
        entries.append(
            {
                "ticker": sym,
                "sentiment": _sentiment_view(_latest(session, SentimentDaily, sym, on_date)),
                "quant": _quant_view(_latest(session, QuantDaily, sym, on_date)),
                "enrichment": _enrichment_view(
                    _latest(session, EnrichmentDaily, sym, on_date)
                ),
            }
        )

    return {"as_of": on_date.isoformat(), "tickers": entries}
