"""Tests for the FastAPI layer (Phase 5)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import main as api_main
from src.storage.models import (
    Base,
    BriefingDaily,
    EnrichmentDaily,
    QuantDaily,
    SentimentDaily,
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def _override_session() -> Session:
        return Factory()

    monkeypatch.setattr(api_main, "_session_factory", lambda: _override_session)
    monkeypatch.setattr(
        api_main,
        "load_watchlist",
        lambda: [{"ticker": "LMT", "sector": "Industrials"}],
    )

    with Factory() as s:
        s.add(
            SentimentDaily(
                ticker="LMT",
                as_of=date(2026, 4, 17),
                sentiment_score=0.72,
                sentiment_direction="improving",
                sentiment_delta_7d=0.15,
                source_breakdown={"news_finnhub": {"score": 0.72, "count": 5}},
                key_topics=["contract"],
                notable_headlines=[{"headline": "Navy contract", "score": 0.8}],
            )
        )
        s.add(
            QuantDaily(
                ticker="LMT",
                as_of=date(2026, 4, 17),
                close=487.32,
                change_1d=1.2,
                rsi_14=58.4,
                above_50sma=True,
                above_200sma=True,
                macd_signal="bullish_crossover",
                volume_vs_20d_avg=1.45,
                sector_etf="XLI",
                relative_return_5d=2.1,
                health_score="strong",
            )
        )
        s.add(
            EnrichmentDaily(
                ticker="LMT",
                as_of=date(2026, 4, 17),
                insider_trades={"net_insider_sentiment": "bullish"},
                next_earnings={"date": "2026-04-22", "estimate_eps": 6.45},
                upcoming_events=[],
                analyst_activity={"trend": "upgrade"},
            )
        )
        s.add(
            BriefingDaily(
                as_of=date(2026, 4, 17),
                tickers=["LMT"],
                payload={"briefing_date": "2026-04-17"},
                briefing_markdown="# Briefing\n\nLMT looks strong.",
                model="claude-opus-4-7",
            )
        )
        s.commit()

    return TestClient(api_main.app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_watchlist(client: TestClient) -> None:
    r = client.get("/watchlist")
    assert r.status_code == 200
    assert r.json() == [{"ticker": "LMT", "sector": "Industrials"}]


def test_ticker_detail(client: TestClient) -> None:
    r = client.get("/tickers/lmt", params={"date": "2026-04-17"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "LMT"
    assert body["sector"] == "Industrials"
    assert body["sentiment"]["sentiment_score"] == 0.72
    assert body["quantitative"]["health_score"] == "strong"
    assert body["enrichment"]["insider_trades"]["net_insider_sentiment"] == "bullish"


def test_ticker_detail_missing(client: TestClient) -> None:
    r = client.get("/tickers/ZZZZ", params={"date": "2026-04-17"})
    assert r.status_code == 404


def test_ticker_history(client: TestClient) -> None:
    r = client.get("/tickers/LMT/history", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body["sentiment"]) == 1
    assert body["sentiment"][0]["score"] == 0.72
    assert body["quant"][0]["close"] == 487.32


def test_watchlist_snapshot(client: TestClient) -> None:
    r = client.get("/watchlist/snapshot", params={"date": "2026-04-17"})
    assert r.status_code == 200
    body = r.json()
    assert body["as_of"] == "2026-04-17"
    assert len(body["entries"]) == 1
    assert body["entries"][0]["ticker"] == "LMT"


def test_briefing_hit(client: TestClient) -> None:
    r = client.get("/briefing/2026-04-17")
    assert r.status_code == 200
    body = r.json()
    assert body["tickers"] == ["LMT"]
    assert "Briefing" in body["markdown"]


def test_briefing_miss(client: TestClient) -> None:
    r = client.get("/briefing/2026-04-18")
    assert r.status_code == 404


def test_pipeline_unknown_engine(client: TestClient) -> None:
    r = client.post("/pipeline/bogus", params={"ticker": "LMT"})
    assert r.status_code == 404
