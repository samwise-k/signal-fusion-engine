"""Anthropic Claude client wrapper for the meta-synthesis call.

Install the ``llm`` dependency group (``uv sync --group llm``) before use.
The system prompt is marked ``cache_control: ephemeral`` so repeated
morning runs hit the prompt cache — only the payload (volatile) changes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MODEL = "claude-opus-4-7"
MAX_TOKENS = 16000
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "daily_briefing.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text()


def generate_briefing(
    payload: dict[str, Any],
    system_prompt: str | None = None,
    *,
    model: str = MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Send ``payload`` through Claude and return the briefing markdown."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "anthropic SDK not installed — run `uv sync --group llm`"
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

    system_prompt = system_prompt or load_system_prompt()
    user_message = (
        "Produce today's briefing from this payload:\n\n"
        f"```json\n{json.dumps(payload, indent=2, default=str)}\n```"
    )

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        final = stream.get_final_message()

    parts = [
        block.text for block in final.content if getattr(block, "type", None) == "text"
    ]
    return "\n".join(parts).strip()
