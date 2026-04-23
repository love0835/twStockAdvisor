"""Tests for technical indicators."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from twadvisor.indicators.technical import compute_indicators


def _sample_frame(length: int) -> pd.DataFrame:
    """Build a deterministic OHLCV dataframe."""

    data = {
        "open": [100 + index for index in range(length)],
        "high": [101 + index for index in range(length)],
        "low": [99 + index for index in range(length)],
        "close": [100 + index for index in range(length)],
        "volume": [1000 + (index * 10) for index in range(length)],
    }
    return pd.DataFrame(data, index=pd.date_range("2025-01-01", periods=length, freq="D"))


def test_ma_calculation_matches_tail_mean() -> None:
    """MA5 should match the trailing 5-day mean."""

    frame = _sample_frame(120)
    indicators = compute_indicators(frame, "2330")
    expected = Decimal(str(frame["close"].tail(5).mean())).quantize(Decimal("0.0001"))
    assert indicators.ma5 == expected


def test_insufficient_data_sets_ma60_none() -> None:
    """MA60 should remain empty when there is not enough history."""

    frame = _sample_frame(30)
    indicators = compute_indicators(frame, "2330")
    assert indicators.ma60 is None
    assert indicators.ma5 is not None
