"""Tests for fetcher helpers and parsing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json

import pandas as pd
import pytest

from twadvisor.fetchers.base import FetcherError, SymbolNotFoundError
from twadvisor.fetchers.cache import TTLCache
from twadvisor.fetchers.factory import create_fetcher
from twadvisor.fetchers.finmind import FinMindFetcher
from twadvisor.fetchers.finmind_keys import FinMindKeyRotator
from twadvisor.fetchers.twstock_fetcher import TwstockFetcher
from twadvisor.fetchers.yahoo import YahooFinanceFetcher
from twadvisor.models import ChipData, Quote
from twadvisor.settings import load_settings


def test_cache_hit_and_expiry() -> None:
    """TTL cache should return fresh values and drop expired values."""

    cache: TTLCache[str] = TTLCache()
    now = datetime(2026, 4, 23, 10, 0, 0)
    cache.set("quote:2330", "value", ttl_seconds=3, now=now)

    assert cache.get("quote:2330", now=now) == "value"
    assert cache.get("quote:2330", now=now.replace(second=4)) is None


def test_create_fetcher_falls_back_to_twstock(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetcher factory should fall back when FinMind token is absent."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "\n".join(
            [
                "[fetcher]",
                'primary = "finmind"',
                'fallback = ["twstock", "yahoo"]',
                f'finmind_keys_path = "{(tmp_path / "missing_finmind_keys.json").as_posix()}"',
                f'finmind_key_state_path = "{(tmp_path / "finmind_key_state.json").as_posix()}"',
                "[security]",
                'keyring_service = "twadvisor"',
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr("twadvisor.fetchers.factory.KeyStore.get_secret", lambda self, key: None)

    fetcher = create_fetcher(settings)
    assert isinstance(fetcher, TwstockFetcher)


def test_create_fetcher_prefers_finmind_when_token_exists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetcher factory should use FinMind when a token exists."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "\n".join(
            [
                "[fetcher]",
                'primary = "finmind"',
                'fallback = ["twstock"]',
                f'finmind_keys_path = "{(tmp_path / "missing_finmind_keys.json").as_posix()}"',
                f'finmind_key_state_path = "{(tmp_path / "finmind_key_state.json").as_posix()}"',
                "[security]",
                'keyring_service = "twadvisor"',
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr("twadvisor.fetchers.factory.KeyStore.get_secret", lambda self, key: "token")

    fetcher = create_fetcher(settings)
    assert isinstance(fetcher, FinMindFetcher)


def test_create_fetcher_prefers_local_finmind_key_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetcher factory should use the local FinMind key file before keyring."""

    key_config = tmp_path / "finmind_keys.local.json"
    key_state = tmp_path / "finmind_key_state.json"
    key_config.write_text(
        json.dumps({"keys": [{"name": "finmind_1", "token": "token-one", "enabled": True}]}),
        encoding="utf-8",
    )
    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "\n".join(
            [
                "[fetcher]",
                'primary = "finmind"',
                'fallback = ["twstock"]',
                f'finmind_keys_path = "{key_config.as_posix()}"',
                f'finmind_key_state_path = "{key_state.as_posix()}"',
                "[security]",
                'keyring_service = "twadvisor"',
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr("twadvisor.fetchers.factory.KeyStore.get_secret", lambda self, key: None)

    fetcher = create_fetcher(settings)

    assert isinstance(fetcher, FinMindFetcher)
    assert fetcher.key_rotator is not None


def test_create_fetcher_uses_yahoo_primary(tmp_path) -> None:
    """Fetcher factory should honor a Yahoo primary setting."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "[fetcher]\nprimary = \"yahoo\"\nfallback = []\n[security]\nkeyring_service = \"twadvisor\"\n",
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")

    fetcher = create_fetcher(settings)
    assert isinstance(fetcher, YahooFinanceFetcher)


@pytest.mark.asyncio
async def test_finmind_get_quote_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """FinMind quote parsing should produce a Quote model."""

    payload = {
        "status": 200,
        "data": [
            {
                "date": "2026-04-22",
                "open": 980,
                "max": 1000,
                "min": 970,
                "close": 990,
                "Trading_Volume": 1000000,
            },
            {
                "date": "2026-04-23",
                "open": 990,
                "max": 1010,
                "min": 980,
                "close": 1000,
                "Trading_Volume": 1200000,
            }
        ],
    }
    monkeypatch.setattr(FinMindFetcher, "_request", lambda self, **params: payload)

    fetcher = FinMindFetcher(api_token="token")
    quote = await fetcher.get_quote("2330")

    assert isinstance(quote, Quote)
    assert quote.symbol == "2330"
    assert quote.volume == 1200
    assert quote.prev_close == Decimal("990")
    assert quote.limit_up == Decimal("1089.00")
    assert quote.limit_down == Decimal("891.00")


@pytest.mark.asyncio
async def test_finmind_get_kline_and_chip(monkeypatch: pytest.MonkeyPatch) -> None:
    """FinMind kline and chip parsing should return structured values."""

    def fake_request(self: object, **params: str) -> dict:
        if params["dataset"] == "TaiwanStockPrice":
            return {
                "status": 200,
                "data": [
                    {
                        "date": "2026-04-22",
                        "open": 990,
                        "max": 1010,
                        "min": 980,
                        "close": 1000,
                        "Trading_Volume": 1200000,
                    }
                ],
            }
        return {
            "status": 200,
            "data": [
                {"name": "Foreign_Investor", "buy_sell": 1000},
                {"name": "Investment_Trust", "buy_sell": -200},
                {"name": "Dealer_self", "buy_sell": 50},
            ],
        }

    monkeypatch.setattr(FinMindFetcher, "_request", fake_request)
    fetcher = FinMindFetcher(api_token="token")

    frame = await fetcher.get_kline("2330", date(2026, 4, 20), date(2026, 4, 23))
    chip = await fetcher.get_chip("2330", date(2026, 4, 23))

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(chip, ChipData)
    assert chip.foreign_net == 1000


def test_finmind_request_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """FinMind low-level request should reject HTTP and API errors."""

    class StubResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    monkeypatch.setattr(
        "twadvisor.fetchers.finmind.requests.get",
        lambda *args, **kwargs: StubResponse(500, {"status": 500}),
    )
    fetcher = FinMindFetcher(api_token="token")
    with pytest.raises(FetcherError):
        fetcher._request(dataset="TaiwanStockPrice")

    monkeypatch.setattr(
        "twadvisor.fetchers.finmind.requests.get",
        lambda *args, **kwargs: StubResponse(200, {"status": 0}),
    )
    with pytest.raises(FetcherError):
        fetcher._request(dataset="TaiwanStockPrice")


def test_finmind_request_rotates_local_keys_on_402(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FinMind 402 should retire the active local key and retry with the next one."""

    class StubResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    key_config = tmp_path / "finmind_keys.local.json"
    key_state = tmp_path / "finmind_key_state.json"
    key_config.write_text(
        json.dumps(
            {
                "keys": [
                    {"name": "finmind_1", "token": "token-one", "enabled": True},
                    {"name": "finmind_2", "token": "token-two", "enabled": True},
                ],
                "rotate_on_status": [402],
                "cooldown_hours": 24,
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs["headers"]["Authorization"])
        if len(calls) == 1:
            return StubResponse(402, {"status": 402})
        return StubResponse(200, {"status": 200, "data": [{"stock_id": "2330"}]})

    monkeypatch.setattr("twadvisor.fetchers.finmind.requests.get", fake_get)
    rotator = FinMindKeyRotator.from_file(key_config, key_state)
    assert rotator is not None
    fetcher = FinMindFetcher(key_rotator=rotator)

    payload = fetcher._request(dataset="TaiwanStockPrice")

    assert payload["data"][0]["stock_id"] == "2330"
    assert calls == ["Bearer token-one", "Bearer token-two"]
    state = json.loads(key_state.read_text(encoding="utf-8"))
    assert state["current_name"] == "finmind_2"
    assert "finmind_1" in state["exhausted"]


@pytest.mark.asyncio
async def test_finmind_get_quote_symbol_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing quote data should raise SymbolNotFoundError."""

    monkeypatch.setattr(FinMindFetcher, "_request", lambda self, **params: {"status": 200, "data": []})
    fetcher = FinMindFetcher(api_token="token")

    with pytest.raises(SymbolNotFoundError):
        await fetcher.get_quote("9999")


@pytest.mark.asyncio
async def test_twstock_fetcher_quote_and_kline(monkeypatch: pytest.MonkeyPatch) -> None:
    """twstock fetcher should parse realtime and history data."""

    monkeypatch.setattr(
        "twadvisor.fetchers.twstock_fetcher.twstock.realtime.get",
        lambda symbol: {
            "success": True,
            "realtime": {
                "latest_trade_price": "1000",
                "open": "990",
                "high": "1010",
                "low": "980",
                "yesterday_close": "995",
                "accumulate_trade_volume": "2500000",
                "best_bid_price": ["999"],
                "best_ask_price": ["1000"],
            },
            "info": {"name": "TSMC"},
        },
    )

    class PriceRow:
        def __init__(self, dt: date) -> None:
            self.date = dt
            self.open = 990
            self.high = 1010
            self.low = 980
            self.close = 1000
            self.capacity = 1000000

    class StubStock:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def fetch_from(self, year: int, month: int) -> list[PriceRow]:
            return [PriceRow(date(2026, 4, 22)), PriceRow(date(2026, 4, 23))]

    monkeypatch.setattr("twadvisor.fetchers.twstock_fetcher.twstock.Stock", StubStock)

    fetcher = TwstockFetcher()
    quote = await fetcher.get_quote("2330")
    frame = await fetcher.get_kline("2330", date(2026, 4, 22), date(2026, 4, 23))
    chip = await fetcher.get_chip("2330", date(2026, 4, 23))

    assert quote.name == "TSMC"
    assert quote.volume == 2500
    assert quote.limit_up == Decimal("1094.50")
    assert quote.limit_down == Decimal("895.50")
    assert not frame.empty
    assert chip.foreign_net == 0


@pytest.mark.asyncio
async def test_twstock_fetcher_symbol_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """twstock fetcher should raise on missing realtime data."""

    monkeypatch.setattr("twadvisor.fetchers.twstock_fetcher.twstock.realtime.get", lambda symbol: {"success": False})
    fetcher = TwstockFetcher()
    with pytest.raises(SymbolNotFoundError):
        await fetcher.get_quote("9999")


@pytest.mark.asyncio
async def test_yahoo_fetcher_quote_and_kline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Yahoo fetcher should parse history into quote and OHLCV frame."""

    index = pd.to_datetime(["2026-04-22", "2026-04-23"])
    history = pd.DataFrame(
        {
            "Open": [990.0, 995.0],
            "High": [1010.0, 1015.0],
            "Low": [980.0, 985.0],
            "Close": [1000.0, 1005.0],
            "Volume": [1000000, 1100000],
        },
        index=index,
    )

    class StubTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, *args, **kwargs) -> pd.DataFrame:
            return history

    monkeypatch.setattr("twadvisor.fetchers.yahoo.yf.Ticker", StubTicker)
    fetcher = YahooFinanceFetcher()

    quote = await fetcher.get_quote("2330")
    frame = await fetcher.get_kline("2330", date(2026, 4, 22), date(2026, 4, 23))
    chip = await fetcher.get_chip("2330", date(2026, 4, 23))

    assert str(quote.price) == "1005.0"
    assert quote.limit_up == Decimal("1100.00")
    assert quote.limit_down == Decimal("900.00")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert chip.short_balance == 0


@pytest.mark.asyncio
async def test_yahoo_fetcher_symbol_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Yahoo fetcher should raise when no history is returned."""

    class EmptyTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, *args, **kwargs) -> pd.DataFrame:
            return pd.DataFrame()

    monkeypatch.setattr("twadvisor.fetchers.yahoo.yf.Ticker", EmptyTicker)
    fetcher = YahooFinanceFetcher()
    with pytest.raises(SymbolNotFoundError):
        await fetcher.get_quote("9999")
