"""Tests for the storage layer (Phase 1: sentiment_daily upsert)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.storage.models import Base, SentimentDaily
from src.storage.sentiment_repo import get_score_near, upsert_sentiment_daily


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def make_payload(score: float = 0.5, headline: str = "Up") -> dict:
    return {
        "ticker": "LMT",
        "date": "2026-04-17",
        "sentiment_score": score,
        "sentiment_direction": "stable",
        "sentiment_delta_7d": None,
        "source_breakdown": {"news_finnhub": {"score": score, "count": 1}},
        "key_topics": [],
        "notable_headlines": [{"headline": headline, "url": "x", "score": score}],
    }


def test_insert_creates_row(session: Session) -> None:
    row = upsert_sentiment_daily(session, make_payload(0.42))
    assert row.id is not None
    assert row.ticker == "LMT"
    assert row.as_of == date(2026, 4, 17)
    assert row.sentiment_score == 0.42
    assert row.source_breakdown == {"news_finnhub": {"score": 0.42, "count": 1}}


def test_upsert_updates_existing_row(session: Session) -> None:
    first = upsert_sentiment_daily(session, make_payload(0.42, headline="Old"))
    second = upsert_sentiment_daily(session, make_payload(0.71, headline="New"))

    assert second.id == first.id  # same row, updated
    rows = session.execute(select(SentimentDaily)).scalars().all()
    assert len(rows) == 1
    assert rows[0].sentiment_score == 0.71
    assert rows[0].notable_headlines[0]["headline"] == "New"


def _seed(session: Session, ticker: str, as_of: date, score: float) -> None:
    session.add(
        SentimentDaily(
            ticker=ticker,
            as_of=as_of,
            sentiment_score=score,
            sentiment_direction="stable",
            sentiment_delta_7d=None,
            source_breakdown={},
            key_topics=[],
            notable_headlines=[],
        )
    )
    session.commit()


class TestGetScoreNear:
    def test_returns_none_when_no_history(self, session: Session) -> None:
        assert get_score_near(session, "LMT", date(2026, 4, 17)) is None

    def test_exact_match_returns_score(self, session: Session) -> None:
        _seed(session, "LMT", date(2026, 4, 10), 0.42)
        assert get_score_near(session, "LMT", date(2026, 4, 10)) == 0.42

    def test_picks_most_recent_within_window(self, session: Session) -> None:
        _seed(session, "LMT", date(2026, 4, 5), 0.10)
        _seed(session, "LMT", date(2026, 4, 8), 0.30)
        # Target 2026-04-10 with default 7-day window should pick the 04-08 row.
        assert get_score_near(session, "LMT", date(2026, 4, 10)) == 0.30

    def test_excludes_rows_outside_window(self, session: Session) -> None:
        _seed(session, "LMT", date(2026, 3, 20), 0.99)
        # Target 2026-04-10 with 7-day window: 03-20 is way outside.
        assert get_score_near(session, "LMT", date(2026, 4, 10)) is None

    def test_excludes_future_rows(self, session: Session) -> None:
        _seed(session, "LMT", date(2026, 4, 15), 0.50)
        assert get_score_near(session, "LMT", date(2026, 4, 10)) is None

    def test_scopes_by_ticker(self, session: Session) -> None:
        _seed(session, "AAPL", date(2026, 4, 10), 0.77)
        assert get_score_near(session, "LMT", date(2026, 4, 10)) is None
