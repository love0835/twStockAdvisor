"""Pydantic schemas for the Web UI API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzePayload(BaseModel):
    """Request body for single-run analysis."""

    strategy: str
    watchlist: list[str] = Field(default_factory=list)
    storage_path: str = "data/portfolio.json"


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
