"""API routes for the TwStockAdvisor Web UI."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from twadvisor.analyzer.factory import create_analyzer
from twadvisor.backtest.engine import BacktestEngine
from twadvisor.fetchers.base import FetcherError, SymbolNotFoundError
from twadvisor.fetchers.factory import create_fetcher
from twadvisor.indicators.technical import compute_indicators
from twadvisor.models import AnalysisRequest, Strategy
from twadvisor.performance.metrics import cumulative_pnl, max_drawdown, sharpe_ratio, win_rate
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.risk.validators import ValidationError, validate_recommendation
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository
from twadvisor.web.schemas import AnalyzePayload, BacktestPayload, PortfolioImportPayload

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness endpoint."""

    return {"status": "ok"}


@router.get("/bootstrap")
async def bootstrap() -> dict[str, object]:
    """Bootstrap payload for the frontend shell."""

    settings = load_settings()
    return {
        "app_name": "TwStockAdvisor",
        "provider": settings.ai.provider,
        "sections": ["portfolio", "analyze", "report", "backtest"],
    }


@router.get("/portfolio")
async def get_portfolio(storage_path: str = Query("data/portfolio.json")) -> dict[str, object]:
    """Return current portfolio rows and summary stats."""

    manager = PortfolioManager(storage_path=storage_path)
    portfolio = manager.load()
    quotes = {}
    if portfolio.positions:
        settings = load_settings()
        fetcher = create_fetcher(settings)
        symbols = [position.symbol for position in portfolio.positions]
        try:
            quotes = await fetcher.get_quotes(symbols)
        except (FetcherError, SymbolNotFoundError):
            quotes = {}

    return {
        "cash": str(portfolio.cash),
        "position_count": len(portfolio.positions),
        "total_cost": str(portfolio.total_cost()),
        "updated_at": portfolio.updated_at.isoformat(sep=" ", timespec="seconds"),
        "rows": manager.build_rows(quotes),
    }


@router.post("/portfolio/import")
async def import_portfolio(payload: PortfolioImportPayload) -> dict[str, object]:
    """Import portfolio positions from a CSV file."""

    manager = PortfolioManager(storage_path=payload.storage_path)
    cash_value = None if payload.cash is None or payload.cash == "" else Decimal(payload.cash)
    try:
        portfolio = manager.import_csv(payload.csv_path, cash=cash_value)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "imported": len(portfolio.positions),
        "cash": str(portfolio.cash),
        "storage_path": payload.storage_path,
    }


@router.post("/analyze")
async def analyze(payload: AnalyzePayload) -> dict[str, object]:
    """Run a single analysis cycle and return structured recommendations."""

    settings = load_settings()
    fetcher = create_fetcher(settings)
    try:
        analyzer = create_analyzer(settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = AdvisorRepository(settings.app.db_path)
    portfolio = PortfolioManager(storage_path=payload.storage_path).load()
    analysis_symbols = payload.watchlist or [position.symbol for position in portfolio.positions]
    all_symbols = sorted({*analysis_symbols, *(position.symbol for position in portfolio.positions)})
    if not all_symbols:
        raise HTTPException(status_code=400, detail="No symbols provided for analysis")

    async def _collect_inputs() -> AnalysisRequest:
        quotes = await fetcher.get_quotes(all_symbols)
        today = date.today()
        start = today.replace(year=today.year - 1)
        indicators = {}
        chips = {}
        for symbol in analysis_symbols:
            frame = await fetcher.get_kline(symbol, start=start, end=today)
            indicators[symbol] = compute_indicators(frame, symbol)
            chips[symbol] = await fetcher.get_chip(symbol, today)
        return AnalysisRequest(
            strategy=Strategy(payload.strategy),
            portfolio=portfolio,
            quotes=quotes,
            indicators=indicators,
            chips=chips,
            watchlist=analysis_symbols,
            risk_preference=settings.risk.risk_preference,
            max_position_pct=settings.risk.max_position_pct,
        )

    try:
        request = await _collect_inputs()
        response = await analyzer.analyze(request)
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = []
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
        rows.append(
            {
                "symbol": recommendation.symbol,
                "action": recommendation.action.value,
                "qty": recommendation.qty,
                "price": "-" if recommendation.price is None else str(recommendation.price),
                "warnings": warning_text,
                "reason": recommendation.reason,
            }
        )

    total_equity = repo.save_portfolio_snapshot(portfolio, request.quotes)
    repo.upsert_performance_daily(total_equity)
    repo.save_recommendations(response.recommendations, response.market_view, response.warnings)

    return {
        "market_view": response.market_view,
        "recommendations": rows,
        "warnings": response.warnings,
        "prompt_tokens": response.raw_prompt_tokens,
        "completion_tokens": response.raw_completion_tokens,
    }


@router.get("/report")
async def report(period: str = Query("30d")) -> dict[str, object]:
    """Return stored performance metrics."""

    settings = load_settings()
    repo = AdvisorRepository(settings.app.db_path)
    days = int(period[:-1]) if period.endswith("d") else int(period)
    rows = repo.list_performance_daily(limit=days)
    pnls = [Decimal(row.daily_pnl) for row in rows]
    equities = [Decimal(row.total_equity) for row in rows]
    returns = [row.daily_return for row in rows]

    return {
        "period": period,
        "win_rate": f"{(win_rate(pnls) * Decimal('100')):.2f}%",
        "cumulative_pnl": str(cumulative_pnl(pnls)),
        "sharpe": f"{sharpe_ratio(returns):.4f}",
        "max_drawdown": f"{(max_drawdown(equities) * Decimal('100')):.2f}%",
        "days": len(rows),
    }


@router.post("/backtest")
async def backtest(payload: BacktestPayload) -> dict[str, object]:
    """Run a historical backtest and return summary metrics."""

    settings = load_settings()
    fetcher = create_fetcher(settings)
    portfolio = PortfolioManager(storage_path=payload.storage_path).load()
    symbols = payload.symbols or [position.symbol for position in portfolio.positions] or ["2330"]
    engine = BacktestEngine(initial_cash=Decimal(payload.initial_cash))

    try:
        result = await engine.run(
            fetcher,
            Strategy(payload.strategy),
            symbols,
            date.fromisoformat(payload.from_date),
            date.fromisoformat(payload.to_date),
        )
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "symbols": result.symbols,
        "initial_cash": f"{result.initial_cash:.4f}",
        "final_equity": f"{result.final_equity:.4f}",
        "total_return": f"{(result.total_return * Decimal('100')):.2f}%",
        "benchmark_return": f"{(result.benchmark_return * Decimal('100')):.2f}%",
        "win_rate": f"{(result.win_rate * Decimal('100')):.2f}%",
        "profit_factor": f"{result.profit_factor:.4f}",
        "sharpe": f"{result.sharpe:.4f}",
        "max_drawdown": f"{(result.max_drawdown * Decimal('100')):.2f}%",
        "trade_count": result.trade_count,
    }
