"""Weighted daily sentiment aggregation across sources."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from loguru import logger

from src.engines.sentiment import news_fetcher, scorer, sec_fetcher, sec_item_codes

NOTABLE_HEADLINE_LIMIT = 3


def weighted_rollup(
    scored_items: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, Any]:
    """Aggregate per-item scores into the per-day sentiment payload.

    Each item in ``scored_items`` must have:
      - ``source``: a key into ``weights`` (e.g. ``"news_finnhub"``)
      - ``score``: float in [-1.0, 1.0]
    Other keys (``headline``, ``url``, ...) are ignored here.

    Sources with weight 0 (or missing from ``weights``) are dropped from both
    the breakdown and the overall score so an unconfigured source can't poison
    the rollup.
    """
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scored_items:
        by_source[item["source"]].append(item)

    breakdown: dict[str, dict[str, Any]] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for source, items in by_source.items():
        w = weights.get(source, 0.0)
        if w <= 0.0:
            continue
        avg = sum(i["score"] for i in items) / len(items)
        breakdown[source] = {"score": round(avg, 4), "count": len(items)}
        weighted_sum += avg * w
        weight_total += w

    overall = weighted_sum / weight_total if weight_total else 0.0
    return {
        "sentiment_score": round(overall, 4),
        "source_breakdown": breakdown,
    }


def _score_finnhub_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for art in articles:
        headline = art.get("headline") or ""
        summary = art.get("summary") or ""
        text = f"{headline}. {summary}".strip(". ")
        scored.append(
            {
                "source": "news_finnhub",
                "score": scorer.score_text(text),
                "headline": headline,
                "url": art.get("url"),
                "publisher": art.get("source"),
            }
        )
    return scored


def _score_edgar_filings(filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for f in filings:
        form = f.get("form") or ""
        items = f.get("items") or ""
        desc = f.get("primary_doc_description") or ""
        # Expand 8-K item codes (e.g. "2.02,7.01") into their SEC English
        # titles so TextBlob has real tokens to score. Without this, the
        # scorer sees just numeric codes and returns ~0.0.
        items_en = sec_item_codes.expand_items(items)
        text = ". ".join(part for part in (items_en, desc, form) if part)
        headline = f"{form} filed {f.get('filed_date', '')}".strip()
        if items:
            headline = f"{headline} — items {items}"
        scored.append(
            {
                "source": "sec_filings",
                "score": scorer.score_text(text),
                "headline": headline,
                "url": f.get("url"),
                "publisher": "SEC EDGAR",
            }
        )
    return scored


def _pick_notable(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(scored, key=lambda x: abs(x["score"]), reverse=True)
    out: list[dict[str, Any]] = []
    for item in ranked:
        if not item.get("headline"):
            continue
        out.append(
            {
                "headline": item["headline"],
                "url": item.get("url"),
                "publisher": item.get("publisher"),
                "score": round(item["score"], 4),
            }
        )
        if len(out) >= NOTABLE_HEADLINE_LIMIT:
            break
    return out


def aggregate(
    ticker: str,
    on_date: date,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """End-to-end sentiment rollup for one ticker on one day.

    Phase 1 wires Finnhub + SEC EDGAR. Reddit / finlight slot in here as each
    fetcher lands — append their scored items to ``scored`` and ensure the
    matching weight key exists in ``config/sources.yaml``.

    Per-source fetcher failures are logged and skipped so a single outage
    doesn't blank the briefing. Direction and 7-day delta are placeholders
    until the history slice lands.
    """
    if weights is None:
        from src.config import load_sentiment_weights

        weights = load_sentiment_weights()

    scored: list[dict[str, Any]] = []

    try:
        articles = news_fetcher.fetch_news(ticker, on_date)
    except Exception as exc:
        logger.warning(f"{ticker}: Finnhub fetch failed: {exc}")
    else:
        scored.extend(_score_finnhub_articles(articles))

    try:
        filings = sec_fetcher.fetch_filings(ticker, on_date)
    except Exception as exc:
        logger.warning(f"{ticker}: EDGAR fetch failed: {exc}")
    else:
        scored.extend(_score_edgar_filings(filings))

    rollup = weighted_rollup(scored, weights)

    return {
        "ticker": ticker,
        "date": on_date.isoformat(),
        "sentiment_score": rollup["sentiment_score"],
        "sentiment_direction": "stable",
        "sentiment_delta_7d": None,
        "source_breakdown": rollup["source_breakdown"],
        "key_topics": [],
        "notable_headlines": _pick_notable(scored),
    }
