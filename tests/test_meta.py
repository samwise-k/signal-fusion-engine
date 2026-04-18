"""Tests for the meta-synthesis layer (payload builder + formatter).

LLM client itself is not exercised here — it makes a live Claude call.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.meta.formatter import format_briefing
from src.meta.payload_builder import build_payload
from src.storage.enrichment_repo import upsert_enrichment_daily
from src.storage.models import Base
from src.storage.quant_repo import upsert_quant_daily
from src.storage.sentiment_repo import upsert_sentiment_daily


def test_meta_package_imports() -> None:
    from src.meta import formatter, llm_client, payload_builder  # noqa: F401


def test_storage_package_imports() -> None:
    from src.storage import db, models  # noqa: F401


def test_pipeline_parser_builds() -> None:
    from src.pipeline import build_parser

    parser = build_parser()
    assert parser.prog == "sfe"


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def _sentiment_payload(ticker: str, on: date, score: float = 0.4) -> dict:
    return {
        "ticker": ticker,
        "date": on.isoformat(),
        "sentiment_score": score,
        "sentiment_direction": "positive",
        "sentiment_delta_7d": 0.1,
        "source_breakdown": {"news_finnhub": score},
        "key_topics": ["ai"],
        "notable_headlines": [{"title": "up", "source": "finnhub"}],
    }


def _quant_payload(ticker: str, on: date) -> dict:
    return {
        "ticker": ticker,
        "date": on.isoformat(),
        "close": 100.0,
        "change_1d": 0.01,
        "change_5d": 0.03,
        "change_20d": 0.05,
        "rsi_14": 55.0,
        "above_50sma": True,
        "above_200sma": True,
        "macd_signal": "bullish",
        "volume_vs_20d_avg": 1.2,
        "sector_etf": "XLK",
        "relative_return_5d": 0.01,
        "health_score": "strong",
    }


def _enrichment_payload(ticker: str, on: date) -> dict:
    return {
        "ticker": ticker,
        "date": on.isoformat(),
        "insider_trades": {"net_insider_sentiment": "bullish", "buy_value": 1.0,
                           "sell_value": 0.0, "recent_filings": []},
        "next_earnings": {"date": "2026-04-25", "days_until": 7},
        "upcoming_events": [{"date": "2026-04-25", "days_until": 7}],
        "analyst_activity": {"trend": "upgrade"},
    }


class TestBuildPayload:
    ON = date(2026, 4, 18)

    def test_missing_data_returns_nulls(self, session: Session) -> None:
        out = build_payload(session, self.ON, tickers=["NVDA"])
        assert out["as_of"] == "2026-04-18"
        assert len(out["tickers"]) == 1
        entry = out["tickers"][0]
        assert entry["ticker"] == "NVDA"
        assert entry["sentiment"] is None
        assert entry["quant"] is None
        assert entry["enrichment"] is None

    def test_all_three_engines_present(self, session: Session) -> None:
        upsert_sentiment_daily(session, _sentiment_payload("NVDA", self.ON))
        upsert_quant_daily(session, _quant_payload("NVDA", self.ON))
        upsert_enrichment_daily(session, _enrichment_payload("NVDA", self.ON))

        out = build_payload(session, self.ON, tickers=["NVDA"])
        entry = out["tickers"][0]
        assert entry["sentiment"]["direction"] == "positive"
        assert entry["quant"]["health_score"] == "strong"
        assert entry["enrichment"]["insider_trades"]["net_insider_sentiment"] == "bullish"

    def test_picks_latest_prior_row(self, session: Session) -> None:
        old = self.ON - timedelta(days=3)
        upsert_sentiment_daily(session, _sentiment_payload("NVDA", old, score=0.1))
        upsert_sentiment_daily(session, _sentiment_payload("NVDA", self.ON, score=0.9))

        out = build_payload(session, self.ON, tickers=["NVDA"])
        assert out["tickers"][0]["sentiment"]["score"] == 0.9

    def test_future_rows_excluded(self, session: Session) -> None:
        future = self.ON + timedelta(days=1)
        upsert_sentiment_daily(session, _sentiment_payload("NVDA", future, score=0.9))

        out = build_payload(session, self.ON, tickers=["NVDA"])
        assert out["tickers"][0]["sentiment"] is None


class TestFormatBriefing:
    def test_passthrough_when_already_headed(self) -> None:
        raw = "# SFE Briefing — 2026-04-18\n\nBody"
        assert format_briefing(raw, on_date=date(2026, 4, 18)) == raw

    def test_prepends_header_when_missing(self) -> None:
        out = format_briefing("just body", on_date=date(2026, 4, 18))
        assert out.startswith("# SFE Briefing — 2026-04-18")
        assert "just body" in out

    def test_empty_returns_empty(self) -> None:
        assert format_briefing("   \n ", on_date=date(2026, 4, 18)) == ""

    def test_strips_whitespace(self) -> None:
        assert format_briefing("  # title\n\nbody\n  ").startswith("# title")
