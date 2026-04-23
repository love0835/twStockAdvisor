"""Tests for portfolio manager and pnl helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from twadvisor.models import Portfolio, Position, Quote
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.portfolio.pnl import unrealized_pnl, unrealized_pnl_pct


def test_import_csv_persists_positions(tmp_path: Path) -> None:
    """Importing a CSV should persist a portfolio snapshot."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    portfolio = manager.import_csv("E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv", cash=Decimal("200000"))

    assert portfolio.cash == Decimal("200000")
    assert len(portfolio.positions) == 2
    assert manager.load().positions[0].symbol == "2330"


def test_load_without_storage_returns_empty_portfolio(tmp_path: Path) -> None:
    """Missing storage should yield an empty portfolio."""

    manager = PortfolioManager(storage_path=tmp_path / "missing.json")
    portfolio = manager.load()
    assert portfolio.cash == Decimal("0")
    assert portfolio.positions == []


def test_build_rows_includes_unrealized_pnl(tmp_path: Path) -> None:
    """Portfolio rows should include current price and pnl columns."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    manager.save(
        Portfolio(
            cash=Decimal("100000"),
            positions=[
                Position(
                    symbol="2330",
                    qty=1000,
                    avg_cost=Decimal("580"),
                    opened_at=date(2025, 1, 2),
                )
            ],
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
        )
    )
    quote = Quote(
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

    rows = manager.build_rows({"2330": quote})

    assert rows[0]["current_price"] == "600"
    assert rows[0]["unrealized_pnl"] == "20000.00"


def test_set_cash_and_missing_quote_row(tmp_path: Path) -> None:
    """Cash updates should persist and missing quotes should render placeholders."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    manager.import_csv("E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv", cash=Decimal("100000"))
    updated = manager.set_cash(Decimal("300000"))
    rows = manager.build_rows({})

    assert updated.cash == Decimal("300000")
    assert rows[0]["current_price"] == "-"
    assert rows[0]["unrealized_pnl"] == "-"


def test_unrealized_pnl_helpers() -> None:
    """PnL helpers should compute absolute and relative returns."""

    position = Position(symbol="2330", qty=1000, avg_cost=Decimal("580"), opened_at=date(2025, 1, 2))
    quote = Quote(
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

    assert unrealized_pnl(position, quote) == Decimal("20000")
    assert unrealized_pnl_pct(position, quote) == Decimal("20000") / Decimal("580000")


def test_unrealized_pnl_pct_zero_cost() -> None:
    """Zero cost basis should not crash pct computation."""

    position = Position(symbol="2330", qty=0, avg_cost=Decimal("0"), opened_at=date(2025, 1, 2))
    quote = Quote(
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
    assert unrealized_pnl_pct(position, quote) == Decimal("0")
