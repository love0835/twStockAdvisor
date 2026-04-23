"""Performance metric helpers."""

from __future__ import annotations

from decimal import Decimal
from math import sqrt


def win_rate(daily_pnls: list[Decimal]) -> Decimal:
    """Return the fraction of positive daily pnl observations."""

    if not daily_pnls:
        return Decimal("0")
    wins = sum(1 for value in daily_pnls if value > 0)
    return Decimal(wins) / Decimal(len(daily_pnls))


def cumulative_pnl(daily_pnls: list[Decimal]) -> Decimal:
    """Return cumulative pnl."""

    return sum(daily_pnls, Decimal("0"))


def sharpe_ratio(daily_returns: list[float]) -> float:
    """Return a simple daily Sharpe ratio."""

    if len(daily_returns) < 2:
        return 0.0
    mean_return = sum(daily_returns) / len(daily_returns)
    variance = sum((value - mean_return) ** 2 for value in daily_returns) / (len(daily_returns) - 1)
    if variance == 0:
        return 0.0
    return (mean_return / variance**0.5) * sqrt(252)


def max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    """Return the maximum drawdown as a negative fraction."""

    if not equity_curve:
        return Decimal("0")
    peak = equity_curve[0]
    worst = Decimal("0")
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = (equity - peak) / peak
            worst = min(worst, drawdown)
    return worst
