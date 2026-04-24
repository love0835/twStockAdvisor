"""Repository helpers for persisted advisor data."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text

from twadvisor.models import Portfolio, Quote, Recommendation
from twadvisor.storage.db import create_session_factory
from twadvisor.storage.models_orm import (
    Base,
    PerformanceDailyRecord,
    PortfolioSnapshotRecord,
    RecommendationRecord,
    TokenUsageRecord,
)


class AdvisorRepository:
    """Repository for SQLite-backed advisor data."""

    def __init__(self, db_path: str) -> None:
        """Create a repository bound to the configured database."""

        self.session_factory = create_session_factory(db_path)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        self._ensure_legacy_columns()

    def _ensure_legacy_columns(self) -> None:
        """Add nullable user columns to existing SQLite tables when upgrading."""

        engine = self.session_factory.kw["bind"]
        with engine.begin() as connection:
            for table in ("recommendations", "portfolio_snapshots", "token_usage"):
                columns = [row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))]
                if columns and "user_id" not in columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))

    def record_token_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        user_id: int | None = None,
    ) -> None:
        """Persist token usage."""

        with self.session_factory() as session:
            session.add(
                TokenUsageRecord(
                    user_id=user_id,
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    created_at=datetime.utcnow().isoformat(),
                )
            )
            session.commit()

    def save_recommendations(
        self,
        recs: list[Recommendation],
        market_view: str,
        warnings: list[str],
        *,
        user_id: int | None = None,
    ) -> None:
        """Persist validated recommendations."""

        with self.session_factory() as session:
            for rec in recs:
                session.add(
                    RecommendationRecord(
                        user_id=user_id,
                        symbol=rec.symbol,
                        action=rec.action.value,
                        qty=rec.qty,
                        price=None if rec.price is None else str(rec.price),
                        reason=rec.reason,
                        confidence=rec.confidence,
                        strategy=rec.strategy.value,
                        market_view=market_view,
                        warnings="; ".join(warnings),
                        created_at=rec.generated_at.isoformat(),
                    )
                )
            session.commit()

    def save_portfolio_snapshot(
        self,
        portfolio: Portfolio,
        quotes: dict[str, Quote],
        *,
        user_id: int | None = None,
    ) -> Decimal:
        """Persist a portfolio snapshot and return total equity."""

        equity = portfolio.cash
        for position in portfolio.positions:
            quote = quotes.get(position.symbol)
            price = quote.price if quote else position.avg_cost
            equity += price * Decimal(position.qty)

        with self.session_factory() as session:
            session.add(
                PortfolioSnapshotRecord(
                    user_id=user_id,
                    snapshot_date=datetime.utcnow().date().isoformat(),
                    cash=str(portfolio.cash),
                    total_equity=str(equity),
                    positions_json=json.dumps(portfolio.model_dump(mode="json")),
                    created_at=datetime.utcnow().isoformat(),
                )
            )
            session.commit()
        return equity

    def upsert_performance_daily(self, total_equity: Decimal) -> None:
        """Persist or update daily performance from total equity."""

        performance_date = datetime.utcnow().date().isoformat()
        with self.session_factory() as session:
            existing = session.scalar(
                select(PerformanceDailyRecord).where(PerformanceDailyRecord.performance_date == performance_date)
            )
            previous = session.scalar(
                select(PerformanceDailyRecord)
                .where(PerformanceDailyRecord.performance_date < performance_date)
                .order_by(PerformanceDailyRecord.performance_date.desc())
            )
            previous_equity = Decimal(previous.total_equity) if previous else total_equity
            daily_pnl = total_equity - previous_equity
            daily_return = float(daily_pnl / previous_equity) if previous_equity else 0.0
            if existing:
                existing.total_equity = str(total_equity)
                existing.daily_pnl = str(daily_pnl)
                existing.daily_return = daily_return
            else:
                session.add(
                    PerformanceDailyRecord(
                        performance_date=performance_date,
                        total_equity=str(total_equity),
                        daily_pnl=str(daily_pnl),
                        daily_return=daily_return,
                        created_at=datetime.utcnow().isoformat(),
                    )
                )
            session.commit()

    def list_performance_daily(self, limit: int | None = None) -> list[PerformanceDailyRecord]:
        """Return daily performance rows ordered by date ascending."""

        with self.session_factory() as session:
            stmt = select(PerformanceDailyRecord).order_by(PerformanceDailyRecord.performance_date.asc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt))

    def count_token_usage(self) -> int:
        """Return the number of recorded token usage rows."""

        with self.session_factory() as session:
            return len(list(session.scalars(select(TokenUsageRecord))))

    def list_token_usage_by_user(self) -> list[dict[str, object]]:
        """Return token usage totals grouped by user id."""

        with self.session_factory() as session:
            rows = session.execute(
                select(
                    TokenUsageRecord.user_id,
                    TokenUsageRecord.provider,
                    func.sum(TokenUsageRecord.prompt_tokens),
                    func.sum(TokenUsageRecord.completion_tokens),
                    func.count(TokenUsageRecord.id),
                ).group_by(TokenUsageRecord.user_id, TokenUsageRecord.provider)
            )
            return [
                {
                    "user_id": row[0],
                    "provider": row[1],
                    "prompt_tokens": int(row[2] or 0),
                    "completion_tokens": int(row[3] or 0),
                    "runs": int(row[4] or 0),
                }
                for row in rows
            ]
