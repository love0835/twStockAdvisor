"""SQLAlchemy ORM models for persisted advisor data."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base ORM model."""


class RecommendationRecord(Base):
    """Persisted recommendation row."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    strategy: Mapped[str] = mapped_column(String(32))
    market_view: Mapped[str] = mapped_column(Text)
    warnings: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64))


class PortfolioSnapshotRecord(Base):
    """Persisted portfolio snapshot row."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[str] = mapped_column(String(32))
    cash: Mapped[str] = mapped_column(String(64))
    total_equity: Mapped[str] = mapped_column(String(64))
    positions_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(64))


class TokenUsageRecord(Base):
    """Persisted token usage row."""

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(64))


class PerformanceDailyRecord(Base):
    """Persisted daily performance row."""

    __tablename__ = "performance_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    performance_date: Mapped[str] = mapped_column(String(32), unique=True)
    total_equity: Mapped[str] = mapped_column(String(64))
    daily_pnl: Mapped[str] = mapped_column(String(64))
    daily_return: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String(64))
