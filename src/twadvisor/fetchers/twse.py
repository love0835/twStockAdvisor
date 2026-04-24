"""Public TWSE CSV fetcher."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

import requests

from twadvisor.fetchers.base import FetcherError
from twadvisor.fetchers.cache import TTLCache

DAY_TRADE_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/twtb4u?response=csv"
ATTENTION_URL = "https://www.twse.com.tw/rwd/zh/announcement/notice?response=csv"
DISPOSITION_URL = "https://www.twse.com.tw/rwd/zh/announcement/punish?response=csv"
SYMBOL_RE = re.compile(r"\b\d{4,6}\b")


class TwseFetcher:
    """Fetch public CSV datasets from TWSE without an API token."""

    def __init__(self, timeout: float = 10.0, cache: TTLCache[set[str]] | None = None) -> None:
        self.timeout = timeout
        self.cache = cache or TTLCache()

    async def get_day_trade_eligible(self, dt: date | None = None) -> set[str]:
        """Return stock IDs eligible for day trading on the given date."""

        return self._get_symbols("daytrade", DAY_TRADE_URL, dt)

    async def get_attention_stocks(self, dt: date | None = None) -> set[str]:
        """Return stock IDs currently on the TWSE attention list."""

        return self._get_symbols("attention", ATTENTION_URL, dt)

    async def get_disposition_stocks(self, dt: date | None = None) -> set[str]:
        """Return stock IDs currently on the TWSE disposition list."""

        return self._get_symbols("disposition", DISPOSITION_URL, dt)

    def _get_symbols(self, dataset: str, url: str, dt: date | None) -> set[str]:
        target_date = dt or date.today()
        cache_key = f"twse:{dataset}:{target_date.isoformat()}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        response = requests.get(url, timeout=self.timeout)
        if response.status_code >= 400:
            raise FetcherError(f"TWSE request failed: {response.status_code}")
        symbols = parse_twse_symbols(response.content)
        self.cache.set(cache_key, symbols, ttl_seconds=24 * 60 * 60, now=datetime.utcnow())
        return symbols


def parse_twse_symbols(content: bytes) -> set[str]:
    """Parse stock symbols from TWSE CSV content with tolerant encoding handling."""

    text = _decode_csv(content)
    symbols: set[str] = set()
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        for cell in row:
            match = SYMBOL_RE.search(cell.strip())
            if match:
                symbols.add(match.group(0))
                break
    return symbols


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "big5", "cp950"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")
