"""Tests for backtest and paper trading helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from twadvisor.backtest.engine import BacktestEngine
from twadvisor.backtest.paper_trader import LOT_SIZE, PaperTrader
from twadvisor.models import Strategy
from twadvisor.performance.metrics import profit_factor


def test_paper_trader_round_trip_realizes_cash() -> None:
    """PaperTrader should buy, sell, and track realized pnl."""

    trader = PaperTrader(symbol="2330", initial_cash=Decimal("1000000"))
    buy_fill = trader.buy_max(date(2026, 1, 2), Decimal("100"))

    assert buy_fill is not None
    assert trader.position_qty >= LOT_SIZE

    sell_fill = trader.sell_all(date(2026, 1, 20), Decimal("120"))

    assert sell_fill is not None
    assert trader.position_qty == 0
    assert sell_fill.realized_pnl > 0
    assert trader.cash > Decimal("1000000")


@pytest.mark.asyncio
async def test_backtest_engine_reports_metrics() -> None:
    """Backtest engine should produce a populated report from historical bars."""

    index = pd.date_range("2025-01-01", periods=120, freq="D")
    close_values = [Decimal("100") + Decimal(str(step)) for step in range(120)]
    frame = pd.DataFrame(
        {
            "open": [float(value) for value in close_values],
            "high": [float(value + Decimal("2")) for value in close_values],
            "low": [float(value - Decimal("2")) for value in close_values],
            "close": [float(value) for value in close_values],
            "volume": [1_000_000 + step * 1000 for step in range(120)],
        },
        index=index,
    )

    class StubFetcher:
        async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
            return frame

    engine = BacktestEngine(initial_cash=Decimal("1000000"))
    report = await engine.run(
        StubFetcher(),
        Strategy.SWING,
        ["2330"],
        date(2025, 1, 1),
        date(2025, 4, 30),
    )

    assert report.symbols == ["2330"]
    assert report.trade_count >= 1
    assert report.final_equity > Decimal("0")
    assert len(report.equity_curve) > 10
    assert report.benchmark_return != Decimal("0")


@pytest.mark.asyncio
async def test_backtest_engine_tolerates_duplicate_dates() -> None:
    """Backtest engine should deduplicate repeated trading dates from fetchers."""

    index = pd.to_datetime(["2025-01-01", "2025-01-01", *pd.date_range("2025-01-02", periods=80, freq="D")])
    frame = pd.DataFrame(
        {
            "open": range(100, 182),
            "high": range(101, 183),
            "low": range(99, 181),
            "close": range(100, 182),
            "volume": range(1000, 1082),
        },
        index=index,
    )

    class StubFetcher:
        async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
            return frame

    engine = BacktestEngine(initial_cash=Decimal("1000000"))
    report = await engine.run(
        StubFetcher(),
        Strategy.SWING,
        ["2330"],
        date(2025, 1, 1),
        date(2025, 3, 31),
    )

    assert report.final_equity > Decimal("0")


def test_profit_factor_handles_mixed_trades() -> None:
    """Profit factor should divide gross winners by gross losers."""

    result = profit_factor([Decimal("100"), Decimal("-40"), Decimal("60"), Decimal("-20")])
    assert result == Decimal("160") / Decimal("60")
