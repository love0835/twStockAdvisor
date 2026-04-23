"""Tests for notifier implementations."""

from __future__ import annotations

from datetime import datetime

import pytest
from rich.console import Console

from twadvisor.models import Recommendation, Strategy
from twadvisor.notifier.console import ConsoleNotifier
from twadvisor.notifier.discord import DiscordWebhookNotifier
from twadvisor.notifier.factory import create_notifier
from twadvisor.settings import load_settings


def _recommendation(symbol: str = "2330") -> Recommendation:
    return Recommendation(
        symbol=symbol,
        action="buy",
        qty=1000,
        order_type="limit",
        price="600",
        stop_loss="580",
        take_profit="640",
        reason="test reason",
        confidence=0.7,
        strategy=Strategy.SWING,
        generated_at=datetime(2026, 4, 24, 10, 0, 0),
    )


@pytest.mark.asyncio
async def test_console_notifier_renders_table() -> None:
    """Console notifier should render the market view and recommendation."""

    console = Console(record=True)
    notifier = ConsoleNotifier(console=console)
    await notifier.notify([_recommendation()], "偏多震盪")
    output = console.export_text()
    assert "偏多震盪" in output
    assert "2330" in output


@pytest.mark.asyncio
async def test_discord_notifier_sends_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discord notifier should post embeds to the webhook."""

    captured: list[dict] = []

    class StubResponse:
        def __init__(self, status_code: int = 204, headers: dict | None = None) -> None:
            self.status_code = status_code
            self.headers = headers or {}

        def raise_for_status(self) -> None:
            return None

    class StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: dict):
            captured.append(json)
            return StubResponse()

    monkeypatch.setattr("twadvisor.notifier.discord.httpx.AsyncClient", lambda timeout: StubClient())
    notifier = DiscordWebhookNotifier("https://example.com/webhook")
    await notifier.notify([_recommendation()], "偏多震盪")
    assert captured[0]["embeds"][0]["title"] == "Buy 2330"


@pytest.mark.asyncio
async def test_discord_notifier_retries_after_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discord notifier should retry after a rate-limit response."""

    calls = {"count": 0}

    class StubResponse:
        def __init__(self, status_code: int, headers: dict | None = None) -> None:
            self.status_code = status_code
            self.headers = headers or {}

        def raise_for_status(self) -> None:
            return None

    class StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: dict):
            calls["count"] += 1
            if calls["count"] == 1:
                return StubResponse(429, {"Retry-After": "0"})
            return StubResponse(204)

    monkeypatch.setattr("twadvisor.notifier.discord.httpx.AsyncClient", lambda timeout: StubClient())
    notifier = DiscordWebhookNotifier("https://example.com/webhook")
    await notifier.notify([_recommendation()], "偏多震盪")
    assert calls["count"] == 2


def test_create_notifier_defaults_to_console(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Notifier factory should fall back to console when webhook is absent."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "[notifier]\nchannels = [\"console\", \"discord\"]\n[notifier.discord]\nwebhook_url_key = \"discord_webhook\"\n[security]\nkeyring_service = \"twadvisor\"\n",
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr("twadvisor.notifier.factory.KeyStore.get_secret", lambda self, key: None)
    notifier = create_notifier(settings)
    assert notifier.notifiers


def test_create_notifier_includes_discord_when_webhook_present(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Notifier factory should include a Discord notifier when a webhook exists."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(
        "[notifier]\nchannels = [\"console\", \"discord\"]\n[notifier.discord]\nwebhook_url_key = \"discord_webhook\"\nembed_color_buy = 1\nembed_color_sell = 2\nembed_color_hold = 3\n[security]\nkeyring_service = \"twadvisor\"\n",
        encoding="utf-8",
    )
    settings = load_settings(default_path=default_path, user_path=tmp_path / "missing.toml")
    monkeypatch.setattr("twadvisor.notifier.factory.KeyStore.get_secret", lambda self, key: "https://example.com/webhook")
    notifier = create_notifier(settings)
    assert len(notifier.notifiers) == 2
