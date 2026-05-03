"""Unit tests for TUI command parsing and renderer."""

from __future__ import annotations

from datetime import date

import pytest
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.tui.commands import COMMAND_NAMES, ParsedCommand, parse_input
from src.tui.renderer import (
    render_calendar_table,
    render_earnings_brief,
    render_error,
    render_help,
    render_progress_step,
    render_status,
    render_ticker_card,
)


class TestParseInput:
    def test_slash_earnings_with_ticker(self) -> None:
        result = parse_input("/earnings NVDA")
        assert result == ParsedCommand(name="earnings", args=["NVDA"])

    def test_slash_calendar_no_args(self) -> None:
        result = parse_input("/calendar")
        assert result == ParsedCommand(name="calendar", args=[])

    def test_slash_quit(self) -> None:
        result = parse_input("/quit")
        assert result == ParsedCommand(name="quit", args=[])

    def test_slash_help(self) -> None:
        result = parse_input("/help")
        assert result == ParsedCommand(name="help", args=[])

    def test_unknown_slash_command(self) -> None:
        result = parse_input("/foobar")
        assert result.name == "unknown"
        assert "/foobar" in result.args[0]

    def test_bare_ticker_quicklook(self) -> None:
        result = parse_input("NVDA")
        assert result == ParsedCommand(name="quicklook", args=["NVDA"])

    def test_bare_ticker_lowercase(self) -> None:
        result = parse_input("aapl")
        assert result == ParsedCommand(name="quicklook", args=["AAPL"])

    def test_empty_input(self) -> None:
        result = parse_input("")
        assert result.name == "empty"

    def test_whitespace_only(self) -> None:
        result = parse_input("   ")
        assert result.name == "empty"

    def test_long_string_not_ticker(self) -> None:
        result = parse_input("this is a sentence")
        assert result.name == "unknown"

    def test_earnings_with_date_arg(self) -> None:
        result = parse_input("/earnings NVDA 2026-05-01")
        assert result == ParsedCommand(name="earnings", args=["NVDA", "2026-05-01"])

    def test_case_insensitive_command(self) -> None:
        result = parse_input("/CALENDAR")
        assert result == ParsedCommand(name="calendar", args=[])

    def test_all_command_names_recognized(self) -> None:
        for name in COMMAND_NAMES:
            result = parse_input(f"/{name}")
            assert result.name == name, f"/{name} not recognized"


class TestRenderer:
    def test_render_earnings_brief_returns_panel(self) -> None:
        result = render_earnings_brief("# Test Brief\nSome content", date(2026, 4, 25))
        assert isinstance(result, Panel)

    def test_render_calendar_table_with_rows(self) -> None:
        rows = [
            {"ticker": "NVDA", "date": "2026-04-29", "days_until": 4, "consensus_eps": 3.22},
            {"ticker": "AAPL", "date": "2026-05-01", "days_until": 6, "consensus_eps": 1.58},
        ]
        result = render_calendar_table(rows)
        assert isinstance(result, Panel)

    def test_render_calendar_table_empty(self) -> None:
        result = render_calendar_table([])
        assert isinstance(result, Panel)

    def test_render_calendar_table_none_eps(self) -> None:
        rows = [{"ticker": "XYZ", "date": "2026-05-01", "days_until": 6, "consensus_eps": None}]
        result = render_calendar_table(rows)
        assert isinstance(result, Panel)

    def test_render_ticker_card_with_data(self) -> None:
        data = {
            "ticker": "NVDA",
            "sentiment": {"sentiment_score": 0.45, "sentiment_direction": "bullish", "sentiment_delta_7d": 0.12},
            "quant": {"health_score": "healthy", "close": 850.0, "rsi_14": 62.0},
            "enrichment": {
                "insider_trades": {"net_insider_sentiment": "bullish"},
                "next_earnings": {"date": "2026-04-29"},
                "analyst_activity": {"trend": "upgrade"},
            },
            "latest_outcome": None,
        }
        result = render_ticker_card(data)
        assert isinstance(result, Panel)

    def test_render_ticker_card_no_data(self) -> None:
        data = {
            "ticker": "XYZ",
            "sentiment": None,
            "quant": None,
            "enrichment": None,
            "latest_outcome": None,
        }
        result = render_ticker_card(data)
        assert isinstance(result, Panel)

    def test_render_progress_step_ok(self) -> None:
        result = render_progress_step("Fetching data", "ok")
        assert isinstance(result, Text)
        assert "✓" in str(result)

    def test_render_progress_step_warn(self) -> None:
        result = render_progress_step("Partial data", "warn")
        assert "⚠" in str(result)

    def test_render_progress_step_fail(self) -> None:
        result = render_progress_step("Failed", "fail")
        assert "✗" in str(result)

    def test_render_progress_step_pending(self) -> None:
        result = render_progress_step("Working", "pending")
        assert "…" in str(result)

    def test_render_help_returns_panel(self) -> None:
        result = render_help()
        assert isinstance(result, Panel)

    def test_render_error(self) -> None:
        result = render_error("Something broke")
        assert isinstance(result, Text)
        assert "Something broke" in str(result)

    def test_render_status(self) -> None:
        counts = {"sentiment_daily": 10, "quant_daily": 5}
        result = render_status(counts)
        assert isinstance(result, Panel)
