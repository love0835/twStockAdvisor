"""Regression tests for FinMind chip data parsing."""

from __future__ import annotations

from datetime import date

import pytest

from twadvisor.fetchers.finmind import FinMindFetcher


@pytest.mark.asyncio
async def test_finmind_get_chip_uses_buy_minus_sell(monkeypatch: pytest.MonkeyPatch) -> None:
    """FinMind institutional records now expose buy and sell columns separately."""

    payload = {
        "status": 200,
        "data": [
            {"name": "Foreign_Investor", "buy": 3000, "sell": 500},
            {"name": "Investment_Trust", "buy": 100, "sell": 300},
            {"name": "Dealer_self", "buy": 0, "sell": 50},
        ],
    }
    monkeypatch.setattr(FinMindFetcher, "_request", lambda self, **params: payload)

    chip = await FinMindFetcher(api_token="token").get_chip("2330", date(2026, 4, 24))

    assert chip.foreign_net == 2500
    assert chip.trust_net == -200
    assert chip.dealer_net == -50
