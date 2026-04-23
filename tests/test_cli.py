"""Phase 1 CLI tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from twadvisor.cli import app
from twadvisor.constants import DEFAULT_CONFIG_PATH
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
