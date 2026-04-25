"""FinBERT backend tests. Skipped unless the sentiment-ml group is installed.

These hit the real ProsusAI/finbert model on first run (downloads weights),
so they're kept out of the default suite to preserve its speed. Run with:

    uv run --group sentiment-ml pytest tests/test_finbert.py
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("transformers") is None
    or importlib.util.find_spec("torch") is None,
    reason="sentiment-ml group not installed",
)


@pytest.fixture(autouse=True)
def _ensure_finbert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTIMENT_SCORER", raising=False)


def test_positive_finance_text_scores_positive() -> None:
    from src.engines.sentiment import scorer

    s = scorer.score_text("The company beat earnings estimates and raised full-year guidance.")
    assert s > 0.2


def test_negative_finance_text_scores_negative() -> None:
    from src.engines.sentiment import scorer

    s = scorer.score_text("The company disclosed a material weakness and going concern doubt.")
    assert s < -0.2


def test_empty_returns_neutral() -> None:
    from src.engines.sentiment import scorer

    assert scorer.score_text("") == 0.0
    assert scorer.score_text("   ") == 0.0


def test_batch_matches_single() -> None:
    from src.engines.sentiment import scorer

    texts = [
        "Beat estimates, strong guidance.",
        "Missed badly, slashed outlook.",
    ]
    batch = scorer.score_texts(texts)
    singles = [scorer.score_text(t) for t in texts]
    for b, s in zip(batch, singles):
        assert abs(b - s) < 1e-4


def test_long_text_is_chunked_not_truncated() -> None:
    from src.engines.sentiment import scorer

    # Negative tail after a long neutral preamble. Truncation would miss it;
    # chunking should pull the overall score into negative territory.
    preamble = "This is a standard quarterly filing. " * 500
    tail = " Material weakness identified. Going concern doubt. Impairment charge recognized."
    s = scorer.score_text(preamble + tail)
    assert s < 0.0
