"""Tests for the signal experiment tracking layer (model, repo, scorer, dashboard)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.storage.models import Base, SignalDaily
from src.storage.signal_repo import upsert_signal_daily
from src.tracking.scorer import _classify, compute_stats, score_signal


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def make_signal_data(**overrides) -> dict:
    defaults = {
        "ticker": "NVDA",
        "as_of": "2026-04-20",
        "direction": "bullish",
        "conviction": 0.8,
        "dominant_component": "convergence",
        "reasoning": "Strong alignment across engines",
        "entry_price": 110.0,
        "signal_components": {"sentiment": 0.7, "quant": 0.6},
    }
    defaults.update(overrides)
    return defaults


class TestSignalRepo:
    def test_insert_creates_row(self, session: Session) -> None:
        row = upsert_signal_daily(session, make_signal_data())
        assert row.id is not None
        assert row.ticker == "NVDA"
        assert row.as_of == date(2026, 4, 20)
        assert row.direction == "bullish"
        assert row.conviction == 0.8

    def test_upsert_updates_existing(self, session: Session) -> None:
        upsert_signal_daily(session, make_signal_data(conviction=0.5))
        upsert_signal_daily(session, make_signal_data(conviction=0.9))
        rows = session.execute(select(SignalDaily)).scalars().all()
        assert len(rows) == 1
        assert rows[0].conviction == 0.9

    def test_different_dates_create_separate_rows(self, session: Session) -> None:
        upsert_signal_daily(session, make_signal_data(as_of="2026-04-20"))
        upsert_signal_daily(session, make_signal_data(as_of="2026-04-21"))
        rows = session.execute(select(SignalDaily)).scalars().all()
        assert len(rows) == 2

    def test_different_tickers_create_separate_rows(self, session: Session) -> None:
        upsert_signal_daily(session, make_signal_data(ticker="NVDA"))
        upsert_signal_daily(session, make_signal_data(ticker="AAPL"))
        rows = session.execute(select(SignalDaily)).scalars().all()
        assert len(rows) == 2

    def test_signal_components_stored_as_json(self, session: Session) -> None:
        row = upsert_signal_daily(session, make_signal_data())
        assert row.signal_components == {"sentiment": 0.7, "quant": 0.6}


class TestClassify:
    def test_bullish_win(self):
        assert _classify(0.02, 0.005, "bullish") == "win"

    def test_bullish_loss(self):
        assert _classify(-0.02, 0.005, "bullish") == "loss"

    def test_bearish_win(self):
        assert _classify(-0.02, 0.005, "bearish") == "win"

    def test_bearish_loss(self):
        assert _classify(0.02, 0.005, "bearish") == "loss"

    def test_dead_zone(self):
        assert _classify(0.003, 0.005, "bullish") == "neutral"
        assert _classify(-0.003, 0.005, "bearish") == "neutral"

    def test_neutral_direction(self):
        assert _classify(0.05, 0.005, "neutral") == "neutral"


class TestScoreSignal:
    def test_immature_signal_returns_none(self, session: Session) -> None:
        row = upsert_signal_daily(session, make_signal_data(as_of=date.today().isoformat()))
        result = score_signal(row, today=date.today())
        assert result is None

    @patch("src.tracking.scorer.fetch_close")
    def test_scores_matured_signal(self, mock_fetch, session: Session) -> None:
        signal_date = date.today() - timedelta(days=6)
        row = upsert_signal_daily(session, make_signal_data(
            as_of=signal_date.isoformat(),
            entry_price=100.0,
            direction="bullish",
        ))

        def fake_close(ticker, target_date):
            days_after = (target_date - signal_date).days
            if days_after == 1:
                return 101.0
            if days_after == 3:
                return 103.0
            if days_after == 5:
                return 105.0
            return 100.0

        mock_fetch.side_effect = fake_close
        result = score_signal(row, today=date.today())

        assert result is not None
        assert result["ticker"] == "NVDA"
        assert "1d" in result["horizons"]
        assert "3d" in result["horizons"]
        assert "5d" in result["horizons"]
        assert result["horizons"]["1d"]["outcome"] == "win"
        assert result["horizons"]["5d"]["outcome"] == "win"
        assert result["horizons"]["5d"]["return"] == pytest.approx(0.05)

    @patch("src.tracking.scorer.fetch_close")
    def test_bearish_signal_scored_correctly(self, mock_fetch, session: Session) -> None:
        signal_date = date.today() - timedelta(days=6)
        row = upsert_signal_daily(session, make_signal_data(
            as_of=signal_date.isoformat(),
            entry_price=100.0,
            direction="bearish",
        ))
        mock_fetch.return_value = 95.0
        result = score_signal(row, today=date.today())
        assert result["horizons"]["5d"]["outcome"] == "win"


class TestComputeStats:
    def test_empty_input(self):
        stats = compute_stats([])
        assert stats["total_signals"] == 0
        assert stats["by_horizon"]["5d"]["n"] == 0

    def test_stats_from_scored(self):
        scored = [
            {
                "ticker": "NVDA", "as_of": "2026-04-15", "direction": "bullish",
                "conviction": 0.8, "dominant_component": "convergence", "entry_price": 100,
                "horizons": {
                    "1d": {"close": 101, "return": 0.01, "outcome": "win"},
                    "5d": {"close": 103, "return": 0.03, "outcome": "win"},
                },
            },
            {
                "ticker": "AAPL", "as_of": "2026-04-15", "direction": "bearish",
                "conviction": 0.4, "dominant_component": "sentiment", "entry_price": 200,
                "horizons": {
                    "1d": {"close": 202, "return": 0.01, "outcome": "loss"},
                    "5d": {"close": 205, "return": 0.025, "outcome": "loss"},
                },
            },
        ]
        stats = compute_stats(scored)
        assert stats["total_signals"] == 2
        assert stats["by_horizon"]["1d"]["wins"] == 1
        assert stats["by_horizon"]["1d"]["losses"] == 1
        assert stats["by_conviction"]["high (>=0.7)"]["n"] == 1
        assert stats["by_conviction"]["low (<0.5)"]["n"] == 1
        assert stats["by_component"]["convergence"]["n"] == 1
        assert stats["by_component"]["sentiment"]["n"] == 1


class TestDashboard:
    def test_render_produces_html(self, session: Session, tmp_path) -> None:
        from pathlib import Path
        from src.tracking.dashboard import render

        output = tmp_path / "test_dashboard.html"
        with patch("src.tracking.dashboard.score_all", return_value=[]):
            result = render(session, today=date.today(), output_path=output)

        assert result == output
        assert output.exists()
        html = output.read_text()
        assert "Signal Experiment Dashboard" in html
        assert "0 signals scored" in html

    def test_kill_indicator_collecting(self):
        from src.tracking.dashboard import _kill_indicator

        stats = {"by_horizon": {"5d": {"n": 5, "ev": 0.001, "accuracy": None}}}
        ki = _kill_indicator(stats)
        assert ki["color"] == "yellow"

    def test_kill_indicator_red(self):
        from src.tracking.dashboard import _kill_indicator

        stats = {"by_horizon": {"5d": {"n": 100, "ev": -0.005, "accuracy": 0.4}}}
        ki = _kill_indicator(stats)
        assert ki["color"] == "red"

    def test_kill_indicator_green(self):
        from src.tracking.dashboard import _kill_indicator

        stats = {"by_horizon": {"5d": {"n": 50, "ev": 0.005, "accuracy": 0.6}}}
        ki = _kill_indicator(stats)
        assert ki["color"] == "green"
