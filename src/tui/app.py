"""SFE Textual TUI application."""

from __future__ import annotations

import os
from datetime import date as Date
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, RichLog

from src.tui.commands import ParsedCommand, parse_input
from src.tui.widgets import CommandInput

HISTORY_FILE = Path.home() / ".sfe_history"
MIN_WIDTH = 80


class SFEApp(App):
    """Signal Fusion Engine — interactive TUI."""

    TITLE = "SFE — Signal Fusion Engine"
    CSS = """
    CommandInput {
        dock: bottom;
        margin: 0 1;
    }
    RichLog {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._load_history()

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(highlight=True, markup=True, wrap=True, id="output")
        yield CommandInput(id="input")
        yield Footer()

    def on_mount(self) -> None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 120
        if width < MIN_WIDTH:
            log = self.query_one("#output", RichLog)
            from src.tui.renderer import render_error
            log.write(render_error(
                f"Terminal is {width} columns wide. SFE needs at least {MIN_WIDTH}. "
                "Resize your terminal for the best experience."
            ))

        log = self.query_one("#output", RichLog)
        from src.tui.renderer import render_help
        log.write(render_help())

    def on_input_submitted(self, event: CommandInput.Submitted) -> None:
        raw = event.value
        input_widget = self.query_one("#input", CommandInput)
        input_widget.value = ""

        if not raw.strip():
            return

        self._append_history(raw.strip())
        cmd = parse_input(raw)

        log = self.query_one("#output", RichLog)
        from src.tui.renderer import render_progress_step
        log.write(render_progress_step(f"Running: {raw.strip()}", status="pending"))

        if cmd.name == "quit":
            self.exit()
            return
        elif cmd.name == "help":
            from src.tui.renderer import render_help
            log.write(render_help())
            return
        elif cmd.name == "empty":
            return
        elif cmd.name == "unknown":
            from src.tui.renderer import render_error
            log.write(render_error(f"Unknown command: {cmd.args[0]}. Type /help for commands."))
            return

        self._run_command(cmd)

    @work(thread=True)
    def _run_command(self, cmd: ParsedCommand) -> None:
        """Execute command in a worker thread to keep UI responsive."""
        from src.tui import renderer

        on_date = Date.today()
        result: dict[str, Any]

        try:
            session = self._get_session()

            if cmd.name == "earnings":
                result = self._exec_earnings(cmd.args, on_date, session)
            elif cmd.name == "sentiment":
                result = self._exec_sentiment(cmd.args, on_date, session)
            elif cmd.name == "quant":
                result = self._exec_quant(cmd.args, on_date, session)
            elif cmd.name in ("enrich", "enrichment"):
                result = self._exec_enrichment(cmd.args, on_date, session)
            elif cmd.name == "meta":
                result = self._exec_meta(cmd.args, on_date, session)
            elif cmd.name == "calendar":
                result = self._exec_calendar(on_date)
            elif cmd.name == "status":
                result = self._exec_status(session)
            elif cmd.name == "quicklook":
                result = self._exec_quicklook(cmd.args[0], on_date, session)
            elif cmd.name == "log":
                result = self._exec_log(cmd.args, session)
            else:
                result = {"type": "error", "message": f"Command not implemented: {cmd.name}"}

            session.close()
        except Exception as exc:
            result = {"type": "error", "message": str(exc)}

        self.call_from_thread(self._render_result, result)

    def _render_result(self, result: dict[str, Any]) -> None:
        from src.tui import renderer

        log = self.query_one("#output", RichLog)

        rtype = result.get("type", "error")

        if rtype == "error":
            log.write(renderer.render_error(result["message"]))
        elif rtype == "earnings_brief":
            log.write(renderer.render_progress_step("Earnings brief generated ✦ saved", "ok"))
            log.write(renderer.render_earnings_brief(result["brief"], Date.today()))
        elif rtype == "meta":
            log.write(renderer.render_progress_step("Meta brief generated ✦ saved", "ok"))
            log.write(renderer.render_earnings_brief(result["brief"], Date.today()))
        elif rtype == "brief_log":
            log.write(renderer.render_brief_log(result["briefs"]))
        elif rtype == "calendar":
            log.write(renderer.render_progress_step("Calendar loaded", "ok"))
            log.write(renderer.render_calendar_table(result["rows"]))
        elif rtype == "quicklook":
            log.write(renderer.render_ticker_card(result["data"]))
        elif rtype == "status":
            log.write(renderer.render_status(result["counts"]))
        elif rtype in ("sentiment", "quant", "enrichment"):
            results = result.get("results", [])
            ok = sum(1 for r in results if "error" not in r)
            fail = sum(1 for r in results if "error" in r)
            if ok:
                log.write(renderer.render_progress_step(f"{rtype}: {ok} ticker(s) processed", "ok"))
            if fail:
                log.write(renderer.render_progress_step(f"{rtype}: {fail} ticker(s) failed", "warn"))
            for r in results:
                if "error" in r:
                    log.write(renderer.render_error(f"{r['ticker']}: {r['error']}"))
        else:
            log.write(renderer.render_progress_step(f"Done ({rtype})", "ok"))

    def _get_session(self):
        from dotenv import load_dotenv
        from src.storage.db import get_engine, get_session
        from src.storage.models import Base

        load_dotenv()
        engine = get_engine()
        db_path = engine.url.database
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(engine)
        return get_session()

    def _exec_earnings(self, args, on_date, session):
        from src.tui.commands import execute_earnings
        return execute_earnings(args, on_date, session)

    def _exec_sentiment(self, args, on_date, session):
        from src.tui.commands import execute_sentiment
        return execute_sentiment(args, on_date, session)

    def _exec_quant(self, args, on_date, session):
        from src.tui.commands import execute_quant
        return execute_quant(args, on_date, session)

    def _exec_enrichment(self, args, on_date, session):
        from src.tui.commands import execute_enrichment
        return execute_enrichment(args, on_date, session)

    def _exec_meta(self, args, on_date, session):
        from src.tui.commands import execute_meta
        return execute_meta(args, on_date, session)

    def _exec_calendar(self, on_date):
        from src.tui.commands import execute_calendar
        return execute_calendar(on_date)

    def _exec_status(self, session):
        from src.tui.commands import execute_status
        return execute_status(session)

    def _exec_log(self, args, session):
        from src.tui.commands import execute_log
        return execute_log(args, session)

    def _exec_quicklook(self, ticker, on_date, session):
        from src.tui.commands import execute_quicklook
        return execute_quicklook(ticker, on_date, session)

    def _load_history(self) -> None:
        if HISTORY_FILE.exists():
            try:
                self._history = HISTORY_FILE.read_text().strip().splitlines()[-100:]
            except Exception:
                pass

    def _append_history(self, line: str) -> None:
        self._history.append(line)
        try:
            with HISTORY_FILE.open("a") as f:
                f.write(line + "\n")
        except Exception:
            pass
