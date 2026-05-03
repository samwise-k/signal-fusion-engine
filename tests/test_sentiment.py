"""Tests for the sentiment engine package."""

from __future__ import annotations

from datetime import date

import pytest

from src.engines.sentiment import (
    aggregator,
    finlight_fetcher,
    news_fetcher,
    scorer,
    sec_fetcher,
    sec_item_codes,
)

# Capture the real body fetcher before the autouse stub replaces it, so tests
# that need to exercise the actual function can restore it.
_REAL_FETCH_FILING_BODY = sec_fetcher.fetch_filing_body
_REAL_FINLIGHT_FETCH_NEWS = finlight_fetcher.fetch_news


def test_sentiment_package_imports() -> None:
    from src.engines.sentiment import (  # noqa: F401
        aggregator,
        news_fetcher,
        scorer,
        sec_fetcher,
        social_fetcher,
    )


class TestScoreText:
    def test_positive_text_scores_positive(self) -> None:
        assert scorer.score_text("Excellent results, fantastic growth, beat estimates") > 0.2

    def test_negative_text_scores_negative(self) -> None:
        assert scorer.score_text("Terrible miss, awful guidance, disastrous quarter") < -0.2

    def test_empty_returns_neutral(self) -> None:
        assert scorer.score_text("") == 0.0
        assert scorer.score_text("   \n\t  ") == 0.0

    def test_score_is_bounded(self) -> None:
        assert -1.0 <= scorer.score_text("ok") <= 1.0


WEIGHTS = {
    "sec_filings": 1.0,
    "news_finnhub": 0.8,
    "news_finlight": 0.8,
    "social_reddit": 0.4,
}


class TestWeightedRollup:
    def test_empty_input_yields_neutral(self) -> None:
        out = aggregator.weighted_rollup([], WEIGHTS)
        assert out == {"sentiment_score": 0.0, "source_breakdown": {}}

    def test_single_source_score_passes_through(self) -> None:
        out = aggregator.weighted_rollup(
            [{"source": "news_finnhub", "score": 0.5}], WEIGHTS
        )
        assert out["sentiment_score"] == 0.5
        assert out["source_breakdown"] == {"news_finnhub": {"score": 0.5, "count": 1}}

    def test_per_source_average_then_weighted(self) -> None:
        # Reddit averages to 0.0 (one +0.6, one -0.6); SEC alone is +0.8.
        # overall = (0.0 * 0.4 + 0.8 * 1.0) / (0.4 + 1.0) ≈ 0.5714
        items = [
            {"source": "social_reddit", "score": 0.6},
            {"source": "social_reddit", "score": -0.6},
            {"source": "sec_filings", "score": 0.8},
        ]
        out = aggregator.weighted_rollup(items, WEIGHTS)
        assert out["sentiment_score"] == pytest.approx(0.5714, abs=1e-3)
        assert out["source_breakdown"]["social_reddit"] == {"score": 0.0, "count": 2}
        assert out["source_breakdown"]["sec_filings"] == {"score": 0.8, "count": 1}

    def test_unweighted_source_is_dropped(self) -> None:
        items = [
            {"source": "news_finnhub", "score": 0.5},
            {"source": "twitter_unknown", "score": 1.0},
        ]
        out = aggregator.weighted_rollup(items, WEIGHTS)
        assert "twitter_unknown" not in out["source_breakdown"]
        assert out["sentiment_score"] == 0.5

class TestDedupArticles:
    def test_cross_source_duplicate_removed(self) -> None:
        items = [
            {"source": "news_finnhub", "score": 0.5, "headline": "LMT wins contract", "publisher": "Reuters"},
            {"source": "news_finlight", "score": 0.6, "headline": "LMT wins contract", "publisher": "reuters.com"},
        ]
        out = aggregator._dedup_articles(items)
        assert len(out) == 1
        assert out[0]["source"] == "news_finnhub"

    def test_different_headlines_kept(self) -> None:
        items = [
            {"source": "news_finnhub", "score": 0.5, "headline": "LMT wins contract", "publisher": "Reuters"},
            {"source": "news_finlight", "score": 0.6, "headline": "NVDA beats estimates", "publisher": "Reuters"},
        ]
        out = aggregator._dedup_articles(items)
        assert len(out) == 2

    def test_case_and_punctuation_normalized(self) -> None:
        items = [
            {"source": "news_finnhub", "score": 0.5, "headline": "LMT Wins Contract!", "publisher": "Reuters"},
            {"source": "news_finlight", "score": 0.6, "headline": "lmt wins contract", "publisher": "reuters"},
        ]
        out = aggregator._dedup_articles(items)
        assert len(out) == 1

    def test_empty_headlines_never_deduped(self) -> None:
        items = [
            {"source": "news_finnhub", "score": 0.0, "headline": "", "publisher": ""},
            {"source": "news_finlight", "score": 0.0, "headline": "", "publisher": ""},
            {"source": "sec_filings", "score": 0.1, "headline": "8-K filed 2026-04-15", "publisher": "SEC EDGAR"},
        ]
        out = aggregator._dedup_articles(items)
        assert len(out) == 3


class TestApplyHistory:
    def _payload(self, score: float) -> dict:
        return {
            "sentiment_score": score,
            "sentiment_direction": "stable",
            "sentiment_delta_7d": None,
        }

    def test_no_prior_keeps_stable_and_none(self) -> None:
        out = aggregator.apply_history(self._payload(0.42), None)
        assert out["sentiment_direction"] == "stable"
        assert out["sentiment_delta_7d"] is None

    def test_rising_above_threshold(self) -> None:
        out = aggregator.apply_history(self._payload(0.30), 0.10)
        assert out["sentiment_direction"] == "rising"
        assert out["sentiment_delta_7d"] == pytest.approx(0.20)

    def test_falling_below_threshold(self) -> None:
        out = aggregator.apply_history(self._payload(-0.20), 0.10)
        assert out["sentiment_direction"] == "falling"
        assert out["sentiment_delta_7d"] == pytest.approx(-0.30)

    def test_within_threshold_is_stable(self) -> None:
        out = aggregator.apply_history(self._payload(0.12), 0.10)
        assert out["sentiment_direction"] == "stable"
        assert out["sentiment_delta_7d"] == pytest.approx(0.02)

    def test_exact_threshold_is_stable(self) -> None:
        # Equal to threshold (not strictly greater) should not flip direction.
        out = aggregator.apply_history(
            self._payload(0.10 + aggregator.DIRECTION_THRESHOLD), 0.10
        )
        assert out["sentiment_direction"] == "stable"


FAKE_FINNHUB_ARTICLES = [
    {
        "headline": "Lockheed Martin secures $2.1B Navy contract extension",
        "summary": "Excellent results, fantastic growth for the defense prime.",
        "url": "https://example.com/1",
        "source": "Reuters",
    },
    {
        "headline": "Analyst warns of disastrous quarter for LMT",
        "summary": "Terrible miss, awful guidance.",
        "url": "https://example.com/2",
        "source": "Bloomberg",
    },
    {
        "headline": "",
        "summary": "",
        "url": "https://example.com/3",
        "source": "Unknown",
    },
]


class TestHtmlToText:
    def test_strips_tags_and_collapses_whitespace(self) -> None:
        html = "<html><body><p>Hello  <b>world</b>.</p>\n\n<p>Next.</p></body></html>"
        assert sec_fetcher._html_to_text(html) == "Hello world . Next."

    def test_drops_script_and_style(self) -> None:
        html = (
            "<html><head><style>body{}</style></head>"
            "<body>Keep.<script>var x = 1;</script> Done.</body></html>"
        )
        out = sec_fetcher._html_to_text(html)
        assert "Keep" in out and "Done" in out
        assert "var x" not in out and "body{}" not in out


class TestFetchFilingBody:
    def test_empty_url_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sec_fetcher, "fetch_filing_body", _REAL_FETCH_FILING_BODY)
        assert sec_fetcher.fetch_filing_body("") == ""

    def test_fetches_strips_and_truncates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec_fetcher, "fetch_filing_body", _REAL_FETCH_FILING_BODY)
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "sfe-test/0.1 (test@example.com)")
        big_body = "excellent " * 10_000  # 100k chars after HTML wrap

        class FakeResp:
            text = f"<html><body>{big_body}</body></html>"
            def raise_for_status(self) -> None: ...

        monkeypatch.setattr(sec_fetcher.httpx, "get", lambda *a, **kw: FakeResp())
        out = sec_fetcher.fetch_filing_body("https://sec.gov/fake.htm")
        assert len(out) == sec_fetcher.BODY_MAX_CHARS
        assert "excellent" in out

    def test_caches_by_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sec_fetcher, "fetch_filing_body", _REAL_FETCH_FILING_BODY)
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "sfe-test/0.1 (test@example.com)")
        calls = {"n": 0}

        class FakeResp:
            text = "<p>once</p>"
            def raise_for_status(self) -> None: ...

        def fake_get(*a, **kw):
            calls["n"] += 1
            return FakeResp()

        monkeypatch.setattr(sec_fetcher.httpx, "get", fake_get)
        url = "https://sec.gov/cached.htm"
        sec_fetcher.fetch_filing_body(url)
        sec_fetcher.fetch_filing_body(url)
        assert calls["n"] == 1


class TestExpandItemCodes:
    def test_empty_input_is_empty(self) -> None:
        assert sec_item_codes.expand_items("") == ""

    def test_expands_known_codes(self) -> None:
        out = sec_item_codes.expand_items("2.02,7.01")
        assert "Results of Operations" in out
        assert "Regulation FD" in out

    def test_tolerates_whitespace(self) -> None:
        assert sec_item_codes.expand_items("2.02, 7.01") == sec_item_codes.expand_items(
            "2.02,7.01"
        )

    def test_drops_unknown_codes(self) -> None:
        out = sec_item_codes.expand_items("2.02,9.99")
        assert "Results of Operations" in out
        assert "9.99" not in out

    def test_every_code_expands_to_non_empty_english(self) -> None:
        # Every mapped code produces parseable text regardless of backend.
        for code, title in sec_item_codes.ITEM_CODE_TITLES.items():
            expanded = sec_item_codes.expand_items(code)
            assert expanded == title
            assert any(c.isalpha() for c in expanded)


class TestFetchNews:
    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FINNHUB_KEY", raising=False)
        with pytest.raises(RuntimeError, match="FINNHUB_KEY"):
            news_fetcher.fetch_news("LMT", date(2026, 4, 17))

    def test_calls_finnhub_with_expected_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        class FakeResponse:
            def raise_for_status(self) -> None: ...
            def json(self) -> list[dict]:
                return FAKE_FINNHUB_ARTICLES

        def fake_get(url: str, params: dict, timeout: float) -> FakeResponse:
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

        monkeypatch.setenv("FINNHUB_KEY", "test-key")
        monkeypatch.setattr(news_fetcher.httpx, "get", fake_get)

        out = news_fetcher.fetch_news("LMT", date(2026, 4, 17), lookback_days=3)

        assert out == FAKE_FINNHUB_ARTICLES
        assert captured["url"].endswith("/company-news")
        assert captured["params"] == {
            "symbol": "LMT",
            "from": "2026-04-15",
            "to": "2026-04-17",
            "token": "test-key",
        }


FAKE_FINLIGHT_ARTICLES = [
    {
        "title": "LMT wins fantastic new contract, excellent growth ahead",
        "summary": "Beat estimates across the board.",
        "link": "https://example.com/fl1",
        "source": "reuters.com",
        "publishDate": "2026-04-16T10:00:00Z",
        "sentiment": "positive",
        "confidence": 0.92,
    },
    {
        "title": "Disastrous quarter feared at defense prime",
        "summary": "Awful guidance, terrible miss.",
        "link": "https://example.com/fl2",
        "source": "bloomberg.com",
        "publishDate": "2026-04-16T11:00:00Z",
        "sentiment": "negative",
        "confidence": 0.88,
    },
]


class TestFinlightFetchNews:
    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(finlight_fetcher, "fetch_news", _REAL_FINLIGHT_FETCH_NEWS)
        monkeypatch.delenv("FINLIGHT_KEY", raising=False)
        with pytest.raises(RuntimeError, match="FINLIGHT_KEY"):
            finlight_fetcher.fetch_news("LMT", date(2026, 4, 17))

    def test_posts_json_body_with_expected_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        class FakeResponse:
            def raise_for_status(self) -> None: ...
            def json(self) -> dict:
                return {"status": "ok", "articles": FAKE_FINLIGHT_ARTICLES}

        def fake_post(url: str, json: dict, headers: dict, timeout: float):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        monkeypatch.setattr(finlight_fetcher, "fetch_news", _REAL_FINLIGHT_FETCH_NEWS)
        monkeypatch.setenv("FINLIGHT_KEY", "test-key")
        monkeypatch.setattr(finlight_fetcher.httpx, "post", fake_post)

        out = finlight_fetcher.fetch_news("LMT", date(2026, 4, 17), lookback_days=3)

        assert out == FAKE_FINLIGHT_ARTICLES
        assert captured["url"].endswith("/v2/articles")
        assert captured["headers"]["X-API-KEY"] == "test-key"
        assert captured["json"]["tickers"] == ["LMT"]
        assert captured["json"]["from"] == "2026-04-15"
        assert captured["json"]["to"] == "2026-04-17"
        assert captured["json"]["language"] == "en"

    def test_missing_articles_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None: ...
            def json(self) -> dict:
                return {"status": "ok"}

        monkeypatch.setattr(finlight_fetcher, "fetch_news", _REAL_FINLIGHT_FETCH_NEWS)
        monkeypatch.setenv("FINLIGHT_KEY", "test-key")
        monkeypatch.setattr(
            finlight_fetcher.httpx,
            "post",
            lambda *a, **kw: FakeResponse(),
        )
        assert finlight_fetcher.fetch_news("LMT", date(2026, 4, 17)) == []


class TestAggregateEndToEnd:
    def test_aggregate_returns_full_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            aggregator.news_fetcher,
            "fetch_news",
            lambda ticker, on_date: FAKE_FINNHUB_ARTICLES,
        )

        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)

        assert out["ticker"] == "LMT"
        assert out["date"] == "2026-04-17"
        assert "news_finnhub" in out["source_breakdown"]
        assert out["source_breakdown"]["news_finnhub"]["count"] == 3
        # Two real headlines selected; the empty-headline article is filtered out.
        assert len(out["notable_headlines"]) == 2
        assert all(h["headline"] for h in out["notable_headlines"])
        # Most-extreme score first.
        scores = [h["score"] for h in out["notable_headlines"]]
        assert abs(scores[0]) >= abs(scores[1])
        # Phase 1 placeholders for fields filled by the history slice.
        assert out["sentiment_direction"] == "stable"
        assert out["sentiment_delta_7d"] is None
        assert out["key_topics"] == []

    def test_aggregate_with_no_articles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            aggregator.news_fetcher, "fetch_news", lambda ticker, on_date: []
        )
        monkeypatch.setattr(
            aggregator.sec_fetcher, "fetch_filings", lambda ticker, on_date: []
        )
        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        assert out["sentiment_score"] == 0.0
        assert out["source_breakdown"] == {}
        assert out["notable_headlines"] == []

    def test_finnhub_failure_does_not_blank_briefing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a, **kw):
            raise RuntimeError("Finnhub down")

        monkeypatch.setattr(aggregator.news_fetcher, "fetch_news", boom)
        monkeypatch.setattr(
            aggregator.sec_fetcher,
            "fetch_filings",
            lambda ticker, on_date: FAKE_EDGAR_FILINGS,
        )
        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        assert "sec_filings" in out["source_breakdown"]
        assert "news_finnhub" not in out["source_breakdown"]

    def test_aggregates_finnhub_and_edgar_together(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            aggregator.news_fetcher,
            "fetch_news",
            lambda ticker, on_date: FAKE_FINNHUB_ARTICLES,
        )
        monkeypatch.setattr(
            aggregator.sec_fetcher,
            "fetch_filings",
            lambda ticker, on_date: FAKE_EDGAR_FILINGS,
        )
        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        assert out["source_breakdown"]["news_finnhub"]["count"] == 3
        assert out["source_breakdown"]["sec_filings"]["count"] == len(
            FAKE_EDGAR_FILINGS
        )

    def test_aggregates_finlight_articles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            aggregator.news_fetcher, "fetch_news", lambda t, d: []
        )
        monkeypatch.setattr(
            aggregator.sec_fetcher, "fetch_filings", lambda t, d: []
        )
        monkeypatch.setattr(
            aggregator.finlight_fetcher,
            "fetch_news",
            lambda t, d: FAKE_FINLIGHT_ARTICLES,
        )
        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        assert out["source_breakdown"]["news_finlight"]["count"] == len(
            FAKE_FINLIGHT_ARTICLES
        )
        assert any(
            h["url"] and h["url"].startswith("https://example.com/fl")
            for h in out["notable_headlines"]
        )

    def test_finlight_failure_does_not_blank_briefing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a, **kw):
            raise RuntimeError("finlight down")

        monkeypatch.setattr(
            aggregator.news_fetcher,
            "fetch_news",
            lambda t, d: FAKE_FINNHUB_ARTICLES,
        )
        monkeypatch.setattr(aggregator.finlight_fetcher, "fetch_news", boom)
        monkeypatch.setattr(
            aggregator.sec_fetcher, "fetch_filings", lambda t, d: []
        )
        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        assert "news_finnhub" in out["source_breakdown"]
        assert "news_finlight" not in out["source_breakdown"]

    def test_body_text_feeds_edgar_scoring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the body-fetch plumbing is wired: a positive body yields a
        positive score; a negative body yields a negative score, on the same
        10-Q filing whose items/description alone would score ~0."""
        filing = [
            {
                "form": "10-Q",
                "filed_date": "2026-04-10",
                "accession_number": "0000936468-26-000099",
                "primary_doc_description": "Quarterly report",
                "items": "",
                "url": "https://sec.gov/fake-10q.htm",
            }
        ]
        monkeypatch.setattr(
            aggregator.news_fetcher, "fetch_news", lambda t, d: []
        )
        monkeypatch.setattr(
            aggregator.sec_fetcher, "fetch_filings", lambda t, d: filing
        )

        monkeypatch.setattr(
            aggregator.sec_fetcher,
            "fetch_filing_body",
            lambda url: "Excellent results, fantastic growth, beat estimates.",
        )
        pos = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)

        monkeypatch.setattr(
            aggregator.sec_fetcher,
            "fetch_filing_body",
            lambda url: "Terrible miss, awful guidance, disastrous quarter.",
        )
        neg = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)

        assert pos["sentiment_score"] > 0.2
        assert neg["sentiment_score"] < -0.2

    def test_body_fetch_failure_falls_back_to_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(url: str) -> str:
            raise RuntimeError("SEC down")

        monkeypatch.setattr(
            aggregator.news_fetcher, "fetch_news", lambda t, d: []
        )
        monkeypatch.setattr(
            aggregator.sec_fetcher,
            "fetch_filings",
            lambda t, d: FAKE_EDGAR_FILINGS,
        )
        monkeypatch.setattr(aggregator.sec_fetcher, "fetch_filing_body", boom)

        out = aggregator.aggregate("LMT", date(2026, 4, 17), weights=WEIGHTS)
        # Filings still aggregate via item-code + metadata expansion.
        assert out["source_breakdown"]["sec_filings"]["count"] == len(
            FAKE_EDGAR_FILINGS
        )


FAKE_EDGAR_FILINGS = [
    {
        "form": "8-K",
        "filed_date": "2026-04-15",
        "accession_number": "0000936468-26-000123",
        "primary_doc_description": "Current report",
        "items": "2.02,7.01",
        "url": "https://www.sec.gov/Archives/edgar/data/936468/000093646826000123/lmt-8k.htm",
    },
    {
        "form": "10-Q",
        "filed_date": "2026-04-10",
        "accession_number": "0000936468-26-000099",
        "primary_doc_description": "Quarterly report",
        "items": "",
        "url": "https://www.sec.gov/Archives/edgar/data/936468/000093646826000099/lmt-10q.htm",
    },
]

FAKE_TICKERS_JSON = {
    "0": {"cik_str": 936468, "ticker": "LMT", "title": "Lockheed Martin Corp"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc"},
}

FAKE_SUBMISSIONS_JSON = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K", "DEF 14A", "10-K"],
            "filingDate": [
                "2026-04-15",
                "2026-04-10",
                "2026-03-01",  # outside default 30-day window from 2026-04-17
                "2026-04-12",  # filtered out by form
                "2026-02-20",  # outside window
            ],
            "accessionNumber": [
                "0000936468-26-000123",
                "0000936468-26-000099",
                "0000936468-26-000050",
                "0000936468-26-000080",
                "0000936468-26-000010",
            ],
            "primaryDocument": [
                "lmt-8k.htm",
                "lmt-10q.htm",
                "lmt-8k-old.htm",
                "lmt-def14a.htm",
                "lmt-10k.htm",
            ],
            "primaryDocDescription": [
                "Current report",
                "Quarterly report",
                "Current report",
                "Proxy statement",
                "Annual report",
            ],
            "items": ["2.02,7.01", "", "8.01", "", ""],
        }
    }
}


@pytest.fixture(autouse=True)
def _clear_edgar_caches():
    # Only clear at setup — monkeypatch may have replaced these attributes by
    # teardown, so calling cache_clear post-yield can hit a bare function.
    sec_fetcher._ticker_cik_map.cache_clear()
    sec_fetcher.fetch_filing_body.cache_clear()
    yield


@pytest.fixture(autouse=True)
def _stub_finlight_fetch(monkeypatch: pytest.MonkeyPatch):
    """Default: no-op finlight fetch so aggregator tests don't hit the network
    or require FINLIGHT_KEY. Tests that want to exercise finlight override it."""
    monkeypatch.setattr(
        aggregator.finlight_fetcher, "fetch_news", lambda ticker, on_date: []
    )


@pytest.fixture(autouse=True)
def _stub_edgar_body_fetch(monkeypatch: pytest.MonkeyPatch):
    """Default: no-op body fetch so aggregator tests don't hit the network.
    Tests that want to exercise body fetching override this.
    """
    monkeypatch.setattr(sec_fetcher, "fetch_filing_body", lambda url: "")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None: ...

    def json(self):
        return self._payload


class TestFetchFilings:
    def test_missing_user_agent_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
        with pytest.raises(RuntimeError, match="SEC_EDGAR_USER_AGENT"):
            sec_fetcher.fetch_filings("LMT", date(2026, 4, 17))

    def test_unknown_ticker_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "sfe/0.1 (test@example.com)")
        monkeypatch.setattr(
            sec_fetcher.httpx,
            "get",
            lambda url, headers, timeout: _FakeResponse(FAKE_TICKERS_JSON),
        )
        assert sec_fetcher.fetch_filings("ZZZZ", date(2026, 4, 17)) == []

    def test_filters_by_form_and_date_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "sfe/0.1 (test@example.com)")

        def fake_get(url: str, headers: dict, timeout: float) -> _FakeResponse:
            if "company_tickers" in url:
                return _FakeResponse(FAKE_TICKERS_JSON)
            if "submissions/CIK" in url:
                assert "CIK0000936468" in url
                return _FakeResponse(FAKE_SUBMISSIONS_JSON)
            raise AssertionError(f"unexpected URL: {url}")

        monkeypatch.setattr(sec_fetcher.httpx, "get", fake_get)

        out = sec_fetcher.fetch_filings("LMT", date(2026, 4, 17))

        # Only the 8-K from 2026-04-15 and the 10-Q from 2026-04-10 survive:
        # - the 2026-03-01 8-K is outside the 14-day window
        # - DEF 14A and the older 10-K are filtered by form / window
        assert [(f["form"], f["filed_date"]) for f in out] == [
            ("8-K", "2026-04-15"),
            ("10-Q", "2026-04-10"),
        ]
        assert out[0]["items"] == "2.02,7.01"
        assert out[0]["url"].endswith("/lmt-8k.htm")
        assert "/936468/" in out[0]["url"]
