"""Application settings loading and merging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from twadvisor.constants import DEFAULT_CONFIG_PATH, USER_CONFIG_PATH


class AppSettings(BaseModel):
    """Application-level settings."""

    timezone: str = "Asia/Taipei"
    log_level: str = "INFO"
    db_path: str = "./data/twadvisor.db"


class MarketSettings(BaseModel):
    """Market polling settings."""

    poll_interval_daytrade: int = 5
    poll_interval_swing: int = 60
    poll_interval_longterm: int = 300


class FetcherSettings(BaseModel):
    """Fetcher settings."""

    primary: str = "finmind"
    fallback: list[str] = Field(default_factory=lambda: ["twstock", "yahoo"])
    cache_ttl_quote: int = 3
    cache_ttl_indicators: int = 300


class AISettings(BaseModel):
    """AI provider settings."""

    provider: str = "claude"
    model_claude: str = "claude-sonnet-4-6"
    model_openai: str = "gpt-4o"
    model_gemini: str = "gemini-2.0-flash"
    temperature: float = 0.2
    max_output_tokens: int = 2000
    use_prompt_cache: bool = True


class RiskSettings(BaseModel):
    """Risk management settings."""

    max_position_pct: float = 0.2
    max_daily_loss_pct: float = 0.02
    stop_loss_default_pct: float = 0.05
    take_profit_default_pct: float = 0.10
    risk_preference: str = "moderate"


class CostSettings(BaseModel):
    """Trading cost settings."""

    commission_rate: float = 0.001425
    commission_discount: float = 0.28
    commission_min: int = 20
    tax_rate_stock: float = 0.003
    tax_rate_daytrade: float = 0.0015


class DiscordSettings(BaseModel):
    """Discord notifier settings."""

    mode: str = "webhook"
    webhook_url_key: str = "discord_webhook"
    mention_user_id: str = ""
    embed_color_buy: int = 0x2ECC71
    embed_color_sell: int = 0xE74C3C
    embed_color_hold: int = 0x95A5A6


class NotifierSettings(BaseModel):
    """Notifier settings."""

    channels: list[str] = Field(default_factory=lambda: ["console"])
    discord: DiscordSettings = Field(default_factory=DiscordSettings)


class SecuritySettings(BaseModel):
    """Security settings."""

    keyring_service: str = "twadvisor"


class Settings(BaseSettings):
    """Merged application settings."""

    model_config = SettingsConfigDict(extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    market: MarketSettings = Field(default_factory=MarketSettings)
    fetcher: FetcherSettings = Field(default_factory=FetcherSettings)
    ai: AISettings = Field(default_factory=AISettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    cost: CostSettings = Field(default_factory=CostSettings)
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""

    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file when it exists."""

    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_settings(
    default_path: str | Path = DEFAULT_CONFIG_PATH,
    user_path: str | Path = USER_CONFIG_PATH,
) -> Settings:
    """Load merged settings from default and user config files."""

    default_data = _read_toml(Path(default_path))
    user_data = _read_toml(Path(user_path))
    merged = deep_merge(default_data, user_data)
    return Settings.model_validate(merged)
