"""Tests for screener pipeline orchestration."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from twadvisor.fetchers.base import FetcherError
from twadvisor.models import ChipData, Quote
from twadvisor.screener.pipeline import ScreenerPipeline
from twadvisor.settings import ScreenerSettings


class FakeFetcher:
    """Fetcher with synchronous market helpers and async per-symbol helpers."""

    def get_market_prices(self, dt: date) -> list[dict[str, object]]:
        return [
            {
                "stock_id": "2330",
                "close": 100,
                "max": 104,
                "min": 100,
                "Trading_Volume": 5_000_000,
                "Trading_money": 500_000_000,
            },
            {
                "stock_id": "0050",
                "close": 180,
                "max": 181,
                "min": 179,
                "Trading_Volume": 6_000_000,
                "Trading_money": 1_080_000_000,
            },
        ]

    def get_stock_info(self) -> dict[str, dict[str, object]]:
        return {
            "2330": {"stock_id": "2330", "stock_name": "台積電", "type": "twse"},
            "0050": {"stock_id": "0050", "stock_name": "元大台灣50", "type": "etf"},
        }

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            name=symbol,
            price=Decimal("100"),
            open=Decimal("99"),
            high=Decimal("104"),
            low=Decimal("100"),
            prev_close=Decimal("99"),
            volume=5000,
            bid=Decimal("100"),
            ask=Decimal("100.5"),
            limit_up=Decimal("110"),
            limit_down=Decimal("90"),
            timestamp=datetime(2026, 4, 24, 10, 0, 0),
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:  # pragma: no cover
        raise NotImplementedError

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        dates = pd.date_range("2026-03-20", periods=25)
        return pd.DataFrame(
            {"open": [90] * 25, "high": [105] * 25, "low": [89] * 25, "close": [100] * 25, "volume": [5_000_000] * 25},
            index=dates,
        )

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        return ChipData(symbol=symbol, foreign_net=500, trust_net=300, dealer_net=0, margin_balance=0, short_balance=0, date=dt)


class RestrictedFinMindLikeFetcher(FakeFetcher):
    """Fetcher that rejects full-market TaiwanStockPrice requests."""

    def get_market_prices(self, dt: date) -> list[dict[str, object]]:
        raise AttributeError("use _request")

    def _request(self, **params: str) -> dict:
        if params["dataset"] == "TaiwanStockPrice":
            raise FetcherError("FinMind request failed: 400")
        if params["dataset"] == "TaiwanStockInfo":
            return {"data": list(self.get_stock_info().values())}
        return {"data": []}


class EmptyMarketFetcher(FakeFetcher):
    """Fetcher that returns no full-market rows on non-trading days."""

    def get_market_prices(self, dt: date) -> list[dict[str, object]]:
        return []


class RangeChipFetcher(FakeFetcher):
    """Fetcher with bulk institutional chip data support."""

    chip_calls = 0

    def _request(self, **params: str) -> dict:
        if params["dataset"] != "TaiwanStockInstitutionalInvestorsBuySell":
            return {"data": []}
        start = date.fromisoformat(str(params["start_date"]))
        end = date.fromisoformat(str(params["end_date"]))
        dates = pd.date_range(start, end)
        return {
            "data": [
                {"date": day.date().isoformat(), "name": "Foreign_Investor", "buy": 2000, "sell": 1000}
                for day in dates
            ]
            + [{"date": end.isoformat(), "name": "Investment_Trust", "buy": 1500, "sell": 500}]
        }

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        self.__class__.chip_calls += 1
        return await super().get_chip(symbol, dt)

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        dates = pd.date_range("2026-03-20", periods=25)
        return pd.DataFrame(
            {"open": [89] * 25, "high": [95] * 25, "low": [88] * 25, "close": [90] * 25, "volume": [5_000_000] * 25},
            index=dates,
        )


class FakeTwse:
    """TWSE list provider."""

    async def get_attention_stocks(self, dt: date) -> set[str]:
        return set()

    async def get_disposition_stocks(self, dt: date) -> set[str]:
        return set()

    async def get_day_trade_eligible(self, dt: date) -> set[str]:
        return {"2330", "0050"}


class EmptyTwse(FakeTwse):
    """TWSE provider with no day-trade eligible symbols."""

    async def get_day_trade_eligible(self, dt: date) -> set[str]:
        return set()


@pytest.mark.asyncio
async def test_pipeline_daytrade_excludes_etf_by_default() -> None:
    """Daytrade pipeline should remove ETF-like candidates when requested."""

    pipeline = ScreenerPipeline(FakeFetcher(), FakeTwse(), None, ScreenerSettings())

    result = await pipeline.run_daytrade(top_n=5, exclude_etf=True)

    assert result.candidates_total == 1
    assert [item.symbol for item in result.recommendations] == ["2330"]


@pytest.mark.asyncio
async def test_pipeline_empty_market_returns_warning() -> None:
    """Empty candidate markets should be a 200-style result, not an exception."""

    pipeline = ScreenerPipeline(FakeFetcher(), EmptyTwse(), None, ScreenerSettings())

    result = await pipeline.run_daytrade(top_n=5, exclude_etf=True)

    assert result.recommendations == []
    assert result.warnings == ["無候選股"]


@pytest.mark.asyncio
async def test_pipeline_daytrade_relaxes_rules_when_strict_rules_are_empty() -> None:
    """Daytrade scanner should avoid a dead-end when strict thresholds are too narrow."""

    settings = ScreenerSettings(daytrade_min_amplitude_pct=9.0)
    pipeline = ScreenerPipeline(FakeFetcher(), FakeTwse(), None, settings)

    result = await pipeline.run_daytrade(top_n=5, exclude_etf=True)

    assert result.recommendations
    assert "已暫時放寬" in result.warnings[0]


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_full_market_finmind_is_restricted() -> None:
    """Registered FinMind levels can reject full-market price requests."""

    pipeline = ScreenerPipeline(RestrictedFinMindLikeFetcher(), FakeTwse(), None, ScreenerSettings())

    result = await pipeline.run_daytrade(top_n=1, exclude_etf=True)

    assert result.candidates_total == 1
    assert result.recommendations[0].symbol == "2330"


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_full_market_rows_are_empty() -> None:
    """Non-trading days can return an empty full-market response."""

    pipeline = ScreenerPipeline(EmptyMarketFetcher(), FakeTwse(), None, ScreenerSettings())

    result = await pipeline.run_daytrade(top_n=1, exclude_etf=True)

    assert result.candidates_total == 1
    assert result.recommendations[0].symbol == "2330"


@pytest.mark.asyncio
async def test_pipeline_uses_bulk_chip_data_for_swing_enrichment() -> None:
    """Swing enrichment should avoid repeated per-day chip calls when range data exists."""

    RangeChipFetcher.chip_calls = 0
    pipeline = ScreenerPipeline(RangeChipFetcher(), FakeTwse(), None, ScreenerSettings())

    result = await pipeline.run_swing(top_n=1, foreign_consecutive_days=3)

    assert result.recommendations
    assert result.recommendations[0].symbol == "2330"
    assert RangeChipFetcher.chip_calls == 0
