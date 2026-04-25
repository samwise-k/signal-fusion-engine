"""Rich renderables for TUI output. No Textual dependency — pure Rich."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

CYAN = "cyan"
GREEN = "green"
RED = "red"
YELLOW = "yellow"
DIM = "dim"


def render_earnings_brief(raw_markdown: str, on_date: Date) -> Panel:
    md = Markdown(raw_markdown)
    return Panel(
        md,
        title=f"[{CYAN} bold]Earnings Brief — {on_date.isoformat()}[/]",
        border_style=CYAN,
        padding=(1, 2),
    )


def render_calendar_table(rows: list[dict[str, Any]]) -> Panel:
    if not rows:
        return Panel(
            Text("No watchlist tickers reporting in the next 14 days.", style=DIM),
            title=f"[{CYAN} bold]Earnings Calendar[/]",
            border_style=CYAN,
        )

    table = Table(show_header=True, header_style=f"bold {CYAN}", expand=True)
    table.add_column("Ticker", style="bold")
    table.add_column("Report Date")
    table.add_column("Days Until", justify="right")
    table.add_column("Consensus EPS", justify="right")

    for r in rows:
        days = r["days_until"]
        days_style = RED if days <= 2 else YELLOW if days <= 5 else ""
        eps = f"${r['consensus_eps']:.2f}" if r["consensus_eps"] is not None else "—"

        table.add_row(
            r["ticker"],
            r["date"],
            Text(str(days), style=days_style),
            eps,
        )

    return Panel(
        table,
        title=f"[{CYAN} bold]Earnings Calendar[/]",
        border_style=CYAN,
    )


def render_ticker_card(data: dict[str, Any]) -> Panel:
    ticker = data["ticker"]
    parts: list[Text | str] = []

    sent = data.get("sentiment")
    if sent and sent.get("sentiment_score") is not None:
        score = sent["sentiment_score"]
        direction = sent.get("sentiment_direction", "")
        color = GREEN if score > 0.1 else RED if score < -0.1 else YELLOW
        delta = sent.get("sentiment_delta_7d")
        delta_str = f"  Δ7d: {delta:+.2f}" if delta is not None else ""
        parts.append(Text(f"Sentiment: {score:+.2f} ({direction}){delta_str}", style=color))
    else:
        parts.append(Text("Sentiment: no data", style=DIM))

    quant = data.get("quant")
    if quant and quant.get("health_score"):
        health = quant["health_score"]
        color = GREEN if health == "healthy" else RED if health == "weak" else YELLOW
        close = quant.get("close")
        rsi = quant.get("rsi_14")
        close_str = f"  Close: ${close:.2f}" if close else ""
        rsi_str = f"  RSI: {rsi:.0f}" if rsi else ""
        parts.append(Text(f"Quant: {health}{close_str}{rsi_str}", style=color))
    else:
        parts.append(Text("Quant: no data", style=DIM))

    enrich = data.get("enrichment")
    if enrich:
        insider = enrich.get("insider_trades", {}).get("net_insider_sentiment", "—")
        next_er = enrich.get("next_earnings")
        er_str = next_er["date"] if next_er else "none scheduled"
        analyst = enrich.get("analyst_activity", {}).get("trend", "—")
        parts.append(Text(f"Insider: {insider}  Analyst: {analyst}  Next ER: {er_str}"))
    else:
        parts.append(Text("Enrichment: no data", style=DIM))

    outcome = data.get("latest_outcome")
    if outcome:
        o_color = GREEN if outcome["outcome"] == "correct" else RED if outcome["outcome"] == "incorrect" else YELLOW
        parts.append(Text(
            f"Last call: {outcome['predicted_dir']} ({outcome['conviction']:.1f}) → {outcome['outcome']}",
            style=o_color,
        ))

    body = Text("\n").join(parts)
    return Panel(
        body,
        title=f"[{CYAN} bold]{ticker}[/]",
        border_style=CYAN,
        padding=(0, 2),
    )


def render_progress_step(label: str, status: str = "ok") -> Text:
    if status == "ok":
        return Text(f"  ✓ {label}", style=GREEN)
    elif status == "warn":
        return Text(f"  ⚠ {label}", style=YELLOW)
    elif status == "fail":
        return Text(f"  ✗ {label}", style=RED)
    else:
        return Text(f"  … {label}", style=DIM)


def render_help() -> Panel:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style=f"bold {CYAN}")
    table.add_column("Description")

    commands = [
        ("/earnings <TICKER>", "Generate an earnings context brief"),
        ("/sentiment <TICKER>", "Run sentiment engine (or all watchlist)"),
        ("/quant <TICKER>", "Run quantitative engine (or all watchlist)"),
        ("/enrich <TICKER>", "Run enrichment engine (or all watchlist)"),
        ("/meta <TICKER>", "Run meta-synthesis layer (or all watchlist)"),
        ("/calendar", "Show upcoming earnings for watchlist"),
        ("/log [TICKER]", "Show saved briefs (optionally filter by ticker)"),
        ("/status", "Show database summary"),
        ("/help", "Show this help message"),
        ("/quit", "Exit the TUI"),
        ("TICKER", "Quick-look: show stored data for ticker"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)

    return Panel(
        table,
        title=f"[{CYAN} bold]SFE Commands[/]",
        border_style=CYAN,
    )


def render_brief_log(briefs: list[dict[str, Any]]) -> Panel:
    table = Table(show_header=True, header_style=f"bold {CYAN}", expand=True)
    table.add_column("Date", style="bold")
    table.add_column("Tickers")
    table.add_column("Model", style=DIM)
    table.add_column("Preview")
    table.add_column("Saved At", style=DIM)

    for b in briefs:
        tickers = ", ".join(b["tickers"]) if b["tickers"] else "—"
        table.add_row(
            b["as_of"],
            tickers,
            b["model"],
            Text(b["preview"] + "…", style=DIM),
            b["created_at"],
        )

    return Panel(
        table,
        title=f"[{CYAN} bold]Brief Log ({len(briefs)} saved)[/]",
        border_style=CYAN,
    )


def render_error(message: str) -> Text:
    return Text(f"  ✗ {message}", style=RED)


def render_status(counts: dict[str, int]) -> Panel:
    table = Table(show_header=True, header_style=f"bold {CYAN}", expand=True)
    table.add_column("Table")
    table.add_column("Rows", justify="right")

    for name, count in counts.items():
        table.add_row(name, str(count))

    return Panel(
        table,
        title=f"[{CYAN} bold]Database Status[/]",
        border_style=CYAN,
    )
