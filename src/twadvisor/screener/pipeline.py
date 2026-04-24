"""Two-stage market screener pipeline."""

from __future__ import annotations

import inspect
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from twadvisor.fetchers.base import BaseFetcher, FetcherError, SymbolNotFoundError
from twadvisor.fetchers.twse import TwseFetcher
from twadvisor.screener.base import Candidate, RankedRecommendation, ScreenResult
from twadvisor.screener.daytrade import DaytradeScreener
from twadvisor.screener.prompts import build_rank_prompt
from twadvisor.screener.swing import SwingScreener
from twadvisor.screener.universe import is_etf, name_from_record, symbol_from_record, to_decimal, to_int
from twadvisor.settings import ScreenerSettings

LIQUID_FALLBACK_SYMBOLS = (
    "2330",
    "2317",
    "2454",
    "2308",
    "2382",
    "2303",
    "3231",
    "3037",
    "3711",
    "2357",
    "2345",
    "2881",
    "2882",
    "2603",
    "2618",
    "2412",
    "2891",
    "2886",
    "2327",
    "2379",
)


class ScreenerPipeline:
    """Run rule pre-screening and candidate ranking."""

    def __init__(
        self,
        fetcher: BaseFetcher,
        twse_fetcher: TwseFetcher,
        analyzer: object | None,
        config: ScreenerSettings,
    ) -> None:
        self.fetcher = fetcher
        self.twse_fetcher = twse_fetcher
        self.analyzer = analyzer
        self.config = config

    async def run_daytrade(
        self,
        top_n: int = 5,
        exclude_etf: bool = True,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        exclude_symbols: set[str] | None = None,
    ) -> ScreenResult:
        """Run the day-trade screener."""

        started = time.perf_counter()
        today = date.today()
        attention, disposition, eligible = await self._twse_lists(today)
        info = self._fetch_stock_info()
        preferred_symbols = self._daytrade_symbols(info, eligible, exclude_etf, top_n)
        rows = await self._fetch_market_rows(today, preferred_symbols)
        candidates = self._build_candidates(rows, info, "daytrade", attention, disposition, eligible)
        if exclude_etf:
            candidates = [item for item in candidates if not is_etf(item.symbol, item.name, info.get(item.symbol))]
        if exclude_symbols:
            candidates = [item for item in candidates if item.symbol not in exclude_symbols]
        screener = DaytradeScreener(
            min_price=min_price or Decimal(str(self.config.daytrade_min_price)),
            max_price=max_price or Decimal(str(self.config.daytrade_max_price)),
            min_amplitude_pct=Decimal(str(self.config.daytrade_min_amplitude_pct)),
            min_turnover=Decimal(str(self.config.daytrade_min_turnover_million)) * Decimal("1000000"),
        )
        screened = screener.screen(candidates)[: self.config.daytrade_candidate_limit]
        result = await self._rank("daytrade", screened, top_n, len(candidates))
        result.elapsed_sec = round(time.perf_counter() - started, 3)
        return result

    async def run_swing(
        self,
        top_n: int = 5,
        foreign_consecutive_days: int = 3,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        exclude_symbols: set[str] | None = None,
    ) -> ScreenResult:
        """Run the swing screener."""

        started = time.perf_counter()
        today = date.today()
        attention, disposition, eligible = await self._twse_lists(today)
        info = self._fetch_stock_info()
        preferred_symbols = self._swing_symbols(info, top_n)
        rows = await self._fetch_market_rows(today, preferred_symbols)
        candidates = self._build_candidates(rows, info, "swing", attention, disposition, eligible)
        if exclude_symbols:
            candidates = [item for item in candidates if item.symbol not in exclude_symbols]
        coarse = sorted(candidates, key=lambda item: item.turnover, reverse=True)[: self.config.swing_candidate_limit]
        enriched = await self._enrich_swing(coarse, today, foreign_consecutive_days)
        screener = SwingScreener(
            min_price=min_price or Decimal(str(self.config.swing_min_price)),
            max_price=max_price or Decimal(str(self.config.swing_max_price)),
            min_volume_lots=self.config.swing_min_volume_lots,
            require_above_ma20=self.config.swing_require_above_ma20,
            min_foreign_net_lots=self.config.swing_min_foreign_net_lots,
        )
        screened = screener.screen(enriched, foreign_consecutive_days=foreign_consecutive_days)
        result = await self._rank("swing", screened, top_n, len(candidates))
        result.elapsed_sec = round(time.perf_counter() - started, 3)
        return result

    def _fetch_stock_info(self) -> dict[str, dict[str, Any]]:
        """Fetch stock metadata when the provider supports it."""

        if hasattr(self.fetcher, "get_stock_info"):
            return self.fetcher.get_stock_info()
        if hasattr(self.fetcher, "_request"):
            payload = self.fetcher._request(dataset="TaiwanStockInfo")
            return {symbol_from_record(row): row for row in payload.get("data", []) if symbol_from_record(row)}
        return {}

    async def _fetch_market_rows(self, dt: date, fallback_symbols: list[str]) -> list[dict[str, Any]]:
        """Fetch market rows, falling back to capped per-symbol quotes on restricted FinMind levels."""

        if hasattr(self.fetcher, "get_market_prices"):
            try:
                return self.fetcher.get_market_prices(dt)
            except (AttributeError, FetcherError):
                return await self._fetch_symbol_quote_rows(fallback_symbols)
        elif hasattr(self.fetcher, "_request"):
            try:
                payload = self.fetcher._request(dataset="TaiwanStockPrice", start_date=str(dt), end_date=str(dt))
                return payload.get("data", [])
            except FetcherError:
                return await self._fetch_symbol_quote_rows(fallback_symbols)
        return await self._fetch_symbol_quote_rows(fallback_symbols)

    async def _fetch_symbol_quote_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        """Build market-like rows from per-symbol quotes."""

        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                quote = await self.fetcher.get_quote(symbol)
            except (FetcherError, SymbolNotFoundError, ValueError):
                continue
            volume_shares = quote.volume * 1000
            rows.append(
                {
                    "stock_id": quote.symbol,
                    "stock_name": quote.name,
                    "close": quote.price,
                    "max": quote.high,
                    "min": quote.low,
                    "Trading_Volume": volume_shares,
                    "Trading_money": quote.price * Decimal(volume_shares),
                }
            )
        return rows

    def _daytrade_symbols(
        self,
        info: dict[str, dict[str, Any]],
        eligible: set[str],
        exclude_etf: bool,
        top_n: int,
    ) -> list[str]:
        """Pick a quota-safe fallback universe for day-trade scans."""

        limit = min(max(top_n * 10, 20), self.config.daytrade_candidate_limit)
        symbols = []
        ordered_symbols = list(LIQUID_FALLBACK_SYMBOLS) + sorted(eligible)
        for symbol in ordered_symbols:
            if symbol in symbols or symbol not in eligible:
                continue
            record = info.get(symbol, {})
            name = name_from_record(record, symbol)
            if exclude_etf and is_etf(symbol, name, record):
                continue
            symbols.append(symbol)
            if len(symbols) >= limit:
                break
        return symbols

    def _swing_symbols(self, info: dict[str, dict[str, Any]], top_n: int) -> list[str]:
        """Pick a quota-safe fallback universe for swing scans."""

        limit = min(max(top_n * 8, 20), self.config.swing_candidate_limit)
        symbols = []
        for symbol, record in sorted(info.items()):
            if str(record.get("type", "")).lower() not in {"twse", "tpex"}:
                continue
            if is_etf(symbol, name_from_record(record, symbol), record):
                continue
            symbols.append(symbol)
            if len(symbols) >= limit:
                break
        return symbols

    async def _twse_lists(self, dt: date) -> tuple[set[str], set[str], set[str]]:
        attention = await self.twse_fetcher.get_attention_stocks(dt)
        disposition = await self.twse_fetcher.get_disposition_stocks(dt)
        eligible = await self.twse_fetcher.get_day_trade_eligible(dt)
        return attention, disposition, eligible

    def _build_candidates(
        self,
        rows: list[dict[str, Any]],
        info: dict[str, dict[str, Any]],
        source: str,
        attention: set[str],
        disposition: set[str],
        eligible: set[str],
    ) -> list[Candidate]:
        candidates = []
        for row in rows:
            symbol = symbol_from_record(row)
            if not symbol:
                continue
            close = to_decimal(row.get("close"))
            high = to_decimal(row.get("max") or row.get("high"))
            low = to_decimal(row.get("min") or row.get("low"))
            volume_shares = to_int(row.get("Trading_Volume") or row.get("volume"))
            volume_lots = volume_shares // 1000 if volume_shares > 1000 else volume_shares
            turnover = to_decimal(row.get("Trading_money"), close * Decimal(volume_shares))
            base = close if close > 0 else Decimal("1")
            amplitude_pct = ((high - low) / base * Decimal("100")).quantize(Decimal("0.01")) if high >= low else Decimal("0")
            record_info = info.get(symbol, {})
            name = name_from_record(record_info or row, symbol)
            candidates.append(
                Candidate(
                    symbol=symbol,
                    name=name,
                    close=close,
                    volume=volume_lots,
                    turnover=turnover,
                    amplitude_pct=amplitude_pct,
                    is_daytrade_eligible=symbol in eligible,
                    is_attention=symbol in attention,
                    is_disposition=symbol in disposition,
                    source=source,
                )
            )
        return candidates

    async def _enrich_swing(self, candidates: list[Candidate], today: date, foreign_days: int) -> list[Candidate]:
        enriched = []
        start = today - timedelta(days=45)
        for candidate in candidates:
            ma20: Decimal | None = None
            above_ma20: bool | None = None
            foreign_net = 0
            trust_net = 0
            try:
                frame = await self.fetcher.get_kline(candidate.symbol, start, today)
                frame = frame.sort_index()
                if not frame.empty and len(frame) >= 5:
                    closes = frame["close"].tail(20).astype(float)
                    if len(closes) >= 20:
                        ma20 = Decimal(str(closes.mean())).quantize(Decimal("0.01"))
                        above_ma20 = candidate.close > ma20
                    chip_dates = list(pd.to_datetime(frame.index).date)[-max(foreign_days, 5) :]
                    chips = [await self.fetcher.get_chip(candidate.symbol, chip_date) for chip_date in chip_dates]
                    foreign_net = sum(chip.foreign_net for chip in chips[-5:])
                    trust_net = sum(chip.trust_net for chip in chips[-5:])
                    if foreign_days > 0 and not all(chip.foreign_net > 0 for chip in chips[-foreign_days:]):
                        foreign_net = 0
            except Exception:
                pass
            enriched.append(
                candidate.model_copy(
                    update={
                        "ma20": ma20,
                        "above_ma20": above_ma20,
                        "foreign_net_5d": foreign_net,
                        "trust_net_5d": trust_net,
                    }
                )
            )
        return enriched

    async def _rank(self, source: str, candidates: list[Candidate], top_n: int, total: int) -> ScreenResult:
        if not candidates:
            return ScreenResult(
                source=source,
                market_view="目前沒有符合規則的候選股。",
                candidates_total=total,
                candidates_after_rules=0,
                recommendations=[],
                warnings=["無候選股"],
            )
        if self.analyzer and hasattr(self.analyzer, "rank_candidates"):
            system_prompt, user_prompt = build_rank_prompt(source, candidates, top_n)
            ranked = self.analyzer.rank_candidates(system_prompt, user_prompt, candidates, top_n)
            if inspect.isawaitable(ranked):
                return await ranked
            return ranked
        return self._fallback_rank(source, candidates, top_n, total)

    def _fallback_rank(self, source: str, candidates: list[Candidate], top_n: int, total: int) -> ScreenResult:
        recommendations = []
        for rank, candidate in enumerate(candidates[:top_n], start=1):
            low = (candidate.close * Decimal("0.99")).quantize(Decimal("0.01"))
            high = (candidate.close * Decimal("1.01")).quantize(Decimal("0.01"))
            recommendations.append(
                RankedRecommendation(
                    rank=rank,
                    symbol=candidate.symbol,
                    name=candidate.name,
                    confidence=min(candidate.score / Decimal("100"), Decimal("0.95")),
                    entry_price_low=low,
                    entry_price_high=high,
                    stop_loss=(candidate.close * Decimal("0.95")).quantize(Decimal("0.01")),
                    take_profit=(candidate.close * Decimal("1.08")).quantize(Decimal("0.01")),
                    reason=f"規則分數 {candidate.score}，量價與籌碼條件優於同批候選。",
                    rule_score=candidate.score,
                )
            )
        return ScreenResult(
            source=source,
            market_view="依規則初篩排序，AI 排名介面可接入後替換此結果。",
            candidates_total=total,
            candidates_after_rules=len(candidates),
            recommendations=recommendations,
            warnings=[],
        )
