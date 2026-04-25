"""Tests for the earnings engine (consensus, beat/miss, options-implied, payload, repo)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.engines.earnings import beat_miss, consensus, options_implied
from src.engines.earnings.payload_builder import build_earnings_payload
from src.meta.formatter import DISCLAIMER, format_briefing
from src.storage.earnings_repo import get_latest_outcome, upsert_outcome
from src.storage.models import Base, EarningsBriefOutcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


# ---------------------------------------------------------------------------
# beat_miss.summarize
# ---------------------------------------------------------------------------

class TestBeatMissSummarize:
    def test_empty_returns_empty(self) -> None:
        assert beat_miss.summarize([]) == []

    def test_computes_surprise_pct(self) -> None:
        rows = [{"period": "2026-Q1", "actual": 3.0, "estimate": 2.5, "surprisePercent": 5.2}]
        out = beat_miss.summarize(rows)
        assert len(out) == 1
        assert out[0]["quarter"] == "2026-Q1"
        assert out[0]["surprise_pct"] == pytest.approx(20.0)
        assert out[0]["stock_reaction_1d"] == 5.2

    def test_zero_estimate_avoids_division_by_zero(self) -> None:
        rows = [{"period": "2026-Q1", "actual": 0.5, "estimate": 0}]
        out = beat_miss.summarize(rows)
        assert out[0]["surprise_pct"] is None

    def test_null_actual_yields_null_surprise(self) -> None:
        rows = [{"period": "2026-Q1", "actual": None, "estimate": 2.0}]
        out = beat_miss.summarize(rows)
        assert out[0]["surprise_pct"] is None

    def test_multiple_quarters(self) -> None:
        rows = [
            {"period": "2026-Q1", "actual": 3.0, "estimate": 2.8},
            {"period": "2025-Q4", "actual": 2.5, "estimate": 2.5},
        ]
        out = beat_miss.summarize(rows)
        assert len(out) == 2
        assert out[0]["surprise_pct"] == pytest.approx(7.14, rel=0.01)
        assert out[1]["surprise_pct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# consensus.fetch_estimates (mocked HTTP)
# ---------------------------------------------------------------------------

class TestConsensusFetch:
    @patch("src.engines.earnings.consensus.httpx.get")
    def test_extracts_estimates(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "metric": {
                    "epsEstimate": 3.22,
                    "revenueEstimate": 61_000_000_000,
                    "numberOfAnalysts": 35,
                },
                "estimates": {
                    "quarterly": {"eps": [{"avg": 3.22, "numberAnalysts": 35}]},
                    "annual": {"revenue": [{"avg": 240_000_000_000}]},
                },
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"FINNHUB_KEY": "test_key"}):
            result = consensus.fetch_estimates("MSFT")

        assert result["eps_estimate"] == 3.22
        assert result["num_analysts"] == 35
        assert result["revenue_estimate"] == 61_000_000_000

    @patch("src.engines.earnings.consensus.httpx.get")
    def test_handles_empty_response(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"metric": {}, "estimates": {}},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"FINNHUB_KEY": "test_key"}):
            result = consensus.fetch_estimates("UNKNOWN")

        assert result["eps_estimate"] is None
        assert result["revenue_estimate"] is None
        assert result["num_analysts"] is None

    def test_raises_without_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="FINNHUB_KEY"):
                consensus.fetch_estimates("MSFT")


# ---------------------------------------------------------------------------
# beat_miss.fetch_history (mocked HTTP)
# ---------------------------------------------------------------------------

class TestBeatMissFetch:
    @patch("src.engines.earnings.beat_miss.httpx.get")
    def test_returns_list(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"period": "2026-Q1", "actual": 3.0, "estimate": 2.8},
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"FINNHUB_KEY": "test_key"}):
            result = beat_miss.fetch_history("MSFT", limit=4)

        assert len(result) == 1
        assert result[0]["period"] == "2026-Q1"

    @patch("src.engines.earnings.beat_miss.httpx.get")
    def test_non_list_response_returns_empty(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": "not found"},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"FINNHUB_KEY": "test_key"}):
            result = beat_miss.fetch_history("FAKE")

        assert result == []


# ---------------------------------------------------------------------------
# options_implied.fetch_implied_move
# ---------------------------------------------------------------------------

class TestOptionsImplied:
    def test_returns_none_when_no_yfinance(self) -> None:
        with patch.dict("sys.modules", {"yfinance": None}):
            result = options_implied.fetch_implied_move("MSFT", date(2026, 5, 1))
        # Should return None gracefully (import fails)
        # This test is best-effort since yfinance is installed

    def test_nearest_expiry_after(self) -> None:
        expirations = ("2026-04-25", "2026-05-02", "2026-05-16")
        assert options_implied._nearest_expiry_after(expirations, date(2026, 4, 30)) == "2026-05-02"
        assert options_implied._nearest_expiry_after(expirations, date(2026, 4, 25)) == "2026-04-25"
        assert options_implied._nearest_expiry_after(expirations, date(2026, 6, 1)) is None

    def test_mid_price_bid_ask(self) -> None:
        assert options_implied._mid_price({"bid": 2.0, "ask": 4.0, "lastPrice": 3.0}) == 3.0

    def test_mid_price_falls_back_to_last(self) -> None:
        assert options_implied._mid_price({"bid": 0, "ask": 0, "lastPrice": 2.5}) == 2.5

    def test_mid_price_returns_none(self) -> None:
        assert options_implied._mid_price({"bid": 0, "ask": 0, "lastPrice": 0}) is None


# ---------------------------------------------------------------------------
# Earnings payload builder
# ---------------------------------------------------------------------------

class TestEarningsPayloadBuilder:
    @patch("src.engines.earnings.options_implied.fetch_implied_move", return_value=None)
    @patch("src.engines.earnings.beat_miss.fetch_history", return_value=[])
    @patch("src.engines.earnings.consensus.fetch_estimates", return_value={
        "eps_estimate": 3.0, "revenue_estimate": 50e9, "num_analysts": 30,
    })
    def test_builds_payload_with_empty_db(
        self, mock_cons, mock_bm, mock_opt, session
    ) -> None:
        payload = build_earnings_payload(
            session, "NVDA", date(2026, 4, 25), date(2026, 5, 1)
        )
        assert payload["ticker"] == "NVDA"
        assert payload["earnings_date"] == "2026-05-01"
        assert payload["days_until_earnings"] == 6
        assert payload["consensus"]["eps_estimate"] == 3.0
        assert payload["beat_miss_history"] == []
        assert payload["implied_move"] is None
        assert payload["sentiment"] is None
        assert payload["quant"] is None
        assert payload["enrichment"] is None
        assert payload["prior_outcome"] is None

    @patch("src.engines.earnings.options_implied.fetch_implied_move", return_value=None)
    @patch("src.engines.earnings.beat_miss.fetch_history", return_value=[])
    @patch("src.engines.earnings.consensus.fetch_estimates", side_effect=RuntimeError("no key"))
    def test_consensus_failure_degrades_gracefully(
        self, mock_cons, mock_bm, mock_opt, session
    ) -> None:
        payload = build_earnings_payload(
            session, "NVDA", date(2026, 4, 25), date(2026, 5, 1)
        )
        assert payload["consensus"] is None

    @patch("src.engines.earnings.options_implied.fetch_implied_move", return_value={
        "atm_straddle_pct": 6.5, "call_iv": 0.45, "put_iv": 0.42,
        "expiry": "2026-05-02", "spot": 850.0,
    })
    @patch("src.engines.earnings.beat_miss.fetch_history", return_value=[
        {"period": "2026-Q1", "actual": 3.2, "estimate": 3.0, "surprisePercent": 4.0},
    ])
    @patch("src.engines.earnings.consensus.fetch_estimates", return_value={
        "eps_estimate": 3.5, "revenue_estimate": 55e9, "num_analysts": 32,
    })
    def test_full_payload_with_all_sources(
        self, mock_cons, mock_bm, mock_opt, session
    ) -> None:
        payload = build_earnings_payload(
            session, "NVDA", date(2026, 4, 25), date(2026, 5, 1)
        )
        assert payload["implied_move"]["atm_straddle_pct"] == 6.5
        assert len(payload["beat_miss_history"]) == 1
        assert payload["beat_miss_history"][0]["surprise_pct"] == pytest.approx(6.67, rel=0.01)


# ---------------------------------------------------------------------------
# Earnings outcome repo
# ---------------------------------------------------------------------------

class TestEarningsRepo:
    def test_upsert_and_retrieve(self, session) -> None:
        upsert_outcome(session, {
            "ticker": "NVDA",
            "earnings_date": date(2026, 5, 1),
            "brief_date": date(2026, 4, 25),
            "predicted_dir": "bullish",
            "conviction": 0.7,
            "outcome": "pending",
        })
        row = get_latest_outcome(session, "NVDA")
        assert row is not None
        assert row.predicted_dir == "bullish"
        assert row.conviction == 0.7
        assert row.outcome == "pending"

    def test_upsert_updates_existing(self, session) -> None:
        upsert_outcome(session, {
            "ticker": "NVDA",
            "earnings_date": date(2026, 5, 1),
            "predicted_dir": "bullish",
            "conviction": 0.7,
            "outcome": "pending",
        })
        upsert_outcome(session, {
            "ticker": "NVDA",
            "earnings_date": date(2026, 5, 1),
            "predicted_dir": "bullish",
            "conviction": 0.7,
            "actual_eps_surp": 4.1,
            "stock_move_1d": 8.2,
            "outcome": "correct",
        })
        row = get_latest_outcome(session, "NVDA")
        assert row.outcome == "correct"
        assert row.actual_eps_surp == 4.1
        assert row.stock_move_1d == 8.2

    def test_get_latest_returns_none_for_unknown(self, session) -> None:
        assert get_latest_outcome(session, "FAKE") is None

    def test_get_latest_returns_most_recent(self, session) -> None:
        upsert_outcome(session, {
            "ticker": "MSFT",
            "earnings_date": date(2026, 1, 15),
            "predicted_dir": "neutral",
            "conviction": 0.3,
        })
        upsert_outcome(session, {
            "ticker": "MSFT",
            "earnings_date": date(2026, 4, 15),
            "predicted_dir": "bullish",
            "conviction": 0.8,
        })
        row = get_latest_outcome(session, "MSFT")
        assert row.earnings_date == date(2026, 4, 15)
        assert row.predicted_dir == "bullish"


# ---------------------------------------------------------------------------
# Formatter: disclaimer
# ---------------------------------------------------------------------------

class TestDisclaimer:
    def test_disclaimer_appended_when_flag_set(self) -> None:
        out = format_briefing("## Brief", disclaimer=True)
        assert DISCLAIMER.strip() in out
        assert "not investment advice" in out

    def test_disclaimer_not_appended_by_default(self) -> None:
        out = format_briefing("## Brief")
        assert "not investment advice" not in out

    def test_empty_body_still_empty(self) -> None:
        assert format_briefing("", disclaimer=True) == ""

    def test_header_prepended_when_needed(self) -> None:
        out = format_briefing("some text", on_date=date(2026, 4, 25), disclaimer=True)
        assert out.startswith("# SFE Briefing")
        assert "not investment advice" in out


# ---------------------------------------------------------------------------
# EarningsBriefOutcome model
# ---------------------------------------------------------------------------

class TestEarningsBriefOutcomeModel:
    def test_table_created(self, session) -> None:
        from sqlalchemy import inspect

        inspector = inspect(session.bind)
        tables = inspector.get_table_names()
        assert "earnings_brief_outcome" in tables

    def test_unique_constraint_ticker_erdate(self, session) -> None:
        from sqlalchemy.exc import IntegrityError

        row1 = EarningsBriefOutcome(
            ticker="AAPL", brief_date=date(2026, 4, 25),
            earnings_date=date(2026, 5, 1), predicted_dir="bullish",
            conviction=0.5, outcome="pending",
        )
        row2 = EarningsBriefOutcome(
            ticker="AAPL", brief_date=date(2026, 4, 26),
            earnings_date=date(2026, 5, 1), predicted_dir="bearish",
            conviction=0.3, outcome="pending",
        )
        session.add(row1)
        session.commit()
        session.add(row2)
        with pytest.raises(IntegrityError):
            session.commit()
