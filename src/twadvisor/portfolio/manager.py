"""Portfolio persistence and presentation helpers."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from twadvisor.constants import DEFAULT_PORTFOLIO_PATH
from twadvisor.models import Portfolio, Position, Quote
from twadvisor.portfolio.pnl import unrealized_cost_basis, unrealized_pnl, unrealized_pnl_pct


class PortfolioManager:
    """Manage persisted portfolio snapshots."""

    def __init__(self, storage_path: str | Path = DEFAULT_PORTFOLIO_PATH) -> None:
        """Create a manager for the given storage path."""

        self.storage_path = Path(storage_path)

    def load(self) -> Portfolio:
        """Load the current portfolio snapshot or return an empty one."""

        if not self.storage_path.exists():
            return Portfolio(cash=Decimal("0"), positions=[], updated_at=datetime.now())
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        return Portfolio.model_validate(payload)

    def save(self, portfolio: Portfolio) -> None:
        """Persist a portfolio snapshot."""

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            portfolio.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def import_csv(self, file_path: str | Path, cash: Decimal | None = None) -> Portfolio:
        """Import portfolio positions from a CSV file and persist them."""

        positions: list[Position] = []
        with Path(file_path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                positions.append(
                    Position(
                        symbol=row["symbol"].strip(),
                        qty=int(row["qty"]),
                        avg_cost=Decimal(row["avg_cost"]),
                        account_type=row.get("account_type", "cash") or "cash",
                        opened_at=date.fromisoformat(row["opened_at"]),
                    )
                )

        portfolio = Portfolio(
            cash=cash if cash is not None else self.load().cash,
            positions=positions,
            updated_at=datetime.now(),
        )
        self.save(portfolio)
        return portfolio

    def set_cash(self, cash: Decimal) -> Portfolio:
        """Update cash on the current portfolio and persist it."""

        portfolio = self.load()
        updated = Portfolio(cash=cash, positions=portfolio.positions, updated_at=datetime.now())
        self.save(updated)
        return updated

    def upsert_position(self, symbol: str, qty: int, avg_cost: Decimal) -> Portfolio:
        """Add or update a position and persist the portfolio."""

        portfolio = self.load()
        normalized_symbol = symbol.strip()
        positions = [
            position.model_copy(update={"qty": qty, "avg_cost": avg_cost})
            if position.symbol == normalized_symbol
            else position
            for position in portfolio.positions
        ]
        if not any(position.symbol == normalized_symbol for position in portfolio.positions):
            positions.append(
                Position(
                    symbol=normalized_symbol,
                    qty=qty,
                    avg_cost=avg_cost,
                    account_type="cash",
                    opened_at=date.today(),
                )
            )
        updated = Portfolio(cash=portfolio.cash, positions=positions, updated_at=datetime.now())
        self.save(updated)
        return updated

    def add_position(self, symbol: str, qty: int, avg_cost: Decimal) -> Portfolio:
        """Add a new position and reject duplicate symbols."""

        portfolio = self.load()
        normalized_symbol = symbol.strip()
        if any(position.symbol == normalized_symbol for position in portfolio.positions):
            raise ValueError(f"Position already exists: {normalized_symbol}")
        updated = Portfolio(
            cash=portfolio.cash,
            positions=[
                *portfolio.positions,
                Position(
                    symbol=normalized_symbol,
                    qty=qty,
                    avg_cost=avg_cost,
                    account_type="cash",
                    opened_at=date.today(),
                ),
            ],
            updated_at=datetime.now(),
        )
        self.save(updated)
        return updated

    def update_position(self, symbol: str, qty: int, avg_cost: Decimal) -> Portfolio:
        """Update an existing position and persist the portfolio."""

        portfolio = self.load()
        normalized_symbol = symbol.strip()
        found = False
        positions = []
        for position in portfolio.positions:
            if position.symbol == normalized_symbol:
                found = True
                positions.append(position.model_copy(update={"qty": qty, "avg_cost": avg_cost}))
            else:
                positions.append(position)
        if not found:
            raise KeyError(normalized_symbol)
        updated = Portfolio(cash=portfolio.cash, positions=positions, updated_at=datetime.now())
        self.save(updated)
        return updated

    def delete_position(self, symbol: str) -> Portfolio:
        """Delete an existing position and persist the portfolio."""

        portfolio = self.load()
        normalized_symbol = symbol.strip()
        positions = [position for position in portfolio.positions if position.symbol != normalized_symbol]
        if len(positions) == len(portfolio.positions):
            raise KeyError(normalized_symbol)
        updated = Portfolio(cash=portfolio.cash, positions=positions, updated_at=datetime.now())
        self.save(updated)
        return updated

    def build_rows(
        self,
        quotes: dict[str, Quote],
        *,
        discount: float | None = None,
        failed_symbols: set[str] | None = None,
    ) -> list[dict[str, str]]:
        """Build display rows for the current portfolio."""

        portfolio = self.load()
        failed_symbols = failed_symbols or set()
        rows: list[dict[str, str]] = []
        for position in portfolio.positions:
            quote = quotes.get(position.symbol)
            if position.symbol in failed_symbols:
                current_price = "更新失敗"
                pnl_value = "更新失敗"
                pnl_pct = "更新失敗"
            elif quote is None:
                current_price = "尚未更新"
                pnl_value = "尚未更新"
                pnl_pct = "尚未更新"
            else:
                current_price = str(quote.price)
                pnl_raw = unrealized_pnl(position, quote, discount=discount)
                pnl_pct_raw = unrealized_pnl_pct(position, quote, discount=discount) * Decimal("100")
                pnl_value = f"{pnl_raw:.2f}"
                pnl_pct = f"{pnl_pct_raw:.2f}%"

            rows.append(
                {
                    "symbol": position.symbol,
                    "qty": str(position.qty),
                    "avg_cost": str(position.avg_cost),
                    "cost_basis": f"{unrealized_cost_basis(position, discount=discount):.2f}",
                    "current_price": current_price,
                    "unrealized_pnl": pnl_value,
                    "unrealized_pnl_pct": pnl_pct,
                }
            )
        return rows
