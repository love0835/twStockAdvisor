"""Claude analyzer implementation."""

from __future__ import annotations

import asyncio

import anthropic

from twadvisor.analyzer.base import BaseAnalyzer, build_analysis_prompt, parse_analysis_payload
from twadvisor.analyzer.schema import RECOMMENDATION_TOOL_SCHEMA
from twadvisor.analyzer.token_usage import record_token_usage
from twadvisor.models import AnalysisRequest, AnalysisResponse


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

        return build_analysis_prompt(req)

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
                return parse_analysis_payload(block.input, req)
        raise ValueError("Claude response did not contain a submit_recommendations tool_use block")
