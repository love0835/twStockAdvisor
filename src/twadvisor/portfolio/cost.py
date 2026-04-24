"""Trading cost helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from twadvisor.constants import (
    COMMISSION_DISCOUNT,
    COMMISSION_MIN,
    COMMISSION_RATE,
    TAX_RATE_DAYTRADE,
    TAX_RATE_STOCK,
)


def _round_money(value: Decimal) -> Decimal:
    """Round money values to the nearest cent."""

    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _commission(gross_amount: Decimal, discount: float = COMMISSION_DISCOUNT) -> Decimal:
    """Return the commission charged for a trade."""

    if gross_amount <= 0:
        return Decimal("0.00")
    commission = gross_amount * Decimal(str(COMMISSION_RATE)) * Decimal(str(discount))
    return max(Decimal(str(COMMISSION_MIN)), _round_money(commission))


def buy_cost(price: Decimal, qty: int, *, discount: float = COMMISSION_DISCOUNT) -> Decimal:
    """Return total buy-side cost including commission."""

    gross_amount = price * Decimal(qty)
    return _round_money(gross_amount + _commission(gross_amount, discount))


def sell_proceeds(
    price: Decimal,
    qty: int,
    *,
    is_daytrade: bool = False,
    discount: float = COMMISSION_DISCOUNT,
) -> Decimal:
    """Return net sell proceeds after commission and tax."""

    gross_amount = price * Decimal(qty)
    commission = _commission(gross_amount, discount)
    tax_rate = Decimal(str(TAX_RATE_DAYTRADE if is_daytrade else TAX_RATE_STOCK))
    tax = _round_money(gross_amount * tax_rate)
    return _round_money(gross_amount - commission - tax)


def breakeven_price(buy_price: Decimal, *, discount: float = COMMISSION_DISCOUNT) -> Decimal:
    """Return the breakeven sell price for one share after round-trip costs."""

    quantity = 1000
    total_buy_cost = buy_cost(buy_price, quantity, discount=discount)
    tax_rate = Decimal(str(TAX_RATE_STOCK))
    denom = Decimal(quantity) * (Decimal("1") - tax_rate)
    return _round_money((total_buy_cost + _commission(buy_price * Decimal(quantity), discount)) / denom)
