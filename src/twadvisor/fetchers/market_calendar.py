"""Taiwan market calendar helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from twadvisor.constants import TAIWAN_TIMEZONE

HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 27),
    date(2026, 4, 3),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 6, 19),
    date(2026, 9, 25),
    date(2026, 10, 9),
}

SessionName = Literal["pre_market", "regular", "post_market", "odd_lot", "closed"]


class MarketCalendar:
    """Trading-day and session rules for Taiwan equities."""

    def is_trading_day(self, trading_date: date) -> bool:
        """Return whether the supplied date is a trading day."""

        if trading_date.weekday() >= 5:
            return False
        return trading_date not in HOLIDAYS_2026

    def current_session(self, now: datetime) -> SessionName:
        """Return the market session for the supplied timestamp."""

        local_now = now.astimezone(TAIWAN_TIMEZONE) if now.tzinfo else now.replace(tzinfo=TAIWAN_TIMEZONE)
        if not self.is_trading_day(local_now.date()):
            return "closed"

        current_time = local_now.time()
        if time(8, 30) <= current_time < time(9, 0):
            return "pre_market"
        if time(9, 0) <= current_time <= time(13, 30):
            return "regular"
        if time(14, 0) <= current_time <= time(14, 30):
            return "post_market"
        return "closed"

    def next_open(self, now: datetime) -> datetime:
        """Return the next regular-market open."""

        local_now = now.astimezone(TAIWAN_TIMEZONE) if now.tzinfo else now.replace(tzinfo=TAIWAN_TIMEZONE)
        probe = local_now.date()
        if self.is_trading_day(probe) and local_now.time() < time(9, 0):
            return datetime.combine(probe, time(9, 0), tzinfo=TAIWAN_TIMEZONE)

        probe += timedelta(days=1)
        while not self.is_trading_day(probe):
            probe += timedelta(days=1)
        return datetime.combine(probe, time(9, 0), tzinfo=TAIWAN_TIMEZONE)
