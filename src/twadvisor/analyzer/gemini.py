"""Gemini analyzer implementation."""

from __future__ import annotations

import asyncio
import json

from google import genai
from google.genai import types

from twadvisor.analyzer.base import BaseAnalyzer, build_analysis_prompt, parse_analysis_payload
from twadvisor.analyzer.schema import gemini_response_schema
from twadvisor.analyzer.token_usage import record_token_usage
from twadvisor.models import AnalysisRequest, AnalysisResponse


class GeminiAnalyzer(BaseAnalyzer):
    """Google Gemini analyzer using structured output JSON schema."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        *,
        max_output_tokens: int = 2000,
        temperature: float = 0.2,
        db_path: str = "./data/twadvisor.db",
        client: genai.Client | None = None,
    ) -> None:
        """Create a Gemini analyzer."""

        self.client = client or genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.db_path = db_path

    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """Build provider-independent prompts."""

        return build_analysis_prompt(req)

    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        """Run analysis with Gemini structured outputs."""

        system_prompt, user_prompt = self.build_prompt(req)
        response = await asyncio.to_thread(self._create_response, system_prompt, user_prompt)
        payload = self._parse_payload(response)
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        record_token_usage(
            self.db_path,
            provider="gemini",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        parsed = parse_analysis_payload(payload, req)
        parsed.raw_prompt_tokens = prompt_tokens
        parsed.raw_completion_tokens = completion_tokens
        return parsed

    def _create_response(self, system_prompt: str, user_prompt: str):
        """Call the Gemini generate_content API."""

        return self.client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                response_mime_type="application/json",
                response_json_schema=gemini_response_schema(),
            ),
        )

    def _parse_payload(self, response: object) -> dict:
        """Extract JSON payload from a Gemini response."""

        text = getattr(response, "text", "")
        if not text:
            raise ValueError("Gemini response did not contain JSON text")
        return json.loads(text)
