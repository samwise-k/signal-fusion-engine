"""Tests for the enrichment engine (insider trades, earnings, analyst revisions)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.engines.enrichment import (
    aggregator,
    analyst_revisions,
    event_calendar,
    insider_trades,
)
from src.storage.enrichment_repo import upsert_enrichment_daily
from src.storage.models import Base, EnrichmentDaily


class TestInsiderSummarize:
    def test_empty_is_neutral(self) -> None:
        out = insider_trades.summarize([])
        assert out["net_insider_sentiment"] == "neutral"
        assert out["recent_filings"] == []
        assert out["buy_value"] == 0.0

    def test_net_buy_is_bullish(self) -> None:
        txns = [
            {"transactionCode": "P", "change": 1000, "transactionPrice": 50.0,
             "name": "J. Doe", "filingDate": "2026-04-10", "transactionDate": "2026-04-08"},
            {"transactionCode": "S", "change": -100, "transactionPrice": 48.0,
             "name": "J. Smith", "filingDate": "2026-04-09", "transactionDate": "2026-04-07"},
        ]
        out = insider_trades.summarize(txns)
        assert out["net_insider_sentiment"] == "bullish"
        assert out["buy_value"] == 50000.0
        assert out["sell_value"] == 4800.0

    def test_net_sell_is_bearish(self) -> None:
        txns = [
            {"transactionCode": "S", "change": -5000, "transactionPrice": 100.0},
            {"transactionCode": "P", "change": 100, "transactionPrice": 100.0},
        ]
        out = insider_trades.summarize(txns)
        assert out["net_insider_sentiment"] == "bearish"

    def test_non_open_market_codes_ignored_for_net(self) -> None:
        # Grants (A), exercises (M) shouldn't swing net sentiment.
        txns = [
            {"transactionCode": "A", "change": 100000, "transactionPrice": 50.0},
            {"transactionCode": "M", "change": 5000, "transactionPrice": 50.0},
        ]
        out = insider_trades.summarize(txns)
        assert out["net_insider_sentiment"] == "neutral"
        assert out["buy_value"] == 0.0
        assert out["sell_value"] == 0.0
        # But they still appear in recent_filings as type "other".
        assert all(r["type"] == "other" for r in out["recent_filings"])

    def test_recent_filings_sorted_desc_and_capped(self) -> None:
        txns = [
            {"transactionCode": "P", "change": 1, "transactionPrice": 1.0,
             "filingDate": f"2026-04-{d:02d}"}
            for d in range(1, 10)
        ]
        out = insider_trades.summarize(txns)
        assert len(out["recent_filings"]) == 5
        assert out["recent_filings"][0]["filing_date"] == "2026-04-09"


class TestEarningsSummarize:
    ON = date(2026, 4, 18)

    def test_empty_returns_none_next(self) -> None:
        out = event_calendar.summarize([], self.ON)
        assert out["next_earnings"] is None
        assert out["upcoming_events"] == []

    def test_past_earnings_excluded(self) -> None:
        rows = [{"date": "2026-04-10", "epsEstimate": 1.0}]
        out = event_calendar.summarize(rows, self.ON)
        assert out["next_earnings"] is None

    def test_picks_soonest_future(self) -> None:
        rows = [
            {"date": "2026-05-01", "epsEstimate": 2.0},
            {"date": "2026-04-22", "epsEstimate": 1.5, "hour": "amc"},
        ]
        out = event_calendar.summarize(rows, self.ON)
        assert out["next_earnings"]["date"] == "2026-04-22"
        assert out["next_earnings"]["days_until"] == 4

    def test_malformed_dates_skipped(self) -> None:
        rows = [{"date": "not-a-date"}, {"date": "2026-04-25"}]
        out = event_calendar.summarize(rows, self.ON)
        assert out["next_earnings"]["date"] == "2026-04-25"


class TestAnalystSummarize:
    def test_empty_trend_stable(self) -> None:
        out = analyst_revisions.summarize([])
        assert out["trend"] == "stable"
        assert out["latest_period"] is None

    def test_single_row_is_stable(self) -> None:
        rows = [{"period": "2026-04-01", "strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0}]
        out = analyst_revisions.summarize(rows)
        assert out["trend"] == "stable"
        assert out["strong_buy"] == 5

    def test_detects_upgrade(self) -> None:
        rows = [
            {"period": "2026-04-01", "strongBuy": 8, "buy": 10, "hold": 3, "sell": 0, "strongSell": 0},
            {"period": "2026-03-01", "strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
        ]
        out = analyst_revisions.summarize(rows)
        assert out["trend"] == "upgrade"

    def test_detects_downgrade(self) -> None:
        rows = [
            {"period": "2026-04-01", "strongBuy": 2, "buy": 5, "hold": 8, "sell": 5, "strongSell": 2},
            {"period": "2026-03-01", "strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
        ]
        out = analyst_revisions.summarize(rows)
        assert out["trend"] == "downgrade"

    def test_before_date_filters_post_earnings_periods(self) -> None:
        rows = [
            {"period": "2026-05-01", "strongBuy": 2, "buy": 2, "hold": 8, "sell": 5, "strongSell": 3},
            {"period": "2026-04-01", "strongBuy": 8, "buy": 10, "hold": 3, "sell": 0, "strongSell": 0},
            {"period": "2026-03-01", "strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
        ]
        out = analyst_revisions.summarize(rows, before_date=date(2026, 4, 22))
        assert out["latest_period"] == "2026-04-01"
        assert out["trend"] == "upgrade"

    def test_before_date_all_filtered_returns_stable(self) -> None:
        rows = [
            {"period": "2026-05-01", "strongBuy": 10, "buy": 10, "hold": 0, "sell": 0, "strongSell": 0},
        ]
        out = analyst_revisions.summarize(rows, before_date=date(2026, 4, 22))
        assert out["trend"] == "stable"
        assert out["latest_period"] is None


class TestAggregate:
    ON = date(2026, 4, 18)

    def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            insider_trades, "fetch_transactions",
            lambda t, d, **k: [{"transactionCode": "P", "change": 1000, "transactionPrice": 50.0,
                                "name": "X", "filingDate": "2026-04-10"}],
        )
        monkeypatch.setattr(
            event_calendar, "fetch_earnings",
            lambda t, d, **k: [{"date": "2026-04-22", "epsEstimate": 1.5}],
        )
        monkeypatch.setattr(
            analyst_revisions, "fetch_recommendations",
            lambda t: [
                {"period": "2026-04-01", "strongBuy": 10, "buy": 10, "hold": 2, "sell": 0, "strongSell": 0},
                {"period": "2026-03-01", "strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
            ],
        )
        payload = aggregator.aggregate("NVDA", self.ON)

        assert payload["ticker"] == "NVDA"
        assert payload["insider_trades"]["net_insider_sentiment"] == "bullish"
        assert payload["next_earnings"]["date"] == "2026-04-22"
        assert payload["analyst_activity"]["trend"] == "upgrade"

    def test_all_sources_failing_degrades_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a, **k):
            raise RuntimeError("API down")

        monkeypatch.setattr(insider_trades, "fetch_transactions", boom)
        monkeypatch.setattr(event_calendar, "fetch_earnings", boom)
        monkeypatch.setattr(analyst_revisions, "fetch_recommendations", boom)

        payload = aggregator.aggregate("NVDA", self.ON)
        assert payload["insider_trades"]["net_insider_sentiment"] == "neutral"
        assert payload["next_earnings"] is None
        assert payload["analyst_activity"]["trend"] == "stable"

    def test_earnings_date_windows_insider_lookback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_fetch_txns(ticker, on_date, **kw):
            captured["insider_end"] = on_date
            return [{"transactionCode": "P", "change": 100, "transactionPrice": 50.0}]

        monkeypatch.setattr(insider_trades, "fetch_transactions", fake_fetch_txns)
        monkeypatch.setattr(
            event_calendar, "fetch_earnings",
            lambda t, d, **k: [{"date": "2026-04-22", "epsEstimate": 1.5}],
        )
        monkeypatch.setattr(analyst_revisions, "fetch_recommendations", lambda t: [])

        aggregator.aggregate("NVDA", self.ON)
        assert captured["insider_end"] == date(2026, 4, 22)

    def test_explicit_earnings_date_overrides_calendar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_fetch_txns(ticker, on_date, **kw):
            captured["insider_end"] = on_date
            return []

        monkeypatch.setattr(insider_trades, "fetch_transactions", fake_fetch_txns)
        monkeypatch.setattr(
            event_calendar, "fetch_earnings",
            lambda t, d, **k: [{"date": "2026-04-22", "epsEstimate": 1.5}],
        )
        monkeypatch.setattr(analyst_revisions, "fetch_recommendations", lambda t: [])

        aggregator.aggregate("NVDA", self.ON, earnings_date=date(2026, 5, 1))
        assert captured["insider_end"] == date(2026, 5, 1)

    def test_no_earnings_falls_back_to_on_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_fetch_txns(ticker, on_date, **kw):
            captured["insider_end"] = on_date
            return []

        monkeypatch.setattr(insider_trades, "fetch_transactions", fake_fetch_txns)
        monkeypatch.setattr(event_calendar, "fetch_earnings", lambda t, d, **k: [])
        monkeypatch.setattr(analyst_revisions, "fetch_recommendations", lambda t: [])

        aggregator.aggregate("NVDA", self.ON)
        assert captured["insider_end"] == self.ON

    def test_partial_failure_preserves_working_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            insider_trades, "fetch_transactions",
            lambda t, d, **k: [{"transactionCode": "P", "change": 500, "transactionPrice": 100.0}],
        )
        monkeypatch.setattr(
            event_calendar, "fetch_earnings",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Finnhub down")),
        )
        monkeypatch.setattr(analyst_revisions, "fetch_recommendations", lambda t: [])

        payload = aggregator.aggregate("NVDA", self.ON)
        assert payload["insider_trades"]["net_insider_sentiment"] == "bullish"
        assert payload["next_earnings"] is None


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


class TestUpsertEnrichmentDaily:
    def _payload(self, **overrides) -> dict:
        base = {
            "ticker": "NVDA",
            "date": "2026-04-18",
            "insider_trades": {"net_insider_sentiment": "bullish", "buy_value": 1.0,
                               "sell_value": 0.0, "recent_filings": []},
            "next_earnings": {"date": "2026-04-22", "days_until": 4},
            "upcoming_events": [{"date": "2026-04-22", "days_until": 4}],
            "analyst_activity": {"trend": "upgrade"},
        }
        base.update(overrides)
        return base

    def test_insert_creates_row(self, session: Session) -> None:
        row = upsert_enrichment_daily(session, self._payload())
        assert row.id is not None
        assert row.insider_trades["net_insider_sentiment"] == "bullish"
        assert row.next_earnings["date"] == "2026-04-22"

    def test_upsert_replaces_existing(self, session: Session) -> None:
        first = upsert_enrichment_daily(session, self._payload())
        second = upsert_enrichment_daily(
            session,
            self._payload(insider_trades={"net_insider_sentiment": "bearish",
                                          "buy_value": 0, "sell_value": 1,
                                          "recent_filings": []}),
        )
        assert second.id == first.id
        rows = session.execute(select(EnrichmentDaily)).scalars().all()
        assert len(rows) == 1
        assert rows[0].insider_trades["net_insider_sentiment"] == "bearish"
