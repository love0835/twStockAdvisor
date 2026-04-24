"""Tests for portfolio manager and pnl helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from twadvisor.models import Portfolio, Position, Quote
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.portfolio.pnl import unrealized_cost_basis, unrealized_pnl, unrealized_pnl_pct


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
    assert rows[0]["cost_basis"] == "580231.42"
    assert rows[0]["unrealized_pnl"] == "17729.18"


def test_set_cash_and_missing_quote_row(tmp_path: Path) -> None:
    """Cash updates should persist and missing quotes should render placeholders."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    manager.import_csv("E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv", cash=Decimal("100000"))
    updated = manager.set_cash(Decimal("300000"))
    rows = manager.build_rows({})

    assert updated.cash == Decimal("300000")
    assert rows[0]["current_price"] == "尚未更新"
    assert rows[0]["unrealized_pnl"] == "尚未更新"


def test_position_crud_helpers(tmp_path: Path) -> None:
    """Position CRUD helpers should persist local portfolio edits."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    manager.set_cash(Decimal("100000"))

    added = manager.add_position("2330", 1000, Decimal("580"))
    assert added.positions[0].symbol == "2330"

    updated = manager.update_position("2330", 2000, Decimal("590"))
    assert updated.positions[0].qty == 2000
    assert updated.positions[0].avg_cost == Decimal("590")

    deleted = manager.delete_position("2330")
    assert deleted.positions == []


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

    assert unrealized_cost_basis(position) == Decimal("580231.42")
    assert unrealized_pnl(position, quote) == Decimal("17729.18")
    assert unrealized_pnl_pct(position, quote).quantize(Decimal("0.0001")) == Decimal("0.0306")


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
