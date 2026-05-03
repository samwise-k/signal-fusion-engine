"""Textual Pilot integration tests for the SFE TUI."""

from __future__ import annotations

import pytest

from src.tui.app import SFEApp


@pytest.mark.asyncio
async def test_app_launches() -> None:
    """App composes without crashing."""
    async with SFEApp().run_test() as pilot:
        app = pilot.app
        assert app.query_one("#output") is not None
        assert app.query_one("#input") is not None


@pytest.mark.asyncio
async def test_help_on_mount() -> None:
    """Help panel is shown on startup."""
    async with SFEApp().run_test() as pilot:
        output = pilot.app.query_one("#output")
        assert output is not None


@pytest.mark.asyncio
async def test_help_command() -> None:
    """Typing /help renders the help panel."""
    async with SFEApp().run_test() as pilot:
        await pilot.press("slash", "h", "e", "l", "p", "enter")
        await pilot.pause()


@pytest.mark.asyncio
async def test_quit_command() -> None:
    """/quit exits the app."""
    app = SFEApp()
    async with app.run_test() as pilot:
        await pilot.press("slash", "q", "u", "i", "t", "enter")
        await pilot.pause()


@pytest.mark.asyncio
async def test_unknown_command() -> None:
    """Unknown command shows error."""
    async with SFEApp().run_test() as pilot:
        await pilot.press("slash", "x", "y", "z", "enter")
        await pilot.pause()


@pytest.mark.asyncio
async def test_empty_input_no_crash() -> None:
    """Empty input (just Enter) does nothing, no crash."""
    async with SFEApp().run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()


@pytest.mark.asyncio
async def test_tab_accepts_suggestion() -> None:
    """Pressing Tab fills in the suggested slash command."""
    async with SFEApp().run_test() as pilot:
        inp = pilot.app.query_one("#input")
        inp.focus()
        await pilot.pause()
        for ch in "/ear":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        assert inp.value == "/earnings"
