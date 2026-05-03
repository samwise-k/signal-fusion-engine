"""Custom Textual widgets for SFE TUI."""

from __future__ import annotations

from textual.binding import Binding
from textual.suggester import SuggestFromList
from textual.widgets import Input

from src.tui.commands import COMMAND_NAMES

SUGGESTIONS = [f"/{name}" for name in COMMAND_NAMES]


class CommandInput(Input):
    """Input field with slash-command autocomplete."""

    BINDINGS = [
        Binding("tab", "accept_suggestion", "Accept suggestion", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(
            placeholder="Type a /command or ticker...",
            suggester=SuggestFromList(SUGGESTIONS, case_sensitive=False),
            **kwargs,
        )

    def action_accept_suggestion(self) -> None:
        """Accept the current autocomplete suggestion."""
        if self._suggestion:
            self.value = self._suggestion
            self.cursor_position = len(self.value)
