"""Database-backed per-user portfolio manager."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import csv

from sqlalchemy import select

from twadvisor.models import Portfolio, Position, Quote
from twadvisor.portfolio.manager import PortfolioManager
from twadvisor.portfolio.pnl import unrealized_cost_basis, unrealized_pnl, unrealized_pnl_pct
from twadvisor.storage.db import create_session_factory
from twadvisor.storage.models_orm import Base, PortfolioAccountRecord, PortfolioPositionRecord


class DbPortfolioManager:
    """Manage a single user's portfolio in SQLite."""

    def __init__(self, db_path: str, user_id: int) -> None:
        self.user_id = user_id
        self.session_factory = create_session_factory(db_path)
        Base.metadata.create_all(self.session_factory.kw["bind"])

    def load(self) -> Portfolio:
        """Load the user's portfolio."""

        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            records = session.scalars(
                select(PortfolioPositionRecord)
                .where(PortfolioPositionRecord.user_id == self.user_id)
                .order_by(PortfolioPositionRecord.symbol.asc())
            )
            positions = [
                Position(
                    symbol=record.symbol,
                    qty=record.qty,
                    avg_cost=Decimal(record.avg_cost),
                    account_type=record.account_type,
                    opened_at=date.fromisoformat(record.opened_at),
                )
                for record in records
            ]
            updated_at = datetime.fromisoformat(account.updated_at)
            return Portfolio(cash=Decimal(account.cash), positions=positions, updated_at=updated_at)

    def get_commission_discount(self) -> Decimal:
        """Return the user's commission discount."""

        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            return Decimal(account.commission_discount)

    def set_cash(self, cash: Decimal) -> Portfolio:
        """Update cash."""

        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            account.cash = str(cash)
            account.updated_at = datetime.utcnow().isoformat()
            session.commit()
        return self.load()

    def set_commission_discount(self, discount: Decimal) -> Portfolio:
        """Update commission discount."""

        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            account.commission_discount = str(discount)
            account.updated_at = datetime.utcnow().isoformat()
            session.commit()
        return self.load()

    def import_from_json(self, storage_path: str) -> Portfolio:
        """Import a JSON portfolio snapshot into this user's DB portfolio."""

        source = PortfolioManager(storage_path=storage_path).load()
        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            account.cash = str(source.cash)
            account.updated_at = datetime.utcnow().isoformat()
            existing = {
                record.symbol: record
                for record in session.scalars(
                    select(PortfolioPositionRecord).where(PortfolioPositionRecord.user_id == self.user_id)
                )
            }
            seen = set()
            for position in source.positions:
                seen.add(position.symbol)
                record = existing.get(position.symbol)
                if record is None:
                    session.add(_position_record(self.user_id, position))
                else:
                    record.qty = position.qty
                    record.avg_cost = str(position.avg_cost)
                    record.account_type = position.account_type
                    record.opened_at = position.opened_at.isoformat()
                    record.updated_at = datetime.utcnow().isoformat()
            for symbol, record in existing.items():
                if symbol not in seen:
                    session.delete(record)
            session.commit()
        return self.load()

    def import_csv(self, file_path: str, cash: Decimal | None = None) -> Portfolio:
        """Import positions from a CSV file into this user's DB portfolio."""

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
        with self.session_factory() as session:
            account = _ensure_account(session, self.user_id)
            if cash is not None:
                account.cash = str(cash)
            account.updated_at = datetime.utcnow().isoformat()
            session.query(PortfolioPositionRecord).filter(PortfolioPositionRecord.user_id == self.user_id).delete()
            for position in positions:
                session.add(_position_record(self.user_id, position))
            session.commit()
        return self.load()

    def add_position(self, symbol: str, qty: int, avg_cost: Decimal) -> Portfolio:
        """Add a new position."""

        normalized = symbol.strip()
        with self.session_factory() as session:
            if _find_position(session, self.user_id, normalized):
                raise ValueError(f"Position already exists: {normalized}")
            session.add(
                PortfolioPositionRecord(
                    user_id=self.user_id,
                    symbol=normalized,
                    qty=qty,
                    avg_cost=str(avg_cost),
                    account_type="cash",
                    opened_at=date.today().isoformat(),
                    updated_at=datetime.utcnow().isoformat(),
                )
            )
            _touch_account(session, self.user_id)
            session.commit()
        return self.load()

    def update_position(self, symbol: str, qty: int, avg_cost: Decimal) -> Portfolio:
        """Update an existing position."""

        normalized = symbol.strip()
        with self.session_factory() as session:
            record = _find_position(session, self.user_id, normalized)
            if record is None:
                raise KeyError(normalized)
            record.qty = qty
            record.avg_cost = str(avg_cost)
            record.updated_at = datetime.utcnow().isoformat()
            _touch_account(session, self.user_id)
            session.commit()
        return self.load()

    def delete_position(self, symbol: str) -> Portfolio:
        """Delete an existing position."""

        normalized = symbol.strip()
        with self.session_factory() as session:
            record = _find_position(session, self.user_id, normalized)
            if record is None:
                raise KeyError(normalized)
            session.delete(record)
            _touch_account(session, self.user_id)
            session.commit()
        return self.load()

    def build_rows(
        self,
        quotes: dict[str, Quote],
        *,
        discount: float | None = None,
        failed_symbols: set[str] | None = None,
    ) -> list[dict[str, str]]:
        """Build display rows for the user's portfolio."""

        portfolio = self.load()
        failed_symbols = failed_symbols or set()
        effective_discount = discount
        if effective_discount is None:
            effective_discount = float(self.get_commission_discount())
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
                pnl_raw = unrealized_pnl(position, quote, discount=effective_discount)
                pnl_pct_raw = unrealized_pnl_pct(position, quote, discount=effective_discount) * Decimal("100")
                pnl_value = f"{pnl_raw:.2f}"
                pnl_pct = f"{pnl_pct_raw:.2f}%"
            rows.append(
                {
                    "symbol": position.symbol,
                    "qty": str(position.qty),
                    "avg_cost": str(position.avg_cost),
                    "cost_basis": f"{unrealized_cost_basis(position, discount=effective_discount):.2f}",
                    "current_price": current_price,
                    "unrealized_pnl": pnl_value,
                    "unrealized_pnl_pct": pnl_pct,
                }
            )
        return rows


def _ensure_account(session, user_id: int) -> PortfolioAccountRecord:
    account = session.scalar(select(PortfolioAccountRecord).where(PortfolioAccountRecord.user_id == user_id))
    if account is None:
        account = PortfolioAccountRecord(user_id=user_id, cash="0", commission_discount="0.28", updated_at=datetime.utcnow().isoformat())
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def _touch_account(session, user_id: int) -> None:
    account = _ensure_account(session, user_id)
    account.updated_at = datetime.utcnow().isoformat()


def _find_position(session, user_id: int, symbol: str) -> PortfolioPositionRecord | None:
    return session.scalar(
        select(PortfolioPositionRecord).where(
            PortfolioPositionRecord.user_id == user_id,
            PortfolioPositionRecord.symbol == symbol,
        )
    )


def _position_record(user_id: int, position: Position) -> PortfolioPositionRecord:
    return PortfolioPositionRecord(
        user_id=user_id,
        symbol=position.symbol,
        qty=position.qty,
        avg_cost=str(position.avg_cost),
        account_type=position.account_type,
        opened_at=position.opened_at.isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )
