"""twstock-backed fetcher."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import twstock

from twadvisor.fetchers.base import BaseFetcher, SymbolNotFoundError
from twadvisor.models import ChipData, Quote


class TwstockFetcher(BaseFetcher):
    """Fetcher backed by the twstock package."""

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch a realtime quote from twstock."""

        realtime = twstock.realtime.get(symbol)
        if not realtime.get("success"):
            raise SymbolNotFoundError(symbol)
        data = realtime["realtime"]
        info = realtime["info"]
        latest_price = data.get("latest_trade_price") or data.get("best_bid_price", ["0"])[0]
        price = Decimal(str(latest_price))
        open_price = Decimal(str(data.get("open", latest_price)))
        high_price = Decimal(str(data.get("high", latest_price)))
        low_price = Decimal(str(data.get("low", latest_price)))
        prev_close = Decimal(str(data.get("yesterday_close", latest_price)))
        return Quote(
            symbol=symbol,
            name=info.get("name", symbol),
            price=price,
            open=open_price,
            high=high_price,
            low=low_price,
            prev_close=prev_close,
            volume=int(data.get("accumulate_trade_volume", "0") or 0) // 1000,
            bid=Decimal(str(data.get("best_bid_price", [latest_price])[0])),
            ask=Decimal(str(data.get("best_ask_price", [latest_price])[0])),
            limit_up=price,
            limit_down=price,
            timestamp=datetime.now(),
            is_suspended=False,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch multiple quotes sequentially."""

        return {symbol: await self.get_quote(symbol) for symbol in symbols}

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch historical data from twstock price history."""

        stock = twstock.Stock(symbol)
        history = []
        cursor_year = start.year
        cursor_month = start.month
        while (cursor_year, cursor_month) <= (end.year, end.month):
            history.extend(stock.fetch_from(cursor_year, cursor_month))
            if cursor_month == 12:
                cursor_year += 1
                cursor_month = 1
            else:
                cursor_month += 1
        if not history:
            raise SymbolNotFoundError(symbol)
        rows = [
            {
                "date": row.date.date() if isinstance(row.date, datetime) else row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.capacity,
            }
            for row in history
            if start <= (row.date.date() if isinstance(row.date, datetime) else row.date) <= end
        ]
        if not rows:
            raise SymbolNotFoundError(symbol)
        frame = pd.DataFrame(rows)
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date").sort_index()

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        """Return a zero-filled chip snapshot when twstock lacks chip data."""

        return ChipData(
            symbol=symbol,
            foreign_net=0,
            trust_net=0,
            dealer_net=0,
            margin_balance=0,
            short_balance=0,
            date=dt,
        )
