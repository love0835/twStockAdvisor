"""Profit and loss helpers."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.models import Position, Quote
from twadvisor.portfolio.cost import buy_cost, sell_proceeds


def unrealized_cost_basis(position: Position, *, discount: float | None = None) -> Decimal:
    """Return buy-side cost basis including commission."""

    kwargs = {} if discount is None else {"discount": discount}
    return buy_cost(position.avg_cost, position.qty, **kwargs)


def unrealized_pnl(position: Position, quote: Quote, *, discount: float | None = None) -> Decimal:
    """Return unrealized PnL after estimated round-trip trading costs."""

    kwargs = {} if discount is None else {"discount": discount}
    return sell_proceeds(quote.price, position.qty, **kwargs) - unrealized_cost_basis(position, discount=discount)


def unrealized_pnl_pct(position: Position, quote: Quote, *, discount: float | None = None) -> Decimal:
    """Return unrealized PnL as a fraction of cost basis including commission."""

    cost_basis = unrealized_cost_basis(position, discount=discount)
    if cost_basis == 0:
        return Decimal("0")
    return unrealized_pnl(position, quote, discount=discount) / cost_basis
