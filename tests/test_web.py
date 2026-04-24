"""Tests for the FastAPI Web UI."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from twadvisor.fetchers.base import SymbolNotFoundError
from twadvisor.models import AnalysisResponse, ChipData, Quote, Recommendation, Strategy
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository
from twadvisor.web.app import create_app
from twadvisor.web.routes import _ANALYZE_INPUT_CACHE


def _settings(tmp_path: Path):
    default_path = tmp_path / "default.toml"
    default_path.write_text(
        f"[app]\ndb_path = \"{str(tmp_path / 'advisor.db').replace(chr(92), '/')}\"\n",
        encoding="utf-8",
    )
    return load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/initial-admin",
        json={"username": "admin", "password": "password123", "display_name": "Admin"},
    )
    assert response.status_code == 200


def test_auth_required_for_portfolio(tmp_path: Path, monkeypatch) -> None:
    """Private API endpoints should require login."""

    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: _settings(tmp_path))
    client = TestClient(create_app())
    response = client.get("/api/portfolio")
    assert response.status_code == 401


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
        async def get_quote(self, symbol: str) -> Quote:
            return (
                await self.get_quotes([symbol])
            )[symbol]

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
    _login(client)
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
    rows_by_symbol = {row["symbol"]: row for row in payload["rows"]}
    assert "2330" in rows_by_symbol
    assert rows_by_symbol["2330"]["current_price"] == "尚未更新"

    quote_response = client.post(
        "/api/portfolio/quotes",
        json={"storage_path": storage, "commission_discount": 0.28},
    )
    assert quote_response.status_code == 200
    quote_payload = quote_response.json()
    quote_rows_by_symbol = {row["symbol"]: row for row in quote_payload["rows"]}
    assert quote_rows_by_symbol["2330"]["current_price"] == "600"
    assert quote_rows_by_symbol["2330"]["unrealized_pnl"] == "17729.18"


def test_portfolio_management_endpoints(tmp_path: Path, monkeypatch) -> None:
    """Portfolio management endpoints should update local holdings."""

    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: _settings(tmp_path))
    client = TestClient(create_app())
    _login(client)
    storage = str(tmp_path / "portfolio.json")

    cash_response = client.post("/api/portfolio/cash", json={"cash": "300000", "storage_path": storage})
    assert cash_response.status_code == 200
    assert cash_response.json()["cash"] == "300000"

    add_response = client.post(
        "/api/portfolio/positions",
        json={"symbol": "2330", "qty": 1000, "avg_cost": "580", "storage_path": storage},
    )
    assert add_response.status_code == 200
    assert add_response.json()["rows"][0]["symbol"] == "2330"

    duplicate_response = client.post(
        "/api/portfolio/positions",
        json={"symbol": "2330", "qty": 1000, "avg_cost": "580", "storage_path": storage},
    )
    assert duplicate_response.status_code == 409

    update_response = client.put(
        "/api/portfolio/positions/2330",
        json={"symbol": "2330", "qty": 2000, "avg_cost": "590", "storage_path": storage},
    )
    assert update_response.status_code == 200
    assert update_response.json()["rows"][0]["qty"] == "2000"

    delete_response = client.request(
        "DELETE",
        "/api/portfolio/positions/2330",
        json={"storage_path": storage},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["rows"] == []


def test_report_endpoint(tmp_path: Path, monkeypatch) -> None:
    """Report endpoint should summarize stored daily performance."""

    settings = _settings(tmp_path)
    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: settings)
    repo = AdvisorRepository(settings.app.db_path)
    repo.upsert_performance_daily(Decimal("100000"))

    client = TestClient(create_app())
    _login(client)
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
    _login(client)
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

    _ANALYZE_INPUT_CACHE.clear()
    settings = _settings(tmp_path)
    monkeypatch.setattr("twadvisor.web.routes.load_settings", lambda: settings)
    storage = tmp_path / "portfolio.json"
    client = TestClient(create_app())
    _login(client)
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
        calls: list[str] = []

        async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
            return {symbol: quote for symbol in symbols}

        async def get_kline(self, symbol: str, start: object, end: object) -> pd.DataFrame:
            self.calls.append(symbol)
            return frame

        async def get_chip(self, symbol: str, dt: object) -> ChipData:
            if symbol == "2317":
                raise SymbolNotFoundError(symbol)
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
        seen_positions: list[str] = []

        async def analyze(self, req) -> AnalysisResponse:
            self.__class__.seen_positions = [position.symbol for position in req.portfolio.positions]
            symbol = req.watchlist[0]
            return AnalysisResponse(
                recommendations=[
                    Recommendation(
                        symbol=symbol,
                        action="hold",
                        qty=0,
                        order_type="limit",
                        price=Decimal("600"),
                        stop_loss=Decimal("570"),
                        take_profit=Decimal("660"),
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
    assert payload["recommendations"][0]["lots"] == "0"
    assert payload["recommendations"][0]["price"] == "600"
    assert payload["recommendations"][0]["stop_loss"] == "570"
    assert payload["recommendations"][0]["take_profit"] == "660"
    assert StubAnalyzer.seen_positions == []
    assert StubFetcher.calls == ["2330"]

    second_response = client.post(
        "/api/analyze",
        json={
            "strategy": "swing",
            "watchlist": ["2330"],
            "storage_path": str(storage),
        },
    )
    assert second_response.status_code == 200
    assert StubFetcher.calls == ["2330"]

    include_response = client.post(
        "/api/analyze",
        json={
            "strategy": "swing",
            "watchlist": [],
            "include_portfolio": True,
            "holding_symbols": ["2317"],
            "storage_path": str(storage),
        },
    )
    assert include_response.status_code == 200
    assert "2317 缺少籌碼資料" in include_response.json()["warnings"][0]
    assert StubAnalyzer.seen_positions == ["2317"]
    assert StubFetcher.calls == ["2330", "2317"]
