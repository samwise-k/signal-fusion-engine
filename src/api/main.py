"""FastAPI application for SFE.

Read endpoints serve the latest engine outputs from the SQLite store;
write endpoints trigger pipeline runs (sync for single-ticker,
background tasks for full-watchlist) that reuse the same aggregators
and repositories as the ``sfe`` CLI.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api import schemas
from src.config import load_watchlist
from src.storage.db import _session_factory, get_engine
from src.storage.models import (
    Base,
    BriefingDaily,
    EnrichmentDaily,
    QuantDaily,
    SentimentDaily,
)

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _init_db() -> None:
    engine = get_engine()
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    _init_db()
    yield


app = FastAPI(title="SFE API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("SFE_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


# ─────────────────────────── Read helpers ─────────────────────────── #


def _latest(session: Session, model, ticker: str, on_date: Date):
    stmt = (
        select(model)
        .where(model.ticker == ticker, model.as_of <= on_date)
        .order_by(model.as_of.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _sentiment_view(row: SentimentDaily | None) -> schemas.SentimentView | None:
    if row is None:
        return None
    return schemas.SentimentView(
        as_of=row.as_of,
        sentiment_score=row.sentiment_score,
        sentiment_direction=row.sentiment_direction,
        sentiment_delta_7d=row.sentiment_delta_7d,
        source_breakdown=row.source_breakdown or {},
        key_topics=row.key_topics or [],
        notable_headlines=row.notable_headlines or [],
    )


def _quant_view(row: QuantDaily | None) -> schemas.QuantView | None:
    if row is None:
        return None
    return schemas.QuantView(
        as_of=row.as_of,
        close=row.close,
        change_1d=row.change_1d,
        change_5d=row.change_5d,
        change_20d=row.change_20d,
        rsi_14=row.rsi_14,
        above_50sma=row.above_50sma,
        above_200sma=row.above_200sma,
        macd_signal=row.macd_signal,
        volume_vs_20d_avg=row.volume_vs_20d_avg,
        sector_etf=row.sector_etf,
        relative_return_5d=row.relative_return_5d,
        health_score=row.health_score,
    )


def _enrichment_view(row: EnrichmentDaily | None) -> schemas.EnrichmentView | None:
    if row is None:
        return None
    return schemas.EnrichmentView(
        as_of=row.as_of,
        insider_trades=row.insider_trades or {},
        next_earnings=row.next_earnings,
        upcoming_events=row.upcoming_events or [],
        analyst_activity=row.analyst_activity or {},
    )


def _sector_for(ticker: str) -> str | None:
    for entry in load_watchlist():
        if entry["ticker"].upper() == ticker.upper():
            return entry.get("sector")
    return None


# ───────────────────────────── Routes ─────────────────────────────── #


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/watchlist", response_model=list[schemas.WatchlistEntry])
def watchlist() -> list[dict[str, Any]]:
    return [{"ticker": e["ticker"], "sector": e.get("sector")} for e in load_watchlist()]


@app.get("/watchlist/snapshot", response_model=schemas.WatchlistSnapshot)
def watchlist_snapshot(
    on_date: Date | None = Query(default=None, alias="date"),
    session: Session = Depends(get_db),
) -> schemas.WatchlistSnapshot:
    target = on_date or Date.today()
    entries: list[schemas.TickerSnapshot] = []
    for cfg in load_watchlist():
        ticker = cfg["ticker"].upper()
        entries.append(
            schemas.TickerSnapshot(
                ticker=ticker,
                sector=cfg.get("sector"),
                sentiment=_sentiment_view(_latest(session, SentimentDaily, ticker, target)),
                quantitative=_quant_view(_latest(session, QuantDaily, ticker, target)),
                enrichment=_enrichment_view(_latest(session, EnrichmentDaily, ticker, target)),
            )
        )
    return schemas.WatchlistSnapshot(as_of=target, entries=entries)


@app.get("/tickers/{symbol}", response_model=schemas.TickerSnapshot)
def ticker_detail(
    symbol: str,
    on_date: Date | None = Query(default=None, alias="date"),
    session: Session = Depends(get_db),
) -> schemas.TickerSnapshot:
    ticker = symbol.upper()
    target = on_date or Date.today()
    sentiment = _sentiment_view(_latest(session, SentimentDaily, ticker, target))
    quant = _quant_view(_latest(session, QuantDaily, ticker, target))
    enrichment = _enrichment_view(_latest(session, EnrichmentDaily, ticker, target))
    if sentiment is None and quant is None and enrichment is None:
        raise HTTPException(status_code=404, detail=f"no data for {ticker} on or before {target}")
    return schemas.TickerSnapshot(
        ticker=ticker,
        sector=_sector_for(ticker),
        sentiment=sentiment,
        quantitative=quant,
        enrichment=enrichment,
    )


@app.get("/tickers/{symbol}/history")
def ticker_history(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    ticker = symbol.upper()

    sent_rows = session.execute(
        select(SentimentDaily)
        .where(SentimentDaily.ticker == ticker)
        .order_by(SentimentDaily.as_of.desc())
        .limit(limit)
    ).scalars().all()

    quant_rows = session.execute(
        select(QuantDaily)
        .where(QuantDaily.ticker == ticker)
        .order_by(QuantDaily.as_of.desc())
        .limit(limit)
    ).scalars().all()

    return {
        "sentiment": [
            {
                "as_of": r.as_of.isoformat(),
                "score": r.sentiment_score,
                "direction": r.sentiment_direction,
            }
            for r in sent_rows
        ],
        "quant": [
            {
                "as_of": r.as_of.isoformat(),
                "close": r.close,
                "change_1d": r.change_1d,
                "rsi_14": r.rsi_14,
                "health_score": r.health_score,
            }
            for r in quant_rows
        ],
    }


@app.get("/briefing/{on_date}", response_model=schemas.BriefingView)
def get_briefing(on_date: Date, session: Session = Depends(get_db)) -> schemas.BriefingView:
    row = session.execute(
        select(BriefingDaily).where(BriefingDaily.as_of == on_date)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no briefing stored for {on_date}")
    return schemas.BriefingView(
        as_of=row.as_of,
        tickers=row.tickers,
        markdown=row.briefing_markdown,
        model=row.model,
        created_at=row.created_at,
    )


# ────────────────────────── Pipeline triggers ─────────────────────── #


def _resolve_tickers(ticker: str | None) -> list[str]:
    if ticker:
        return [ticker.upper()]
    tickers = [t["ticker"].upper() for t in load_watchlist()]
    if not tickers:
        raise HTTPException(status_code=400, detail="watchlist is empty; pass ?ticker=SYM")
    return tickers


def _run_sentiment_job(tickers: list[str], on_date: Date) -> None:
    from src.engines.sentiment.aggregator import aggregate, apply_history
    from src.storage.sentiment_repo import get_score_near, upsert_sentiment_daily

    session = _session_factory()()
    try:
        for ticker in tickers:
            try:
                payload = aggregate(ticker, on_date)
                prior = get_score_near(
                    session, ticker, on_date - timedelta(days=7), window_days=7
                )
                apply_history(payload, prior)
                upsert_sentiment_daily(session, payload)
            except Exception as exc:
                logger.exception(f"api: sentiment {ticker} failed: {exc}")
    finally:
        session.close()


def _run_quant_job(tickers: list[str], on_date: Date) -> None:
    from src.engines.quantitative.aggregator import aggregate
    from src.storage.quant_repo import upsert_quant_daily

    watchlist = {t["ticker"].upper(): t.get("sector") for t in load_watchlist()}
    session = _session_factory()()
    try:
        for ticker in tickers:
            try:
                payload = aggregate(ticker, on_date, sector=watchlist.get(ticker))
                upsert_quant_daily(session, payload)
            except Exception as exc:
                logger.exception(f"api: quant {ticker} failed: {exc}")
    finally:
        session.close()


def _run_enrichment_job(tickers: list[str], on_date: Date) -> None:
    from src.engines.enrichment.aggregator import aggregate
    from src.storage.enrichment_repo import upsert_enrichment_daily

    session = _session_factory()()
    try:
        for ticker in tickers:
            try:
                payload = aggregate(ticker, on_date)
                upsert_enrichment_daily(session, payload)
            except Exception as exc:
                logger.exception(f"api: enrichment {ticker} failed: {exc}")
    finally:
        session.close()


def _run_meta_job(tickers: list[str], on_date: Date) -> None:
    from src.meta.llm_client import MODEL, generate_briefing
    from src.meta.payload_builder import build_payload

    session = _session_factory()()
    try:
        payload = build_payload(session, on_date, tickers=tickers)
        markdown = generate_briefing(payload)
        existing = session.execute(
            select(BriefingDaily).where(BriefingDaily.as_of == on_date)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                BriefingDaily(
                    as_of=on_date,
                    tickers=tickers,
                    payload=payload,
                    briefing_markdown=markdown,
                    model=MODEL,
                )
            )
        else:
            existing.tickers = tickers
            existing.payload = payload
            existing.briefing_markdown = markdown
            existing.model = MODEL
        session.commit()
    finally:
        session.close()


_JOBS = {
    "sentiment": _run_sentiment_job,
    "quant": _run_quant_job,
    "enrichment": _run_enrichment_job,
}


@app.post("/pipeline/meta", response_model=schemas.PipelineRunResponse)
def run_meta(
    background: BackgroundTasks,
    ticker: str | None = None,
    on_date: Date | None = Query(default=None, alias="date"),
    wait: bool = False,
) -> schemas.PipelineRunResponse:
    tickers = _resolve_tickers(ticker)
    target = on_date or Date.today()

    if wait:
        _run_meta_job(tickers, target)
        return schemas.PipelineRunResponse(
            status="completed",
            command="meta",
            tickers=tickers,
            as_of=target,
        )

    background.add_task(_run_meta_job, tickers, target)
    return schemas.PipelineRunResponse(
        status="scheduled",
        command="meta",
        tickers=tickers,
        as_of=target,
        detail="running in background",
    )


@app.post("/pipeline/{engine}", response_model=schemas.PipelineRunResponse)
def run_pipeline(
    engine: str,
    background: BackgroundTasks,
    ticker: str | None = None,
    on_date: Date | None = Query(default=None, alias="date"),
    wait: bool = False,
) -> schemas.PipelineRunResponse:
    if engine not in _JOBS:
        raise HTTPException(status_code=404, detail=f"unknown engine: {engine}")
    tickers = _resolve_tickers(ticker)
    target = on_date or Date.today()
    job = _JOBS[engine]

    if wait:
        job(tickers, target)
        return schemas.PipelineRunResponse(
            status="completed",
            command=engine,
            tickers=tickers,
            as_of=target,
        )

    background.add_task(job, tickers, target)
    return schemas.PipelineRunResponse(
        status="scheduled",
        command=engine,
        tickers=tickers,
        as_of=target,
        detail="running in background",
    )


# ───────────────────────────── Entrypoint ─────────────────────────── #


def serve() -> None:
    """Console script entrypoint: ``sfe-api``."""
    import uvicorn

    host = os.environ.get("SFE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SFE_API_PORT", "8000"))
    uvicorn.run("src.api.main:app", host=host, port=port, reload=False)
