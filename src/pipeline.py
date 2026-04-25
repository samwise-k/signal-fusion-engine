"""SFE CLI entry point. Dispatches to engines, meta-layer, and delivery."""

from __future__ import annotations

import argparse
import sys
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger


# ---------------------------------------------------------------------------
# Shared bootstrap helpers (DRY: previously repeated 4x, now centralized)
# ---------------------------------------------------------------------------


def _bootstrap_db():
    """Load env, create DB dir if needed, run CREATE TABLE, return session."""
    load_dotenv()

    from src.storage.db import get_engine, get_session
    from src.storage.models import Base

    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    return get_session()


def _parse_date(args: argparse.Namespace) -> Date:
    return Date.fromisoformat(args.date) if args.date else Date.today()


def _resolve_tickers(args: argparse.Namespace) -> list[str] | None:
    """Return ticker list from --ticker flag or watchlist. None = empty watchlist."""
    from src.config import load_watchlist

    if args.ticker:
        return [args.ticker.upper()]
    tickers = [t["ticker"] for t in load_watchlist()]
    if not tickers:
        logger.error(
            "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
        )
        return None
    return tickers


def _resolve_watchlist_entries(args: argparse.Namespace) -> list[dict[str, Any]] | None:
    """Like _resolve_tickers but returns full watchlist dicts (with sector)."""
    from src.config import load_watchlist

    watchlist = load_watchlist()
    if args.ticker:
        sym = args.ticker.upper()
        sector = next(
            (t.get("sector") for t in watchlist if t["ticker"].upper() == sym), None
        )
        return [{"ticker": sym, "sector": sector}]
    if not watchlist:
        logger.error(
            "watchlist is empty — pass --ticker SYM or fill config/watchlist.yaml"
        )
        return None
    return watchlist


# ---------------------------------------------------------------------------
# Engine commands
# ---------------------------------------------------------------------------


def run_sentiment(args: argparse.Namespace) -> int:
    from src.engines.sentiment.aggregator import aggregate, apply_history
    from src.storage.sentiment_repo import get_score_near, upsert_sentiment_daily

    session = _bootstrap_db()
    on_date = _parse_date(args)
    tickers = _resolve_tickers(args)
    if tickers is None:
        return 1

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
    from src.engines.quantitative.aggregator import aggregate
    from src.storage.quant_repo import upsert_quant_daily

    session = _bootstrap_db()
    as_of = _parse_date(args)
    entries = _resolve_watchlist_entries(args)
    if entries is None:
        return 1

    try:
        for entry in entries:
            ticker = entry["ticker"]
            try:
                payload = aggregate(ticker, as_of, sector=entry.get("sector"))
            except Exception as exc:
                logger.exception(f"{ticker}: quant aggregate failed: {exc}")
                continue
            upsert_quant_daily(session, payload)
            logger.info(
                "{ticker} {date}: close={close} rsi={rsi} health={health}",
                ticker=ticker,
                date=as_of,
                close=payload["close"],
                rsi=payload["rsi_14"],
                health=payload["health_score"],
            )
    finally:
        session.close()
    return 0


def run_enrichment(args: argparse.Namespace) -> int:
    from src.engines.enrichment.aggregator import aggregate
    from src.storage.enrichment_repo import upsert_enrichment_daily

    session = _bootstrap_db()
    on_date = _parse_date(args)
    tickers = _resolve_tickers(args)
    if tickers is None:
        return 1

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
    from src.meta.formatter import format_briefing
    from src.meta.llm_client import generate_briefing
    from src.meta.payload_builder import build_payload

    session = _bootstrap_db()
    on_date = _parse_date(args)
    tickers = _resolve_tickers(args)
    if tickers is None:
        return 1

    try:
        payload = build_payload(session, on_date, tickers=tickers)
    finally:
        session.close()

    logger.info("meta: calling Claude for {n} ticker(s) on {d}", n=len(tickers), d=on_date)
    try:
        raw = generate_briefing(payload)
    except Exception as exc:
        logger.error("Claude API call failed: {exc}", exc=exc)
        return 1
    print(format_briefing(raw, on_date=on_date))
    return 0


def run_earnings_brief(args: argparse.Namespace) -> int:
    from pathlib import Path

    from src.engines.earnings.payload_builder import build_earnings_payload
    from src.meta.formatter import format_briefing
    from src.meta.llm_client import generate_briefing

    session = _bootstrap_db()
    on_date = _parse_date(args)
    ticker = args.ticker.upper()

    earnings_date: Date | None = None
    if args.earnings_date:
        earnings_date = Date.fromisoformat(args.earnings_date)
    else:
        from src.engines.enrichment.event_calendar import fetch_earnings, summarize

        try:
            events = fetch_earnings(ticker, on_date)
            summary = summarize(events, on_date)
            if summary["next_earnings"]:
                earnings_date = Date.fromisoformat(summary["next_earnings"]["date"])
        except Exception as exc:
            logger.warning(f"{ticker}: earnings date lookup failed: {exc}")

    if earnings_date is None:
        logger.error(
            f"{ticker}: no upcoming earnings found. Pass --earnings-date YYYY-MM-DD"
        )
        return 1

    try:
        payload = build_earnings_payload(session, ticker, on_date, earnings_date)
    finally:
        session.close()

    logger.info(
        "earnings brief: {ticker} reporting {er_date} ({days}d away)",
        ticker=ticker,
        er_date=earnings_date,
        days=(earnings_date - on_date).days,
    )

    prompt_path = Path(__file__).resolve().parent / "meta" / "prompts" / "earnings_briefing.txt"
    system_prompt = prompt_path.read_text()

    try:
        raw = generate_briefing(
            payload,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.error("Claude API call failed: {exc}", exc=exc)
        return 1
    print(format_briefing(raw, on_date=on_date, disclaimer=True))
    return 0


def log_outcome(args: argparse.Namespace) -> int:
    from src.storage.earnings_repo import upsert_outcome

    session = _bootstrap_db()

    data = {
        "ticker": args.ticker.upper(),
        "earnings_date": Date.fromisoformat(args.earnings_date),
        "brief_date": Date.fromisoformat(args.brief_date) if args.brief_date else Date.today(),
        "predicted_dir": args.predicted_dir,
        "conviction": float(args.conviction),
        "actual_eps_surp": float(args.actual_eps_surp) if args.actual_eps_surp else None,
        "actual_rev_surp": float(args.actual_rev_surp) if args.actual_rev_surp else None,
        "stock_move_1d": float(args.stock_move_1d) if args.stock_move_1d else None,
        "outcome": args.outcome or "pending",
        "notes": args.notes,
    }

    try:
        upsert_outcome(session, data)
    finally:
        session.close()

    logger.info(
        "logged outcome: {ticker} {er_date} → {outcome}",
        ticker=data["ticker"],
        er_date=data["earnings_date"],
        outcome=data["outcome"],
    )
    return 0


def earnings_calendar(args: argparse.Namespace) -> int:
    from src.config import load_watchlist
    from src.engines.earnings.consensus import fetch_estimates
    from src.engines.enrichment.event_calendar import fetch_earnings, summarize

    _bootstrap_db()
    on_date = _parse_date(args)
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

    if not rows:
        print("No watchlist tickers reporting in the next 14 days.")
        return 0

    rows.sort(key=lambda r: r["date"])

    header = f"{'TICKER':<10} {'REPORT DATE':<14} {'DAYS UNTIL':<12} {'CONSENSUS EPS':<16}"
    print(header)
    print("-" * len(header))
    for r in rows:
        eps_str = f"${r['consensus_eps']:.2f}" if r["consensus_eps"] is not None else "—"
        print(
            f"{r['ticker']:<10} {r['date']:<14} {r['days_until']:<12} {eps_str:<16}"
        )
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

    p_eb = subs.add_parser("run-earnings-brief", help="Generate an earnings context brief")
    p_eb.add_argument("--ticker", required=True, help="Ticker symbol (required)")
    p_eb.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_eb.add_argument(
        "--earnings-date",
        help="Override earnings date (YYYY-MM-DD); auto-detected from Finnhub if omitted",
    )
    p_eb.set_defaults(func=run_earnings_brief)

    p_lo = subs.add_parser("log-outcome", help="Log an earnings brief outcome")
    p_lo.add_argument("--ticker", required=True, help="Ticker symbol")
    p_lo.add_argument("--earnings-date", required=True, help="Earnings date (YYYY-MM-DD)")
    p_lo.add_argument(
        "--predicted-dir", required=True, choices=["bullish", "bearish", "neutral"],
        help="Predicted direction from the brief",
    )
    p_lo.add_argument("--conviction", required=True, help="Conviction score 0.0-1.0")
    p_lo.add_argument("--actual-eps-surp", help="Actual EPS surprise %%")
    p_lo.add_argument("--actual-rev-surp", help="Actual revenue surprise %%")
    p_lo.add_argument("--stock-move-1d", help="1-day stock move post-print %%")
    p_lo.add_argument(
        "--outcome", choices=["correct", "incorrect", "mixed", "pending"],
        help="Outcome assessment (default: pending)",
    )
    p_lo.add_argument("--brief-date", help="Date brief was published (default: today)")
    p_lo.add_argument("--notes", help="Free-form notes")
    p_lo.set_defaults(func=log_outcome)

    p_cal = subs.add_parser("earnings-calendar", help="Show upcoming earnings for watchlist")
    p_cal.add_argument("--date", help="ISO date (YYYY-MM-DD); defaults to today")
    p_cal.set_defaults(func=earnings_calendar)

    subs.add_parser("run-all", help="Run the full pipeline end to end").set_defaults(func=run_all)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
