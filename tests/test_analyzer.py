"""Tests for the Claude analyzer."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from twadvisor.analyzer.claude import ClaudeAnalyzer
from twadvisor.analyzer.factory import create_analyzer
from twadvisor.analyzer.gemini import GeminiAnalyzer
from twadvisor.analyzer.openai_analyzer import OpenAIAnalyzer
from twadvisor.models import AnalysisRequest, Portfolio, Position, Quote, Strategy, TechnicalIndicators, ChipData
from twadvisor.settings import load_settings


def _request() -> AnalysisRequest:
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
    return AnalysisRequest(
        strategy=Strategy.SWING,
        portfolio=Portfolio(
            cash=Decimal("200000"),
            positions=[Position(symbol="2330", qty=1000, avg_cost=Decimal("580"), opened_at=date(2025, 1, 2))],
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
        ),
        quotes={"2330": quote},
        indicators={
            "2330": TechnicalIndicators(
                symbol="2330",
                ma5=Decimal("598"),
                ma20=Decimal("590"),
                ma60=Decimal("580"),
                kd_k=Decimal("72"),
                kd_d=Decimal("66"),
                macd=Decimal("1.2"),
                macd_signal=Decimal("0.9"),
                rsi14=Decimal("61"),
                bband_upper=Decimal("610"),
                bband_lower=Decimal("570"),
                volume_ratio=Decimal("1.1"),
            )
        },
        chips={"2330": ChipData(symbol="2330", foreign_net=1000, trust_net=20, dealer_net=-10, margin_balance=0, short_balance=0, date=date(2026, 4, 24))},
        watchlist=["2330"],
        risk_preference="moderate",
        max_position_pct=0.2,
    )


def _tool_response(payload: dict) -> object:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="working"),
            SimpleNamespace(type="tool_use", name="submit_recommendations", input=payload),
        ],
        usage=SimpleNamespace(input_tokens=321, output_tokens=123),
    )


def test_prompt_includes_all_portfolio() -> None:
    """Prompt should include holdings, watchlist, and strategy guidance."""

    analyzer = ClaudeAnalyzer(api_key="token", client=SimpleNamespace(messages=None))
    system_prompt, user_prompt = analyzer.build_prompt(_request())
    assert "台股分析助理" in system_prompt
    assert "建議限價下單價" in system_prompt
    assert "2330" in user_prompt
    assert "qty=1000" in user_prompt
    assert "strategy" not in system_prompt.lower()


def test_parse_tool_use_response() -> None:
    """Tool-use blocks should parse into AnalysisResponse."""

    payload = json.loads(Path("E:\\TwStockAdvisor\\tests\\fixtures\\ai_response_sample.json").read_text(encoding="utf-8"))
    analyzer = ClaudeAnalyzer(api_key="token", client=SimpleNamespace(messages=None))
    response = analyzer._parse(_tool_response(payload), _request())
    assert response.market_view == payload["market_view"]
    assert response.recommendations[1].symbol == "2317"


@pytest.mark.asyncio
async def test_retry_on_rate_limit(tmp_path: Path) -> None:
    """Analyzer should retry on RateLimitError and eventually succeed."""

    payload = json.loads(Path("E:\\TwStockAdvisor\\tests\\fixtures\\ai_response_sample.json").read_text(encoding="utf-8"))
    calls = {"count": 0}

    class StubMessages:
        def create(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                request = SimpleNamespace(method="POST", url="https://api.anthropic.com/v1/messages", headers={})
                response = SimpleNamespace(status_code=429, request=request, headers={})
                raise anthropic.RateLimitError("rate limited", response=response, body={})
            return _tool_response(payload)

    client = SimpleNamespace(messages=StubMessages())
    analyzer = ClaudeAnalyzer(api_key="token", client=client, db_path=str(tmp_path / "tokens.db"))
    result = await analyzer.analyze(_request())
    assert calls["count"] == 2
    assert result.market_view == payload["market_view"]


def test_prompt_cache_enabled() -> None:
    """Prompt caching should add cache_control to the system block."""

    captured: dict[str, object] = {}

    class StubMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _tool_response({"market_view": "ok", "recommendations": []})

    client = SimpleNamespace(messages=StubMessages())
    analyzer = ClaudeAnalyzer(api_key="token", client=client, use_prompt_cache=True)
    analyzer._create_message("system", "user")
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_token_usage_is_recorded(tmp_path: Path) -> None:
    """Successful analysis should write token usage into SQLite."""

    payload = json.loads(Path("E:\\TwStockAdvisor\\tests\\fixtures\\ai_response_sample.json").read_text(encoding="utf-8"))

    class StubMessages:
        def create(self, **kwargs):
            return _tool_response(payload)

    db_path = tmp_path / "tokens.db"
    analyzer = ClaudeAnalyzer(api_key="token", client=SimpleNamespace(messages=StubMessages()), db_path=str(db_path))
    await analyzer.analyze(_request())

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT provider, model, prompt_tokens, completion_tokens FROM token_usage").fetchall()
    finally:
        connection.close()

    assert rows[0][0] == "claude"
    assert rows[0][2] == 321


@pytest.mark.asyncio
async def test_openai_analyzer_records_structured_output(tmp_path: Path) -> None:
    """OpenAI analyzer should parse JSON schema output and record token usage."""

    payload = json.loads(Path("E:\\TwStockAdvisor\\tests\\fixtures\\ai_response_sample.json").read_text(encoding="utf-8"))

    class StubResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps(payload),
                usage=SimpleNamespace(input_tokens=210, output_tokens=80),
                output=[],
            )

    analyzer = OpenAIAnalyzer(
        api_key="token",
        client=SimpleNamespace(responses=StubResponses()),
        db_path=str(tmp_path / "openai.db"),
    )
    result = await analyzer.analyze(_request())

    assert result.market_view == payload["market_view"]
    assert result.recommendations[0].symbol == payload["recommendations"][0]["symbol"]


@pytest.mark.asyncio
async def test_gemini_analyzer_records_structured_output(tmp_path: Path) -> None:
    """Gemini analyzer should parse JSON text output and record token usage."""

    payload = json.loads(Path("E:\\TwStockAdvisor\\tests\\fixtures\\ai_response_sample.json").read_text(encoding="utf-8"))

    class StubModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(
                text=json.dumps(payload),
                usage_metadata=SimpleNamespace(prompt_token_count=188, candidates_token_count=61),
            )

    analyzer = GeminiAnalyzer(
        api_key="token",
        client=SimpleNamespace(models=StubModels()),
        db_path=str(tmp_path / "gemini.db"),
    )
    result = await analyzer.analyze(_request())

    assert result.market_view == payload["market_view"]
    assert result.raw_prompt_tokens == 188


def test_create_analyzer_supports_multiple_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory should instantiate the configured provider from keyring secrets."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "\n".join(
            [
                "[app]",
                f"db_path = \"{str(tmp_path / 'advisor.db').replace(chr(92), '/')}\"",
                "[ai]",
                "provider = \"openai\"",
                "model_openai = \"gpt-4o\"",
                "model_gemini = \"gemini-2.0-flash\"",
                "[security]",
                "keyring_service = \"twadvisor\"",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr(
        "twadvisor.analyzer.factory.KeyStore.get_secret",
        lambda self, key: "token" if key == "openai" else None,
    )

    analyzer = create_analyzer(settings)

    assert isinstance(analyzer, OpenAIAnalyzer)
