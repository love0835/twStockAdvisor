"""Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from twadvisor.constants import (
    APP_NAME,
    DEFAULT_CONFIG_PATH,
    DEFAULT_PORTFOLIO_PATH,
    DISCLAIMER_LINES,
    USER_CONFIG_PATH,
)
from twadvisor.fetchers.base import FetcherError, SymbolNotFoundError
from twadvisor.fetchers.factory import create_fetcher
from twadvisor.indicators.technical import compute_indicators
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import load_settings

app = typer.Typer(help="Taiwan stock AI advisor")
keys_app = typer.Typer(help="Manage API keys and secrets")
portfolio_app = typer.Typer(help="Manage portfolio holdings")
app.add_typer(keys_app, name="keys")
app.add_typer(portfolio_app, name="portfolio")
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


@app.command()
def quote(symbol: str = typer.Argument(..., help="Taiwan stock symbol")) -> None:
    """Print a realtime quote for a symbol."""

    _render_disclaimer()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    try:
        quote_obj = asyncio.run(fetcher.get_quote(symbol))
    except SymbolNotFoundError:
        console.print(f"Symbol not found: {symbol}", style="red")
        raise typer.Exit(code=1)
    except FetcherError as exc:
        console.print(f"Fetcher error: {exc}", style="red")
        raise typer.Exit(code=1)

    table = Table(title=f"Quote {quote_obj.symbol}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Name", quote_obj.name)
    table.add_row("Price", str(quote_obj.price))
    table.add_row("Open", str(quote_obj.open))
    table.add_row("High", str(quote_obj.high))
    table.add_row("Low", str(quote_obj.low))
    table.add_row("Prev Close", str(quote_obj.prev_close))
    table.add_row("Volume(lot)", str(quote_obj.volume))
    table.add_row("Timestamp", quote_obj.timestamp.isoformat(sep=" ", timespec="seconds"))
    console.print(table)


@app.command()
def indicators(symbol: str = typer.Argument(..., help="Taiwan stock symbol")) -> None:
    """Print technical indicators for a symbol."""

    _render_disclaimer()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    today = date.today()
    start = today.replace(year=today.year - 1)
    try:
        frame = asyncio.run(fetcher.get_kline(symbol, start=start, end=today))
    except SymbolNotFoundError:
        console.print(f"Symbol not found: {symbol}", style="red")
        raise typer.Exit(code=1)
    except FetcherError as exc:
        console.print(f"Fetcher error: {exc}", style="red")
        raise typer.Exit(code=1)

    indicator_snapshot = compute_indicators(frame, symbol)
    table = Table(title=f"Indicators {symbol}")
    table.add_column("Indicator")
    table.add_column("Value")
    for field_name, value in indicator_snapshot.model_dump().items():
        if field_name == "symbol":
            continue
        table.add_row(field_name, "-" if value is None else str(value))
    console.print(table)


@portfolio_app.command("import")
def portfolio_import(
    file: Path = typer.Option(..., "--file", exists=True, readable=True, help="CSV file path"),
    cash: str | None = typer.Option(None, help="Available cash after import"),
    storage: Path = typer.Option(Path(DEFAULT_PORTFOLIO_PATH), help="Portfolio storage path"),
) -> None:
    """Import portfolio positions from a CSV file."""

    _render_disclaimer()
    manager = PortfolioManager(storage_path=storage)
    cash_value = None if cash is None else Decimal(cash)
    portfolio = manager.import_csv(file, cash=cash_value)
    console.print(f"Imported {len(portfolio.positions)} positions", style="green")


@portfolio_app.command("show")
def portfolio_show(
    storage: Path = typer.Option(Path(DEFAULT_PORTFOLIO_PATH), help="Portfolio storage path"),
) -> None:
    """Show current portfolio rows with unrealized PnL."""

    _render_disclaimer()
    manager = PortfolioManager(storage_path=storage)
    portfolio = manager.load()
    quotes = {}
    if portfolio.positions:
        settings = load_settings()
        fetcher = create_fetcher(settings)
        symbols = [position.symbol for position in portfolio.positions]
        try:
            quotes = asyncio.run(fetcher.get_quotes(symbols))
        except (SymbolNotFoundError, FetcherError):
            quotes = {}

    table = Table(title="Portfolio")
    table.add_column("Symbol")
    table.add_column("Qty")
    table.add_column("Avg Cost")
    table.add_column("Current")
    table.add_column("PnL")
    table.add_column("PnL %")
    for row in manager.build_rows(quotes):
        table.add_row(
            row["symbol"],
            row["qty"],
            row["avg_cost"],
            row["current_price"],
            row["unrealized_pnl"],
            row["unrealized_pnl_pct"],
        )
    console.print(table)
    console.print(f"Cash: {portfolio.cash}")


def main() -> None:
    """Run the Typer application."""

    app()
