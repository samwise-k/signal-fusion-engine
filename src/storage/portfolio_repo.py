"""Repository helpers for the simulated portfolio."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import AgentSession, Portfolio, Position, Trade


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def get_or_create_portfolio(
    session: Session,
    name: str = "default",
    starting_equity: float = 100_000.0,
    inception_date: Date | None = None,
) -> Portfolio:
    row = session.execute(
        select(Portfolio).where(Portfolio.name == name, Portfolio.active.is_(True))
    ).scalar_one_or_none()

    if row is not None:
        return row

    row = Portfolio(
        name=name,
        starting_equity=starting_equity,
        cash=starting_equity,
        inception_date=inception_date or Date.today(),
    )
    session.add(row)
    session.commit()
    return row


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def get_positions(session: Session, portfolio_id: int) -> list[Position]:
    return list(
        session.execute(
            select(Position).where(Position.portfolio_id == portfolio_id)
        ).scalars().all()
    )


def get_position(session: Session, portfolio_id: int, ticker: str) -> Position | None:
    return session.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.ticker == ticker.upper(),
        )
    ).scalar_one_or_none()


def open_position(
    session: Session,
    portfolio: Portfolio,
    ticker: str,
    direction: str,
    shares: float,
    price: float,
    trade_date: Date,
    reasoning: str = "",
) -> Position:
    ticker = ticker.upper()
    cost = shares * price
    if direction == "long":
        portfolio.cash -= cost
    else:
        portfolio.cash += cost

    pos = Position(
        portfolio_id=portfolio.id,
        ticker=ticker,
        direction=direction,
        shares=shares,
        entry_price=price,
        entry_date=trade_date,
        current_price=price,
        reasoning=reasoning,
    )
    session.add(pos)

    trade = Trade(
        portfolio_id=portfolio.id,
        ticker=ticker,
        action="open",
        direction=direction,
        shares=shares,
        price=price,
        trade_date=trade_date,
        reasoning=reasoning,
    )
    session.add(trade)
    session.commit()
    return pos


def close_position(
    session: Session,
    portfolio: Portfolio,
    pos: Position,
    price: float,
    trade_date: Date,
    reasoning: str = "",
) -> Trade:
    proceeds = pos.shares * price
    if pos.direction == "long":
        portfolio.cash += proceeds
    else:
        portfolio.cash -= proceeds

    trade = Trade(
        portfolio_id=portfolio.id,
        ticker=pos.ticker,
        action="close",
        direction=pos.direction,
        shares=pos.shares,
        price=price,
        trade_date=trade_date,
        reasoning=reasoning,
    )
    session.add(trade)
    session.delete(pos)
    session.commit()
    return trade


def resize_position(
    session: Session,
    portfolio: Portfolio,
    pos: Position,
    new_shares: float,
    price: float,
    trade_date: Date,
    reasoning: str = "",
) -> Trade:
    delta = new_shares - pos.shares
    cost = abs(delta) * price
    if pos.direction == "long":
        if delta > 0:
            portfolio.cash -= cost
        else:
            portfolio.cash += cost
    else:
        if delta > 0:
            portfolio.cash += cost
        else:
            portfolio.cash -= cost

    pos.shares = new_shares
    pos.current_price = price

    trade = Trade(
        portfolio_id=portfolio.id,
        ticker=pos.ticker,
        action="resize",
        direction=pos.direction,
        shares=abs(delta),
        price=price,
        trade_date=trade_date,
        reasoning=reasoning,
    )
    session.add(trade)
    session.commit()
    return trade


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def get_trades(
    session: Session, portfolio_id: int, *, limit: int = 50
) -> list[Trade]:
    return list(
        session.execute(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_id)
            .order_by(Trade.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )


# ---------------------------------------------------------------------------
# Portfolio snapshot (for agent context)
# ---------------------------------------------------------------------------


def portfolio_snapshot(
    session: Session, portfolio: Portfolio, current_prices: dict[str, float]
) -> dict[str, Any]:
    positions = get_positions(session, portfolio.id)
    pos_list = []
    total_position_value = 0.0

    for p in positions:
        cur_price = current_prices.get(p.ticker, p.current_price or p.entry_price)
        p.current_price = cur_price
        if p.direction == "long":
            market_value = p.shares * cur_price
            unrealized_pnl = (cur_price - p.entry_price) * p.shares
            total_position_value += market_value
        else:
            market_value = p.shares * cur_price
            unrealized_pnl = (p.entry_price - cur_price) * p.shares
            total_position_value -= market_value

        pos_list.append({
            "ticker": p.ticker,
            "direction": p.direction,
            "shares": p.shares,
            "entry_price": round(p.entry_price, 2),
            "current_price": round(cur_price, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "entry_date": p.entry_date.isoformat(),
            "reasoning": p.reasoning or "",
        })

    session.commit()

    equity = portfolio.cash + total_position_value
    total_return_pct = ((equity - portfolio.starting_equity) / portfolio.starting_equity) * 100

    return {
        "portfolio_id": portfolio.id,
        "name": portfolio.name,
        "inception_date": portfolio.inception_date.isoformat(),
        "starting_equity": portfolio.starting_equity,
        "cash": round(portfolio.cash, 2),
        "equity": round(equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "positions": pos_list,
        "position_count": len(pos_list),
    }


# ---------------------------------------------------------------------------
# Agent sessions
# ---------------------------------------------------------------------------


def log_agent_session(
    session: Session,
    portfolio_id: int,
    run_date: Date,
    decisions_made: int,
    reasoning_trace: list[dict[str, Any]],
    snapshot_before: dict[str, Any],
    snapshot_after: dict[str, Any],
    model: str,
) -> AgentSession:
    row = AgentSession(
        portfolio_id=portfolio_id,
        run_date=run_date,
        decisions_made=decisions_made,
        reasoning_trace=reasoning_trace,
        portfolio_snapshot_before=snapshot_before,
        portfolio_snapshot_after=snapshot_after,
        model=model,
    )
    session.add(row)
    session.commit()
    return row
