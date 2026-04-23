"""Technical indicator calculation helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from twadvisor.models import TechnicalIndicators


def _to_decimal(value: float | int | None) -> Decimal | None:
    """Convert numeric values to rounded Decimal instances."""

    if value is None or pd.isna(value):
        return None
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def compute_indicators(df: pd.DataFrame, symbol: str) -> TechnicalIndicators:
    """Compute a basic set of technical indicators from OHLCV data."""

    if df.empty:
        raise ValueError("OHLCV dataframe must not be empty")

    frame = df.sort_index().copy()
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1] if len(frame) >= 60 else None

    lowest_low = low.rolling(9).min()
    highest_high = high.rolling(9).max()
    rsv = ((close - lowest_low) / (highest_high - lowest_low) * 100).fillna(0)
    kd_k = rsv.ewm(alpha=1 / 3, adjust=False).mean().iloc[-1]
    kd_d = rsv.ewm(alpha=1 / 3, adjust=False).mean().ewm(alpha=1 / 3, adjust=False).mean().iloc[-1]

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12.iloc[-1] - ema26.iloc[-1]
    macd_signal = (ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi14 = (100 - (100 / (1 + rs))).iloc[-1]

    ma20_series = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bband_upper = (ma20_series + (std20 * 2)).iloc[-1]
    bband_lower = (ma20_series - (std20 * 2)).iloc[-1]

    avg_volume5 = volume.rolling(5).mean().iloc[-1]
    volume_ratio = volume.iloc[-1] / avg_volume5 if avg_volume5 else None

    return TechnicalIndicators(
        symbol=symbol,
        ma5=_to_decimal(ma5),
        ma20=_to_decimal(ma20),
        ma60=_to_decimal(ma60),
        kd_k=_to_decimal(kd_k),
        kd_d=_to_decimal(kd_d),
        macd=_to_decimal(macd),
        macd_signal=_to_decimal(macd_signal),
        rsi14=_to_decimal(rsi14),
        bband_upper=_to_decimal(bband_upper),
        bband_lower=_to_decimal(bband_lower),
        volume_ratio=_to_decimal(volume_ratio),
    )
