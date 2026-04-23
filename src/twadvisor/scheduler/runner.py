"""Scheduler runner for repeated advisor ticks."""

from __future__ import annotations

import asyncio
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from twadvisor.fetchers.base import FetcherError, SymbolNotFoundError
from twadvisor.fetchers.market_calendar import MarketCalendar
from twadvisor.indicators.technical import compute_indicators
from twadvisor.models import AnalysisRequest, Strategy
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.risk.validators import ValidationError, validate_recommendation


class AdvisorRunner:
    """Coordinate periodic data collection, analysis, and notifications."""

    def __init__(self, settings, fetcher, analyzer, portfolio_mgr, notifier) -> None:
        """Create a runner instance."""

        self.settings = settings
        self.fetcher = fetcher
        self.analyzer = analyzer
        self.portfolio_mgr = portfolio_mgr
        self.notifier = notifier
        self.scheduler = AsyncIOScheduler()
        self.market_calendar = MarketCalendar()
        self._ticks_run = 0

    async def tick(self, strategy: Strategy, watchlist: list[str]) -> None:
        """Execute a single advisor cycle."""

        now = datetime.now()
        if self.market_calendar.current_session(now) == "closed":
            return

        portfolio = self.portfolio_mgr.load()
        symbols = sorted({*watchlist, *(position.symbol for position in portfolio.positions)})
        if not symbols:
            return

        quotes = await self.fetcher.get_quotes(symbols)
        today = date.today()
        start = today.replace(year=today.year - 1)
        indicators = {}
        chips = {}
        for symbol in symbols:
            frame = await self.fetcher.get_kline(symbol, start=start, end=today)
            indicators[symbol] = compute_indicators(frame, symbol)
            chips[symbol] = await self.fetcher.get_chip(symbol, today)

        request = AnalysisRequest(
            strategy=strategy,
            portfolio=portfolio,
            quotes=quotes,
            indicators=indicators,
            chips=chips,
            watchlist=watchlist,
            risk_preference=self.settings.risk.risk_preference,
            max_position_pct=self.settings.risk.max_position_pct,
        )
        response = await self.analyzer.analyze(request)
        valid_recs = []
        for rec in response.recommendations:
            try:
                validate_recommendation(
                    rec,
                    quotes[rec.symbol],
                    portfolio,
                    max_position_pct=self.settings.risk.max_position_pct,
                )
            except ValidationError:
                continue
            valid_recs.append(rec)
        if valid_recs:
            await self.notifier.notify(valid_recs, response.market_view)
        self._ticks_run += 1

    def _resolve_interval(self, strategy: Strategy) -> int:
        """Resolve polling interval from strategy."""

        if strategy == Strategy.DAYTRADE:
            return self.settings.market.poll_interval_daytrade
        if strategy == Strategy.SWING:
            return self.settings.market.poll_interval_swing
        return self.settings.market.poll_interval_longterm

    async def start(self, strategy: Strategy, watchlist: list[str], interval_override: int | None = None, max_ticks: int | None = None) -> None:
        """Start the repeating scheduler until cancelled or max ticks reached."""

        interval = interval_override or self._resolve_interval(strategy)
        done = asyncio.Event()
        attempts = 0

        async def _job() -> None:
            nonlocal attempts
            attempts += 1
            try:
                await self.tick(strategy, watchlist)
            except (FetcherError, SymbolNotFoundError, ValueError):
                pass
            if max_ticks is not None and attempts >= max_ticks:
                done.set()

        self.scheduler.add_job(_job, "interval", seconds=interval, max_instances=1)
        self.scheduler.start()
        try:
            await _job()
            if max_ticks is not None and attempts >= max_ticks:
                return
            await done.wait() if max_ticks is not None else asyncio.Future()
        finally:
            self.scheduler.shutdown(wait=False)
