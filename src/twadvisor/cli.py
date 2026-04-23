"""Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from twadvisor.analyzer.factory import create_analyzer
from twadvisor.backtest.engine import BacktestEngine
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
from twadvisor.models import AnalysisRequest, Strategy
from twadvisor.notifier.factory import create_notifier
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.performance.metrics import cumulative_pnl, max_drawdown, sharpe_ratio, win_rate
from twadvisor.risk.validators import ValidationError, validate_recommendation
from twadvisor.scheduler.runner import AdvisorRunner
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository

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


@app.command()
def analyze(
    strategy: Strategy = typer.Option(..., "--strategy", case_sensitive=False),
    watchlist: str = typer.Option(..., "--watchlist", help="Comma-separated stock symbols"),
    storage: Path = typer.Option(Path(DEFAULT_PORTFOLIO_PATH), help="Portfolio storage path"),
) -> None:
    """Run a single AI analysis cycle."""

    _render_disclaimer()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    analyzer = create_analyzer(settings)
    repo = AdvisorRepository(settings.app.db_path)
    portfolio = PortfolioManager(storage_path=storage).load()

    watchlist_symbols = [symbol.strip() for symbol in watchlist.split(",") if symbol.strip()]
    all_symbols = sorted({*watchlist_symbols, *(position.symbol for position in portfolio.positions)})
    if not all_symbols:
        console.print("No symbols provided for analysis", style="red")
        raise typer.Exit(code=1)

    async def _collect_inputs() -> AnalysisRequest:
        quotes = await fetcher.get_quotes(all_symbols)
        today = date.today()
        start = today.replace(year=today.year - 1)
        indicators = {}
        chips = {}
        for symbol in all_symbols:
            frame = await fetcher.get_kline(symbol, start=start, end=today)
            indicators[symbol] = compute_indicators(frame, symbol)
            chips[symbol] = await fetcher.get_chip(symbol, today)
        return AnalysisRequest(
            strategy=strategy,
            portfolio=portfolio,
            quotes=quotes,
            indicators=indicators,
            chips=chips,
            watchlist=watchlist_symbols,
            risk_preference=settings.risk.risk_preference,
            max_position_pct=settings.risk.max_position_pct,
        )

    try:
        request = asyncio.run(_collect_inputs())
        response = asyncio.run(analyzer.analyze(request))
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        console.print(f"Analyze failed: {exc}", style="red")
        raise typer.Exit(code=1)

    table = Table(title="Recommendations")
    table.add_column("Symbol")
    table.add_column("Action")
    table.add_column("Qty")
    table.add_column("Price")
    table.add_column("Warnings")
    table.add_column("Reason")
    for recommendation in response.recommendations:
        quote = request.quotes[recommendation.symbol]
        try:
            warnings = validate_recommendation(
                recommendation,
                quote,
                portfolio,
                max_position_pct=settings.risk.max_position_pct,
            )
            warning_text = "; ".join(warnings) if warnings else "-"
        except ValidationError as exc:
            warning_text = f"blocked: {exc}"
        table.add_row(
            recommendation.symbol,
            recommendation.action.value,
            str(recommendation.qty),
            "-" if recommendation.price is None else str(recommendation.price),
            warning_text,
            recommendation.reason,
        )
    total_equity = repo.save_portfolio_snapshot(portfolio, request.quotes)
    repo.upsert_performance_daily(total_equity)
    repo.save_recommendations(response.recommendations, response.market_view, response.warnings)
    console.print(f"Market view: {response.market_view}")
    console.print(table)
    console.print(
        f"Tokens - prompt: {response.raw_prompt_tokens}, completion: {response.raw_completion_tokens}",
        style="cyan",
    )


@app.command()
def run(
    strategy: Strategy = typer.Option(..., "--strategy", case_sensitive=False),
    watchlist: str = typer.Option("", "--watchlist", help="Comma-separated stock symbols"),
    interval: int | None = typer.Option(None, "--interval", help="Override polling interval in seconds"),
    storage: Path = typer.Option(Path(DEFAULT_PORTFOLIO_PATH), help="Portfolio storage path"),
    max_ticks: int | None = typer.Option(None, "--max-ticks", hidden=True),
) -> None:
    """Start the advisor polling loop."""

    _render_disclaimer()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    analyzer = create_analyzer(settings)
    notifier = create_notifier(settings)
    portfolio_mgr = PortfolioManager(storage_path=storage)
    repo = AdvisorRepository(settings.app.db_path)
    watchlist_symbols = [symbol.strip() for symbol in watchlist.split(",") if symbol.strip()]
    runner = AdvisorRunner(settings, fetcher, analyzer, portfolio_mgr, notifier, repo)
    try:
        asyncio.run(runner.start(strategy, watchlist_symbols, interval_override=interval, max_ticks=max_ticks))
    except KeyboardInterrupt:
        console.print("Runner stopped", style="yellow")


@app.command()
def report(
    period: str = typer.Option("30d", "--period", help="Reporting window, e.g. 30d"),
) -> None:
    """Show stored performance metrics."""

    _render_disclaimer()
    settings = load_settings()
    repo = AdvisorRepository(settings.app.db_path)
    days = int(period[:-1]) if period.endswith("d") else int(period)
    rows = repo.list_performance_daily(limit=days)
    pnls = [Decimal(row.daily_pnl) for row in rows]
    equities = [Decimal(row.total_equity) for row in rows]
    returns = [row.daily_return for row in rows]

    table = Table(title=f"Performance Report ({period})")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Win Rate", f"{(win_rate(pnls) * Decimal('100')):.2f}%")
    table.add_row("Cumulative PnL", str(cumulative_pnl(pnls)))
    table.add_row("Sharpe", f"{sharpe_ratio(returns):.4f}")
    table.add_row("Max Drawdown", f"{(max_drawdown(equities) * Decimal('100')):.2f}%")
    table.add_row("Days", str(len(rows)))
    console.print(table)


@app.command()
def backtest(
    strategy: Strategy = typer.Option(..., "--strategy", case_sensitive=False),
    from_date: str = typer.Option(..., "--from", help="Backtest start date (YYYY-MM-DD)"),
    to_date: str = typer.Option(..., "--to", help="Backtest end date (YYYY-MM-DD)"),
    watchlist: str = typer.Option("", "--watchlist", help="Comma-separated symbols"),
    storage: Path = typer.Option(Path(DEFAULT_PORTFOLIO_PATH), help="Portfolio storage path"),
    initial_cash: str = typer.Option("1000000", "--initial-cash", help="Initial capital"),
) -> None:
    """Run a historical backtest and print summary metrics."""

    _render_disclaimer()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    portfolio = PortfolioManager(storage_path=storage).load()
    watchlist_symbols = [symbol.strip() for symbol in watchlist.split(",") if symbol.strip()]
    symbols = watchlist_symbols or [position.symbol for position in portfolio.positions] or ["2330"]
    engine = BacktestEngine(initial_cash=Decimal(initial_cash))
    try:
        start_dt = date.fromisoformat(from_date)
        end_dt = date.fromisoformat(to_date)
    except ValueError as exc:
        console.print(f"Backtest failed: {exc}", style="red")
        raise typer.Exit(code=1)

    try:
        result = asyncio.run(engine.run(fetcher, strategy, symbols, start_dt, end_dt))
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        console.print(f"Backtest failed: {exc}", style="red")
        raise typer.Exit(code=1)

    table = Table(title=f"Backtest Report ({strategy.value})")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Symbols", ", ".join(result.symbols))
    table.add_row("Period", f"{result.start.isoformat()} -> {result.end.isoformat()}")
    table.add_row("Initial Cash", f"{result.initial_cash:.4f}")
    table.add_row("Final Equity", f"{result.final_equity:.4f}")
    table.add_row("Total Return", f"{(result.total_return * Decimal('100')):.2f}%")
    table.add_row("Benchmark Return", f"{(result.benchmark_return * Decimal('100')):.2f}%")
    table.add_row("Win Rate", f"{(result.win_rate * Decimal('100')):.2f}%")
    table.add_row("Profit Factor", f"{result.profit_factor:.4f}")
    table.add_row("Sharpe", f"{result.sharpe:.4f}")
    table.add_row("Max Drawdown", f"{(result.max_drawdown * Decimal('100')):.2f}%")
    table.add_row("Closed Trades", str(result.trade_count))
    console.print(table)


def main() -> None:
    """Run the Typer application."""

    app()
