"""Rule screener for short swing candidates."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.screener.base import Candidate


class SwingScreener:
    """Filter and score swing candidates."""

    def __init__(
        self,
        min_price: Decimal,
        max_price: Decimal,
        min_volume_lots: int,
        require_above_ma20: bool,
        min_foreign_net_lots: int,
    ) -> None:
        self.min_price = min_price
        self.max_price = max_price
        self.min_volume_lots = min_volume_lots
        self.require_above_ma20 = require_above_ma20
        self.min_foreign_net_lots = min_foreign_net_lots

    def screen(self, candidates: list[Candidate], foreign_consecutive_days: int = 3) -> list[Candidate]:
        """Return candidates passing swing rules, sorted by score."""

        passed = []
        for candidate in candidates:
            if candidate.is_attention or candidate.is_disposition:
                continue
            if not (self.min_price <= candidate.close <= self.max_price):
                continue
            if candidate.volume < self.min_volume_lots:
                continue
            if self.require_above_ma20 and not candidate.above_ma20:
                continue
            if foreign_consecutive_days == 0:
                if max(candidate.foreign_net_5d, candidate.trust_net_5d) < self.min_foreign_net_lots:
                    continue
            elif candidate.foreign_net_5d <= 0:
                continue
            passed.append(candidate.model_copy(update={"score": swing_score(candidate)}))
        return sorted(passed, key=lambda item: item.score, reverse=True)


def swing_score(candidate: Candidate) -> Decimal:
    """Score a swing candidate from 0 to 100."""

    foreign = min(Decimal(max(candidate.foreign_net_5d, 0)) / Decimal("10000"), Decimal("1")) * Decimal("30")
    trust = min(Decimal(max(candidate.trust_net_5d, 0)) / Decimal("5000"), Decimal("1")) * Decimal("20")
    strength = Decimal("0")
    if candidate.ma20 and candidate.ma20 > 0:
        strength = min(max((candidate.close - candidate.ma20) / candidate.ma20, Decimal("0")), Decimal("0.10"))
        strength = strength / Decimal("0.10") * Decimal("25")
    turnover = min(candidate.turnover / Decimal("500000000"), Decimal("1")) * Decimal("25")
    return (foreign + trust + strength + turnover).quantize(Decimal("0.01"))
