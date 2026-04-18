"""Configuration loaders for SFE. YAML-backed, cached for the process."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def load_sentiment_weights() -> dict[str, float]:
    """Return the ``sentiment_weights`` map from ``config/sources.yaml``."""
    with (CONFIG_DIR / "sources.yaml").open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("sentiment_weights") or {}


@lru_cache(maxsize=1)
def load_watchlist() -> list[dict[str, Any]]:
    """Return the ticker entries from ``config/watchlist.yaml`` (may be empty)."""
    with (CONFIG_DIR / "watchlist.yaml").open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("tickers") or []
