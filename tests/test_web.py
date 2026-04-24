"""Tests for the FastAPI Web UI."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from twadvisor.models import AnalysisResponse, ChipData, Quote, Recommendation, Strategy
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository
from twadvisor.web.app import create_app


def _settings(tmp_path: Path):
    default_path = tmp_path / "default.toml"
    default_path.write_text(
        f"[app]\ndb_path = \"{str(tmp_path / 'advisor.db').replace(chr(92), '/')}\"\n",
        encoding="utf-8",
    )
    return load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")


def test_health_endpoint() -> None:
    """Health endpoint should report ok."""

    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_portfolio_import_and_read(tmp_path: Path, monkeypatch) -> None:
    """Portfolio endpoints should import CSV data and read it back."""

    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: _settings(tmp_path))

    class StubFetcher:
        async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
            return {
                symbol: Quote(
                    symbol=symbol,
                    name=symbol,
                    price=Decimal("600"),
                    open=Decimal("590"),
                    high=Decimal("605"),
                    low=Decimal("588"),
                    prev_close=Decimal("595"),
                    volume=1000,
                    bid=Decimal("599"),
                    ask=Decimal("600"),
                    limit_up=Decimal("654"),
                    limit_down=Decimal("536"),
                    timestamp=datetime(2026, 4, 24, 10, 0, 0),
                )
                for symbol in symbols
            }

    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: StubFetcher())
    client = TestClient(create_app())
    storage = str(tmp_path / "portfolio.json")

    import_response = client.post(
        "/api/portfolio/import",
        json={
            "csv_path": "E:/TwStockAdvisor/tests/fixtures/portfolio_sample.csv",
            "cash": "200000",
            "storage_path": storage,
        },
    )
    assert import_response.status_code == 200
    assert import_response.json()["imported"] == 2

    response = client.get("/api/portfolio", params={"storage_path": storage})
    assert response.status_code == 200
    payload = response.json()
    assert payload["position_count"] == 2
    assert payload["rows"][0]["symbol"] == "2330"


def test_report_endpoint(tmp_path: Path, monkeypatch) -> None:
    """Report endpoint should summarize stored daily performance."""

    settings = _settings(tmp_path)
    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: settings)
    repo = AdvisorRepository(settings.app.db_path)
    repo.upsert_performance_daily(Decimal("100000"))

    client = TestClient(create_app())
    response = client.get("/api/report", params={"period": "30d"})
    assert response.status_code == 200
    assert response.json()["days"] == 1


def test_backtest_endpoint(tmp_path: Path, monkeypatch) -> None:
    """Backtest endpoint should return summary metrics."""

    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: _settings(tmp_path))

    frame = pd.DataFrame(
        {
            "open": range(100, 230),
            "high": range(101, 231),
            "low": range(99, 229),
            "close": range(100, 230),
            "volume": range(1000, 1130),
        },
        index=pd.date_range("2025-01-01", periods=130, freq="D"),
    )

    class StubFetcher:
        async def get_kline(self, symbol: str, start: date, end: date) -> pd.DataFrame:
            return frame

    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: StubFetcher())
    client = TestClient(create_app())
    response = client.post(
        "/api/backtest",
        json={
            "strategy": "swing",
            "symbols": ["2330"],
            "from_date": "2025-01-01",
            "to_date": "2025-05-10",
            "initial_cash": "1000000",
            "storage_path": str(tmp_path / "portfolio.json"),
        },
    )
    assert response.status_code == 200
    assert "final_equity" in response.json()


def test_analyze_endpoint(tmp_path: Path, monkeypatch) -> None:
    """Analyze endpoint should return structured recommendations."""

    settings = _settings(tmp_path)
    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: settings)
    storage = tmp_path / "portfolio.json"
    client = TestClient(create_app())
    client.post(
        "/api/portfolio/import",
        json={
            "csv_path": "E:/TwStockAdvisor/tests/fixtures/portfolio_sample.csv",
            "cash": "200000",
            "storage_path": str(storage),
        },
    )

    quote = Quote(
        symbol="2330",
        name="TSMC",
        price=Decimal("600"),
        open=Decimal("590"),
        high=Decimal("605"),
        low=Decimal("588"),
        prev_close=Decimal("595"),
        volume=1000,
        bid=Decimal("599"),
        ask=Decimal("600"),
        limit_up=Decimal("654"),
        limit_down=Decimal("536"),
        timestamp=datetime(2026, 4, 24, 10, 0, 0),
    )

    frame = pd.DataFrame(
        {
            "open": range(100, 220),
            "high": range(101, 221),
            "low": range(99, 219),
            "close": range(100, 220),
            "volume": range(1000, 1120),
        },
        index=pd.date_range("2025-01-01", periods=120, freq="D"),
    )

    class StubFetcher:
        async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
            return {symbol: quote for symbol in symbols}

        async def get_kline(self, symbol: str, start: object, end: object) -> pd.DataFrame:
            return frame

        async def get_chip(self, symbol: str, dt: object) -> ChipData:
            return ChipData(
                symbol=symbol,
                foreign_net=0,
                trust_net=0,
                dealer_net=0,
                margin_balance=0,
                short_balance=0,
                date=date(2026, 4, 24),
            )

    class StubAnalyzer:
        async def analyze(self, req) -> AnalysisResponse:
            return AnalysisResponse(
                recommendations=[
                    Recommendation(
                        symbol="2330",
                        action="hold",
                        qty=0,
                        order_type="limit",
                        reason="等待整理結束",
                        confidence=0.7,
                        strategy=Strategy.SWING,
                        generated_at=datetime(2026, 4, 24, 10, 0, 0),
                    )
                ],
                market_view="區間震盪",
                warnings=[],
                raw_prompt_tokens=100,
                raw_completion_tokens=50,
            )

    monkeypatch.setattr("twadvisor.web.routes.create_fetcher", lambda settings: StubFetcher())
    monkeypatch.setattr("twadvisor.web.routes.create_analyzer", lambda settings: StubAnalyzer())

    response = client.post(
        "/api/analyze",
        json={
            "strategy": "swing",
            "watchlist": ["2330"],
            "storage_path": str(storage),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["market_view"] == "區間震盪"
    assert payload["recommendations"][0]["symbol"] == "2330"
