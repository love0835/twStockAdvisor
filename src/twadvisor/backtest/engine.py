"""Historical backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from twadvisor.backtest.paper_trader import LOT_SIZE, PaperTrader, TradeFill
from twadvisor.models import Strategy
from twadvisor.performance.metrics import max_drawdown, profit_factor, sharpe_ratio


@dataclass(slots=True)
class BacktestReport:
    """Aggregated backtest results."""

    strategy: Strategy
    symbols: list[str]
    start: date
    end: date
    initial_cash: Decimal
    final_equity: Decimal
    total_return: Decimal
    benchmark_return: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    sharpe: float
    max_drawdown: Decimal
    trade_count: int
    equity_curve: list[Decimal]
    daily_pnls: list[Decimal]
    trade_pnls: list[Decimal]
    trades: list[TradeFill]


class BacktestEngine:
    """Run deterministic technical-rule backtests on daily kline data."""

    def __init__(self, initial_cash: Decimal = Decimal("1000000")) -> None:
        """Create a backtest engine."""

        self.initial_cash = initial_cash

    async def run(
        self,
        fetcher,
        strategy: Strategy,
        symbols: list[str],
        start: date,
        end: date,
    ) -> BacktestReport:
        """Run a backtest for one or more symbols."""

        clean_symbols = [symbol for symbol in symbols if symbol]
        if not clean_symbols:
            raise ValueError("At least one symbol is required for backtest")

        allocation = self.initial_cash / Decimal(len(clean_symbols))
        equity_series: list[pd.Series] = []
        benchmark_final = Decimal("0")
        all_trades: list[TradeFill] = []
        all_trade_pnls: list[Decimal] = []

        for symbol in clean_symbols:
            frame = await fetcher.get_kline(symbol, start, end)
            prepared = self._prepare_frame(frame)
            if prepared.empty:
                continue
            trader = PaperTrader(symbol=symbol, initial_cash=allocation)
            self._simulate_symbol(strategy, trader, prepared)
            if trader.position_qty > 0:
                trader.sell_all(prepared.index[-1].date(), Decimal(str(prepared.iloc[-1]["close"])))

            series = prepared["equity"].copy()
            series.name = symbol
            equity_series.append(series)
            benchmark_final += self._benchmark_equity(allocation, prepared)
            all_trades.extend(trader.trades)
            all_trade_pnls.extend(fill.realized_pnl for fill in trader.trades if fill.side == "sell")

        combined_equity = pd.concat(equity_series, axis=1).sum(axis=1)
        if combined_equity.empty:
            raise ValueError("No usable kline data for backtest")
        equity_curve = [Decimal(str(value)).quantize(Decimal("0.0001")) for value in combined_equity.tolist()]
        daily_pnls = self._daily_pnls(equity_curve)
        final_equity = equity_curve[-1]
        total_return = ((final_equity - self.initial_cash) / self.initial_cash) if self.initial_cash else Decimal("0")
        benchmark_return = (
            (benchmark_final - self.initial_cash) / self.initial_cash if self.initial_cash else Decimal("0")
        )
        wins = sum(1 for pnl in all_trade_pnls if pnl > 0)
        trade_win_rate = Decimal("0")
        if all_trade_pnls:
            trade_win_rate = Decimal(wins) / Decimal(len(all_trade_pnls))
        daily_returns = [
            float((equity_curve[idx] - equity_curve[idx - 1]) / equity_curve[idx - 1])
            for idx in range(1, len(equity_curve))
            if equity_curve[idx - 1] != 0
        ]
        return BacktestReport(
            strategy=strategy,
            symbols=clean_symbols,
            start=start,
            end=end,
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            benchmark_return=benchmark_return,
            win_rate=trade_win_rate,
            profit_factor=profit_factor(all_trade_pnls),
            sharpe=sharpe_ratio(daily_returns),
            max_drawdown=max_drawdown(equity_curve),
            trade_count=len(all_trade_pnls),
            equity_curve=equity_curve,
            daily_pnls=daily_pnls,
            trade_pnls=all_trade_pnls,
            trades=all_trades,
        )

    def _prepare_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Normalize and augment a kline frame for signal generation."""

        prepared = frame.copy().sort_index()
        if prepared.index.has_duplicates:
            prepared = prepared[~prepared.index.duplicated(keep="last")]
        prepared["ma5"] = prepared["close"].rolling(5).mean()
        prepared["ma20"] = prepared["close"].rolling(20).mean()
        prepared["ma60"] = prepared["close"].rolling(60).mean()
        prepared["volume_ma5"] = prepared["volume"].rolling(5).mean()
        delta = prepared["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        prepared["rsi14"] = (100 - (100 / (1 + rs))).fillna(50)
        prepared["equity"] = Decimal("0")
        return prepared.dropna(subset=["ma5", "ma20"])

    def _simulate_symbol(self, strategy: Strategy, trader: PaperTrader, frame: pd.DataFrame) -> None:
        """Run the selected strategy on a single symbol."""

        if frame.empty:
            return
        prev_row = None
        for trade_date, row in frame.iterrows():
            price = Decimal(str(row["close"]))
            if trader.position_qty == 0:
                if self._should_buy(strategy, row, prev_row):
                    trader.buy_max(trade_date.date(), price)
            else:
                if self._should_sell(strategy, row, trader.entry_price):
                    trader.sell_all(trade_date.date(), price)
            frame.at[trade_date, "equity"] = trader.equity(price)
            prev_row = row

    def _should_buy(self, strategy: Strategy, row: pd.Series, prev_row: pd.Series | None) -> bool:
        """Return whether the current bar opens a long position."""

        close = float(row["close"])
        ma5 = float(row["ma5"])
        ma20 = float(row["ma20"])
        ma60 = float(row["ma60"]) if pd.notna(row.get("ma60")) else ma20
        rsi = float(row["rsi14"])
        volume = float(row["volume"])
        volume_ma5 = float(row["volume_ma5"]) if pd.notna(row["volume_ma5"]) else volume
        crossed_ma20 = prev_row is None or (
            float(prev_row["close"]) <= float(prev_row["ma20"]) and close > ma20
        )

        if strategy == Strategy.DAYTRADE:
            return close > ma5 and rsi < 70 and volume >= volume_ma5
        if strategy == Strategy.POSITION:
            return crossed_ma20 and ma20 > ma60 and rsi < 72
        if strategy == Strategy.LONGTERM:
            return close > ma60 and ma20 >= ma60 and rsi < 68
        if strategy == Strategy.DIVIDEND:
            return close < ma20 * 0.97 and rsi < 40
        return crossed_ma20 and ma5 >= ma20 and rsi < 70

    def _should_sell(self, strategy: Strategy, row: pd.Series, entry_price: Decimal | None) -> bool:
        """Return whether the current bar closes a long position."""

        close = Decimal(str(row["close"]))
        ma5 = Decimal(str(row["ma5"]))
        ma20 = Decimal(str(row["ma20"]))
        ma60 = Decimal(str(row["ma60"])) if pd.notna(row.get("ma60")) else ma20
        rsi = float(row["rsi14"])
        stop_reference = entry_price or close

        if strategy == Strategy.DAYTRADE:
            return close < ma5 or rsi > 74
        if strategy == Strategy.POSITION:
            return close < ma20 or ma20 < ma60 or close <= stop_reference * Decimal("0.90")
        if strategy == Strategy.LONGTERM:
            return close < ma60 or ma20 < ma60
        if strategy == Strategy.DIVIDEND:
            return close >= ma20 or rsi > 60
        return close < ma20 or rsi > 76 or close <= stop_reference * Decimal("0.92")

    def _benchmark_equity(self, allocation: Decimal, frame: pd.DataFrame) -> Decimal:
        """Return final equity for a buy-and-hold benchmark."""

        entry_price = Decimal(str(frame.iloc[0]["close"]))
        exit_price = Decimal(str(frame.iloc[-1]["close"]))
        if entry_price <= 0:
            return allocation
        lot_cost = LOT_SIZE * entry_price
        qty = int(allocation // lot_cost) * LOT_SIZE
        if qty <= 0:
            return allocation
        trader = PaperTrader(symbol="benchmark", initial_cash=allocation)
        trader.buy_max(frame.index[0].date(), entry_price)
        trader.sell_all(frame.index[-1].date(), exit_price)
        return trader.cash

    def _daily_pnls(self, equity_curve: list[Decimal]) -> list[Decimal]:
        """Return day-over-day pnl values."""

        if not equity_curve:
            return []
        pnls = [Decimal("0")]
        for idx in range(1, len(equity_curve)):
            pnls.append((equity_curve[idx] - equity_curve[idx - 1]).quantize(Decimal("0.0001")))
        return pnls
