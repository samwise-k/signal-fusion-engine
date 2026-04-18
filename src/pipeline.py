"""SFE CLI entry point. Dispatches to engines, meta-layer, and delivery."""

from __future__ import annotations

import argparse
import sys
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger


def run_sentiment(args: argparse.Namespace) -> int:
    load_dotenv()

    from src.config import load_watchlist
    from src.engines.sentiment.aggregator import aggregate, apply_history
    from src.storage.db import get_engine, get_session
    from src.storage.models import Base
    from src.storage.sentiment_repo import get_score_near, upsert_sentiment_daily

    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    on_date = Date.fromisoformat(args.date) if args.date else Date.today()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t["ticker"] for t in load_watchlist()]
        if not tickers:
            logger.error(
                "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
            )
            return 1

    session = get_session()
    try:
        for ticker in tickers:
            try:
                payload = aggregate(ticker, on_date)
            except Exception as exc:
                logger.exception(f"{ticker}: aggregate failed: {exc}")
                continue
            prior_score = get_score_near(
                session, ticker, on_date - timedelta(days=7), window_days=7
            )
            apply_history(payload, prior_score)
            upsert_sentiment_daily(session, payload)
            logger.info(
                "{ticker} {date}: score={score} sources={sources}",
                ticker=ticker,
                date=on_date,
                score=payload["sentiment_score"],
                sources=list(payload["source_breakdown"].keys()),
            )
    finally:
        session.close()
    return 0


def run_quant(args: argparse.Namespace) -> int:
    load_dotenv()

    from src.config import load_watchlist
    from src.engines.quantitative.aggregator import aggregate
    from src.storage.db import get_engine, get_session
    from src.storage.models import Base
    from src.storage.quant_repo import upsert_quant_daily

    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    on_date = Date.fromisoformat(args.date) if args.date else Date.today()

    watchlist = load_watchlist()
    if args.ticker:
        sym = args.ticker.upper()
        sector = next(
            (t.get("sector") for t in watchlist if t["ticker"].upper() == sym), None
        )
        entries = [{"ticker": sym, "sector": sector}]
    else:
        entries = watchlist
        if not entries:
            logger.error(
                "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
            )
            return 1

    session = get_session()
    try:
        for entry in entries:
            ticker = entry["ticker"]
            try:
                payload = aggregate(ticker, on_date, sector=entry.get("sector"))
            except Exception as exc:
                logger.exception(f"{ticker}: quant aggregate failed: {exc}")
                continue
            upsert_quant_daily(session, payload)
            logger.info(
                "{ticker} {date}: close={close} rsi={rsi} health={health}",
                ticker=ticker,
                date=on_date,
                close=payload["close"],
                rsi=payload["rsi_14"],
                health=payload["health_score"],
            )
    finally:
        session.close()
    return 0


def run_enrichment(args: argparse.Namespace) -> int:
    load_dotenv()

    from src.config import load_watchlist
    from src.engines.enrichment.aggregator import aggregate
    from src.storage.db import get_engine, get_session
    from src.storage.enrichment_repo import upsert_enrichment_daily
    from src.storage.models import Base

    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    on_date = Date.fromisoformat(args.date) if args.date else Date.today()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t["ticker"] for t in load_watchlist()]
        if not tickers:
            logger.error(
                "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
            )
            return 1

    session = get_session()
    try:
        for ticker in tickers:
            try:
                payload = aggregate(ticker, on_date)
            except Exception as exc:
                logger.exception(f"{ticker}: enrichment aggregate failed: {exc}")
                continue
            upsert_enrichment_daily(session, payload)
            next_er = payload["next_earnings"]
            logger.info(
                "{ticker} {date}: insider={insider} next_earn={er} analyst={analyst}",
                ticker=ticker,
                date=on_date,
                insider=payload["insider_trades"]["net_insider_sentiment"],
                er=next_er["date"] if next_er else "—",
                analyst=payload["analyst_activity"]["trend"],
            )
    finally:
        session.close()
    return 0


def run_meta(args: argparse.Namespace) -> int:
    load_dotenv()

    from src.config import load_watchlist
    from src.meta.formatter import format_briefing
    from src.meta.llm_client import generate_briefing
    from src.meta.payload_builder import build_payload
    from src.storage.db import get_engine, get_session
    from src.storage.models import Base

    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    on_date = Date.fromisoformat(args.date) if args.date else Date.today()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t["ticker"] for t in load_watchlist()]
        if not tickers:
            logger.error(
                "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
            )
            return 1

    session = get_session()
    try:
        payload = build_payload(session, on_date, tickers=tickers)
    finally:
        session.close()

    logger.info("meta: calling Claude for {n} ticker(s) on {d}", n=len(tickers), d=on_date)
    raw = generate_briefing(payload)
    print(format_briefing(raw, on_date=on_date))
    return 0


def run_all(args: argparse.Namespace) -> int:
    logger.info("full pipeline: not yet implemented")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sfe", description="Signal Fusion Engine CLI")
    subs = parser.add_subparsers(dest="command", required=True)

    p_sent = subs.add_parser("run-sentiment", help="Run the sentiment engine")
    p_sent.add_argument("--ticker", help="Run for one ticker, bypassing the watchlist")
    p_sent.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_sent.set_defaults(func=run_sentiment)

    p_quant = subs.add_parser("run-quant", help="Run the quantitative engine")
    p_quant.add_argument("--ticker", help="Run for one ticker, bypassing the watchlist")
    p_quant.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_quant.set_defaults(func=run_quant)
    p_enrich = subs.add_parser("run-enrichment", help="Run enrichment signals")
    p_enrich.add_argument("--ticker", help="Run for one ticker, bypassing the watchlist")
    p_enrich.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_enrich.set_defaults(func=run_enrichment)
    p_meta = subs.add_parser("run-meta", help="Run the meta-synthesis layer")
    p_meta.add_argument("--ticker", help="Run for one ticker, bypassing the watchlist")
    p_meta.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_meta.set_defaults(func=run_meta)
    subs.add_parser("run-all", help="Run the full pipeline end to end").set_defaults(func=run_all)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
