"""Pydantic schemas for the Web UI API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzePayload(BaseModel):
    """Request body for single-run analysis."""

    strategy: str
    provider: str | None = None
    watchlist: list[str] = Field(default_factory=list)
    include_portfolio: bool = False
    holding_symbols: list[str] = Field(default_factory=list)
    storage_path: str = "data/portfolio.json"


class LoginPayload(BaseModel):
    """Request body for login."""

    username: str
    password: str


class CreateInitialAdminPayload(BaseModel):
    """Request body for first-run admin creation."""

    username: str
    password: str
    display_name: str | None = None


class UserCreatePayload(BaseModel):
    """Request body for admin-created family member."""

    username: str
    password: str
    display_name: str | None = None
    role: str = "member"


class PasswordChangePayload(BaseModel):
    """Request body for changing own password."""

    current_password: str
    new_password: str


class BacktestPayload(BaseModel):
    """Request body for historical backtest."""

    strategy: str
    symbols: list[str] = Field(default_factory=list)
    from_date: str
    to_date: str
    initial_cash: str = "1000000"
    storage_path: str = "data/portfolio.json"


class PortfolioImportPayload(BaseModel):
    """Request body for importing a portfolio CSV."""

    csv_path: str
    cash: str | None = None
    storage_path: str = "data/portfolio.json"


class PortfolioCashPayload(BaseModel):
    """Request body for updating portfolio cash."""

    cash: str
    storage_path: str = "data/portfolio.json"


class PortfolioCommissionPayload(BaseModel):
    """Request body for updating commission discount."""

    commission_discount: str
    storage_path: str = "data/portfolio.json"


class PortfolioPositionPayload(BaseModel):
    """Request body for adding or updating a portfolio position."""

    symbol: str
    qty: int = Field(ge=0)
    avg_cost: str
    storage_path: str = "data/portfolio.json"


class PortfolioDeletePayload(BaseModel):
    """Request body for deleting a portfolio position."""

    storage_path: str = "data/portfolio.json"


class PortfolioQuotePayload(BaseModel):
    """Request body for updating portfolio market prices."""

    storage_path: str = "data/portfolio.json"
    commission_discount: float | None = Field(default=None, ge=0, le=1)


class ScreenerPayload(BaseModel):
    """Request body for market scanner endpoints."""

    top_n: int = Field(default=5, ge=1, le=20)
    exclude_holdings: bool = True
    min_price: float | None = None
    max_price: float | None = None
    exclude_etf: bool = True
    foreign_consecutive_days: int = Field(default=3, ge=0, le=10)
    storage_path: str = "data/portfolio.json"


class ScreenerDecisionCandidate(BaseModel):
    """Candidate row already produced by the market scanner."""

    symbol: str
    name: str = ""
    entry_range: str = ""
    stop_loss: str = ""
    take_profit: str = ""
    reason: str = ""
    rule_score: str = "0"


class ScreenerDecisionPayload(BaseModel):
    """Request body for AI decisions based on scanner rows."""

    strategy: str
    provider: str | None = None
    candidates: list[ScreenerDecisionCandidate] = Field(default_factory=list)
    include_portfolio: bool = False
    holding_symbols: list[str] = Field(default_factory=list)
    storage_path: str = "data/portfolio.json"
