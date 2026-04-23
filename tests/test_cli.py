"""Phase 1 CLI tests."""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal

import pandas as pd
from typer.testing import CliRunner

from twadvisor.cli import app
from twadvisor.constants import DEFAULT_CONFIG_PATH
from twadvisor.models import AnalysisResponse, Quote, Recommendation, Strategy
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


def test_portfolio_import_command_creates_storage(tmp_path: Path) -> None:
    """Portfolio import should persist data to the selected storage path."""

    storage = tmp_path / "portfolio.json"
    result = runner.invoke(
        app,
        [
            "portfolio",
            "import",
            "--file",
            "E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv",
            "--cash",
            "200000",
            "--storage",
            str(storage),
        ],
    )
    assert result.exit_code == 0
    assert storage.exists()
    assert "Imported 2 positions" in result.stdout


def test_portfolio_show_command_renders_rows(tmp_path: Path, monkeypatch: object) -> None:
    """Portfolio show should print imported rows and pnl columns."""

    storage = tmp_path / "portfolio.json"
    runner.invoke(
        app,
        [
            "portfolio",
            "import",
            "--file",
            "E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv",
            "--cash",
            "200000",
            "--storage",
            str(storage),
        ],
    )

    quote_2330 = Quote(
        symbol="2330",
        name="TSMC",
        price="600",
        open="590",
        high="605",
        low="588",
        prev_close="595",
        volume=1000,
        bid="599",
        ask="600",
        limit_up="654",
        limit_down="536",
        timestamp="2026-04-24T10:00:00",
    )
    quote_2317 = Quote(
        symbol="2317",
        name="HonHai",
        price="190",
        open="188",
        high="191",
        low="187",
        prev_close="189",
        volume=1000,
        bid="189",
        ask="190",
        limit_up="207",
        limit_down="171",
        timestamp="2026-04-24T10:00:00",
    )

    class StubFetcher:
        async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
            return {"2330": quote_2330, "2317": quote_2317}

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    result = runner.invoke(app, ["portfolio", "show", "--storage", str(storage)])
    assert result.exit_code == 0
    assert "Portfolio" in result.stdout
    assert "2330" in result.stdout
    assert "2317" in result.stdout


def test_analyze_command_renders_recommendations(tmp_path: Path, monkeypatch: object) -> None:
    """Analyze command should print structured recommendations."""

    storage = tmp_path / "portfolio.json"
    runner.invoke(
        app,
        [
            "portfolio",
            "import",
            "--file",
            "E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv",
            "--cash",
            "200000",
            "--storage",
            str(storage),
        ],
    )

    quote_2330 = Quote(
        symbol="2330",
        name="TSMC",
        price="600",
        open="590",
        high="605",
        low="588",
        prev_close="595",
        volume=1000,
        bid="599",
        ask="600",
        limit_up="654",
        limit_down="536",
        timestamp="2026-04-24T10:00:00",
    )
    quote_2317 = Quote(
        symbol="2317",
        name="HonHai",
        price="190",
        open="188",
        high="191",
        low="187",
        prev_close="189",
        volume=1000,
        bid="189",
        ask="190",
        limit_up="207",
        limit_down="171",
        timestamp="2026-04-24T10:00:00",
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
            return {"2330": quote_2330, "2317": quote_2317}

        async def get_kline(self, symbol: str, start: object, end: object) -> pd.DataFrame:
            return frame

        async def get_chip(self, symbol: str, dt: object):
            from twadvisor.models import ChipData

            return ChipData(symbol=symbol, foreign_net=0, trust_net=0, dealer_net=0, margin_balance=0, short_balance=0, date=pd.Timestamp("2026-04-24").date())

    class StubAnalyzer:
        async def analyze(self, req):
            return AnalysisResponse(
                recommendations=[
                    Recommendation(
                        symbol="2317",
                        action="buy",
                        qty=1000,
                        order_type="limit",
                        price="190",
                        stop_loss="182",
                        take_profit="205",
                        reason="量價轉強",
                        confidence=0.7,
                        strategy=Strategy.SWING,
                        generated_at="2026-04-24T10:00:00",
                    )
                ],
                market_view="偏多震盪",
                warnings=[],
                raw_prompt_tokens=100,
                raw_completion_tokens=50,
            )

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    monkeypatch.setattr("twadvisor.cli.create_analyzer", lambda settings: StubAnalyzer())
    result = runner.invoke(
        app,
        [
            "analyze",
            "--strategy",
            "swing",
            "--watchlist",
            "2317",
            "--storage",
            str(storage),
        ],
    )
    assert result.exit_code == 0
    assert "Recommendations" in result.stdout
    assert "偏多震盪" in result.stdout
    assert "2317" in result.stdout


def test_run_command_executes_single_tick(tmp_path: Path, monkeypatch: object) -> None:
    """Run command should execute a bounded runner for tests."""

    storage = tmp_path / "portfolio.json"
    runner.invoke(
        app,
        [
            "portfolio",
            "import",
            "--file",
            "E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv",
            "--cash",
            "200000",
            "--storage",
            str(storage),
        ],
    )

    class StubRunner:
        def __init__(self, *args, **kwargs) -> None:
            self.called = True

        async def start(self, strategy, watchlist, interval_override=None, max_ticks=None):
            return None

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: object())
    monkeypatch.setattr("twadvisor.cli.create_analyzer", lambda settings: object())
    monkeypatch.setattr("twadvisor.cli.create_notifier", lambda settings: object())
    monkeypatch.setattr("twadvisor.cli.AdvisorRunner", StubRunner)

    result = runner.invoke(
        app,
        [
            "run",
            "--strategy",
            "swing",
            "--watchlist",
            "2330",
            "--storage",
            str(storage),
            "--max-ticks",
            "1",
        ],
    )
    assert result.exit_code == 0


def test_report_command_renders_metrics(tmp_path: Path, monkeypatch: object) -> None:
    """Report command should render stored metrics."""

    monkeypatch.setenv("PYTHONUTF8", "1")
    from twadvisor.storage.repo import AdvisorRepository

    db_path = tmp_path / "advisor.db"
    repo = AdvisorRepository(str(db_path))
    repo.record_token_usage("claude", "model", 10, 5)
    repo.upsert_performance_daily(Decimal("100000"))

    default_config = tmp_path / "default.toml"
    default_config.write_text(
        f"[app]\ndb_path = \"{str(db_path).replace(chr(92), '/')}\"\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("twadvisor.cli.load_settings", lambda: load_settings(default_path=default_config, user_path=tmp_path / "missing.toml"))
    result = runner.invoke(app, ["report", "--period", "30d"])
    assert result.exit_code == 0
    assert "Performance Report" in result.stdout


def test_backtest_command_renders_report(tmp_path: Path, monkeypatch: object) -> None:
    """Backtest command should render summary metrics."""

    storage = tmp_path / "portfolio.json"
    runner.invoke(
        app,
        [
            "portfolio",
            "import",
            "--file",
            "E:\\TwStockAdvisor\\tests\\fixtures\\portfolio_sample.csv",
            "--cash",
            "200000",
            "--storage",
            str(storage),
        ],
    )

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
        async def get_kline(self, symbol: str, start: object, end: object) -> pd.DataFrame:
            return frame

    monkeypatch.setattr("twadvisor.cli.create_fetcher", lambda settings: StubFetcher())
    result = runner.invoke(
        app,
        [
            "backtest",
            "--strategy",
            "swing",
            "--from",
            "2025-01-01",
            "--to",
            "2025-05-10",
            "--watchlist",
            "2330",
            "--storage",
            str(storage),
        ],
    )
    assert result.exit_code == 0
    assert "Backtest Report" in result.stdout
    assert "Benchmark Return" in result.stdout
