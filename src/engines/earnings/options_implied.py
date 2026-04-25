"""Options-implied move via yfinance.

Best-effort: if yfinance returns no chain data, returns None so the
prompt and brief skip the implied-move section gracefully.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from loguru import logger


def fetch_implied_move(ticker: str, earnings_date: date) -> dict[str, Any] | None:
    """Return ATM straddle implied move for the nearest expiry after earnings_date.

    Returns None (not raises) when data is unavailable, so the caller
    can treat it as a missing-but-non-fatal field.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — run `uv sync --group quant`")
        return None

    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            logger.info(f"{ticker}: no options expirations available")
            return None

        target = _nearest_expiry_after(expirations, earnings_date)
        if target is None:
            logger.info(f"{ticker}: no expiry on or after earnings date {earnings_date}")
            return None

        chain = stock.option_chain(target)
        calls = chain.calls
        puts = chain.puts

        if calls.empty or puts.empty:
            logger.info(f"{ticker}: empty chain for {target}")
            return None

        spot = stock.info.get("regularMarketPrice") or stock.info.get("currentPrice")
        if spot is None or spot <= 0:
            logger.info(f"{ticker}: no spot price available")
            return None

        atm_call = _nearest_strike(calls, spot)
        atm_put = _nearest_strike(puts, spot)

        if atm_call is None or atm_put is None:
            return None

        call_mid = _mid_price(atm_call)
        put_mid = _mid_price(atm_put)
        if call_mid is None or put_mid is None:
            return None

        straddle = call_mid + put_mid
        straddle_pct = round((straddle / spot) * 100, 2)

        return {
            "atm_straddle_pct": straddle_pct,
            "call_iv": _safe_round(atm_call.get("impliedVolatility")),
            "put_iv": _safe_round(atm_put.get("impliedVolatility")),
            "expiry": target,
            "spot": round(spot, 2),
        }

    except Exception as exc:
        logger.warning(f"{ticker}: options fetch failed: {exc}")
        return None


def _nearest_expiry_after(expirations: tuple[str, ...], target: date) -> str | None:
    """Pick the earliest expiration on or after target date."""
    for exp_str in sorted(expirations):
        try:
            exp_date = date.fromisoformat(exp_str)
        except ValueError:
            continue
        if exp_date >= target:
            return exp_str
    return None


def _nearest_strike(chain_df, spot: float) -> dict[str, Any] | None:
    """Return the row with strike closest to spot, as a dict."""
    if chain_df.empty:
        return None
    idx = (chain_df["strike"] - spot).abs().idxmin()
    return chain_df.loc[idx].to_dict()


def _mid_price(row: dict[str, Any]) -> float | None:
    bid = row.get("bid")
    ask = row.get("ask")
    if bid is not None and ask is not None and bid >= 0 and ask > 0:
        return (bid + ask) / 2
    last = row.get("lastPrice")
    if last is not None and last > 0:
        return last
    return None


def _safe_round(v: Any, digits: int = 4) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), digits)
    except (ValueError, TypeError):
        return None
