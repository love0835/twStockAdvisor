"""Profit and loss helpers."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.models import Position, Quote


def unrealized_pnl(position: Position, quote: Quote) -> Decimal:
    """Return the unrealized PnL for a position."""

    return (quote.price - position.avg_cost) * Decimal(position.qty)


def unrealized_pnl_pct(position: Position, quote: Quote) -> Decimal:
    """Return unrealized PnL as a fraction of cost basis."""

    if position.cost_basis == 0:
        return Decimal("0")
    return unrealized_pnl(position, quote) / position.cost_basis
