"""SQLAlchemy declarative models. Per-phase schemas are filled in as engines land."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all SFE tables."""


class SentimentDaily(Base):
    """Per-ticker daily sentiment rollup (Phase 1).

    Mirrors the JSON schema in the planning doc. ``source_breakdown``,
    ``key_topics``, and ``notable_headlines`` are JSON columns so a row
    round-trips into the meta-layer payload without a join.
    """

    __tablename__ = "sentiment_daily"
    __table_args__ = (UniqueConstraint("ticker", "as_of", name="uq_sentiment_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    sentiment_score: Mapped[float] = mapped_column(Float)
    sentiment_direction: Mapped[str] = mapped_column(String(16))
    sentiment_delta_7d: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    key_topics: Mapped[list] = mapped_column(JSON, default=list)
    notable_headlines: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuantDaily(Base):
    """Per-ticker daily quantitative scorecard. Columns filled in Phase 2."""

    __tablename__ = "quant_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class EnrichmentDaily(Base):
    """Per-ticker daily enrichment signals. Columns filled in Phase 3."""

    __tablename__ = "enrichment_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
