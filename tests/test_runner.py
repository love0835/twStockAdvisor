"""Tests for the scheduler runner."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from twadvisor.models import AnalysisResponse, Portfolio, Position, Quote, Recommendation, Strategy, ChipData
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.scheduler.runner import AdvisorRunner
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository


class StubNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Recommendation], str]] = []

    async def notify(self, recs: list[Recommendation], market_view: str) -> None:
        self.calls.append((recs, market_view))


class StubFetcher:
    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {
            symbol: Quote(
                symbol=symbol,
                name=symbol,
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
            for symbol in symbols
        }

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": range(100, 220),
                "high": range(101, 221),
                "low": range(99, 219),
                "close": range(100, 220),
                "volume": range(1000, 1120),
            },
            index=pd.date_range("2025-01-01", periods=120, freq="D"),
        )

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        return ChipData(symbol=symbol, foreign_net=0, trust_net=0, dealer_net=0, margin_balance=0, short_balance=0, date=dt)


class StubAnalyzer:
    async def analyze(self, req) -> AnalysisResponse:
        return AnalysisResponse(
            recommendations=[
                Recommendation(
                    symbol="2330",
                    action="hold",
                    qty=0,
                    order_type="limit",
                    reason="持有觀察",
                    confidence=0.7,
                    strategy=Strategy.SWING,
                    generated_at=datetime(2026, 4, 24, 10, 0, 0),
                )
            ],
            market_view="偏多震盪",
        )


@pytest.mark.asyncio
async def test_runner_tick_notifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Runner tick should notify when valid recommendations exist."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    manager.save(
        Portfolio(
            cash=Decimal("200000"),
            positions=[Position(symbol="2330", qty=1000, avg_cost=Decimal("580"), opened_at=date(2025, 1, 2))],
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
        )
    )
    settings = load_settings()
    notifier = StubNotifier()
    runner = AdvisorRunner(settings, StubFetcher(), StubAnalyzer(), manager, notifier, AdvisorRepository(str(tmp_path / "advisor.db")))
    monkeypatch.setattr("twadvisor.scheduler.runner.MarketCalendar.current_session", lambda self, now: "regular")
    await runner.tick(Strategy.SWING, ["2330"])
    assert notifier.calls


@pytest.mark.asyncio
async def test_runner_tick_skips_closed_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Closed sessions should skip notification work."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    settings = load_settings()
    notifier = StubNotifier()
    runner = AdvisorRunner(settings, StubFetcher(), StubAnalyzer(), manager, notifier, AdvisorRepository(str(tmp_path / "advisor.db")))
    monkeypatch.setattr("twadvisor.scheduler.runner.MarketCalendar.current_session", lambda self, now: "closed")
    await runner.tick(Strategy.SWING, ["2330"])
    assert notifier.calls == []


@pytest.mark.asyncio
async def test_runner_start_exits_after_max_ticks_when_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bounded runs should exit even when every session is closed."""

    manager = PortfolioManager(storage_path=tmp_path / "portfolio.json")
    settings = load_settings()
    notifier = StubNotifier()
    runner = AdvisorRunner(settings, StubFetcher(), StubAnalyzer(), manager, notifier, AdvisorRepository(str(tmp_path / "advisor.db")))
    monkeypatch.setattr("twadvisor.scheduler.runner.MarketCalendar.current_session", lambda self, now: "closed")
    await runner.start(Strategy.SWING, ["2330"], interval_override=10, max_ticks=1)
    assert notifier.calls == []
