"""API routes for the TwStockAdvisor Web UI."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from twadvisor.analyzer.api_keys import ai_provider_options, resolve_ai_provider
from twadvisor.analyzer.factory import create_analyzer
from twadvisor.analyzer.token_usage import reset_token_usage_user, set_token_usage_user
from twadvisor.auth import AuthService, CurrentUser, SESSION_COOKIE_NAME
from twadvisor.backtest.engine import BacktestEngine
from twadvisor.constants import DEFAULT_PORTFOLIO_PATH
from twadvisor.fetchers.base import FetcherError, SymbolNotFoundError
from twadvisor.fetchers.factory import create_fetcher
from twadvisor.fetchers.twse import TwseFetcher
from twadvisor.indicators.technical import compute_indicators
from twadvisor.models import AnalysisRequest, AnalysisResponse, ChipData, Portfolio, Recommendation, Strategy
from twadvisor.performance.metrics import cumulative_pnl, max_drawdown, sharpe_ratio, win_rate
from twadvisor.portfolio.db_manager import DbPortfolioManager
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.risk.validators import ValidationError, validate_recommendation
from twadvisor.screener.pipeline import ScreenerPipeline
from twadvisor.settings import load_settings
from twadvisor.storage.repo import AdvisorRepository
from twadvisor.web.schemas import (
    AnalyzePayload,
    BacktestPayload,
    CreateInitialAdminPayload,
    LoginPayload,
    PasswordChangePayload,
    PortfolioCashPayload,
    PortfolioCommissionPayload,
    PortfolioDeletePayload,
    PortfolioImportPayload,
    PortfolioPositionPayload,
    PortfolioQuotePayload,
    ScreenerDecisionPayload,
    ScreenerPayload,
    UserCreatePayload,
)

router = APIRouter()
_ANALYZE_INPUT_CACHE: dict[tuple[str, str, str], tuple[datetime, object, object]] = {}
_ANALYZE_CACHE_TTL = timedelta(minutes=10)
_SCREENER_CACHE: dict[tuple[str, str], tuple[datetime, dict[str, object]]] = {}
_WARNING_TRANSLATIONS = {
    "Recommendation symbol does not match quote": "AI 回傳的股票代號與行情資料不一致",
    "Recommendation price is outside the daily limit range": "建議下單價超出今日漲跌停範圍",
    "Insufficient cash for buy recommendation": "買進建議所需現金不足",
    "Position size exceeds configured maximum percentage": "單一持股比重超過設定上限",
    "BUY recommendation must satisfy stop_loss < price < take_profit": "買進建議必須符合：停損價 < 下單價 < 停利價",
    "Insufficient holdings for sell recommendation": "賣出建議超過目前持股數量",
    "Quantity is not a round lot multiple of 1000": "股數不是整張 1000 股的倍數",
    "Odd-lot quantity detected": "偵測到零股交易數量",
}


def _auth_service() -> AuthService:
    settings = load_settings()
    service = AuthService(settings.app.db_path)
    service.create_initial_admin_from_env()
    return service


def _current_user(request: Request) -> CurrentUser:
    user = _auth_service().get_user_by_session(request.cookies.get(SESSION_COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _admin_user(user: CurrentUser = Depends(_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    return user


@router.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness endpoint."""

    return {"status": "ok"}


@router.get("/bootstrap")
async def bootstrap() -> dict[str, object]:
    """Bootstrap payload for the frontend shell."""

    settings = load_settings()
    provider = resolve_ai_provider(settings)
    return {
        "app_name": "TwStockAdvisor",
        "provider": provider,
        "ai": {
            "provider": provider,
            "providers": ai_provider_options(settings),
            "keys_path": settings.ai.keys_path,
        },
        "sections": ["portfolio", "analyze", "report", "backtest"],
    }


@router.get("/auth/bootstrap")
async def auth_bootstrap() -> dict[str, object]:
    """Return whether first-run admin setup is needed."""

    service = _auth_service()
    return {"needs_admin": service.user_count() == 0}


@router.post("/auth/initial-admin")
async def create_initial_admin(payload: CreateInitialAdminPayload, response: Response) -> dict[str, object]:
    """Create the first admin account when no users exist."""

    service = _auth_service()
    if service.user_count() > 0:
        raise HTTPException(status_code=409, detail="Admin already initialized")
    try:
        user = service.create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = load_settings()
    if settings.app.db_path == "./data/twadvisor.db" and PortfolioManager(storage_path=DEFAULT_PORTFOLIO_PATH).storage_path.exists():
        DbPortfolioManager(settings.app.db_path, user.id).import_from_json(DEFAULT_PORTFOLIO_PATH)
    _set_session_cookie(service, response, user)
    return {"user": user.__dict__}


@router.post("/auth/login")
async def login(payload: LoginPayload, response: Response) -> dict[str, object]:
    """Log in a family member."""

    service = _auth_service()
    user = service.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _set_session_cookie(service, response, user)
    return {"user": user.__dict__}


@router.post("/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Log out the current session."""

    _auth_service().delete_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/auth/me")
async def me(user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Return current user."""

    return {"user": user.__dict__}


@router.post("/auth/password")
async def change_password(payload: PasswordChangePayload, user: CurrentUser = Depends(_current_user)) -> dict[str, str]:
    """Change the current user's password."""

    try:
        _auth_service().change_password(user.id, payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/admin/users")
async def admin_users(user: CurrentUser = Depends(_admin_user)) -> dict[str, object]:
    """List family users."""

    return {"users": _auth_service().list_users()}


@router.post("/admin/users")
async def admin_create_user(payload: UserCreatePayload, user: CurrentUser = Depends(_admin_user)) -> dict[str, object]:
    """Create a family user."""

    try:
        created = _auth_service().create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": created.__dict__}


@router.get("/admin/usage")
async def admin_usage(user: CurrentUser = Depends(_admin_user)) -> dict[str, object]:
    """Return token usage grouped by user."""

    repo = AdvisorRepository(load_settings().app.db_path)
    users = {entry["id"]: entry for entry in _auth_service().list_users()}
    rows = []
    for row in repo.list_token_usage_by_user():
        usage_user = users.get(row["user_id"])
        rows.append(
            {
                **row,
                "username": "-" if usage_user is None else usage_user["username"],
                "display_name": "-" if usage_user is None else usage_user["display_name"],
            }
        )
    return {"rows": rows}


def _set_session_cookie(service: AuthService, response: Response, user: CurrentUser) -> None:
    token, expires_at = service.create_session(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,
    )


@router.get("/portfolio")
async def get_portfolio(user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Return current portfolio rows and summary stats."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    portfolio = manager.load()

    return {
        "cash": str(portfolio.cash),
        "commission_discount": str(manager.get_commission_discount()),
        "position_count": len(portfolio.positions),
        "total_cost": str(portfolio.total_cost()),
        "updated_at": portfolio.updated_at.isoformat(sep=" ", timespec="seconds"),
        "rows": manager.build_rows({}),
    }


@router.post("/portfolio/import")
async def import_portfolio(payload: PortfolioImportPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Import portfolio positions from a CSV file."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
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


@router.post("/portfolio/cash")
async def update_portfolio_cash(payload: PortfolioCashPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Update portfolio cash from the Web UI."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    try:
        portfolio = manager.set_cash(Decimal(payload.cash))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _portfolio_payload(manager, portfolio)


@router.post("/portfolio/commission")
async def update_portfolio_commission(
    payload: PortfolioCommissionPayload,
    user: CurrentUser = Depends(_current_user),
) -> dict[str, object]:
    """Update commission discount from the Web UI."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    try:
        portfolio = manager.set_commission_discount(Decimal(payload.commission_discount))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _portfolio_payload(manager, portfolio)


@router.post("/portfolio/positions")
async def add_portfolio_position(payload: PortfolioPositionPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Add a portfolio position from the Web UI."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    try:
        portfolio = manager.add_position(payload.symbol, payload.qty, Decimal(payload.avg_cost))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _portfolio_payload(manager, portfolio)


@router.put("/portfolio/positions/{symbol}")
async def update_portfolio_position(
    symbol: str,
    payload: PortfolioPositionPayload,
    user: CurrentUser = Depends(_current_user),
) -> dict[str, object]:
    """Update an existing portfolio position from the Web UI."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    try:
        portfolio = manager.update_position(symbol, payload.qty, Decimal(payload.avg_cost))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Position not found: {symbol}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _portfolio_payload(manager, portfolio)


@router.delete("/portfolio/positions/{symbol}")
async def delete_portfolio_position(
    symbol: str,
    payload: PortfolioDeletePayload,
    user: CurrentUser = Depends(_current_user),
) -> dict[str, object]:
    """Delete an existing portfolio position from the Web UI."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    try:
        portfolio = manager.delete_position(symbol)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Position not found: {symbol}") from exc
    return _portfolio_payload(manager, portfolio)


@router.post("/portfolio/quotes")
async def update_portfolio_quotes(payload: PortfolioQuotePayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Fetch quotes for portfolio positions and return calculated PnL rows."""

    manager = DbPortfolioManager(load_settings().app.db_path, user.id)
    portfolio = manager.load()
    settings = load_settings()
    fetcher = create_fetcher(settings)
    quotes = {}
    failed_symbols: set[str] = set()
    for position in portfolio.positions:
        try:
            quotes[position.symbol] = await fetcher.get_quote(position.symbol)
        except (FetcherError, SymbolNotFoundError, ValueError):
            failed_symbols.add(position.symbol)
    return {
        **_portfolio_payload(manager, portfolio, quotes=quotes, discount=payload.commission_discount),
        "failed_symbols": sorted(failed_symbols),
        "rows": manager.build_rows(quotes, discount=payload.commission_discount, failed_symbols=failed_symbols),
    }


def _portfolio_payload(
    manager: DbPortfolioManager,
    portfolio: Portfolio,
    *,
    quotes: dict | None = None,
    discount: float | None = None,
) -> dict[str, object]:
    return {
        "cash": str(portfolio.cash),
        "commission_discount": str(manager.get_commission_discount()),
        "position_count": len(portfolio.positions),
        "total_cost": str(portfolio.total_cost()),
        "updated_at": portfolio.updated_at.isoformat(sep=" ", timespec="seconds"),
        "rows": manager.build_rows(quotes or {}, discount=discount),
    }


@router.post("/analyze")
async def analyze(payload: AnalyzePayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Run a single analysis cycle and return structured recommendations."""

    settings = load_settings()
    fetcher = create_fetcher(settings)
    provider = _requested_ai_provider(settings, payload.provider)
    try:
        analyzer = create_analyzer(settings, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = AdvisorRepository(settings.app.db_path)
    portfolio = DbPortfolioManager(settings.app.db_path, user.id).load()
    ai_portfolio = _select_ai_portfolio(
        portfolio,
        include_portfolio=payload.include_portfolio,
        holding_symbols=payload.holding_symbols,
    )
    analysis_symbols = list(payload.watchlist)
    if payload.include_portfolio:
        analysis_symbols.extend(position.symbol for position in ai_portfolio.positions)
    analysis_symbols = sorted(set(analysis_symbols))
    all_symbols = sorted(set(analysis_symbols) | {position.symbol for position in ai_portfolio.positions})
    if not all_symbols:
        raise HTTPException(status_code=400, detail="No symbols provided for analysis")
    input_warnings: list[str] = []

    async def _collect_inputs() -> AnalysisRequest:
        quotes = await fetcher.get_quotes(all_symbols)
        today = date.today()
        start = today.replace(year=today.year - 1)
        indicators = {}
        chips = {}
        for symbol in analysis_symbols:
            cache_key = (symbol, str(start), str(today))
            cached = _ANALYZE_INPUT_CACHE.get(cache_key)
            if cached and datetime.utcnow() - cached[0] < _ANALYZE_CACHE_TTL:
                indicators[symbol], chips[symbol] = cached[1], cached[2]
                continue
            frame = await fetcher.get_kline(symbol, start=start, end=today)
            indicator = compute_indicators(frame, symbol)
            try:
                chip = await fetcher.get_chip(symbol, today)
            except SymbolNotFoundError:
                chip = _empty_chip(symbol, today)
                input_warnings.append(f"{symbol} 缺少籌碼資料，已用 0 值繼續分析")
            indicators[symbol] = indicator
            chips[symbol] = chip
            _ANALYZE_INPUT_CACHE[cache_key] = (datetime.utcnow(), indicator, chip)
        return AnalysisRequest(
            strategy=Strategy(payload.strategy),
            portfolio=ai_portfolio,
            quotes=quotes,
            indicators=indicators,
            chips=chips,
            watchlist=analysis_symbols,
            risk_preference=settings.risk.risk_preference,
            max_position_pct=settings.risk.max_position_pct,
        )

    try:
        request = await _collect_inputs()
        usage_token = set_token_usage_user(user.id)
        try:
            response = await analyzer.analyze(request)
        finally:
            reset_token_usage_user(usage_token)
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc

    response.warnings = [*input_warnings, *response.warnings]
    total_equity = repo.save_portfolio_snapshot(portfolio, request.quotes, user_id=user.id)
    repo.upsert_performance_daily(total_equity)
    repo.save_recommendations(response.recommendations, response.market_view, response.warnings, user_id=user.id)
    return _serialize_analysis_response(response, request, portfolio, settings.risk.max_position_pct, ai_provider=provider)


@router.post("/screener/decision")
async def screener_decision(payload: ScreenerDecisionPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Ask AI for a trading decision from already-scanned candidates without refetching market data."""

    if not payload.candidates:
        raise HTTPException(status_code=400, detail="No scanner candidates provided")
    settings = load_settings()
    provider = _requested_ai_provider(settings, payload.provider)
    try:
        analyzer = create_analyzer(settings, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    portfolio = DbPortfolioManager(settings.app.db_path, user.id).load()
    ai_portfolio = _select_ai_portfolio(
        portfolio,
        include_portfolio=payload.include_portfolio,
        holding_symbols=payload.holding_symbols,
    )
    today = date.today()
    watchlist = [candidate.symbol for candidate in payload.candidates]
    quotes = {}
    indicators = {}
    chips = {}
    warnings = ["已使用掃描結果做 AI 決策，未重新呼叫 FinMind 行情 API。"]
    for candidate in payload.candidates:
        entry_low, entry_high = _parse_entry_range(candidate.entry_range)
        price = entry_low or entry_high or Decimal("0")
        quotes[candidate.symbol] = _scanner_quote(candidate.symbol, _scanner_candidate_note(candidate), price, today)
        indicators[candidate.symbol] = _scanner_indicator(candidate.symbol, candidate)
        chips[candidate.symbol] = _empty_chip(candidate.symbol, today)

    request = AnalysisRequest(
        strategy=Strategy(payload.strategy),
        portfolio=ai_portfolio,
        quotes=quotes,
        indicators=indicators,
        chips=chips,
        watchlist=watchlist,
        risk_preference=settings.risk.risk_preference,
        max_position_pct=settings.risk.max_position_pct,
    )
    try:
        usage_token = set_token_usage_user(user.id)
        try:
            response = await analyzer.analyze(request)
        finally:
            reset_token_usage_user(usage_token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc

    response.warnings = [*warnings, *response.warnings]
    return _serialize_analysis_response(response, request, portfolio, settings.risk.max_position_pct, ai_provider=provider)


def _requested_ai_provider(settings, provider: str | None) -> str:
    try:
        return resolve_ai_provider(settings, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _select_ai_portfolio(
    portfolio: Portfolio,
    *,
    include_portfolio: bool,
    holding_symbols: list[str],
) -> Portfolio:
    if not include_portfolio:
        return Portfolio(cash=portfolio.cash, positions=[], updated_at=portfolio.updated_at)
    selected = {symbol.strip() for symbol in holding_symbols if symbol.strip()}
    positions = [position for position in portfolio.positions if not selected or position.symbol in selected]
    return Portfolio(cash=portfolio.cash, positions=positions, updated_at=portfolio.updated_at)


def _empty_chip(symbol: str, dt: date) -> ChipData:
    return ChipData(
        symbol=symbol,
        foreign_net=0,
        trust_net=0,
        dealer_net=0,
        margin_balance=0,
        short_balance=0,
        date=dt,
    )


def _serialize_analysis_response(
    response: AnalysisResponse,
    request: AnalysisRequest,
    portfolio: Portfolio,
    max_position_pct: float,
    *,
    ai_provider: str,
) -> dict[str, object]:
    rows = []
    for recommendation in response.recommendations:
        quote = request.quotes.get(recommendation.symbol)
        if quote is None:
            response.warnings.append(f"AI returned unknown symbol: {recommendation.symbol}")
            continue
        try:
            warnings = validate_recommendation(
                recommendation,
                quote,
                portfolio,
                max_position_pct=max_position_pct,
            )
            warning_text = _localize_warning_text("; ".join(warnings)) if warnings else "-"
        except ValidationError as exc:
            warning_text = _localize_warning_text(f"blocked: {exc}")
        rows.append(_serialize_recommendation_row(recommendation, warning_text))
    return {
        "provider": ai_provider,
        "market_view": response.market_view,
        "recommendations": rows,
        "warnings": [_localize_warning_text(warning) for warning in response.warnings],
        "prompt_tokens": response.raw_prompt_tokens,
        "completion_tokens": response.raw_completion_tokens,
    }


def _serialize_recommendation_row(recommendation: Recommendation, warning_text: str) -> dict[str, object]:
    return {
        "symbol": recommendation.symbol,
        "action": recommendation.action.value,
        "qty": recommendation.qty,
        "lots": _format_lots(recommendation.qty),
        "order_type": recommendation.order_type.value,
        "price": "-" if recommendation.price is None else str(recommendation.price),
        "stop_loss": "-" if recommendation.stop_loss is None else str(recommendation.stop_loss),
        "take_profit": "-" if recommendation.take_profit is None else str(recommendation.take_profit),
        "warnings": warning_text,
        "reason": recommendation.reason,
    }


def _parse_entry_range(value: str) -> tuple[Decimal | None, Decimal | None]:
    normalized = str(value or "").replace("～", "~").replace("—", "~").replace("-", "~")
    parts = [part.strip() for part in normalized.split("~")]
    decimals = []
    for part in parts[:2]:
        try:
            decimals.append(Decimal(part))
        except Exception:
            decimals.append(None)
    while len(decimals) < 2:
        decimals.append(None)
    return decimals[0], decimals[1]


def _scanner_quote(symbol: str, name: str, price: Decimal, dt: date):
    from twadvisor.fetchers.limits import limit_down_from_prev_close, limit_up_from_prev_close
    from twadvisor.models import Quote

    return Quote(
        symbol=symbol,
        name=name,
        price=price,
        open=price,
        high=price,
        low=price,
        prev_close=price,
        volume=0,
        bid=price,
        ask=price,
        limit_up=limit_up_from_prev_close(price),
        limit_down=limit_down_from_prev_close(price),
        timestamp=datetime.combine(dt, datetime.min.time()),
        is_suspended=False,
    )


def _scanner_candidate_note(candidate) -> str:
    name = candidate.name or candidate.symbol
    return (
        f"{name}; scanner_entry_range={candidate.entry_range}; "
        f"scanner_stop_loss={candidate.stop_loss}; scanner_take_profit={candidate.take_profit}; "
        f"scanner_rule_score={candidate.rule_score}; scanner_reason={candidate.reason}"
    )


def _scanner_indicator(symbol: str, candidate) -> object:
    from twadvisor.models import TechnicalIndicators

    score = _decimal_or_none(candidate.rule_score)
    return TechnicalIndicators(symbol=symbol, ma5=None, ma20=None, ma60=None, rsi14=score)


def _decimal_or_none(value: str) -> Decimal | None:
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _localize_warning_text(text: str) -> str:
    if not text or text == "-":
        return text
    if text.startswith("blocked: "):
        reason = text.removeprefix("blocked: ")
        return f"封鎖：{_WARNING_TRANSLATIONS.get(reason, reason)}"
    parts = [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]
    if len(parts) > 1:
        return "；".join(_WARNING_TRANSLATIONS.get(part, part) for part in parts)
    return _WARNING_TRANSLATIONS.get(text, text)


def _format_lots(qty: int) -> str:
    if qty == 0:
        return "0"
    lots = Decimal(qty) / Decimal("1000")
    return f"{lots.normalize()} 張" if qty % 1000 == 0 else f"{lots.normalize()} 張（零股 {qty} 股）"


@router.post("/screener/daytrade")
async def screener_daytrade(payload: ScreenerPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Run a market-wide day-trade scan."""

    return await _run_screener("daytrade", payload, user)


@router.post("/screener/swing")
async def screener_swing(payload: ScreenerPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Run a market-wide swing scan."""

    return await _run_screener("swing", payload, user)


async def _run_screener(source: str, payload: ScreenerPayload, user: CurrentUser) -> dict[str, object]:
    settings = load_settings()
    cache_ttl = timedelta(minutes=settings.screener.cache_ttl_minutes)
    cache_key = (
        source,
        json.dumps(payload.model_dump(), sort_keys=True, ensure_ascii=False) + f":{date.today().isoformat()}",
    )
    cached = _SCREENER_CACHE.get(cache_key)
    if cached and datetime.utcnow() - cached[0] < cache_ttl:
        result = dict(cached[1])
        result["elapsed_sec"] = 0.0
        return result

    started = time.perf_counter()
    fetcher = create_fetcher(settings)
    portfolio = DbPortfolioManager(settings.app.db_path, user.id).load()
    exclude_symbols = {position.symbol for position in portfolio.positions} if payload.exclude_holdings else set()
    pipeline = ScreenerPipeline(fetcher, TwseFetcher(), None, settings.screener)

    try:
        if source == "daytrade":
            result = await pipeline.run_daytrade(
                top_n=payload.top_n,
                exclude_etf=payload.exclude_etf,
                min_price=None if payload.min_price is None else Decimal(str(payload.min_price)),
                max_price=None if payload.max_price is None else Decimal(str(payload.max_price)),
                exclude_symbols=exclude_symbols,
            )
        else:
            result = await pipeline.run_swing(
                top_n=payload.top_n,
                foreign_consecutive_days=payload.foreign_consecutive_days,
                min_price=None if payload.min_price is None else Decimal(str(payload.min_price)),
                max_price=None if payload.max_price is None else Decimal(str(payload.max_price)),
                exclude_symbols=exclude_symbols,
            )
    except (FetcherError, SymbolNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = _serialize_screen_result(result)
    response["elapsed_sec"] = round(time.perf_counter() - started, 3)
    response["warnings"] = [*response.get("warnings", []), "市場掃描僅使用行情資料與規則排序，未呼叫 AI。"]
    _SCREENER_CACHE[cache_key] = (datetime.utcnow(), response)
    return response


def _serialize_screen_result(result) -> dict[str, object]:
    rows = []
    for recommendation in result.recommendations:
        entry_low = "-" if recommendation.entry_price_low is None else str(recommendation.entry_price_low)
        entry_high = "-" if recommendation.entry_price_high is None else str(recommendation.entry_price_high)
        rows.append(
            {
                "rank": recommendation.rank,
                "symbol": recommendation.symbol,
                "name": recommendation.name,
                "action": recommendation.action,
                "confidence": f"{(recommendation.confidence * Decimal('100')):.0f}%",
                "entry_range": f"{entry_low} ~ {entry_high}",
                "stop_loss": "-" if recommendation.stop_loss is None else str(recommendation.stop_loss),
                "take_profit": "-" if recommendation.take_profit is None else str(recommendation.take_profit),
                "reason": recommendation.reason,
                "rule_score": str(recommendation.rule_score),
                "warnings": "；".join(recommendation.warnings) if recommendation.warnings else "-",
            }
        )
    return {
        "source": result.source,
        "market_view": result.market_view,
        "candidates_total": result.candidates_total,
        "candidates_after_rules": result.candidates_after_rules,
        "recommendations": rows,
        "warnings": result.warnings,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "elapsed_sec": result.elapsed_sec,
    }


@router.get("/report")
async def report(period: str = Query("30d"), user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
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
async def backtest(payload: BacktestPayload, user: CurrentUser = Depends(_current_user)) -> dict[str, object]:
    """Run a historical backtest and return summary metrics."""

    settings = load_settings()
    fetcher = create_fetcher(settings)
    portfolio = DbPortfolioManager(settings.app.db_path, user.id).load()
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
