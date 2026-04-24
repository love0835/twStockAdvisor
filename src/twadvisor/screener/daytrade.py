"""Rule screener for day-trade candidates."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.screener.base import Candidate


class DaytradeScreener:
    """Filter and score day-trade candidates."""

    def __init__(
        self,
        min_price: Decimal,
        max_price: Decimal,
        min_amplitude_pct: Decimal,
        min_turnover: Decimal,
    ) -> None:
        self.min_price = min_price
        self.max_price = max_price
        self.min_amplitude_pct = min_amplitude_pct
        self.min_turnover = min_turnover

    def screen(self, candidates: list[Candidate]) -> list[Candidate]:
        """Return candidates passing day-trade rules, sorted by score."""

        passed = []
        for candidate in candidates:
            if not candidate.is_daytrade_eligible:
                continue
            if candidate.is_attention or candidate.is_disposition:
                continue
            if not (self.min_price <= candidate.close <= self.max_price):
                continue
            if candidate.amplitude_pct < self.min_amplitude_pct:
                continue
            if candidate.turnover < self.min_turnover:
                continue
            passed.append(candidate.model_copy(update={"score": daytrade_score(candidate)}))
        return sorted(passed, key=lambda item: item.score, reverse=True)


def daytrade_score(candidate: Candidate) -> Decimal:
    """Score a day-trade candidate from 0 to 100."""

    amplitude = min(candidate.amplitude_pct / Decimal("5"), Decimal("1")) * Decimal("40")
    turnover = min(candidate.turnover / Decimal("1000000000"), Decimal("1")) * Decimal("40")
    ratio = min(candidate.daytrade_ratio or Decimal("0"), Decimal("1")) * Decimal("20")
    return (amplitude + turnover + ratio).quantize(Decimal("0.01"))
