"""Notifier base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod

from twadvisor.models import Recommendation


class BaseNotifier(ABC):
    """Common interface for all notification channels."""

    @abstractmethod
    async def notify(self, recs: list[Recommendation], market_view: str) -> None:
        """Send notifications for validated recommendations."""
