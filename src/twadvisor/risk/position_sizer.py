"""Position sizing helpers."""

from __future__ import annotations

from decimal import Decimal


def fixed_fraction_size(total_equity: Decimal, max_position_pct: float, price: Decimal) -> int:
    """Return the maximum purchasable whole-share quantity for a fixed fraction."""

    budget = total_equity * Decimal(str(max_position_pct))
    if price <= 0:
        return 0
    return int(budget // price)
