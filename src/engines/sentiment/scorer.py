"""Sentiment scoring with pluggable backends.

Default backend is FinBERT (ProsusAI/finbert) — finance-domain accuracy that
matters for SEC filings and earnings text. Requires the ``sentiment-ml``
dependency group (``uv sync --group sentiment-ml``). Falls back to TextBlob
with a warning if torch/transformers are not installed. Override with
``SENTIMENT_SCORER=textblob`` for lightweight dev/CI runs.
"""

from __future__ import annotations

import os
from functools import lru_cache


def score_text(text: str) -> float:
    """Return a sentiment score in [-1.0, 1.0] for ``text``.

    Empty or whitespace-only input returns 0.0 (neutral) so upstream fetchers
    can pass article snippets without pre-filtering.
    """
    if not text or not text.strip():
        return 0.0
    return score_texts([text])[0]


def score_texts(texts: list[str]) -> list[float]:
    """Batch variant of :func:`score_text`. Same [-1.0, 1.0] output semantics.

    FinBERT benefits substantially from batching; TextBlob is unaffected but
    keeps the same interface so callers don't branch on backend.
    """
    if not texts:
        return []
    backend = _resolve_backend()
    return backend(texts)


def _resolve_backend():
    import importlib.util

    name = os.environ.get("SENTIMENT_SCORER", "finbert").strip().lower()
    if name == "finbert":
        if (
            importlib.util.find_spec("transformers") is not None
            and importlib.util.find_spec("torch") is not None
        ):
            return _finbert_score
        import logging

        logging.getLogger(__name__).warning(
            "FinBERT requested but sentiment-ml deps missing; falling back to TextBlob. "
            "Install with: uv sync --group sentiment-ml"
        )
    return _textblob_score


def _textblob_score(texts: list[str]) -> list[float]:
    from textblob import TextBlob

    out: list[float] = []
    for t in texts:
        if not t or not t.strip():
            out.append(0.0)
        else:
            out.append(float(TextBlob(t).sentiment.polarity))
    return out


# FinBERT: ProsusAI/finbert, 3-class (positive/negative/neutral).
# Score = P(positive) - P(negative), naturally bounded to [-1, 1].
_FINBERT_MODEL = "ProsusAI/finbert"
_FINBERT_MAX_TOKENS = 510  # 512 minus [CLS]/[SEP]
_FINBERT_CHUNK_THRESHOLD_CHARS = 2000  # ~500 tokens at 4 chars/token heuristic
_FINBERT_BATCH_SIZE = 16


@lru_cache(maxsize=1)
def _load_finbert():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_FINBERT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(_FINBERT_MODEL)
    model.eval()
    # Label order for ProsusAI/finbert: positive, negative, neutral.
    id2label = {i: model.config.id2label[i].lower() for i in range(model.config.num_labels)}
    pos_idx = next(i for i, l in id2label.items() if l == "positive")
    neg_idx = next(i for i, l in id2label.items() if l == "negative")
    return tokenizer, model, torch, pos_idx, neg_idx


def _finbert_score(texts: list[str]) -> list[float]:
    tokenizer, model, torch, pos_idx, neg_idx = _load_finbert()

    # Expand each input into chunks; remember the mapping so we can average
    # chunk scores back up to one score per original input.
    chunks: list[str] = []
    owners: list[int] = []
    neutrals: dict[int, float] = {}
    for i, text in enumerate(texts):
        if not text or not text.strip():
            neutrals[i] = 0.0
            continue
        if len(text) <= _FINBERT_CHUNK_THRESHOLD_CHARS:
            chunks.append(text)
            owners.append(i)
        else:
            for piece in _chunk_by_tokens(text, tokenizer):
                chunks.append(piece)
                owners.append(i)

    per_chunk_scores: list[float] = []
    for start in range(0, len(chunks), _FINBERT_BATCH_SIZE):
        batch = chunks[start : start + _FINBERT_BATCH_SIZE]
        enc = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=_FINBERT_MAX_TOKENS + 2,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(**enc).logits
        probs = torch.softmax(logits, dim=-1)
        per_chunk_scores.extend(
            (probs[:, pos_idx] - probs[:, neg_idx]).tolist()
        )

    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for owner, s in zip(owners, per_chunk_scores):
        sums[owner] = sums.get(owner, 0.0) + s
        counts[owner] = counts.get(owner, 0) + 1

    out: list[float] = []
    for i in range(len(texts)):
        if i in neutrals:
            out.append(0.0)
        else:
            out.append(sums[i] / counts[i])
    return out


def _chunk_by_tokens(text: str, tokenizer) -> list[str]:
    """Split ``text`` into chunks that each tokenize to <= max tokens.

    Token-accurate so we don't silently lose the tail of long filings.
    """
    ids = tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        return []
    pieces: list[str] = []
    for start in range(0, len(ids), _FINBERT_MAX_TOKENS):
        window = ids[start : start + _FINBERT_MAX_TOKENS]
        pieces.append(tokenizer.decode(window, skip_special_tokens=True))
    return pieces
