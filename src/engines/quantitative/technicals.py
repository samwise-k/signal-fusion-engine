"""Technical indicator calculations.

Pure functions over an OHLCV list (as returned by ``price_fetcher.fetch_ohlcv``),
so they're trivially unit-testable without hitting the network.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_WINDOW = 20


def _to_frame(ohlcv: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv)
    if df.empty:
        return df
    return df.sort_values("date").reset_index(drop=True)


def _rsi(close: pd.Series, period: int = RSI_PERIOD) -> float | None:
    if len(close) <= period:
        return None
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return None if pd.isna(val) else round(float(val), 2)


def _macd_signal(close: pd.Series) -> str:
    if len(close) < MACD_SLOW + MACD_SIGNAL:
        return "insufficient_data"
    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hist = macd - signal
    last, prev = hist.iloc[-1], hist.iloc[-2]
    if prev <= 0 < last:
        return "bullish_crossover"
    if prev >= 0 > last:
        return "bearish_crossover"
    return "bullish" if last > 0 else "bearish"


def _pct_change(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    prev = close.iloc[-periods - 1]
    if prev == 0:
        return None
    return round(float((close.iloc[-1] - prev) / prev * 100), 2)


def compute_indicators(ohlcv: list[dict]) -> dict[str, Any]:
    """Compute technicals from an OHLCV series sorted any order.

    Returns a payload shaped to slot into the ``QuantDaily`` row. Missing
    history (e.g. young ticker) yields ``None`` for the affected fields rather
    than raising, so aggregation still succeeds.
    """
    df = _to_frame(ohlcv)
    if df.empty:
        return {
            "close": None, "change_1d": None, "change_5d": None, "change_20d": None,
            "rsi_14": None, "above_50sma": None, "above_200sma": None,
            "macd_signal": "insufficient_data", "volume_vs_20d_avg": None,
        }

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    last_close = float(close.iloc[-1])

    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan

    vol_avg = volume.rolling(VOLUME_WINDOW).mean().iloc[-2] if len(volume) > VOLUME_WINDOW else np.nan
    vol_ratio = (
        round(float(volume.iloc[-1] / vol_avg), 2)
        if not pd.isna(vol_avg) and vol_avg > 0
        else None
    )

    return {
        "close": round(last_close, 4),
        "change_1d": _pct_change(close, 1),
        "change_5d": _pct_change(close, 5),
        "change_20d": _pct_change(close, 20),
        "rsi_14": _rsi(close),
        "above_50sma": None if pd.isna(sma_50) else bool(last_close > sma_50),
        "above_200sma": None if pd.isna(sma_200) else bool(last_close > sma_200),
        "macd_signal": _macd_signal(close),
        "volume_vs_20d_avg": vol_ratio,
    }
