"""Token usage logging."""

from __future__ import annotations

from contextvars import ContextVar

from twadvisor.storage.repo import AdvisorRepository

_current_user_id: ContextVar[int | None] = ContextVar("twadvisor_token_usage_user_id", default=None)


def record_token_usage(db_path: str, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Persist token usage into the repository."""

    AdvisorRepository(db_path).record_token_usage(
        provider,
        model,
        prompt_tokens,
        completion_tokens,
        user_id=_current_user_id.get(),
    )


def set_token_usage_user(user_id: int | None):
    """Set the user id used by analyzer token logging."""

    return _current_user_id.set(user_id)


def reset_token_usage_user(token) -> None:
    """Reset the user id context for analyzer token logging."""

    _current_user_id.reset(token)
