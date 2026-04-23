"""Tests for Taiwan market calendar helpers."""

from __future__ import annotations

from datetime import date, datetime

from twadvisor.fetchers.market_calendar import MarketCalendar


def test_holiday_is_not_trading_day() -> None:
    """Spring festival should be treated as market holiday."""

    calendar = MarketCalendar()
    assert calendar.is_trading_day(date(2026, 2, 17)) is False


def test_regular_session_is_reported() -> None:
    """A regular market timestamp should map to the regular session."""

    calendar = MarketCalendar()
    now = datetime(2026, 4, 7, 10, 15)
    assert calendar.current_session(now) == "regular"


def test_pre_market_and_post_market_sessions() -> None:
    """Session helper should distinguish pre-market and post-market windows."""

    calendar = MarketCalendar()
    assert calendar.current_session(datetime(2026, 4, 7, 8, 45)) == "pre_market"
    assert calendar.current_session(datetime(2026, 4, 7, 14, 15)) == "post_market"


def test_closed_session_on_holiday() -> None:
    """Holiday timestamps should always be closed."""

    calendar = MarketCalendar()
    assert calendar.current_session(datetime(2026, 2, 17, 10, 0)) == "closed"


def test_next_open_skips_weekend() -> None:
    """next_open should skip closed days."""

    calendar = MarketCalendar()
    now = datetime(2026, 4, 10, 15, 0)
    next_open = calendar.next_open(now)
    assert next_open.date() == date(2026, 4, 13)
    assert next_open.hour == 9
