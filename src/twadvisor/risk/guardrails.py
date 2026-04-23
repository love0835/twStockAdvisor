"""Simple portfolio-level guardrail helpers."""

from __future__ import annotations

from decimal import Decimal


def position_pct(exposure: Decimal, total_equity: Decimal) -> Decimal:
    """Return exposure as a fraction of total equity."""

    if total_equity <= 0:
        return Decimal("0")
    return exposure / total_equity
