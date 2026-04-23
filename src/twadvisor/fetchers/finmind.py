"""FinMind data fetcher."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import requests

from twadvisor.fetchers.base import BaseFetcher, FetcherError, SymbolNotFoundError
from twadvisor.models import ChipData, Quote

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"


class FinMindFetcher(BaseFetcher):
    """Fetcher backed by the FinMind API."""

    def __init__(self, api_token: str, timeout: float = 10.0) -> None:
        """Create a FinMind fetcher."""

        self.api_token = api_token
        self.timeout = timeout

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch a single quote from FinMind daily stock info."""

        payload = self._request(
            dataset="TaiwanStockPrice",
            data_id=symbol,
            start_date=str(date.today()),
            end_date=str(date.today()),
        )
        records = payload.get("data", [])
        if not records:
            raise SymbolNotFoundError(symbol)
        latest = records[-1]
        return Quote(
            symbol=symbol,
            name=symbol,
            price=Decimal(str(latest["close"])),
            open=Decimal(str(latest["open"])),
            high=Decimal(str(latest["max"])),
            low=Decimal(str(latest["min"])),
            prev_close=Decimal(str(latest["close"])),
            volume=int(latest["Trading_Volume"]) // 1000,
            bid=Decimal(str(latest["close"])),
            ask=Decimal(str(latest["close"])),
            limit_up=Decimal(str(latest["close"])),
            limit_down=Decimal(str(latest["close"])),
            timestamp=datetime.fromisoformat(latest["date"]),
            is_suspended=False,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch multiple quotes sequentially."""

        return {symbol: await self.get_quote(symbol) for symbol in symbols}

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch historical OHLCV data."""

        payload = self._request(
            dataset="TaiwanStockPrice",
            data_id=symbol,
            start_date=str(start),
            end_date=str(end),
        )
        records = payload.get("data", [])
        if not records:
            raise SymbolNotFoundError(symbol)
        frame = pd.DataFrame.from_records(records)
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.rename(
            columns={
                "open": "open",
                "max": "high",
                "min": "low",
                "close": "close",
                "Trading_Volume": "volume",
            }
        )
        frame = frame[["date", "open", "high", "low", "close", "volume"]]
        return frame.set_index("date").sort_index()

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        """Fetch chip data for the given symbol and date."""

        payload = self._request(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            start_date=str(dt),
            end_date=str(dt),
        )
        records = payload.get("data", [])
        if not records:
            raise SymbolNotFoundError(symbol)
        grouped: dict[str, int] = {entry["name"]: int(entry["buy_sell"]) for entry in records}
        return ChipData(
            symbol=symbol,
            foreign_net=grouped.get("Foreign_Investor", 0),
            trust_net=grouped.get("Investment_Trust", 0),
            dealer_net=grouped.get("Dealer_self", 0),
            margin_balance=0,
            short_balance=0,
            date=dt,
        )

    def _request(self, **params: str) -> dict:
        """Perform a FinMind request and return the JSON payload."""

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = requests.get(FINMIND_API, params=params, headers=headers, timeout=self.timeout)
        if response.status_code >= 400:
            raise FetcherError(f"FinMind request failed: {response.status_code}")
        payload = response.json()
        if not payload.get("status", 0):
            raise FetcherError("FinMind returned an unsuccessful response")
        return payload
