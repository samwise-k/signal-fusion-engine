"""Experiment dashboard — renders scored signals to static HTML."""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from loguru import logger
from sqlalchemy.orm import Session

from src.tracking.scorer import compute_stats, score_all

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT = Path("output/dashboard.html")


def _kill_indicator(stats: dict[str, Any]) -> dict[str, str]:
    ev5 = stats["by_horizon"].get("5d", {})
    n = ev5.get("n", 0)

    if n < 20:
        return {"color": "yellow", "label": "Collecting data", "reason": f"{n} signals — need ~100 for significance"}

    ev = ev5.get("ev", 0)
    accuracy = ev5.get("accuracy")

    if n >= 100 and ev < 0:
        return {"color": "red", "label": "KILL", "reason": f"EV negative ({ev:.4f}) at {n} signals"}

    if ev < 0 and n >= 50:
        return {"color": "red", "label": "Trending bad", "reason": f"EV negative ({ev:.4f}) — watch closely"}

    if ev > 0 and accuracy and accuracy > 0.5:
        return {"color": "green", "label": "On track", "reason": f"EV positive ({ev:.4f}), accuracy {accuracy:.0%}"}

    return {"color": "yellow", "label": "Inconclusive", "reason": f"EV {ev:.4f}, {n} signals — keep collecting"}


def render(
    session: Session,
    today: Date | None = None,
    output_path: Path | None = None,
) -> Path:
    today = today or Date.today()
    output_path = output_path or DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scored = score_all(session, today)
    stats = compute_stats(scored)
    kill_indicator = _kill_indicator(stats)

    recent = sorted(scored, key=lambda s: s["as_of"], reverse=True)[:20]

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("dashboard.html")

    html = template.render(
        stats=stats,
        kill_indicator=kill_indicator,
        recent_signals=recent,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output_path.write_text(html)
    logger.info("dashboard written to {path}", path=output_path)
    return output_path
