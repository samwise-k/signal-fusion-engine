"""Pydantic response models for the SFE API.

These mirror the engine output shapes (see planning doc for canonical
schemas). Nested JSON blobs stay as ``dict[str, Any]`` rather than fully
typed Pydantic models — the engine layer is the source of truth, and
typing every nested field here would duplicate that without benefit.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class WatchlistEntry(BaseModel):
    ticker: str
    sector: str | None = None


class SentimentView(BaseModel):
    as_of: date
    sentiment_score: float
    sentiment_direction: str
    sentiment_delta_7d: float | None = None
    source_breakdown: dict[str, Any] = {}
    key_topics: list[str] = []
    notable_headlines: list[dict[str, Any]] = []


class QuantView(BaseModel):
    as_of: date
    close: float | None = None
    change_1d: float | None = None
    change_5d: float | None = None
    change_20d: float | None = None
    rsi_14: float | None = None
    above_50sma: bool | None = None
    above_200sma: bool | None = None
    macd_signal: str | None = None
    volume_vs_20d_avg: float | None = None
    sector_etf: str | None = None
    relative_return_5d: float | None = None
    health_score: str


class EnrichmentView(BaseModel):
    as_of: date
    insider_trades: dict[str, Any] = {}
    next_earnings: dict[str, Any] | None = None
    upcoming_events: list[dict[str, Any]] = []
    analyst_activity: dict[str, Any] = {}


class TickerSnapshot(BaseModel):
    ticker: str
    sector: str | None = None
    sentiment: SentimentView | None = None
    quantitative: QuantView | None = None
    enrichment: EnrichmentView | None = None


class WatchlistSnapshot(BaseModel):
    as_of: date
    entries: list[TickerSnapshot]


class BriefingView(BaseModel):
    as_of: date
    tickers: list[str]
    markdown: str
    model: str
    created_at: datetime


class PipelineRunResponse(BaseModel):
    status: str
    command: str
    tickers: list[str]
    as_of: date
    detail: str | None = None
