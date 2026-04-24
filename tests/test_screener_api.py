"""Tests for Web screener endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from twadvisor.screener.base import RankedRecommendation, ScreenResult
from twadvisor.web.app import create_app
from twadvisor.web.routes import _SCREENER_CACHE


class FakePipeline:
    """Screener pipeline stub for API tests."""

    calls = 0
    empty = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def run_daytrade(self, **kwargs: object) -> ScreenResult:
        FakePipeline.calls += 1
        if FakePipeline.empty:
            return ScreenResult(
                source="daytrade",
                market_view="沒有候選股",
                candidates_total=2,
                candidates_after_rules=0,
                recommendations=[],
                warnings=["無候選股"],
            )
        return ScreenResult(
            source="daytrade",
            market_view="盤勢偏多",
            candidates_total=2,
            candidates_after_rules=1,
            recommendations=[
                RankedRecommendation(
                    rank=1,
                    symbol="2330",
                    name="台積電",
                    confidence=Decimal("0.82"),
                    entry_price_low=Decimal("100"),
                    entry_price_high=Decimal("102"),
                    stop_loss=Decimal("95"),
                    take_profit=Decimal("110"),
                    reason="量價條件優於同批候選。",
                    rule_score=Decimal("82"),
                )
            ],
        )

    async def run_swing(self, **kwargs: object) -> ScreenResult:
        return await self.run_daytrade(**kwargs)


def test_screener_daytrade_endpoint_returns_recommendations(monkeypatch) -> None:
    """Daytrade scanner endpoint should serialize ranked recommendations."""

    _SCREENER_CACHE.clear()
    FakePipeline.calls = 0
    FakePipeline.empty = False
    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.create_analyzer", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.TwseFetcher", lambda: object())
    monkeypatch.setattr("twadvisor.web.routes.ScreenerPipeline", FakePipeline)

    client = TestClient(create_app())
    response = client.post("/api/screener/daytrade", json={"top_n": 5, "storage_path": "missing.json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendations"][0]["symbol"] == "2330"
    assert payload["recommendations"][0]["confidence"] == "82%"
    assert payload["candidates_after_rules"] == 1


def test_screener_empty_candidates_return_warning(monkeypatch) -> None:
    """Empty markets should return 200 with a warning."""

    _SCREENER_CACHE.clear()
    FakePipeline.empty = True
    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.create_analyzer", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.TwseFetcher", lambda: object())
    monkeypatch.setattr("twadvisor.web.routes.ScreenerPipeline", FakePipeline)

    client = TestClient(create_app())
    response = client.post("/api/screener/daytrade", json={"top_n": 5, "storage_path": "missing.json"})

    assert response.status_code == 200
    assert response.json()["recommendations"] == []
    assert response.json()["warnings"] == ["無候選股"]


def test_screener_endpoint_uses_cache(monkeypatch) -> None:
    """Repeated identical requests should return from the 10-minute cache."""

    _SCREENER_CACHE.clear()
    FakePipeline.calls = 0
    FakePipeline.empty = False
    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.create_analyzer", lambda settings: object())
    monkeypatch.setattr("twadvisor.web.routes.TwseFetcher", lambda: object())
    monkeypatch.setattr("twadvisor.web.routes.ScreenerPipeline", FakePipeline)

    client = TestClient(create_app())
    first = client.post("/api/screener/daytrade", json={"top_n": 5, "storage_path": "missing.json"})
    second = client.post("/api/screener/daytrade", json={"top_n": 5, "storage_path": "missing.json"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert FakePipeline.calls == 1
    assert second.json()["elapsed_sec"] == 0.0
