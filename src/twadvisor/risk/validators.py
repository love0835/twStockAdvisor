"""Recommendation validation helpers."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.models import Action, Portfolio, Quote, Recommendation
from twadvisor.portfolio.cost import buy_cost
from twadvisor.risk.guardrails import position_pct


class ValidationError(Exception):
    """Raised when a recommendation violates hard rules."""


def _position_qty(portfolio: Portfolio, symbol: str) -> int:
    """Return held quantity for a symbol."""

    for position in portfolio.positions:
        if position.symbol == symbol:
            return position.qty
    return 0


def validate_recommendation(
    rec: Recommendation,
    quote: Quote,
    portfolio: Portfolio,
    *,
    max_position_pct: float,
) -> list[str]:
    """Validate a recommendation and return non-fatal warnings."""

    warnings: list[str] = []

    if rec.symbol != quote.symbol:
        raise ValidationError("Recommendation symbol does not match quote")

    if rec.price is not None and not (quote.limit_down <= rec.price <= quote.limit_up):
        raise ValidationError("Recommendation price is outside the daily limit range")

    if rec.action == Action.BUY:
        target_price = rec.price or quote.price
        required_cash = buy_cost(target_price, rec.qty)
        if portfolio.cash < required_cash:
            raise ValidationError("Insufficient cash for buy recommendation")

        total_equity = portfolio.cash + portfolio.total_cost()
        current_exposure = Decimal("0")
        for position in portfolio.positions:
            if position.symbol == rec.symbol:
                current_exposure += position.cost_basis
        proposed_exposure = current_exposure + (target_price * Decimal(rec.qty))
        if position_pct(proposed_exposure, total_equity) > Decimal(str(max_position_pct)):
            warnings.append("Position size exceeds configured maximum percentage")

        if rec.stop_loss is not None and rec.take_profit is not None:
            if not (rec.stop_loss < target_price < rec.take_profit):
                raise ValidationError("BUY recommendation must satisfy stop_loss < price < take_profit")

    if rec.action == Action.SELL and _position_qty(portfolio, rec.symbol) < rec.qty:
        raise ValidationError("Insufficient holdings for sell recommendation")

    if rec.qty >= 1000 and rec.qty % 1000 != 0:
        warnings.append("Quantity is not a round lot multiple of 1000")
    if 0 < rec.qty < 1000:
        warnings.append("Odd-lot quantity detected")

    return warnings
