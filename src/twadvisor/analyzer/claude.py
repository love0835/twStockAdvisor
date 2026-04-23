"""Claude analyzer implementation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import anthropic

from twadvisor.analyzer.base import BaseAnalyzer
from twadvisor.analyzer.schema import RECOMMENDATION_TOOL_SCHEMA
from twadvisor.analyzer.token_usage import record_token_usage
from twadvisor.models import AnalysisRequest, AnalysisResponse, Recommendation

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class ClaudeAnalyzer(BaseAnalyzer):
    """Anthropic Claude analyzer with tool-use parsing and retries."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        *,
        max_output_tokens: int = 2000,
        temperature: float = 0.2,
        use_prompt_cache: bool = True,
        db_path: str = "./data/twadvisor.db",
        client: anthropic.Anthropic | None = None,
        max_retries: int = 3,
    ) -> None:
        """Create a Claude analyzer."""

        self.client = client or anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.use_prompt_cache = use_prompt_cache
        self.db_path = db_path
        self.max_retries = max_retries

    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """Build system and user prompts from the request."""

        system_prompt = self._load_prompt("system.md")
        strategy_file = {
            "daytrade": "strategy_daytrade.md",
            "swing": "strategy_swing.md",
            "position": "strategy_swing.md",
            "longterm": "strategy_longterm.md",
            "dividend": "strategy_dividend.md",
        }[req.strategy.value]
        strategy_prompt = self._load_prompt(strategy_file)

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
                f"## 策略\n{req.strategy.value}",
                f"## 策略說明\n{strategy_prompt}",
                f"## 風險偏好\n{req.risk_preference}",
                f"## 現金\n{req.portfolio.cash}",
                f"## 單檔上限\n{req.max_position_pct}",
                "## 目前持倉\n" + "\n".join(positions_lines),
                "## Watchlist\n" + "\n\n".join(watchlist_lines),
                "## 任務\n請依據以上資料提出結構化建議，使用 submit_recommendations 工具回傳。",
            ]
        )
        return system_prompt, user_prompt

    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        """Run Claude analysis and parse structured recommendations."""

        system_prompt, user_prompt = self.build_prompt(req)
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await asyncio.to_thread(self._create_message, system_prompt, user_prompt)
                parsed = self._parse(response, req)
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
                completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0
                record_token_usage(
                    self.db_path,
                    provider="claude",
                    model=self.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                parsed.raw_prompt_tokens = prompt_tokens
                parsed.raw_completion_tokens = completion_tokens
                return parsed
            except anthropic.RateLimitError as exc:
                last_error = exc
                await asyncio.sleep(2**attempt)
            except Exception as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Claude analysis failed without a captured exception")

    def _create_message(self, system_prompt: str, user_prompt: str):
        """Call the Anthropic Messages API."""

        system_blocks: list[dict] = [{"type": "text", "text": system_prompt}]
        if self.use_prompt_cache:
            system_blocks[0]["cache_control"] = {"type": "ephemeral"}

        return self.client.messages.create(
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            system=system_blocks,
            tools=[RECOMMENDATION_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_recommendations"},
            messages=[{"role": "user", "content": user_prompt}],
        )

    def _parse(self, response: object, req: AnalysisRequest) -> AnalysisResponse:
        """Parse a tool-use response into the local schema."""

        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_recommendations":
                payload = block.input
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
        raise ValueError("Claude response did not contain a submit_recommendations tool_use block")

    def _load_prompt(self, filename: str) -> str:
        """Read a prompt template from disk."""

        return (PROMPTS_DIR / filename).read_text(encoding="utf-8")
