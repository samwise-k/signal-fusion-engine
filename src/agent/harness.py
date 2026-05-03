"""Agentic portfolio harness — tool-use loop via the Anthropic SDK.

Feeds engine outputs to Claude, lets it call portfolio tools, and logs
the full decision trace.
"""

from __future__ import annotations

import json
import os
from datetime import date as Date
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.agent.tools import TOOL_SCHEMAS, ToolContext, execute_tool
from src.storage.models import Portfolio
from src.storage.portfolio_repo import (
    get_or_create_portfolio,
    log_agent_session,
    portfolio_snapshot,
)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_TURNS = 20
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "portfolio_agent.txt"


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text()


def _fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices for all tickers via yfinance."""
    try:
        import yfinance as yf

        prices: dict[str, float] = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                if price is not None:
                    prices[ticker] = float(price)
            except Exception as exc:
                logger.warning(f"price fetch failed for {ticker}: {exc}")
        return prices
    except ImportError:
        logger.warning("yfinance not available — using entry prices as fallback")
        return {}


def run_agent(
    session: Session,
    on_date: Date,
    *,
    model: str = MODEL,
    portfolio_name: str = "default",
    starting_equity: float = 100_000.0,
) -> dict[str, Any]:
    """Run one agent session: read signals, make decisions, log everything."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK not installed — run `uv sync --group llm`"
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

    from src.meta.payload_builder import build_payload

    portfolio = get_or_create_portfolio(
        session, name=portfolio_name, starting_equity=starting_equity,
        inception_date=on_date,
    )

    signals_payload = build_payload(session, on_date)
    tickers = [t["ticker"] for t in signals_payload.get("tickers", [])]

    logger.info(
        "agent: fetching prices for {n} tickers",
        n=len(tickers),
    )
    current_prices = _fetch_current_prices(tickers)

    snapshot_before = portfolio_snapshot(session, portfolio, current_prices)

    ctx = ToolContext(
        session=session,
        portfolio=portfolio,
        signals_payload=signals_payload,
        current_prices=current_prices,
        trade_date=on_date,
    )

    system_prompt = _load_system_prompt()
    user_message = (
        f"Today is {on_date.isoformat()}. "
        f"Review your portfolio and the latest signals, then make your allocation decisions for today."
    )

    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]

    reasoning_trace: list[dict[str, Any]] = []
    decisions_made = 0
    trade_tools = {"open_position", "close_position", "resize_position"}

    logger.info(
        "agent: starting tool-use loop (model={m}, portfolio={p})",
        m=model,
        p=portfolio_name,
    )

    for turn in range(MAX_TURNS):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text_parts = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            if text_parts:
                reasoning_trace.append({
                    "turn": turn,
                    "type": "final_message",
                    "content": "\n".join(text_parts),
                })
            logger.info("agent: completed after {n} turns", n=turn + 1)
            break

        tool_calls = [
            block for block in response.content
            if getattr(block, "type", None) == "tool_use"
        ]

        if not tool_calls:
            text_parts = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            if text_parts:
                reasoning_trace.append({
                    "turn": turn,
                    "type": "message",
                    "content": "\n".join(text_parts),
                })
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            tool_name = tc.name
            tool_input = tc.input

            logger.info(
                "agent: calling {tool} with {inp}",
                tool=tool_name,
                inp=json.dumps(tool_input, default=str)[:200],
            )

            result_str = execute_tool(ctx, tool_name, tool_input)

            reasoning_trace.append({
                "turn": turn,
                "type": "tool_call",
                "tool": tool_name,
                "input": tool_input,
                "result": json.loads(result_str),
            })

            if tool_name in trade_tools:
                result_data = json.loads(result_str)
                if "error" not in result_data:
                    decisions_made += 1

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})
    else:
        logger.warning("agent: hit max turns ({n})", n=MAX_TURNS)

    snapshot_after = portfolio_snapshot(session, portfolio, current_prices)

    log_agent_session(
        session,
        portfolio_id=portfolio.id,
        run_date=on_date,
        decisions_made=decisions_made,
        reasoning_trace=reasoning_trace,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        model=model,
    )

    logger.info(
        "agent: {d} decisions made, equity {before} → {after}",
        d=decisions_made,
        before=f"${snapshot_before['equity']:,.2f}",
        after=f"${snapshot_after['equity']:,.2f}",
    )

    return {
        "run_date": on_date.isoformat(),
        "decisions_made": decisions_made,
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
        "reasoning_trace": reasoning_trace,
        "model": model,
    }
