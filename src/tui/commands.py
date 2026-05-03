"""TUI command parsing and dispatch to core.py functions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

COMMAND_NAMES = [
    "earnings", "sentiment", "quant", "enrich", "meta",
    "calendar", "log", "status", "help", "quit",
]


@dataclass
class ParsedCommand:
    name: str
    args: list[str]


def parse_input(raw: str) -> ParsedCommand:
    text = raw.strip()
    if not text:
        return ParsedCommand(name="empty", args=[])

    if text.startswith("/"):
        parts = text[1:].split()
        name = parts[0].lower() if parts else ""
        args = parts[1:]
        if name in COMMAND_NAMES:
            return ParsedCommand(name=name, args=args)
        return ParsedCommand(name="unknown", args=[text])

    if re.match(r"^[A-Za-z]{1,10}$", text):
        return ParsedCommand(name="quicklook", args=[text.upper()])

    return ParsedCommand(name="unknown", args=[text])


def execute_sentiment(args: list[str], on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import run_sentiment

    tickers = _ticker_from_args_or_watchlist(args)
    results = run_sentiment(tickers, on_date, session)
    return {"type": "sentiment", "results": results}


def execute_quant(args: list[str], on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import run_quant
    from src.config import load_watchlist

    if args:
        ticker = args[0].upper()
        watchlist = load_watchlist()
        sector = next(
            (t.get("sector") for t in watchlist if t["ticker"].upper() == ticker), None
        )
        entries = [{"ticker": ticker, "sector": sector}]
    else:
        entries = load_watchlist()
        if not entries:
            return {"type": "error", "message": "Watchlist is empty."}

    results = run_quant(entries, on_date, session)
    return {"type": "quant", "results": results}


def execute_enrichment(args: list[str], on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import run_enrichment

    tickers = _ticker_from_args_or_watchlist(args)
    results = run_enrichment(tickers, on_date, session)
    return {"type": "enrichment", "results": results}


def execute_meta(args: list[str], on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import run_meta

    tickers = _ticker_from_args_or_watchlist(args)
    result = run_meta(tickers, on_date, session)
    _save_brief(session, on_date, tickers, result)
    return {"type": "meta", "brief": result}


def execute_earnings(args: list[str], on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import run_earnings_brief

    if not args:
        return {"type": "error", "message": "Usage: /earnings <TICKER>"}

    ticker = args[0].upper()
    earnings_date = None
    if len(args) > 1:
        try:
            earnings_date = Date.fromisoformat(args[1])
        except ValueError:
            return {"type": "error", "message": f"Invalid date: {args[1]}"}

    result = run_earnings_brief(ticker, on_date, session, earnings_date=earnings_date)
    _save_brief(session, on_date, [ticker], result)
    return {"type": "earnings_brief", "brief": result}


def execute_calendar(on_date: Date) -> dict[str, Any]:
    from src.core import earnings_calendar

    rows = earnings_calendar(on_date)
    return {"type": "calendar", "rows": rows}


def execute_quicklook(ticker: str, on_date: Date, session: Session) -> dict[str, Any]:
    from src.core import get_ticker_summary

    data = get_ticker_summary(ticker, on_date, session)
    has_data = any(
        data.get(k) and (isinstance(data[k], dict) and any(v is not None for v in data[k].values()))
        for k in ("sentiment", "quant", "enrichment")
    )
    if not has_data:
        return {"type": "error", "message": f"No data for {ticker}. Run engines first."}
    return {"type": "quicklook", "data": data}


def execute_status(session: Session) -> dict[str, Any]:
    from sqlalchemy import func, select
    from src.storage.models import (
        BriefingDaily, EarningsBriefOutcome, EnrichmentDaily, QuantDaily, SentimentDaily,
    )

    counts = {}
    for model in [SentimentDaily, QuantDaily, EnrichmentDaily, EarningsBriefOutcome, BriefingDaily]:
        count = session.execute(select(func.count()).select_from(model)).scalar() or 0
        counts[model.__tablename__] = count
    return {"type": "status", "counts": counts}


def execute_log(args: list[str], session: Session) -> dict[str, Any]:
    from src.storage.models import BriefingDaily

    query = (
        select(BriefingDaily)
        .order_by(BriefingDaily.as_of.desc())
        .limit(20)
    )
    if args:
        ticker = args[0].upper()
        query = query.where(BriefingDaily.tickers.contains(ticker))

    rows = session.execute(query).scalars().all()
    if not rows:
        label = f" for {args[0].upper()}" if args else ""
        return {"type": "error", "message": f"No saved briefs{label}. Run /earnings or /meta first."}

    briefs = [
        {
            "as_of": row.as_of.isoformat(),
            "tickers": row.tickers,
            "model": row.model,
            "preview": row.briefing_markdown[:120].replace("\n", " "),
            "created_at": row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "—",
        }
        for row in rows
    ]
    return {"type": "brief_log", "briefs": briefs}


def _save_brief(session: Session, on_date: Date, tickers: list[str], markdown: str) -> None:
    from src.meta.llm_client import MODEL
    from src.storage.models import BriefingDaily

    existing = session.execute(
        select(BriefingDaily).where(BriefingDaily.as_of == on_date)
    ).scalar_one_or_none()

    if existing is None:
        session.add(BriefingDaily(
            as_of=on_date,
            tickers=tickers,
            payload={},
            briefing_markdown=markdown,
            model=MODEL,
        ))
    else:
        existing.tickers = tickers
        existing.briefing_markdown = markdown
        existing.model = MODEL
    session.commit()


def _ticker_from_args_or_watchlist(args: list[str]) -> list[str]:
    if args:
        return [args[0].upper()]
    from src.config import load_watchlist
    tickers = [t["ticker"] for t in load_watchlist()]
    if not tickers:
        raise ValueError("Watchlist is empty — pass a ticker or fill config/watchlist.yaml")
    return tickers
