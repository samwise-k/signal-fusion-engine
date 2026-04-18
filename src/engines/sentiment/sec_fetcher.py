"""SEC EDGAR fetcher (10-K, 10-Q, 8-K filings)."""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any

import httpx

EDGAR_DATA_BASE = "https://data.sec.gov"
EDGAR_FILES_BASE = "https://www.sec.gov/files"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_FORMS: tuple[str, ...] = ("10-K", "10-Q", "8-K")
DEFAULT_LOOKBACK_DAYS = 30
EDGAR_TIMEOUT = 20.0
# 10-K/10-Q primary docs commonly exceed 1MB of HTML. We truncate post-strip
# to bound TextBlob runtime and avoid a single long filing dominating the
# per-day rollup. 50k chars ≈ ~8k words — enough of the front matter to pick
# up MD&A-ish prose without drowning the scorer in risk-factor boilerplate.
BODY_MAX_CHARS = 50_000
_SKIP_TAGS = frozenset({"script", "style", "head", "title"})


def _user_agent() -> str:
    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_EDGAR_USER_AGENT not set; SEC requires a descriptive UA "
            "(e.g. 'sfe/0.1 (your-email@example.com)')"
        )
    return ua


@lru_cache(maxsize=1)
def _ticker_cik_map() -> dict[str, str]:
    """Return ``{TICKER: zero-padded-CIK}`` from SEC's master ticker file."""
    response = httpx.get(
        f"{EDGAR_FILES_BASE}/company_tickers.json",
        headers={"User-Agent": _user_agent()},
        timeout=EDGAR_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return {
        row["ticker"].upper(): str(row["cik_str"]).zfill(10)
        for row in data.values()
    }


def _ticker_to_cik(ticker: str) -> str | None:
    return _ticker_cik_map().get(ticker.upper())


def fetch_filings(
    ticker: str,
    on_date: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forms: tuple[str, ...] = DEFAULT_FORMS,
) -> list[dict[str, Any]]:
    """Return filings for ``ticker`` of type ``forms`` filed in the lookback window.

    Each dict carries: ``form``, ``filed_date``, ``accession_number``,
    ``primary_doc_description``, ``items`` (8-K item codes), and ``url`` to
    the primary document.
    """
    cik = _ticker_to_cik(ticker)
    if cik is None:
        return []

    headers = {"User-Agent": _user_agent()}
    response = httpx.get(
        f"{EDGAR_DATA_BASE}/submissions/CIK{cik}.json",
        headers=headers,
        timeout=EDGAR_TIMEOUT,
    )
    response.raise_for_status()
    recent = response.json().get("filings", {}).get("recent", {})

    forms_list: list[str] = recent.get("form", [])
    dates_list: list[str] = recent.get("filingDate", [])
    accession: list[str] = recent.get("accessionNumber", [])
    primary_docs: list[str] = recent.get("primaryDocument", [])
    primary_desc: list[str] = recent.get("primaryDocDescription", [])
    items_list: list[str] = recent.get("items", [])

    forms_set = set(forms)
    start = on_date - timedelta(days=max(lookback_days - 1, 0))
    cik_int = int(cik)
    out: list[dict[str, Any]] = []
    for i, form in enumerate(forms_list):
        if form not in forms_set:
            continue
        try:
            filed = date.fromisoformat(dates_list[i])
        except (ValueError, IndexError):
            continue
        if not (start <= filed <= on_date):
            continue

        acc_raw = accession[i] if i < len(accession) else ""
        doc = primary_docs[i] if i < len(primary_docs) else ""
        url = None
        if acc_raw and doc:
            url = f"{EDGAR_ARCHIVES_BASE}/{cik_int}/{acc_raw.replace('-', '')}/{doc}"

        out.append(
            {
                "form": form,
                "filed_date": dates_list[i],
                "accession_number": acc_raw,
                "primary_doc_description": primary_desc[i] if i < len(primary_desc) else "",
                "items": items_list[i] if i < len(items_list) else "",
                "url": url,
            }
        )
    return out


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.chunks.append(data)


def _html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return " ".join(" ".join(extractor.chunks).split())


@lru_cache(maxsize=256)
def fetch_filing_body(url: str) -> str:
    """Fetch a filing's primary document and return truncated plain text.

    Cached by URL (accession numbers are stable) so same-day reruns across
    multiple tickers don't re-hit SEC. Returns ``""`` for a falsy URL.
    """
    if not url:
        return ""
    response = httpx.get(
        url,
        headers={"User-Agent": _user_agent()},
        timeout=EDGAR_TIMEOUT,
    )
    response.raise_for_status()
    return _html_to_text(response.text)[:BODY_MAX_CHARS]
