"""Local AI provider key configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from twadvisor.security.keystore import KeyStore

AI_PROVIDER_LABELS = {
    "claude": "Claude",
    "openai": "ChatGPT",
    "gemini": "Gemini",
}

_PROVIDER_ALIASES = {
    "anthropic": "claude",
    "claude": "claude",
    "calaude": "claude",
    "calauade": "claude",
    "chatgpt": "openai",
    "gpt": "openai",
    "openai": "openai",
    "gemini": "gemini",
    "google": "gemini",
}

_KEYRING_NAMES = {
    "claude": "anthropic",
    "openai": "openai",
    "gemini": "gemini",
}

_PLACEHOLDERS = {
    "",
    "paste_your_key_here",
    "paste_anthropic_api_key_here",
    "paste_openai_api_key_here",
    "paste_gemini_api_key_here",
}


@dataclass(frozen=True)
class AIProviderKey:
    """A configured AI provider key."""

    provider: str
    label: str
    api_key: str


class AIKeyConfig:
    """AI provider keys loaded from an ignored local JSON file."""

    def __init__(self, keys: dict[str, AIProviderKey], default_provider: str | None = None) -> None:
        """Create a local AI key config."""

        self.keys = keys
        self.default_provider = default_provider

    @classmethod
    def from_file(cls, path: str | Path) -> "AIKeyConfig | None":
        """Load AI provider keys from a JSON file when it exists."""

        config_path = Path(path)
        if not config_path.exists():
            return None
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid AI key config JSON: {config_path}") from exc
        if not isinstance(raw, dict):
            raise ValueError("AI key config must be a JSON object")

        default_provider = _optional_normalized_provider(raw.get("default_provider"))
        providers = raw.get("providers", {})
        if not isinstance(providers, dict):
            raise ValueError("AI key config field 'providers' must be an object")

        keys: dict[str, AIProviderKey] = {}
        for raw_name, record in providers.items():
            parsed = _parse_provider_record(str(raw_name), record)
            if parsed is not None:
                keys[parsed.provider] = parsed
        return cls(keys=keys, default_provider=default_provider)

    def api_key_for(self, provider: str) -> str | None:
        """Return the configured API key for a provider."""

        normalized = normalize_ai_provider(provider)
        key = self.keys.get(normalized)
        return None if key is None else key.api_key

    def configured_providers(self) -> set[str]:
        """Return normalized provider names with configured local keys."""

        return set(self.keys)


def normalize_ai_provider(provider: str | None) -> str:
    """Normalize UI/config provider names to internal provider IDs."""

    raw = str(provider or "claude").strip().lower()
    normalized = _PROVIDER_ALIASES.get(raw)
    if normalized is None:
        raise ValueError(f"Unsupported analyzer provider: {provider}")
    return normalized


def resolve_ai_provider(settings: object, provider: str | None = None) -> str:
    """Resolve the requested provider, honoring the local file default when present."""

    if provider:
        return normalize_ai_provider(provider)
    config = AIKeyConfig.from_file(getattr(settings.ai, "keys_path", "data/ai_keys.local.json"))
    if config is not None and config.default_provider and config.api_key_for(config.default_provider):
        return config.default_provider
    return normalize_ai_provider(settings.ai.provider)


def resolve_ai_api_key(settings: object, provider: str) -> tuple[str, str]:
    """Return an API key and source label for the requested provider."""

    normalized = normalize_ai_provider(provider)
    config = AIKeyConfig.from_file(getattr(settings.ai, "keys_path", "data/ai_keys.local.json"))
    if config is not None:
        api_key = config.api_key_for(normalized)
        if api_key:
            return api_key, "file"

    keystore = KeyStore(settings.security.keyring_service)
    fallback_key = keystore.get_secret(_KEYRING_NAMES[normalized])
    if fallback_key:
        return fallback_key, "keyring"
    label = AI_PROVIDER_LABELS[normalized]
    raise ValueError(f"Missing {label} API key in {getattr(settings.ai, 'keys_path', 'data/ai_keys.local.json')}")


def ai_provider_options(settings: object) -> list[dict[str, object]]:
    """Return public provider option metadata without exposing keys."""

    config = AIKeyConfig.from_file(getattr(settings.ai, "keys_path", "data/ai_keys.local.json"))
    file_configured = config.configured_providers() if config is not None else set()
    keystore = KeyStore(settings.security.keyring_service)
    options = []
    for provider, label in AI_PROVIDER_LABELS.items():
        source = "file" if provider in file_configured else None
        configured = provider in file_configured
        if not configured and keystore.get_secret(_KEYRING_NAMES[provider]):
            configured = True
            source = "keyring"
        options.append(
            {
                "provider": provider,
                "label": label,
                "configured": configured,
                "source": source or "missing",
            }
        )
    return options


def _parse_provider_record(name: str, record: object) -> AIProviderKey | None:
    provider = normalize_ai_provider(name)
    label = AI_PROVIDER_LABELS[provider]
    enabled = True
    api_key = ""
    if isinstance(record, str):
        api_key = record.strip()
    elif isinstance(record, dict):
        enabled = bool(record.get("enabled", True))
        label = str(record.get("label") or label).strip() or label
        api_key = str(record.get("api_key") or record.get("key") or record.get("token") or "").strip()
    else:
        return None

    if not enabled or api_key.lower() in _PLACEHOLDERS:
        return None
    return AIProviderKey(provider=provider, label=label, api_key=api_key)


def _optional_normalized_provider(value: object) -> str | None:
    if value is None:
        return None
    return normalize_ai_provider(str(value))
