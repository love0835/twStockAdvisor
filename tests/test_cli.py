"""Phase 1 CLI tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from twadvisor.cli import app
from twadvisor.constants import DEFAULT_CONFIG_PATH
from twadvisor.models import Quote
from twadvisor.settings import load_settings

runner = CliRunner()


def test_cli_help_shows_commands() -> None:
    """The root CLI help should render successfully."""

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "keys" in result.stdout


def test_keys_set_stores_secret(monkeypatch: object) -> None:
    """The keys set command should write to the keystore."""

    captured: dict[str, str] = {}

    def fake_set_secret(self: object, key: str, value: str) -> None:
        captured[key] = value

    monkeypatch.setattr("twadvisor.security.keystore.KeyStore.set_secret", fake_set_secret)

    result = runner.invoke(app, ["keys", "set", "anthropic", "--value", "secret-token"])
    assert result.exit_code == 0
    assert captured["anthropic"] == "secret-token"


def test_load_settings_reads_default_config(tmp_path: Path) -> None:
    """Settings loader should parse the default config structure."""

    default_path = tmp_path / "default.toml"
    default_path.write_text(Path(DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"), encoding="utf-8")

    settings = load_settings(default_path=default_path, user_path=tmp_path / "user.toml")

    assert settings.app.timezone == "Asia/Taipei"
    assert settings.fetcher.primary == "finmind"


def test_quote_command_renders_quote(monkeypatch: object) -> None:
    """The quote command should print quote data."""

    quote = Quote(
        symbol="2330",
        name="TSMC",
        price="1000",
        open="990",
        high="1010",
        low="980",
        prev_close="995",
        volume=1234,
        bid="999",
        ask="1000",
        limit_up="1094",
        limit_down="896",
        timestamp="2026-04-23T10:00:00",
    )

    class StubFetcher:
        async def get_quote(self, symbol: str) -> Quote:
            return quote

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    result = runner.invoke(app, ["quote", "2330"])
    assert result.exit_code == 0
    assert "TSMC" in result.stdout
    assert "1000" in result.stdout


def test_indicators_command_renders_table(monkeypatch: object) -> None:
    """The indicators command should print indicator rows."""

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
        async def get_kline(self, symbol: str, start: object, end: object) -> pd.DataFrame:
            return frame

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    result = runner.invoke(app, ["indicators", "2330"])
    assert result.exit_code == 0
    assert "ma5" in result.stdout
    assert "macd" in result.stdout


def test_quote_command_symbol_not_found(monkeypatch: object) -> None:
    """The quote command should exit with code 1 when the symbol is unknown."""

    class StubFetcher:
        async def get_quote(self, symbol: str) -> Quote:
            from twadvisor.fetchers.base import SymbolNotFoundError

            raise SymbolNotFoundError(symbol)

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    result = runner.invoke(app, ["quote", "9999"])
    assert result.exit_code == 1
    assert "Symbol not found" in result.stdout


def test_init_command_creates_files(tmp_path: Path) -> None:
    """The init command should write config files to the requested paths."""

    default_config = tmp_path / "config" / "default.toml"
    user_config = tmp_path / "config" / "user.toml"
    result = runner.invoke(
        app,
        [
            "init",
            "--default-config",
            str(default_config),
            "--user-config",
            str(user_config),
        ],
    )
    assert result.exit_code == 0
    assert default_config.exists()
    assert user_config.exists()
