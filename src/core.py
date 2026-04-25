"""Core orchestration functions for SFE engines.

Each function takes typed arguments and returns data. No argparse, no print,
no exit codes. Both the CLI (pipeline.py) and TUI (tui/) import from here.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session


def run_sentiment(
    tickers: list[str],
    on_date: Date,
    session: Session,
) -> list[dict[str, Any]]:
    from src.engines.sentiment.aggregator import aggregate, apply_history
    from src.storage.sentiment_repo import get_score_near, upsert_sentiment_daily

    results: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            payload = aggregate(ticker, on_date)
        except Exception as exc:
            logger.exception(f"{ticker}: aggregate failed: {exc}")
            results.append({"ticker": ticker, "error": str(exc)})
            continue
        prior_score = get_score_near(
            session, ticker, on_date - timedelta(days=7), window_days=7
        )
        apply_history(payload, prior_score)
        upsert_sentiment_daily(session, payload)
        results.append(payload)
        logger.info(
            "{ticker} {date}: score={score} sources={sources}",
            ticker=ticker,
            date=on_date,
            score=payload["sentiment_score"],
            sources=list(payload["source_breakdown"].keys()),
        )
    return results


def run_quant(
    entries: list[dict[str, Any]],
    as_of: Date,
    session: Session,
) -> list[dict[str, Any]]:
    from src.engines.quantitative.aggregator import aggregate
    from src.storage.quant_repo import upsert_quant_daily

    results: list[dict[str, Any]] = []
    for entry in entries:
        ticker = entry["ticker"]
        try:
            payload = aggregate(ticker, as_of, sector=entry.get("sector"))
        except Exception as exc:
            logger.exception(f"{ticker}: quant aggregate failed: {exc}")
            results.append({"ticker": ticker, "error": str(exc)})
            continue
        upsert_quant_daily(session, payload)
        results.append(payload)
        logger.info(
            "{ticker} {date}: close={close} rsi={rsi} health={health}",
            ticker=ticker,
            date=as_of,
            close=payload["close"],
            rsi=payload["rsi_14"],
            health=payload["health_score"],
        )
    return results


def run_enrichment(
    tickers: list[str],
    on_date: Date,
    session: Session,
) -> list[dict[str, Any]]:
    from src.engines.enrichment.aggregator import aggregate
    from src.storage.enrichment_repo import upsert_enrichment_daily

    results: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            payload = aggregate(ticker, on_date)
        except Exception as exc:
            logger.exception(f"{ticker}: enrichment aggregate failed: {exc}")
            results.append({"ticker": ticker, "error": str(exc)})
            continue
        upsert_enrichment_daily(session, payload)
        results.append(payload)
        next_er = payload["next_earnings"]
        logger.info(
            "{ticker} {date}: insider={insider} next_earn={er} analyst={analyst}",
            ticker=ticker,
            date=on_date,
            insider=payload["insider_trades"]["net_insider_sentiment"],
            er=next_er["date"] if next_er else "—",
            analyst=payload["analyst_activity"]["trend"],
        )
    return results


def run_meta(
    tickers: list[str],
    on_date: Date,
    session: Session,
) -> str:
    from src.meta.formatter import format_briefing
    from src.meta.llm_client import generate_briefing
    from src.meta.payload_builder import build_payload

    payload = build_payload(session, on_date, tickers=tickers)
    logger.info("meta: calling Claude for {n} ticker(s) on {d}", n=len(tickers), d=on_date)
    raw = generate_briefing(payload)
    return format_briefing(raw, on_date=on_date)


def run_earnings_brief(
    ticker: str,
    on_date: Date,
    session: Session,
    earnings_date: Date | None = None,
) -> str:
    from src.engines.earnings.payload_builder import build_earnings_payload
    from src.meta.formatter import format_briefing
    from src.meta.llm_client import generate_briefing

    if earnings_date is None:
        from src.engines.enrichment.event_calendar import fetch_earnings, summarize

        try:
            events = fetch_earnings(ticker, on_date)
            summary = summarize(events, on_date)
            if summary["next_earnings"]:
                earnings_date = Date.fromisoformat(summary["next_earnings"]["date"])
        except Exception as exc:
            logger.warning(f"{ticker}: earnings date lookup failed: {exc}")

    if earnings_date is None:
        raise ValueError(
            f"{ticker}: no upcoming earnings found. Pass earnings_date explicitly."
        )

    payload = build_earnings_payload(session, ticker, on_date, earnings_date)
    logger.info(
        "earnings brief: {ticker} reporting {er_date} ({days}d away)",
        ticker=ticker,
        er_date=earnings_date,
        days=(earnings_date - on_date).days,
    )

    prompt_path = Path(__file__).resolve().parent / "meta" / "prompts" / "earnings_briefing.txt"
    system_prompt = prompt_path.read_text()

    raw = generate_briefing(payload, system_prompt=system_prompt)
    return format_briefing(raw, on_date=on_date, disclaimer=True)


def earnings_calendar(on_date: Date) -> list[dict[str, Any]]:
    from src.config import load_watchlist
    from src.engines.earnings.consensus import fetch_estimates
    from src.engines.enrichment.event_calendar import fetch_earnings, summarize

    watchlist = load_watchlist()
    tickers = [t["ticker"] for t in watchlist]

    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            events = fetch_earnings(ticker, on_date, lookahead_days=14)
            summary = summarize(events, on_date)
            if not summary["next_earnings"]:
                continue
            ne = summary["next_earnings"]

            est: dict[str, Any] = {}
            try:
                est = fetch_estimates(ticker)
            except Exception:
                pass

            rows.append({
                "ticker": ticker,
                "date": ne["date"],
                "days_until": ne["days_until"],
                "consensus_eps": est.get("eps_estimate"),
                "prior_surprise": ne.get("estimate_eps"),
            })
        except Exception as exc:
            logger.warning(f"{ticker}: calendar lookup failed: {exc}")

    rows.sort(key=lambda r: r["date"])
    return rows


def log_outcome(data: dict[str, Any], session: Session) -> None:
    from src.storage.earnings_repo import upsert_outcome

    upsert_outcome(session, data)
    logger.info(
        "logged outcome: {ticker} {er_date} → {outcome}",
        ticker=data["ticker"],
        er_date=data["earnings_date"],
        outcome=data["outcome"],
    )


def get_ticker_summary(
    ticker: str,
    on_date: Date,
    session: Session,
) -> dict[str, Any]:
    """Quick-look: pull latest stored data for a ticker. No API calls."""
    from src.meta.payload_builder import _enrichment_view, _latest, _quant_view, _sentiment_view
    from src.storage.earnings_repo import get_latest_outcome
    from src.storage.models import EnrichmentDaily, QuantDaily, SentimentDaily

    sentiment = _sentiment_view(_latest(session, SentimentDaily, ticker, on_date))
    quant = _quant_view(_latest(session, QuantDaily, ticker, on_date))
    enrichment = _enrichment_view(_latest(session, EnrichmentDaily, ticker, on_date))
    outcome = get_latest_outcome(session, ticker)

    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "quant": quant,
        "enrichment": enrichment,
        "latest_outcome": {
            "predicted_dir": outcome.predicted_dir,
            "conviction": outcome.conviction,
            "outcome": outcome.outcome,
            "earnings_date": outcome.earnings_date.isoformat(),
        } if outcome else None,
    }
