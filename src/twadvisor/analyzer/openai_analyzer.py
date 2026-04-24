"""OpenAI analyzer implementation."""

from __future__ import annotations

import asyncio
import json

from openai import OpenAI

from twadvisor.analyzer.base import BaseAnalyzer, build_analysis_prompt, parse_analysis_payload
from twadvisor.analyzer.schema import RECOMMENDATION_RESPONSE_SCHEMA
from twadvisor.analyzer.token_usage import record_token_usage
from twadvisor.models import AnalysisRequest, AnalysisResponse


class OpenAIAnalyzer(BaseAnalyzer):
    """OpenAI analyzer using the Responses API structured outputs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        *,
        max_output_tokens: int = 2000,
        temperature: float = 0.2,
        db_path: str = "./data/twadvisor.db",
        client: OpenAI | None = None,
    ) -> None:
        """Create an OpenAI analyzer."""

        self.client = client or OpenAI(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.db_path = db_path

    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """Build provider-independent prompts."""

        return build_analysis_prompt(req)

    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        """Run analysis with OpenAI structured outputs."""

        system_prompt, user_prompt = self.build_prompt(req)
        response = await asyncio.to_thread(self._create_response, system_prompt, user_prompt)
        if getattr(response, "status", None) == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "unknown")
            raise ValueError(f"OpenAI response incomplete: {reason}")
        payload = self._parse_payload(response)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0
        record_token_usage(
            self.db_path,
            provider="openai",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        parsed = parse_analysis_payload(payload, req)
        parsed.raw_prompt_tokens = prompt_tokens
        parsed.raw_completion_tokens = completion_tokens
        return parsed

    def _create_response(self, system_prompt: str, user_prompt: str):
        """Call the OpenAI Responses API."""

        return self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "submit_recommendations",
                    "strict": True,
                    "schema": RECOMMENDATION_RESPONSE_SCHEMA,
                }
            },
        )

    def _parse_payload(self, response: object) -> dict:
        """Extract JSON payload from a Responses API object."""

        output_text = getattr(response, "output_text", "")
        if output_text:
            return json.loads(output_text)
        for item in getattr(response, "output", []):
            for block in getattr(item, "content", []):
                if getattr(block, "type", None) == "output_text":
                    return json.loads(block.text)
                if getattr(block, "type", None) == "refusal":
                    raise ValueError(f"OpenAI refusal: {block.refusal}")
        raise ValueError("OpenAI response did not contain structured output text")
