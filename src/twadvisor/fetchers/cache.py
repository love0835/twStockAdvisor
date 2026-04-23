"""Small in-memory TTL cache for fetchers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Single cache entry with expiration metadata."""

    value: T
    expires_at: datetime


class TTLCache(Generic[T]):
    """Simple process-local TTL cache."""

    def __init__(self) -> None:
        """Create an empty cache."""

        self._store: dict[str, CacheEntry[T]] = {}

    def get(self, key: str, now: datetime | None = None) -> T | None:
        """Return a cached value when it is still fresh."""

        current_time = now or datetime.utcnow()
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= current_time:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: T, ttl_seconds: int, now: datetime | None = None) -> None:
        """Store a cache entry with the provided TTL."""

        current_time = now or datetime.utcnow()
        self._store[key] = CacheEntry(
            value=value,
            expires_at=current_time + timedelta(seconds=ttl_seconds),
        )
