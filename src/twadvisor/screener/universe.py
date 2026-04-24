"""Helpers for building and filtering the market universe."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

ETF_KEYWORDS = ("ETF", "ETN", "正", "反", "指數")


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert a value to Decimal without raising for blank market fields."""

    if value is None or value == "":
        return default
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    """Convert market numeric values to int."""

    if value is None or value == "":
        return default
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return default


def symbol_from_record(record: dict[str, Any]) -> str:
    """Extract the stock symbol from common FinMind/TWSE field names."""

    return str(record.get("stock_id") or record.get("symbol") or record.get("code") or "").strip()


def name_from_record(record: dict[str, Any], fallback: str) -> str:
    """Extract the stock name from common field names."""

    return str(record.get("stock_name") or record.get("name") or fallback).strip()


def is_etf(symbol: str, name: str, info: dict[str, Any] | None = None) -> bool:
    """Return whether a symbol should be treated as ETF-like."""

    info_type = str((info or {}).get("type", "")).lower()
    if info_type == "etf":
        return True
    upper_name = name.upper()
    if any(keyword in upper_name for keyword in ETF_KEYWORDS):
        return True
    return symbol.startswith("00") and len(symbol) >= 4
