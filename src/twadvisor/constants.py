"""Project-wide constants."""

from zoneinfo import ZoneInfo

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_CONFIG_PATH = "config/default.toml"
USER_CONFIG_PATH = "config/user.toml"
APP_NAME = "TwStockAdvisor"

DISCLAIMER_LINES = (
    "[Disclaimer] AI-assisted analysis for research and personal reference only.",
    "[Disclaimer] Suggestions are not investment advice.",
    "[Disclaimer] Past performance does not guarantee future results.",
    "[Disclaimer] This tool never places orders automatically.",
)
