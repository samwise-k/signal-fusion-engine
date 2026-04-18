"""Technical-health scoring.

Phase 2 ships a rule-based scorer so the pipeline is usable end-to-end.
The GBT model slots in later by swapping ``predict_health`` for a trained
estimator without changing the caller.
"""

from __future__ import annotations

from typing import Any


def predict_health(indicators: dict[str, Any]) -> str:
    """Return ``'strong' | 'neutral' | 'weak'`` from a technicals payload.

    Scores five bullish conditions (price above both SMAs, RSI not oversold,
    MACD positive, above-average volume with a positive 5-day return).
    Oversold (RSI<30) or blown-out (RSI>70) conditions subtract. Threshold
    tuning deferred — the meta-layer sees the raw indicators too, so this
    label is just a coarse pre-filter.
    """
    score = 0

    if indicators.get("above_50sma"):
        score += 1
    if indicators.get("above_200sma"):
        score += 1

    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if 40 <= rsi <= 65:
            score += 1
        elif rsi > 75 or rsi < 25:
            score -= 1

    macd = indicators.get("macd_signal") or ""
    if "bullish" in macd:
        score += 1
    elif "bearish" in macd:
        score -= 1

    vol_ratio = indicators.get("volume_vs_20d_avg")
    change_5d = indicators.get("change_5d")
    if vol_ratio and vol_ratio > 1.2 and change_5d is not None:
        score += 1 if change_5d > 0 else -1

    if score >= 3:
        return "strong"
    if score <= -1:
        return "weak"
    return "neutral"
