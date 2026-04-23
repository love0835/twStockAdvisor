"""Project-wide constants."""

from zoneinfo import ZoneInfo

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_CONFIG_PATH = "config/default.toml"
USER_CONFIG_PATH = "config/user.toml"
DEFAULT_PORTFOLIO_PATH = "data/portfolio.json"
APP_NAME = "TwStockAdvisor"

COMMISSION_RATE = 0.001425
COMMISSION_DISCOUNT = 0.28
COMMISSION_MIN = 20
TAX_RATE_STOCK = 0.003
TAX_RATE_DAYTRADE = 0.0015

DISCLAIMER_LINES = (
    "[Disclaimer] AI-assisted analysis for research and personal reference only.",
    "[Disclaimer] Suggestions are not investment advice.",
    "[Disclaimer] Past performance does not guarantee future results.",
    "[Disclaimer] This tool never places orders automatically.",
)
