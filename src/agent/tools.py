"""Agent tool definitions and execution for the portfolio harness.

Each tool has a JSON schema (for the Anthropic tool_use API) and an execute
function that takes the parsed input and returns a result dict.
"""

from __future__ import annotations

import json
from datetime import date as Date
from typing import Any

from sqlalchemy.orm import Session

from src.storage.models import Portfolio
from src.storage.portfolio_repo import (
    close_position,
    get_position,
    get_positions,
    get_trades,
    open_position,
    portfolio_snapshot,
    resize_position,
)

# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool_use format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_portfolio_state",
        "description": (
            "Get the current portfolio state: cash, equity, total return, "
            "and all open positions with unrealized P&L."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_signals",
        "description": (
            "Get the latest engine outputs (sentiment, quant, enrichment) "
            "for all watchlist tickers. This is your primary source of market data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_ticker_detail",
        "description": (
            "Get a detailed view of a single ticker: all engine data, "
            "current position (if any), and recent trades."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol (e.g. NVDA)",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "open_position",
        "description": (
            "Open a new position. Specify the ticker, direction (long/short), "
            "and size as a percentage of total portfolio equity. "
            "Cannot open a position in a ticker you already hold — use resize_position instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol",
                },
                "direction": {
                    "type": "string",
                    "enum": ["long", "short"],
                    "description": "Position direction",
                },
                "allocation_pct": {
                    "type": "number",
                    "description": "Position size as percentage of total portfolio equity (e.g. 5.0 for 5%)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why you are opening this position — cite the specific signals driving this decision",
                },
            },
            "required": ["ticker", "direction", "allocation_pct", "reasoning"],
        },
    },
    {
        "name": "close_position",
        "description": (
            "Close an existing position entirely. All shares are sold at the current market price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol of the position to close",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why you are closing this position",
                },
            },
            "required": ["ticker", "reasoning"],
        },
    },
    {
        "name": "resize_position",
        "description": (
            "Resize an existing position to a new allocation percentage of total equity. "
            "Use this to increase or decrease position size."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol of the position to resize",
                },
                "new_allocation_pct": {
                    "type": "number",
                    "description": "New target size as percentage of total equity (e.g. 3.0 for 3%)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why you are resizing this position",
                },
            },
            "required": ["ticker", "new_allocation_pct", "reasoning"],
        },
    },
    {
        "name": "get_trade_history",
        "description": (
            "Get the history of your recent trades — what you bought, sold, "
            "resized, and why. Use this to review your past decisions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent trades to return (default 20)",
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution context
# ---------------------------------------------------------------------------


class ToolContext:
    """Holds the state needed to execute agent tools."""

    def __init__(
        self,
        session: Session,
        portfolio: Portfolio,
        signals_payload: dict[str, Any],
        current_prices: dict[str, float],
        trade_date: Date,
    ):
        self.session = session
        self.portfolio = portfolio
        self.signals_payload = signals_payload
        self.current_prices = current_prices
        self.trade_date = trade_date

    def _snapshot(self) -> dict[str, Any]:
        return portfolio_snapshot(
            self.session, self.portfolio, self.current_prices
        )

    def _equity(self) -> float:
        snap = self._snapshot()
        return snap["equity"]


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------


def execute_tool(ctx: ToolContext, tool_name: str, tool_input: dict[str, Any]) -> str:
    handlers = {
        "get_portfolio_state": _exec_get_portfolio_state,
        "get_signals": _exec_get_signals,
        "get_ticker_detail": _exec_get_ticker_detail,
        "open_position": _exec_open_position,
        "close_position": _exec_close_position,
        "resize_position": _exec_resize_position,
        "get_trade_history": _exec_get_trade_history,
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = handler(ctx, tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _exec_get_portfolio_state(ctx: ToolContext, _input: dict) -> dict:
    return ctx._snapshot()


def _exec_get_signals(ctx: ToolContext, _input: dict) -> dict:
    return ctx.signals_payload


def _exec_get_ticker_detail(ctx: ToolContext, inp: dict) -> dict:
    ticker = inp["ticker"].upper()
    ticker_data = None
    for t in ctx.signals_payload.get("tickers", []):
        if t["ticker"] == ticker:
            ticker_data = t
            break

    pos = get_position(ctx.session, ctx.portfolio.id, ticker)
    pos_data = None
    if pos is not None:
        cur_price = ctx.current_prices.get(ticker, pos.current_price or pos.entry_price)
        if pos.direction == "long":
            pnl = (cur_price - pos.entry_price) * pos.shares
        else:
            pnl = (pos.entry_price - cur_price) * pos.shares
        pos_data = {
            "direction": pos.direction,
            "shares": pos.shares,
            "entry_price": pos.entry_price,
            "current_price": cur_price,
            "unrealized_pnl": round(pnl, 2),
            "entry_date": pos.entry_date.isoformat(),
        }

    trades = get_trades(ctx.session, ctx.portfolio.id, limit=50)
    ticker_trades = [
        {
            "action": t.action,
            "direction": t.direction,
            "shares": t.shares,
            "price": t.price,
            "trade_date": t.trade_date.isoformat(),
            "reasoning": t.reasoning or "",
        }
        for t in trades
        if t.ticker == ticker
    ][:10]

    return {
        "ticker": ticker,
        "signals": ticker_data,
        "current_position": pos_data,
        "recent_trades": ticker_trades,
    }


def _exec_open_position(ctx: ToolContext, inp: dict) -> dict:
    ticker = inp["ticker"].upper()
    direction = inp["direction"]
    alloc_pct = inp["allocation_pct"]
    reasoning = inp["reasoning"]

    existing = get_position(ctx.session, ctx.portfolio.id, ticker)
    if existing is not None:
        return {
            "error": f"Already holding {ticker}. Use resize_position to adjust, or close_position first."
        }

    price = ctx.current_prices.get(ticker)
    if price is None:
        return {"error": f"No current price available for {ticker}"}

    equity = ctx._equity()
    target_value = equity * (alloc_pct / 100.0)
    shares = round(target_value / price, 4)

    if shares * price > ctx.portfolio.cash and direction == "long":
        return {
            "error": f"Insufficient cash. Need ${shares * price:,.2f} but only ${ctx.portfolio.cash:,.2f} available."
        }

    pos = open_position(
        ctx.session, ctx.portfolio, ticker, direction,
        shares, price, ctx.trade_date, reasoning,
    )
    return {
        "status": "opened",
        "ticker": ticker,
        "direction": direction,
        "shares": pos.shares,
        "price": price,
        "cost": round(shares * price, 2),
        "allocation_pct": alloc_pct,
    }


def _exec_close_position(ctx: ToolContext, inp: dict) -> dict:
    ticker = inp["ticker"].upper()
    reasoning = inp["reasoning"]

    pos = get_position(ctx.session, ctx.portfolio.id, ticker)
    if pos is None:
        return {"error": f"No open position in {ticker}"}

    price = ctx.current_prices.get(ticker)
    if price is None:
        price = pos.current_price or pos.entry_price

    if pos.direction == "long":
        pnl = (price - pos.entry_price) * pos.shares
    else:
        pnl = (pos.entry_price - price) * pos.shares

    close_position(ctx.session, ctx.portfolio, pos, price, ctx.trade_date, reasoning)
    return {
        "status": "closed",
        "ticker": ticker,
        "shares": pos.shares,
        "entry_price": pos.entry_price,
        "exit_price": price,
        "realized_pnl": round(pnl, 2),
    }


def _exec_resize_position(ctx: ToolContext, inp: dict) -> dict:
    ticker = inp["ticker"].upper()
    new_alloc_pct = inp["new_allocation_pct"]
    reasoning = inp["reasoning"]

    pos = get_position(ctx.session, ctx.portfolio.id, ticker)
    if pos is None:
        return {"error": f"No open position in {ticker}. Use open_position to start one."}

    price = ctx.current_prices.get(ticker)
    if price is None:
        price = pos.current_price or pos.entry_price

    equity = ctx._equity()
    target_value = equity * (new_alloc_pct / 100.0)
    new_shares = round(target_value / price, 4)

    delta = new_shares - pos.shares
    if delta > 0 and (delta * price) > ctx.portfolio.cash and pos.direction == "long":
        return {
            "error": f"Insufficient cash to increase position. Need ${delta * price:,.2f} more."
        }

    resize_position(
        ctx.session, ctx.portfolio, pos, new_shares,
        price, ctx.trade_date, reasoning,
    )
    return {
        "status": "resized",
        "ticker": ticker,
        "old_shares": pos.shares - delta,
        "new_shares": new_shares,
        "price": price,
        "new_allocation_pct": new_alloc_pct,
    }


def _exec_get_trade_history(ctx: ToolContext, inp: dict) -> dict:
    limit = inp.get("limit", 20)
    trades = get_trades(ctx.session, ctx.portfolio.id, limit=limit)
    return {
        "trades": [
            {
                "ticker": t.ticker,
                "action": t.action,
                "direction": t.direction,
                "shares": t.shares,
                "price": t.price,
                "trade_date": t.trade_date.isoformat(),
                "reasoning": t.reasoning or "",
            }
            for t in trades
        ]
    }
