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
    logger.info("quantitative engine: not yet implemented")
    return 0


def run_enrichment(args: argparse.Namespace) -> int:
    logger.info("enrichment signals: not yet implemented")
    return 0


def run_meta(args: argparse.Namespace) -> int:
    logger.info("meta-synthesis layer: not yet implemented")
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

    subs.add_parser("run-quant", help="Run the quantitative engine").set_defaults(func=run_quant)
    subs.add_parser("run-enrichment", help="Run enrichment signals").set_defaults(func=run_enrichment)
    subs.add_parser("run-meta", help="Run the meta-synthesis layer").set_defaults(func=run_meta)
    subs.add_parser("run-all", help="Run the full pipeline end to end").set_defaults(func=run_all)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
