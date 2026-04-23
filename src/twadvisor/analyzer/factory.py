"""Analyzer selection helpers."""

from __future__ import annotations

from twadvisor.analyzer.claude import ClaudeAnalyzer
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import Settings


def create_analyzer(settings: Settings) -> ClaudeAnalyzer:
    """Create the configured analyzer implementation."""

    provider = settings.ai.provider
    keystore = KeyStore(settings.security.keyring_service)
    if provider != "claude":
        raise ValueError(f"Unsupported analyzer provider for Phase 4: {provider}")
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
