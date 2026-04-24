"""Yahoo Finance-backed fetcher."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf

from twadvisor.fetchers.base import BaseFetcher, SymbolNotFoundError
from twadvisor.fetchers.limits import limit_down_from_prev_close, limit_up_from_prev_close
from twadvisor.models import ChipData, Quote


class YahooFinanceFetcher(BaseFetcher):
    """Fetcher backed by Yahoo Finance."""

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch a single quote using the TSE symbol suffix."""

        ticker = yf.Ticker(f"{symbol}.TW")
        history = ticker.history(period="5d", interval="1d")
        if history.empty:
            raise SymbolNotFoundError(symbol)
        latest = history.iloc[-1]
        previous = history.iloc[-2] if len(history) > 1 else latest
        timestamp = history.index[-1].to_pydatetime()
        prev_close = Decimal(str(round(float(previous["Close"]), 4)))
        return Quote(
            symbol=symbol,
            name=symbol,
            price=Decimal(str(round(float(latest["Close"]), 4))),
            open=Decimal(str(round(float(latest["Open"]), 4))),
            high=Decimal(str(round(float(latest["High"]), 4))),
            low=Decimal(str(round(float(latest["Low"]), 4))),
            prev_close=prev_close,
            volume=int(latest["Volume"]) // 1000,
            bid=Decimal(str(round(float(latest["Close"]), 4))),
            ask=Decimal(str(round(float(latest["Close"]), 4))),
            limit_up=limit_up_from_prev_close(prev_close),
            limit_down=limit_down_from_prev_close(prev_close),
            timestamp=timestamp,
            is_suspended=False,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch multiple quotes sequentially."""

        return {symbol: await self.get_quote(symbol) for symbol in symbols}

    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch historical OHLCV data from Yahoo Finance."""

        ticker = yf.Ticker(f"{symbol}.TW")
        frame = ticker.history(start=start, end=end + timedelta(days=1), interval="1d")
        if frame.empty:
            raise SymbolNotFoundError(symbol)
        frame = frame.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        return frame[["open", "high", "low", "close", "volume"]]

    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        """Return a zero-filled chip snapshot when Yahoo lacks chip data."""

        return ChipData(
            symbol=symbol,
            foreign_net=0,
            trust_net=0,
            dealer_net=0,
            margin_balance=0,
            short_balance=0,
            date=dt,
        )
