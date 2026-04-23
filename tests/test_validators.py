"""Tests for risk validators and position sizing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from twadvisor.models import Action, OrderType, Portfolio, Position, Quote, Recommendation, Strategy
from twadvisor.risk.guardrails import position_pct
from twadvisor.risk.position_sizer import fixed_fraction_size
from twadvisor.risk.validators import ValidationError, validate_recommendation


def _portfolio(cash: str = "200000", qty: int = 1000) -> Portfolio:
    return Portfolio(
        cash=Decimal(cash),
        positions=[
            Position(
                symbol="2330",
                qty=qty,
                avg_cost=Decimal("580"),
                opened_at=date(2025, 1, 2),
            )
        ],
        updated_at=datetime(2026, 4, 24, 10, 0, 0),
    )


def _quote() -> Quote:
    return Quote(
        symbol="2330",
        name="TSMC",
        price=Decimal("600"),
        open=Decimal("590"),
        high=Decimal("605"),
        low=Decimal("588"),
        prev_close=Decimal("595"),
        volume=1000,
        bid=Decimal("599"),
        ask=Decimal("600"),
        limit_up=Decimal("654"),
        limit_down=Decimal("536"),
        timestamp=datetime(2026, 4, 24, 10, 0, 0),
    )


def _recommendation(action: Action, qty: int, price: str = "600") -> Recommendation:
    return Recommendation(
        symbol="2330",
        action=action,
        qty=qty,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        stop_loss=Decimal("570") if action == Action.BUY else None,
        take_profit=Decimal("660") if action == Action.BUY else None,
        reason="test",
        confidence=0.7,
        strategy=Strategy.SWING,
        generated_at=datetime(2026, 4, 24, 10, 0, 0),
    )


def test_reject_price_above_limit_up() -> None:
    """Prices above limit-up should fail validation."""

    with pytest.raises(ValidationError):
        validate_recommendation(
            _recommendation(Action.BUY, 1000, price="700"),
            _quote(),
            _portfolio(),
            max_position_pct=0.2,
        )


def test_reject_insufficient_cash() -> None:
    """Insufficient cash should fail buy validation."""

    with pytest.raises(ValidationError):
        validate_recommendation(
            _recommendation(Action.BUY, 1000),
            _quote(),
            _portfolio(cash="1000"),
            max_position_pct=0.2,
        )


def test_reject_oversold_position() -> None:
    """Selling more than held should fail validation."""

    with pytest.raises(ValidationError):
        validate_recommendation(
            _recommendation(Action.SELL, 2000),
            _quote(),
            _portfolio(qty=1000),
            max_position_pct=0.2,
        )


def test_warn_position_pct_exceeded() -> None:
    """Large buy recommendations should emit a warning."""

    warnings = validate_recommendation(
        _recommendation(Action.BUY, 1000),
        _quote(),
        _portfolio(cash="800000"),
        max_position_pct=0.2,
    )
    assert any("Position size exceeds" in warning for warning in warnings)


def test_warn_odd_lot_quantity() -> None:
    """Odd-lot quantities should emit a warning."""

    warnings = validate_recommendation(
        _recommendation(Action.BUY, 500),
        _quote(),
        _portfolio(cash="800000"),
        max_position_pct=0.5,
    )
    assert any("Odd-lot" in warning for warning in warnings)


def test_reject_symbol_mismatch() -> None:
    """Mismatched quote and recommendation symbols should fail."""

    rec = _recommendation(Action.BUY, 1000)
    quote = _quote().model_copy(update={"symbol": "2317"})
    with pytest.raises(ValidationError):
        validate_recommendation(rec, quote, _portfolio(cash="800000"), max_position_pct=0.5)


def test_reject_invalid_stop_loss_take_profit() -> None:
    """BUY recommendations must keep stop loss below price and take profit above price."""

    rec = _recommendation(Action.BUY, 1000).model_copy(
        update={"stop_loss": Decimal("610"), "take_profit": Decimal("620")}
    )
    with pytest.raises(ValidationError):
        validate_recommendation(rec, _quote(), _portfolio(cash="800000"), max_position_pct=0.5)


def test_position_pct_zero_total_equity() -> None:
    """Zero total equity should return zero exposure."""

    assert position_pct(Decimal("100"), Decimal("0")) == Decimal("0")


def test_fixed_fraction_size() -> None:
    """Position sizing should return a whole-share quantity."""

    assert fixed_fraction_size(Decimal("100000"), 0.2, Decimal("50")) == 400


def test_fixed_fraction_size_non_positive_price() -> None:
    """Non-positive prices should size to zero."""

    assert fixed_fraction_size(Decimal("100000"), 0.2, Decimal("0")) == 0
