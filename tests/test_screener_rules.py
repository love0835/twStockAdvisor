"""Tests for screener rule layers."""

from __future__ import annotations

from decimal import Decimal

from twadvisor.screener.base import Candidate
from twadvisor.screener.daytrade import DaytradeScreener
from twadvisor.screener.swing import SwingScreener
from twadvisor.screener.universe import is_etf


def candidate(**overrides: object) -> Candidate:
    """Build a candidate with rule-friendly defaults."""

    data = {
        "symbol": "2330",
        "name": "台積電",
        "close": Decimal("100"),
        "volume": 3000,
        "turnover": Decimal("500000000"),
        "amplitude_pct": Decimal("3"),
        "ma20": Decimal("95"),
        "above_ma20": True,
        "foreign_net_5d": 1500,
        "trust_net_5d": 1200,
        "daytrade_ratio": Decimal("0.30"),
        "is_daytrade_eligible": True,
        "is_attention": False,
        "is_disposition": False,
        "source": "daytrade",
    }
    data.update(overrides)
    return Candidate(**data)


def test_daytrade_screener_filters_attention_and_low_turnover() -> None:
    """Daytrade rules should reject risk lists and thin liquidity."""

    screener = DaytradeScreener(
        min_price=Decimal("15"),
        max_price=Decimal("800"),
        min_amplitude_pct=Decimal("2"),
        min_turnover=Decimal("300000000"),
    )

    passed = screener.screen(
        [
            candidate(symbol="2330"),
            candidate(symbol="2317", is_attention=True),
            candidate(symbol="2881", turnover=Decimal("100000000")),
        ]
    )

    assert [item.symbol for item in passed] == ["2330"]
    assert passed[0].score > 0


def test_swing_screener_honors_foreign_consecutive_option() -> None:
    """Swing rules should allow looser chip filtering when N is zero."""

    screener = SwingScreener(
        min_price=Decimal("20"),
        max_price=Decimal("2500"),
        min_volume_lots=1000,
        require_above_ma20=True,
        min_foreign_net_lots=1000,
    )

    loose = screener.screen([candidate(foreign_net_5d=0, trust_net_5d=1600)], foreign_consecutive_days=0)
    strict = screener.screen([candidate(foreign_net_5d=0, trust_net_5d=1600)], foreign_consecutive_days=3)

    assert len(loose) == 1
    assert strict == []


def test_is_etf_uses_info_name_and_symbol_fallbacks() -> None:
    """ETF detection should use type, name, and 00xx-style fallbacks."""

    assert is_etf("00878", "國泰永續高股息", None)
    assert is_etf("1234", "範例 ETF", None)
    assert is_etf("9999", "範例", {"type": "etf"})
    assert not is_etf("2330", "台積電", {"type": "twse"})
