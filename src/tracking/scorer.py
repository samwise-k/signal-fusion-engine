"""Outcome scorer for the signal experiment.

For matured signals (older than horizon), fetches actual close prices and
scores win/loss/neutral against the directional call.
"""

from __future__ import annotations

import os
from datetime import date as Date
from datetime import timedelta
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import SignalDaily

HORIZONS = {1: 0.005, 3: 0.01, 5: 0.015}

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _fetch_close_yfinance(ticker: str, target_date: Date) -> float | None:
    try:
        import yfinance as yf

        end = target_date + timedelta(days=1)
        start = target_date - timedelta(days=5)
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df = df.droplevel(1, axis=1)
        last = df[df.index.date <= target_date]
        if last.empty:
            return None
        return float(last.iloc[-1]["Close"])
    except Exception as exc:
        logger.debug("yfinance failed for {t} on {d}: {e}", t=ticker, d=target_date, e=exc)
        return None


def _fetch_close_finnhub(ticker: str, target_date: Date) -> float | None:
    api_key = os.environ.get("FINNHUB_KEY")
    if not api_key:
        return None
    try:
        import time

        ts_from = int(time.mktime((target_date - timedelta(days=5)).timetuple()))
        ts_to = int(time.mktime((target_date + timedelta(days=1)).timetuple()))
        resp = httpx.get(
            f"{FINNHUB_BASE}/stock/candle",
            params={
                "symbol": ticker,
                "resolution": "D",
                "from": ts_from,
                "to": ts_to,
                "token": api_key,
            },
            timeout=15.0,
        )
        data = resp.json()
        if data.get("s") != "ok" or not data.get("c"):
            return None
        return float(data["c"][-1])
    except Exception as exc:
        logger.debug("finnhub failed for {t} on {d}: {e}", t=ticker, d=target_date, e=exc)
        return None


def fetch_close(ticker: str, target_date: Date) -> float | None:
    price = _fetch_close_yfinance(ticker, target_date)
    if price is not None:
        return price
    return _fetch_close_finnhub(ticker, target_date)


def _classify(ret: float, dead_zone: float, direction: str) -> str:
    if abs(ret) <= dead_zone:
        return "neutral"
    if direction == "bullish":
        return "win" if ret > 0 else "loss"
    if direction == "bearish":
        return "win" if ret < 0 else "loss"
    return "neutral"


def score_signal(
    signal: SignalDaily,
    today: Date | None = None,
) -> dict[str, Any] | None:
    """Score a single signal across all horizons. Returns None if not yet maturable."""
    today = today or Date.today()
    age = (today - signal.as_of).days

    if age < 1:
        return None

    entry = signal.entry_price
    if entry is None:
        entry_price = fetch_close(signal.ticker, signal.as_of)
        if entry_price is None:
            logger.warning("no entry price for {t} on {d}", t=signal.ticker, d=signal.as_of)
            return None
        entry = entry_price

    results: dict[str, Any] = {
        "ticker": signal.ticker,
        "as_of": signal.as_of.isoformat(),
        "direction": signal.direction,
        "conviction": signal.conviction,
        "dominant_component": signal.dominant_component,
        "entry_price": entry,
        "horizons": {},
    }

    for horizon, dead_zone in HORIZONS.items():
        if age < horizon:
            continue
        target_date = signal.as_of + timedelta(days=horizon)
        close = fetch_close(signal.ticker, target_date)
        if close is None:
            continue
        ret = (close - entry) / entry
        outcome = _classify(ret, dead_zone, signal.direction)
        results["horizons"][f"{horizon}d"] = {
            "close": close,
            "return": round(ret, 6),
            "outcome": outcome,
        }

    if not results["horizons"]:
        return None
    return results


def score_all(session: Session, today: Date | None = None) -> list[dict[str, Any]]:
    """Score all maturable signals."""
    today = today or Date.today()
    cutoff = today - timedelta(days=1)

    signals = session.execute(
        select(SignalDaily)
        .where(SignalDaily.as_of <= cutoff)
        .order_by(SignalDaily.as_of.desc())
    ).scalars().all()

    scored: list[dict[str, Any]] = []
    for sig in signals:
        result = score_signal(sig, today)
        if result:
            scored.append(result)
    logger.info("scored {n}/{total} signals", n=len(scored), total=len(signals))
    return scored


def compute_stats(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate experiment statistics from scored signals."""
    stats: dict[str, Any] = {"by_horizon": {}, "by_conviction": {}, "by_component": {}}

    for horizon_key in ["1d", "3d", "5d"]:
        outcomes = [
            s["horizons"][horizon_key]
            for s in scored
            if horizon_key in s["horizons"]
        ]
        if not outcomes:
            stats["by_horizon"][horizon_key] = {"n": 0}
            continue

        wins = sum(1 for o in outcomes if o["outcome"] == "win")
        losses = sum(1 for o in outcomes if o["outcome"] == "loss")
        neutrals = sum(1 for o in outcomes if o["outcome"] == "neutral")
        n = len(outcomes)
        actionable = wins + losses
        accuracy = wins / actionable if actionable > 0 else None

        returns = [o["return"] for o in outcomes]
        ev = sum(returns) / n if n > 0 else 0.0

        stats["by_horizon"][horizon_key] = {
            "n": n,
            "wins": wins,
            "losses": losses,
            "neutrals": neutrals,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "ev": round(ev, 6),
            "returns": returns,
        }

    _bucket_stats(scored, stats, "by_conviction", _conviction_bucket)
    _bucket_stats(scored, stats, "by_component", lambda s: s["dominant_component"])

    total_scored = len(scored)
    all_5d = [s for s in scored if "5d" in s["horizons"]]
    stats["total_signals"] = total_scored
    stats["total_5d_scored"] = len(all_5d)
    stats["calls_for_significance"] = max(0, 100 - total_scored)

    return stats


def _conviction_bucket(signal: dict[str, Any]) -> str:
    c = signal["conviction"]
    if c >= 0.7:
        return "high (>=0.7)"
    if c >= 0.5:
        return "medium (0.5-0.7)"
    return "low (<0.5)"


def _bucket_stats(
    scored: list[dict[str, Any]],
    stats: dict[str, Any],
    key: str,
    bucket_fn,
) -> None:
    from collections import defaultdict

    buckets: dict[str, list] = defaultdict(list)
    for s in scored:
        if "5d" not in s["horizons"]:
            continue
        buckets[bucket_fn(s)].append(s)

    stats[key] = {}
    for bucket_name, signals in sorted(buckets.items()):
        wins = sum(1 for s in signals if s["horizons"]["5d"]["outcome"] == "win")
        losses = sum(1 for s in signals if s["horizons"]["5d"]["outcome"] == "loss")
        n = len(signals)
        actionable = wins + losses
        returns = [s["horizons"]["5d"]["return"] for s in signals]
        ev = sum(returns) / n if n > 0 else 0.0
        stats[key][bucket_name] = {
            "n": n,
            "wins": wins,
            "losses": losses,
            "accuracy": round(wins / actionable, 4) if actionable > 0 else None,
            "ev": round(ev, 6),
        }
