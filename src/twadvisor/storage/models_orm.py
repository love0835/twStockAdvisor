"""SQLAlchemy ORM models for persisted advisor data."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base ORM model."""


class RecommendationRecord(Base):
    """Persisted recommendation row."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_date: Mapped[str] = mapped_column(String(32))
    cash: Mapped[str] = mapped_column(String(64))
    total_equity: Mapped[str] = mapped_column(String(64))
    positions_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(64))


class TokenUsageRecord(Base):
    """Persisted token usage row."""

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class UserRecord(Base):
    """Family member account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="member")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64))


class UserSessionRecord(Base):
    """Hashed login session token."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer)
    session_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[str] = mapped_column(String(64))


class PortfolioAccountRecord(Base):
    """Per-user portfolio account settings."""

    __tablename__ = "portfolio_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True)
    cash: Mapped[str] = mapped_column(String(64), default="0")
    commission_discount: Mapped[str] = mapped_column(String(32), default="0.28")
    updated_at: Mapped[str] = mapped_column(String(64))


class PortfolioPositionRecord(Base):
    """Per-user portfolio position."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_portfolio_position_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(16))
    qty: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[str] = mapped_column(String(64))
    account_type: Mapped[str] = mapped_column(String(16), default="cash")
    opened_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(64))
