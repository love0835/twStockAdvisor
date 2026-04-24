"""Abstract base class and shared helpers for analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from twadvisor.models import AnalysisRequest, AnalysisResponse, Recommendation

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class BaseAnalyzer(ABC):
    """Common interface for AI analyzers."""

    @abstractmethod
    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        """Run analysis for a single request."""

    @abstractmethod
    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """Return the system and user prompts."""


def build_analysis_prompt(req: AnalysisRequest) -> tuple[str, str]:
    """Build shared system and user prompts from the request."""

    system_prompt = _load_prompt("system.md")
    strategy_file = {
        "daytrade": "strategy_daytrade.md",
        "swing": "strategy_swing.md",
        "position": "strategy_swing.md",
        "longterm": "strategy_longterm.md",
        "dividend": "strategy_dividend.md",
    }[req.strategy.value]
    strategy_prompt = _load_prompt(strategy_file)

    positions_lines = []
    for position in req.portfolio.positions:
        quote = req.quotes.get(position.symbol)
        price = quote.price if quote else Decimal("0")
        pnl = (price - position.avg_cost) * Decimal(position.qty) if quote else Decimal("0")
        positions_lines.append(
            f"- {position.symbol}: qty={position.qty}, avg_cost={position.avg_cost}, price={price}, unrealized_pnl={pnl}"
        )
    if not positions_lines:
        positions_lines.append("- no positions")

    watchlist_lines = []
    for symbol in req.watchlist:
        quote = req.quotes[symbol]
        indicator = req.indicators[symbol]
        chip = req.chips[symbol]
        watchlist_lines.append(
            "\n".join(
                [
                    f"### {symbol}",
                    f"price={quote.price}, prev_close={quote.prev_close}, limit_up={quote.limit_up}, limit_down={quote.limit_down}",
                    f"ma5={indicator.ma5}, ma20={indicator.ma20}, ma60={indicator.ma60}, kd_k={indicator.kd_k}, kd_d={indicator.kd_d}, macd={indicator.macd}, rsi14={indicator.rsi14}",
                    f"foreign_net={chip.foreign_net}, trust_net={chip.trust_net}, dealer_net={chip.dealer_net}",
                ]
            )
        )

    user_prompt = "\n\n".join(
        [
            f"## 绛栫暐\n{req.strategy.value}",
            f"## 绛栫暐瑾槑\n{strategy_prompt}",
            f"## 棰ㄩ毆鍋忓ソ\n{req.risk_preference}",
            f"## 鐝鹃噾\n{req.portfolio.cash}",
            f"## 鍠獢涓婇檺\n{req.max_position_pct}",
            "## 鐩墠鎸佸€塡n" + "\n".join(positions_lines),
            "## Watchlist\n" + "\n\n".join(watchlist_lines),
            "## 浠诲嫏\n璜嬩緷鎿氫互涓婅硣鏂欐彁鍑虹祼妲嬪寲寤鸿锛屽洖傳 JSON，包含 market_view、recommendations、warnings。",
        ]
    )
    return system_prompt, user_prompt


def parse_analysis_payload(payload: dict, req: AnalysisRequest) -> AnalysisResponse:
    """Parse a structured payload into the local response model."""

    recommendations = [
        Recommendation(
            symbol=item["symbol"],
            action=item["action"],
            qty=item.get("qty", 0),
            order_type=item.get("order_type", "limit"),
            price=item.get("price"),
            stop_loss=item.get("stop_loss"),
            take_profit=item.get("take_profit"),
            reason=item["reason"],
            confidence=item["confidence"],
            strategy=req.strategy,
            generated_at=datetime.now(),
        )
        for item in payload.get("recommendations", [])
    ]
    return AnalysisResponse(
        recommendations=recommendations,
        market_view=payload["market_view"],
        warnings=payload.get("warnings", []),
    )


def _load_prompt(filename: str) -> str:
    """Read a prompt template from disk."""

    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")
