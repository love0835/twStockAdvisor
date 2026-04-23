"""Simple paper trading primitives for backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from twadvisor.portfolio.cost import buy_cost, sell_proceeds

LOT_SIZE = 1000


@dataclass(slots=True)
class TradeFill:
    """A simulated trade fill."""

    trade_date: date
    symbol: str
    side: str
    qty: int
    price: Decimal
    cash_after: Decimal
    realized_pnl: Decimal = Decimal("0")


class PaperTrader:
    """Track a single-symbol paper trading account."""

    def __init__(self, symbol: str, initial_cash: Decimal) -> None:
        """Create a trader with starting cash."""

        self.symbol = symbol
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position_qty = 0
        self.entry_price: Decimal | None = None
        self.trades: list[TradeFill] = []

    def buy_max(self, trade_date: date, price: Decimal) -> TradeFill | None:
        """Buy the maximum number of whole lots allowed by available cash."""

        lot_cost = buy_cost(price, LOT_SIZE)
        if lot_cost <= 0:
            return None
        lots = int(self.cash // lot_cost)
        qty = lots * LOT_SIZE
        if qty <= 0:
            return None
        total_cost = buy_cost(price, qty)
        self.cash -= total_cost
        self.position_qty += qty
        self.entry_price = price
        fill = TradeFill(
            trade_date=trade_date,
            symbol=self.symbol,
            side="buy",
            qty=qty,
            price=price,
            cash_after=self.cash,
        )
        self.trades.append(fill)
        return fill

    def sell_all(self, trade_date: date, price: Decimal) -> TradeFill | None:
        """Close the full open position if one exists."""

        if self.position_qty <= 0 or self.entry_price is None:
            return None
        qty = self.position_qty
        proceeds = sell_proceeds(price, qty)
        realized_pnl = proceeds - buy_cost(self.entry_price, qty)
        self.cash += proceeds
        self.position_qty = 0
        self.entry_price = None
        fill = TradeFill(
            trade_date=trade_date,
            symbol=self.symbol,
            side="sell",
            qty=qty,
            price=price,
            cash_after=self.cash,
            realized_pnl=realized_pnl,
        )
        self.trades.append(fill)
        return fill

    def equity(self, mark_price: Decimal) -> Decimal:
        """Return mark-to-market account equity."""

        return self.cash + (mark_price * Decimal(self.position_qty))
