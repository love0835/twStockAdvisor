"""Portfolio persistence and presentation helpers."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from twadvisor.constants import DEFAULT_PORTFOLIO_PATH
from twadvisor.models import Portfolio, Position, Quote
from twadvisor.portfolio.pnl import unrealized_pnl, unrealized_pnl_pct


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

    def build_rows(self, quotes: dict[str, Quote]) -> list[dict[str, str]]:
        """Build display rows for the current portfolio."""

        portfolio = self.load()
        rows: list[dict[str, str]] = []
        for position in portfolio.positions:
            quote = quotes.get(position.symbol)
            if quote is None:
                current_price = "-"
                pnl_value = "-"
                pnl_pct = "-"
            else:
                current_price = str(quote.price)
                pnl_raw = unrealized_pnl(position, quote)
                pnl_pct_raw = unrealized_pnl_pct(position, quote) * Decimal("100")
                pnl_value = f"{pnl_raw:.2f}"
                pnl_pct = f"{pnl_pct_raw:.2f}%"

            rows.append(
                {
                    "symbol": position.symbol,
                    "qty": str(position.qty),
                    "avg_cost": str(position.avg_cost),
                    "current_price": current_price,
                    "unrealized_pnl": pnl_value,
                    "unrealized_pnl_pct": pnl_pct,
                }
            )
        return rows
