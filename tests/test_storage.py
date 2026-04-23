"""Tests for storage repository helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from twadvisor.models import Portfolio, Position, Quote, Recommendation, Strategy
from twadvisor.storage.repo import AdvisorRepository


def test_repo_records_token_usage_and_snapshots(tmp_path) -> None:
    """Repository should persist token usage and portfolio snapshots."""

    repo = AdvisorRepository(str(tmp_path / "advisor.db"))
    repo.record_token_usage("claude", "model", 10, 5)
    portfolio = Portfolio(
        cash=Decimal("100000"),
        positions=[Position(symbol="2330", qty=1000, avg_cost=Decimal("580"), opened_at=date(2025, 1, 2))],
        updated_at=datetime(2026, 4, 24, 10, 0, 0),
    )
    quotes = {
        "2330": Quote(
            symbol="2330",
            name="TSMC",
            price=Decimal("600"),
            open=Decimal("590"),
            high=Decimal("605"),
            low=Decimal("588"),
            prev_close=Decimal("595"),
            volume=1000,
            bid=Decimal("599"),
            ask=Decimal("600"),
            limit_up=Decimal("654"),
            limit_down=Decimal("536"),
            timestamp=datetime(2026, 4, 24, 10, 0, 0),
        )
    }
    equity = repo.save_portfolio_snapshot(portfolio, quotes)
    repo.upsert_performance_daily(equity)
    repo.save_recommendations(
        [
            Recommendation(
                symbol="2330",
                action="hold",
                qty=0,
                order_type="limit",
                reason="hold",
                confidence=0.7,
                strategy=Strategy.SWING,
                generated_at=datetime(2026, 4, 24, 10, 0, 0),
            )
        ],
        "偏多震盪",
        [],
    )

    assert repo.count_token_usage() == 1
    assert repo.list_performance_daily()
