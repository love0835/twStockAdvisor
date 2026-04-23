"""Console notifier."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from twadvisor.models import Recommendation
from twadvisor.notifier.base import BaseNotifier


class ConsoleNotifier(BaseNotifier):
    """Render recommendations to the terminal."""

    def __init__(self, console: Console | None = None) -> None:
        """Create a console notifier."""

        self.console = console or Console()

    async def notify(self, recs: list[Recommendation], market_view: str) -> None:
        """Print recommendations as a rich table."""

        table = Table(title="Advisor Tick")
        table.add_column("Symbol")
        table.add_column("Action")
        table.add_column("Qty")
        table.add_column("Price")
        table.add_column("Reason")
        for rec in recs:
            table.add_row(
                rec.symbol,
                rec.action.value,
                str(rec.qty),
                "-" if rec.price is None else str(rec.price),
                rec.reason,
            )
        self.console.print(f"Market view: {market_view}")
        self.console.print(table)
