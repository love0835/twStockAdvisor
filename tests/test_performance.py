"""Tests for performance metrics."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.performance.metrics import cumulative_pnl, max_drawdown, sharpe_ratio, win_rate


def test_performance_metrics() -> None:
    """Metrics helpers should produce stable outputs."""

    pnls = [Decimal("100"), Decimal("-50"), Decimal("150")]
    equities = [Decimal("1000"), Decimal("950"), Decimal("1100")]
    returns = [0.1, -0.05, 0.1579]

    assert win_rate(pnls) == Decimal("2") / Decimal("3")
    assert cumulative_pnl(pnls) == Decimal("200")
    assert max_drawdown(equities) == Decimal("-0.05")
    assert sharpe_ratio(returns) != 0
