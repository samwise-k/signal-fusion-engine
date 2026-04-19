"""SQLAlchemy declarative models. Per-phase schemas are filled in as engines land."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    """Per-ticker daily quantitative scorecard (Phase 2)."""

    __tablename__ = "quant_daily"
    __table_args__ = (UniqueConstraint("ticker", "as_of", name="uq_quant_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_14: Mapped[float | None] = mapped_column(Float, nullable=True)
    above_50sma: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    above_200sma: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    macd_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_vs_20d_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_etf: Mapped[str | None] = mapped_column(String(10), nullable=True)
    relative_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    health_score: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EnrichmentDaily(Base):
    """Per-ticker daily enrichment signals (Phase 3)."""

    __tablename__ = "enrichment_daily"
    __table_args__ = (UniqueConstraint("ticker", "as_of", name="uq_enrichment_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    insider_trades: Mapped[dict] = mapped_column(JSON, default=dict)
    next_earnings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    upcoming_events: Mapped[list] = mapped_column(JSON, default=list)
    analyst_activity: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BriefingDaily(Base):
    """Cached meta-layer briefing output (Phase 5).

    One row per briefing date. ``payload`` stores the exact JSON sent to
    Claude so a briefing can be regenerated or inspected later without
    re-querying the engine tables.
    """

    __tablename__ = "briefing_daily"
    __table_args__ = (UniqueConstraint("as_of", name="uq_briefing_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    tickers: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    briefing_markdown: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
