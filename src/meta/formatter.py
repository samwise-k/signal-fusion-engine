"""Format the LLM briefing output for terminal/email delivery.

The prompt already asks Claude for markdown in the target shape, so this
is a thin passthrough: strip whitespace and prepend a header if the
model didn't already include a dated title line. Delivery-specific
rendering (HTML email, Slack blocks) lands in ``src/delivery/`` in
Phase 5.
"""

from __future__ import annotations

from datetime import date


def format_briefing(raw_output: str, *, on_date: date | None = None) -> str:
    body = raw_output.strip()
    if not body:
        return ""
    if on_date and not body.lstrip().startswith(("#", "SFE")):
        return f"# SFE Briefing — {on_date.isoformat()}\n\n{body}"
    return body
