"""Shared screener models."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """A pre-screened stock candidate before AI ranking."""

    symbol: str
    name: str
    close: Decimal
    volume: int
    turnover: Decimal
    amplitude_pct: Decimal
    ma20: Decimal | None = None
    above_ma20: bool | None = None
    foreign_net_5d: int = 0
    trust_net_5d: int = 0
    daytrade_ratio: Decimal | None = None
    is_daytrade_eligible: bool = False
    is_attention: bool = False
    is_disposition: bool = False
    score: Decimal = Decimal("0")
    source: str


class RankedRecommendation(BaseModel):
    """A ranked recommendation returned by the screener."""

    rank: int = Field(ge=1)
    symbol: str
    name: str
    action: str = "buy"
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    entry_price_low: Decimal | None = None
    entry_price_high: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    reason: str
    rule_score: Decimal = Decimal("0")
    warnings: list[str] = Field(default_factory=list)


class ScreenResult(BaseModel):
    """Screener response before Web serialization."""

    source: str
    market_view: str
    candidates_total: int
    candidates_after_rules: int
    recommendations: list[RankedRecommendation]
    warnings: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_sec: float = 0


class RuleScreener(Protocol):
    """Protocol for rule-based screeners."""

    def screen(self, candidates: list[Candidate]) -> list[Candidate]:
        """Return candidates that pass rules."""
