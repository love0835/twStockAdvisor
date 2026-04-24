"""Price limit helpers for Taiwan stock fetchers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def limit_up_from_prev_close(prev_close: Decimal) -> Decimal:
    """Return an approximate Taiwan stock limit-up price from previous close."""

    return (prev_close * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def limit_down_from_prev_close(prev_close: Decimal) -> Decimal:
    """Return an approximate Taiwan stock limit-down price from previous close."""

    return (prev_close * Decimal("0.90")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
