"""Weighted daily sentiment aggregation across sources."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

from loguru import logger

from src.engines.sentiment import (
    finlight_fetcher,
    news_fetcher,
    scorer,
    sec_fetcher,
    sec_item_codes,
)

NOTABLE_HEADLINE_LIMIT = 3
DIRECTION_THRESHOLD = 0.05


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
    texts: list[str] = []
    meta: list[dict[str, Any]] = []
    for art in articles:
        headline = art.get("headline") or ""
        summary = art.get("summary") or ""
        texts.append(f"{headline}. {summary}".strip(". "))
        meta.append({"headline": headline, "url": art.get("url"), "publisher": art.get("source")})
    scores = scorer.score_texts(texts)
    return [
        {"source": "news_finnhub", "score": s, **m}
        for s, m in zip(scores, meta)
    ]


def _score_finlight_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts: list[str] = []
    meta: list[dict[str, Any]] = []
    for art in articles:
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        texts.append(f"{title}. {summary}".strip(". "))
        meta.append({"headline": title, "url": art.get("link"), "publisher": art.get("source")})
    scores = scorer.score_texts(texts)
    return [
        {"source": "news_finlight", "score": s, **m}
        for s, m in zip(scores, meta)
    ]


def _score_edgar_filings(filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts: list[str] = []
    meta: list[dict[str, Any]] = []
    for f in filings:
        form = f.get("form") or ""
        items = f.get("items") or ""
        desc = f.get("primary_doc_description") or ""
        # Expand 8-K item codes (e.g. "2.02,7.01") into their SEC English
        # titles so the scorer sees real tokens, not numeric codes.
        items_en = sec_item_codes.expand_items(items)
        # Best-effort body fetch — gives 10-K/10-Q actual prose to score.
        # Isolated per-filing so one flaky doc doesn't blank the batch.
        url = f.get("url") or ""
        body = ""
        if url:
            try:
                body = sec_fetcher.fetch_filing_body(url)
            except Exception as exc:
                logger.warning(f"EDGAR body fetch failed for {url}: {exc}")
        texts.append(". ".join(part for part in (items_en, desc, form, body) if part))
        headline = f"{form} filed {f.get('filed_date', '')}".strip()
        if items:
            headline = f"{headline} — items {items}"
        meta.append({"headline": headline, "url": f.get("url"), "publisher": "SEC EDGAR"})
    scores = scorer.score_texts(texts)
    return [
        {"source": "sec_filings", "score": s, **m}
        for s, m in zip(scores, meta)
    ]


def _normalize_headline(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _dedup_articles(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop cross-source duplicate articles (wire-service reprints).

    Keyed on normalized headline only — publisher names vary across sources
    for the same wire story (e.g. "Reuters" vs "reuters.com"). Empty
    headlines are never deduped (they're typically EDGAR filings with
    generated descriptions). First occurrence wins, so source ordering in
    ``aggregate()`` determines tie-breaking.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in scored:
        headline = item.get("headline") or ""
        key = _normalize_headline(headline)
        if not key or key not in seen:
            if key:
                seen.add(key)
            out.append(item)
    return out


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


def apply_history(
    payload: dict[str, Any],
    prior_score: float | None,
) -> dict[str, Any]:
    """Set ``sentiment_direction`` and ``sentiment_delta_7d`` on ``payload``
    given the score from roughly a week ago.

    Pure function — pipeline.py is responsible for fetching ``prior_score``
    from the repo and passing it in. With no prior datapoint, direction
    stays ``"stable"`` and delta stays ``None`` so the row is still writable
    on day-one of a new ticker.
    """
    if prior_score is None:
        payload["sentiment_delta_7d"] = None
        payload["sentiment_direction"] = "stable"
        return payload

    delta = round(payload["sentiment_score"] - prior_score, 4)
    payload["sentiment_delta_7d"] = delta
    if delta > DIRECTION_THRESHOLD:
        payload["sentiment_direction"] = "rising"
    elif delta < -DIRECTION_THRESHOLD:
        payload["sentiment_direction"] = "falling"
    else:
        payload["sentiment_direction"] = "stable"
    return payload


def aggregate(
    ticker: str,
    on_date: date,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """End-to-end sentiment rollup for one ticker on one day.

    Phase 1 wires Finnhub, finlight, and SEC EDGAR. Reddit slots in here
    once its fetcher lands — append its scored items to ``scored`` and
    ensure the matching weight key exists in ``config/sources.yaml``.

    Per-source fetcher failures are logged and skipped so a single outage
    doesn't blank the briefing. Direction and 7-day delta are filled by
    ``apply_history`` once the pipeline supplies the prior score.
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
        finlight_articles = finlight_fetcher.fetch_news(ticker, on_date)
    except Exception as exc:
        logger.warning(f"{ticker}: finlight fetch failed: {exc}")
    else:
        scored.extend(_score_finlight_articles(finlight_articles))

    try:
        filings = sec_fetcher.fetch_filings(ticker, on_date)
    except Exception as exc:
        logger.warning(f"{ticker}: EDGAR fetch failed: {exc}")
    else:
        scored.extend(_score_edgar_filings(filings))

    scored = _dedup_articles(scored)
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
