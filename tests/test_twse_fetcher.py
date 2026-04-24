"""Tests for TWSE public CSV fetcher."""

from __future__ import annotations

from datetime import date

import pytest

from twadvisor.fetchers.twse import TwseFetcher, parse_twse_symbols


def test_parse_twse_symbols_handles_big5_csv() -> None:
    """TWSE CSV payloads can be parsed from Big5 content."""

    content = "證券代號,證券名稱\n2330,台積電\n0050,元大台灣50\n".encode("big5")

    assert parse_twse_symbols(content) == {"2330", "0050"}


@pytest.mark.asyncio
async def test_twse_fetcher_caches_by_dataset_and_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated calls for the same date should hit the in-memory cache."""

    calls = {"count": 0}

    class Response:
        status_code = 200
        content = "證券代號,證券名稱\n2330,台積電\n".encode("big5")

    def fake_get(*args: object, **kwargs: object) -> Response:
        calls["count"] += 1
        return Response()

    monkeypatch.setattr("twadvisor.fetchers.twse.requests.get", fake_get)
    fetcher = TwseFetcher()

    first = await fetcher.get_day_trade_eligible(date(2026, 4, 24))
    second = await fetcher.get_day_trade_eligible(date(2026, 4, 24))

    assert first == {"2330"}
    assert second == {"2330"}
    assert calls["count"] == 1
