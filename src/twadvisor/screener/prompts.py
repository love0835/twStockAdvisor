"""Prompt helpers for screener AI ranking."""

from __future__ import annotations

import json
from decimal import Decimal

from twadvisor.screener.base import Candidate


def build_rank_prompt(source: str, candidates: list[Candidate], top_n: int) -> tuple[str, str]:
    """Build a compact Traditional Chinese prompt for candidate ranking."""

    system = "你是台股研究助理，只提供研究參考，不是投資建議。請用繁體中文輸出嚴格 JSON。"
    rows = [
        {
            "symbol": item.symbol,
            "name": item.name,
            "close": str(item.close),
            "volume_lots": item.volume,
            "turnover": str(item.turnover),
            "amplitude_pct": str(item.amplitude_pct),
            "ma20": None if item.ma20 is None else str(item.ma20),
            "foreign_net_5d": item.foreign_net_5d,
            "trust_net_5d": item.trust_net_5d,
            "rule_score": str(item.score),
        }
        for item in candidates
    ]
    user = json.dumps(
        {
            "source": source,
            "top_n": top_n,
            "candidates": rows,
            "required_schema": {
                "ranked": [
                    {
                        "rank": 1,
                        "symbol": "2330",
                        "name": "台積電",
                        "confidence": 0.8,
                        "entry_price_low": 1000,
                        "entry_price_high": 1010,
                        "stop_loss": 960,
                        "take_profit": 1080,
                        "reason": "30 到 80 字理由",
                    }
                ],
                "market_view": "盤勢摘要",
                "warnings": [],
            },
        },
        ensure_ascii=False,
        default=lambda value: str(value) if isinstance(value, Decimal) else value,
    )
    return system, user
