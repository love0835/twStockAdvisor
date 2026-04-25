"""Analyzer selection helpers."""

from __future__ import annotations

from twadvisor.analyzer.api_keys import resolve_ai_api_key, resolve_ai_provider
from twadvisor.analyzer.claude import ClaudeAnalyzer
from twadvisor.analyzer.gemini import GeminiAnalyzer
from twadvisor.analyzer.openai_analyzer import OpenAIAnalyzer
from twadvisor.settings import Settings


def create_analyzer(settings: Settings, provider: str | None = None):
    """Create the configured analyzer implementation."""

    provider = resolve_ai_provider(settings, provider)
    api_key, _source = resolve_ai_api_key(settings, provider)
    if provider == "claude":
        return ClaudeAnalyzer(
            api_key=api_key,
            model=settings.ai.model_claude,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            use_prompt_cache=settings.ai.use_prompt_cache,
            db_path=settings.app.db_path,
        )
    if provider == "openai":
        return OpenAIAnalyzer(
            api_key=api_key,
            model=settings.ai.model_openai,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            db_path=settings.app.db_path,
        )
    if provider == "gemini":
        return GeminiAnalyzer(
            api_key=api_key,
            model=settings.ai.model_gemini,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            db_path=settings.app.db_path,
        )
    raise ValueError(f"Unsupported analyzer provider: {provider}")
