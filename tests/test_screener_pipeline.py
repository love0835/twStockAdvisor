"""Tests for screener pipeline orchestration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

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

    async def get_quote(self, symbol: str) -> Quote:  # pragma: no cover - protocol filler
        raise NotImplementedError

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


class FakeTwse:
    """TWSE list provider."""

    async def get_attention_stocks(self, dt: date) -> set[str]:
        return set()

    async def get_disposition_stocks(self, dt: date) -> set[str]:
        return set()

    async def get_day_trade_eligible(self, dt: date) -> set[str]:
        return {"2330", "0050"}


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

    settings = ScreenerSettings(daytrade_min_turnover_million=99999)
    pipeline = ScreenerPipeline(FakeFetcher(), FakeTwse(), None, settings)

    result = await pipeline.run_daytrade(top_n=5, exclude_etf=True)

    assert result.recommendations == []
    assert result.warnings == ["無候選股"]
