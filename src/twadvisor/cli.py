"""Typer CLI entrypoint."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from twadvisor.constants import APP_NAME, DEFAULT_CONFIG_PATH, DISCLAIMER_LINES, USER_CONFIG_PATH
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import load_settings

app = typer.Typer(help="Taiwan stock AI advisor")
keys_app = typer.Typer(help="Manage API keys and secrets")
app.add_typer(keys_app, name="keys")
console = Console()

CONFIG_TEMPLATE_SOURCE = Path(__file__).resolve().parents[2] / DEFAULT_CONFIG_PATH


def _ensure_parent(path: Path) -> None:
    """Create the parent directory for a file path."""

    path.parent.mkdir(parents=True, exist_ok=True)


def _render_disclaimer() -> None:
    """Render the project disclaimer."""

    for line in DISCLAIMER_LINES:
        console.print(line, style="yellow")


@app.callback(invoke_without_command=False)
def callback() -> None:
    """Root CLI callback."""


@app.command()
def init(
    default_config: Path = typer.Option(Path(DEFAULT_CONFIG_PATH), help="Default config path"),
    user_config: Path = typer.Option(Path(USER_CONFIG_PATH), help="User config path"),
) -> None:
    """Initialize project config files."""

    _render_disclaimer()
    _ensure_parent(default_config)
    _ensure_parent(user_config)
    if not default_config.exists():
        default_config.write_text(CONFIG_TEMPLATE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    if not user_config.exists():
        user_config.write_text("[ai]\nprovider = \"claude\"\n", encoding="utf-8")
    console.print(f"{APP_NAME} initialized", style="green")
    console.print(f"default config: {default_config}")
    console.print(f"user config: {user_config}")


@keys_app.command("set")
def set_key(
    key_name: str = typer.Argument(..., help="Key name to store"),
    value: str | None = typer.Option(None, "--value", help="Provide the secret directly"),
) -> None:
    """Store a secret in the OS keyring."""

    _render_disclaimer()
    settings = load_settings()
    secret = value if value is not None else typer.prompt("Secret", hide_input=True)
    keystore = KeyStore(settings.security.keyring_service)
    keystore.set_secret(key_name, secret)
    console.print(f"Stored key: {key_name}", style="green")


def main() -> None:
    """Run the Typer application."""

    app()
