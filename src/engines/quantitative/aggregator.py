"""End-to-end quantitative rollup for one ticker on one day."""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from src.engines.quantitative import model, price_fetcher, technicals

# S&P SPDR sector ETFs keyed by the ``sector`` value used in watchlist.yaml.
SECTOR_ETF: dict[str, str] = {
    "technology": "XLK",
    "communication-services": "XLC",
    "consumer-discretionary": "XLY",
    "consumer-staples": "XLP",
    "financials": "XLF",
    "healthcare": "XLV",
    "energy": "XLE",
    "industrials": "XLI",
    "utilities": "XLU",
    "real-estate": "XLRE",
    "materials": "XLB",
}


def _sector_relative(
    ticker_ohlcv: list[dict],
    sector: str | None,
    on_date: date,
) -> dict[str, Any]:
    etf = SECTOR_ETF.get(sector or "")
    if not etf or len(ticker_ohlcv) < 6:
        return {"sector_etf": etf, "relative_return_5d": None}

    try:
        etf_ohlcv = price_fetcher.fetch_ohlcv(etf, on_date, days=30)
    except Exception as exc:
        logger.warning(f"sector ETF {etf} fetch failed: {exc}")
        return {"sector_etf": etf, "relative_return_5d": None}
    if len(etf_ohlcv) < 6:
        return {"sector_etf": etf, "relative_return_5d": None}

    def _ret_5d(rows: list[dict]) -> float:
        return (rows[-1]["close"] - rows[-6]["close"]) / rows[-6]["close"] * 100

    rel = _ret_5d(ticker_ohlcv) - _ret_5d(etf_ohlcv)
    return {"sector_etf": etf, "relative_return_5d": round(rel, 2)}


def aggregate(
    ticker: str,
    on_date: date,
    *,
    sector: str | None = None,
) -> dict[str, Any]:
    """Fetch OHLCV, compute technicals + sector-relative, score health.

    The payload mirrors the planning-doc schema so it round-trips into the
    meta-layer without a join. Raises on total fetch failure — callers in
    ``pipeline.py`` catch and log per-ticker so one bad ticker doesn't blank
    the run.
    """
    ohlcv = price_fetcher.fetch_ohlcv(ticker, on_date)
    if not ohlcv:
        raise RuntimeError(f"no OHLCV data returned for {ticker}")

    indicators = technicals.compute_indicators(ohlcv)
    health = model.predict_health(indicators)
    sector_rel = _sector_relative(ohlcv, sector, on_date)

    return {
        "ticker": ticker,
        "date": on_date.isoformat(),
        "close": indicators["close"],
        "change_1d": indicators["change_1d"],
        "change_5d": indicators["change_5d"],
        "change_20d": indicators["change_20d"],
        "rsi_14": indicators["rsi_14"],
        "above_50sma": indicators["above_50sma"],
        "above_200sma": indicators["above_200sma"],
        "macd_signal": indicators["macd_signal"],
        "volume_vs_20d_avg": indicators["volume_vs_20d_avg"],
        "sector_etf": sector_rel["sector_etf"],
        "relative_return_5d": sector_rel["relative_return_5d"],
        "health_score": health,
    }
