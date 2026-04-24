"""Analyzer selection helpers."""

from __future__ import annotations

from twadvisor.analyzer.claude import ClaudeAnalyzer
from twadvisor.analyzer.gemini import GeminiAnalyzer
from twadvisor.analyzer.openai_analyzer import OpenAIAnalyzer
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import Settings


def create_analyzer(settings: Settings):
    """Create the configured analyzer implementation."""

    provider = settings.ai.provider
    keystore = KeyStore(settings.security.keyring_service)
    if provider == "claude":
        api_key = keystore.get_secret("anthropic")
        if not api_key:
            raise ValueError("Missing anthropic API key in keyring")
        return ClaudeAnalyzer(
            api_key=api_key,
            model=settings.ai.model_claude,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            use_prompt_cache=settings.ai.use_prompt_cache,
            db_path=settings.app.db_path,
        )
    if provider == "openai":
        api_key = keystore.get_secret("openai")
        if not api_key:
            raise ValueError("Missing openai API key in keyring")
        return OpenAIAnalyzer(
            api_key=api_key,
            model=settings.ai.model_openai,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            db_path=settings.app.db_path,
        )
    if provider == "gemini":
        api_key = keystore.get_secret("gemini")
        if not api_key:
            raise ValueError("Missing gemini API key in keyring")
        return GeminiAnalyzer(
            api_key=api_key,
            model=settings.ai.model_gemini,
            max_output_tokens=settings.ai.max_output_tokens,
            temperature=settings.ai.temperature,
            db_path=settings.app.db_path,
        )
    raise ValueError(f"Unsupported analyzer provider: {provider}")
