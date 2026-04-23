"""Tests for portfolio cost helpers."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.portfolio.cost import breakeven_price, buy_cost, sell_proceeds


def test_buy_cost_includes_commission() -> None:
    """Buy cost should include broker commission."""

    result = buy_cost(Decimal("500"), 1000, discount=0.28)
    expected = Decimal("500000") + max(Decimal("20"), Decimal("500000") * Decimal("0.001425") * Decimal("0.28"))
    assert result == expected.quantize(Decimal("0.01"))


def test_daytrade_tax_rate() -> None:
    """Day-trade sells should use the reduced tax rate."""

    result = sell_proceeds(Decimal("500"), 1000, is_daytrade=True, discount=0.28)
    assert result == Decimal("499050.50")


def test_breakeven_price_is_above_buy_price() -> None:
    """Breakeven should be higher than the original buy price."""

    assert breakeven_price(Decimal("500")) > Decimal("500")
