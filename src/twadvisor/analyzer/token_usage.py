"""Token usage logging."""

from __future__ import annotations

from twadvisor.storage.repo import AdvisorRepository


def record_token_usage(db_path: str, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Persist token usage into the repository."""

    AdvisorRepository(db_path).record_token_usage(provider, model, prompt_tokens, completion_tokens)
