"""Abstract base class for market data fetchers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

from twadvisor.models import ChipData, Quote


class SymbolNotFoundError(ValueError):
    """Raised when a symbol cannot be resolved by a fetcher."""


class FetcherError(RuntimeError):
    """Raised when a fetcher cannot complete a request."""


class BaseFetcher(ABC):
    """Common interface for all data providers."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Return a single quote snapshot."""

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Return quote snapshots for multiple symbols."""

    @abstractmethod
    async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return an OHLCV dataframe indexed by trading date."""

    @abstractmethod
    async def get_chip(self, symbol: str, dt: date) -> ChipData:
        """Return chip data for a symbol on the given date."""
