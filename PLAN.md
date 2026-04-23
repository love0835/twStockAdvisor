# TwStockAdvisor — 台股 AI 分析助手 · 完整實作規格

> 本文件為 Codex / AI Coding Agent 的實作指引。每個模組皆附 **檔案路徑、介面簽章、資料格式、測試案例、驗收條件**，可獨立開發並循環驗證。
>
> 原則：
> - 僅提供**建議**，不自動下單。
> - 先 CLI，再 Web；先模擬盤，再接真實資料。
> - 每個模組都要有單元測試，整合測試以 Paper Trading 驗證。

---

## 0. 總覽

### 功能範圍
- 使用者提供 AI API Key（Claude / OpenAI / Gemini 擇一或多個）
- 使用者輸入持股與可用餘額
- 依使用者選擇的策略（當沖 / 短線 / 波段 / 長線 / 存股）產出：
  - 建議動作（買 / 賣 / 持有 / 觀望）
  - 標的、股數、限價、停損、停利
  - AI 理由 + 信心分數
- 每 X 秒輪詢一次（盤中）
- 通知：終端機 / Line Notify / Telegram
- 完整日誌與績效追蹤

### 非功能需求
- **安全**：API Key 使用 OS keyring 加密儲存
- **合規**：每次輸出附免責聲明
- **可測試**：所有外部呼叫皆可 mock
- **可觀測**：結構化 log（JSON）+ SQLite 決策紀錄

---

## 1. 技術棧

| 類別 | 選擇 | 版本 / 備註 |
|---|---|---|
| 語言 | Python | 3.11+ |
| 套件管理 | `uv` 或 `poetry` | 推薦 `uv`（快） |
| 資料抓取 | `FinMind`, `twstock`, `yfinance`, `requests` | FinMind 需免費註冊 |
| 指標計算 | `pandas-ta` | 比 `TA-Lib` 安裝簡單 |
| 資料處理 | `pandas`, `numpy` | — |
| 資料驗證 | `pydantic` v2 | — |
| 排程 | `APScheduler` | — |
| AI SDK | `anthropic`, `openai`, `google-generativeai` | 擇一起步 |
| CLI | `typer` + `rich` | 互動式顯示 |
| 儲存 | `sqlite3` + `sqlalchemy` | 單機即可 |
| 設定檔 | `pydantic-settings` + `.toml` | — |
| Keyring | `keyring` | Windows Credential Manager |
| 測試 | `pytest`, `pytest-asyncio`, `pytest-mock`, `responses` | — |
| 日誌 | `structlog` | JSON 輸出 |
| 通知 | `requests`（Line/Telegram webhook） | — |

---

## 2. 專案結構

```
TwStockAdvisor/
├── pyproject.toml                  # 專案設定 + 依賴
├── README.md
├── PLAN.md                         # 本文件
├── .env.example                    # 環境變數範例
├── config/
│   ├── default.toml                # 預設設定
│   └── user.toml                   # 使用者覆寫（gitignore）
├── src/
│   └── twadvisor/
│       ├── __init__.py
│       ├── __main__.py             # python -m twadvisor
│       ├── cli.py                  # typer CLI 入口
│       ├── settings.py             # pydantic-settings
│       ├── models.py               # 全域 Pydantic 資料模型
│       ├── constants.py            # 常數（手續費、稅率、市場時段）
│       │
│       ├── fetchers/               # 資料抓取層
│       │   ├── __init__.py
│       │   ├── base.py             # BaseFetcher 抽象類別
│       │   ├── finmind.py          # FinMind 實作
│       │   ├── twstock_fetcher.py  # twstock 實作
│       │   ├── yahoo.py            # Yahoo Finance 備援
│       │   ├── market_calendar.py  # 交易日/時段判斷
│       │   └── cache.py            # 本地快取（避免重複請求）
│       │
│       ├── indicators/             # 技術指標
│       │   ├── __init__.py
│       │   ├── technical.py        # MA, KD, MACD, RSI, BBands
│       │   └── chip.py             # 三大法人、融資券變化
│       │
│       ├── portfolio/              # 持倉與資金
│       │   ├── __init__.py
│       │   ├── manager.py          # PortfolioManager
│       │   ├── cost.py             # 手續費 / 證交稅 計算
│       │   └── pnl.py              # 已實現 / 未實現損益
│       │
│       ├── risk/                   # 風險管理
│       │   ├── __init__.py
│       │   ├── position_sizer.py   # 部位計算（Kelly / 固定比例）
│       │   ├── guardrails.py       # 漲跌停、單日虧損上限、部位上限
│       │   └── validators.py       # AI 輸出驗證（股號、價格合理性）
│       │
│       ├── analyzer/               # AI 分析層
│       │   ├── __init__.py
│       │   ├── base.py             # BaseAnalyzer 抽象類別
│       │   ├── claude.py           # Anthropic
│       │   ├── openai_analyzer.py  # OpenAI
│       │   ├── gemini.py           # Google
│       │   ├── prompts/            # Prompt 模板
│       │   │   ├── system.md
│       │   │   ├── strategy_daytrade.md
│       │   │   ├── strategy_swing.md
│       │   │   ├── strategy_longterm.md
│       │   │   └── strategy_dividend.md
│       │   └── schema.py           # AI 結構化輸出 schema
│       │
│       ├── scheduler/              # 排程
│       │   ├── __init__.py
│       │   └── runner.py           # APScheduler 包裝
│       │
│       ├── notifier/               # 通知
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── console.py
│       │   └── discord.py          # Webhook + （可選）Bot
│       │
│       ├── storage/                # 儲存
│       │   ├── __init__.py
│       │   ├── db.py               # SQLAlchemy 引擎
│       │   ├── models_orm.py       # ORM models
│       │   └── repo.py             # Repository pattern
│       │
│       ├── backtest/               # 回測
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   └── paper_trader.py
│       │
│       ├── performance/            # 績效分析
│       │   ├── __init__.py
│       │   └── metrics.py          # 勝率、Sharpe、最大回撤
│       │
│       └── security/               # 安全
│           ├── __init__.py
│           └── keystore.py         # keyring 包裝
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── finmind_quote.json
│   │   ├── portfolio_sample.toml
│   │   └── ai_response_sample.json
│   ├── unit/
│   │   ├── test_fetchers.py
│   │   ├── test_indicators.py
│   │   ├── test_portfolio.py
│   │   ├── test_risk.py
│   │   ├── test_analyzer.py
│   │   ├── test_validators.py
│   │   └── test_cost.py
│   └── integration/
│       ├── test_end_to_end.py
│       └── test_paper_trading.py
│
└── scripts/
    ├── init_db.py                  # 初始化 SQLite
    ├── import_portfolio.py         # CSV 匯入持倉
    └── backfill_history.py         # 補歷史資料
```

---

## 3. 資料模型（`src/twadvisor/models.py`）

> 所有跨模組傳遞的資料**必須**用 Pydantic model，禁止 dict 亂傳。

```python
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class Strategy(str, Enum):
    DAYTRADE = "daytrade"       # 當沖
    SWING = "swing"             # 短線 3-10 日
    POSITION = "position"       # 波段 數週
    LONGTERM = "longterm"       # 長線 月~年
    DIVIDEND = "dividend"       # 存股


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class Quote(BaseModel):
    """即時報價"""
    symbol: str                       # 股票代號 e.g. "2330"
    name: str                         # 股票名稱
    price: Decimal                    # 成交價
    open: Decimal
    high: Decimal
    low: Decimal
    prev_close: Decimal
    volume: int                       # 成交量（張）
    bid: Decimal
    ask: Decimal
    limit_up: Decimal                 # 漲停價
    limit_down: Decimal               # 跌停價
    timestamp: datetime
    is_suspended: bool = False


class Position(BaseModel):
    """持倉"""
    symbol: str
    qty: int                          # 股數（非張數）
    avg_cost: Decimal                 # 平均成本
    account_type: Literal["cash", "margin", "short"] = "cash"
    opened_at: date

    @property
    def cost_basis(self) -> Decimal:
        return self.avg_cost * self.qty


class Portfolio(BaseModel):
    """投資組合快照"""
    cash: Decimal                     # 可用餘額
    positions: list[Position]
    updated_at: datetime

    def total_cost(self) -> Decimal:
        return sum((p.cost_basis for p in self.positions), Decimal(0))


class TechnicalIndicators(BaseModel):
    """技術指標快照"""
    symbol: str
    ma5: Optional[Decimal]
    ma20: Optional[Decimal]
    ma60: Optional[Decimal]
    kd_k: Optional[Decimal]
    kd_d: Optional[Decimal]
    macd: Optional[Decimal]
    macd_signal: Optional[Decimal]
    rsi14: Optional[Decimal]
    bband_upper: Optional[Decimal]
    bband_lower: Optional[Decimal]
    volume_ratio: Optional[Decimal]   # 量比（當日量 / 5日均量）


class ChipData(BaseModel):
    """籌碼面"""
    symbol: str
    foreign_net: int                  # 外資買賣超（張）
    trust_net: int                    # 投信
    dealer_net: int                   # 自營商
    margin_balance: int               # 融資餘額變化
    short_balance: int                # 融券餘額變化
    date: date


class Recommendation(BaseModel):
    """AI 產出的建議（結構化）"""
    symbol: str
    action: Action
    qty: int = Field(0, ge=0)         # 股數（含零股）
    order_type: OrderType = OrderType.LIMIT
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    reason: str                       # AI 理由（繁體中文）
    confidence: float = Field(ge=0.0, le=1.0)
    strategy: Strategy
    generated_at: datetime

    @field_validator("qty")
    @classmethod
    def check_qty_for_action(cls, v, info):
        action = info.data.get("action")
        if action in (Action.BUY, Action.SELL) and v == 0:
            raise ValueError("buy/sell 必須指定 qty")
        return v


class AnalysisRequest(BaseModel):
    """送給 AI 的輸入"""
    strategy: Strategy
    portfolio: Portfolio
    quotes: dict[str, Quote]
    indicators: dict[str, TechnicalIndicators]
    chips: dict[str, ChipData]
    watchlist: list[str]              # 想分析的股票代號
    risk_preference: Literal["conservative", "moderate", "aggressive"]
    max_position_pct: float = 0.2     # 單檔部位上限（佔總資產）


class AnalysisResponse(BaseModel):
    """AI 輸出"""
    recommendations: list[Recommendation]
    market_view: str                  # 大盤看法
    warnings: list[str] = []
    raw_prompt_tokens: int = 0
    raw_completion_tokens: int = 0
```

---

## 4. 設定檔（`config/default.toml`）

```toml
[app]
timezone = "Asia/Taipei"
log_level = "INFO"
db_path = "./data/twadvisor.db"

[market]
# 盤中輪詢間隔（秒），依策略不同
poll_interval_daytrade = 5
poll_interval_swing = 60
poll_interval_longterm = 300

[fetcher]
primary = "finmind"                 # finmind | twstock | yahoo
fallback = ["twstock", "yahoo"]
cache_ttl_quote = 3                 # 報價快取秒數
cache_ttl_indicators = 300

[ai]
provider = "claude"                 # claude | openai | gemini
model_claude = "claude-sonnet-4-6"
model_openai = "gpt-4o"
model_gemini = "gemini-2.0-flash"
temperature = 0.2
max_output_tokens = 2000
use_prompt_cache = true             # Anthropic only

[risk]
max_position_pct = 0.20             # 單檔上限佔總資產
max_daily_loss_pct = 0.02           # 單日最大虧損 2%
stop_loss_default_pct = 0.05        # 預設停損 5%
take_profit_default_pct = 0.10
risk_preference = "moderate"

[cost]
commission_rate = 0.001425          # 手續費
commission_discount = 0.28          # 券商折扣（2.8 折）
commission_min = 20                 # 最低手續費
tax_rate_stock = 0.003              # 一般現股賣出
tax_rate_daytrade = 0.0015          # 當沖賣出

[notifier]
channels = ["console"]              # console | discord

[notifier.discord]
mode = "webhook"                    # webhook（一般通知）| bot（雙向互動，future）
webhook_url_key = "discord_webhook" # 實際 URL 存 keyring，這裡只放 key 名稱
mention_user_id = ""                # 重要建議時 @使用者（Discord User ID）
embed_color_buy = 0x2ECC71          # 綠
embed_color_sell = 0xE74C3C         # 紅
embed_color_hold = 0x95A5A6         # 灰

[security]
keyring_service = "twadvisor"
```

使用者覆寫（`config/user.toml`）：
```toml
[ai]
provider = "claude"

[risk]
risk_preference = "conservative"
max_position_pct = 0.15

[notifier]
channels = ["console", "telegram"]
```

API Keys **不放 toml**，改用：
```bash
python -m twadvisor keys set anthropic
# 互動式輸入，存入 OS keyring
```

---

## 5. 核心模組規格

### 5.1 `fetchers/base.py`

```python
from abc import ABC, abstractmethod
from datetime import date
from twadvisor.models import Quote, ChipData

class BaseFetcher(ABC):
    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]: ...

    @abstractmethod
    async def get_kline(self, symbol: str, start: date, end: date) -> "pd.DataFrame": ...

    @abstractmethod
    async def get_chip(self, symbol: str, dt: date) -> ChipData: ...
```

**驗收**：
- `get_quotes(["2330", "2317"])` 回傳兩筆 `Quote`，價格 > 0
- 遇到無效代號 `"9999"` 丟 `SymbolNotFoundError`
- 非交易日/休市呼叫仍回傳前一交易日收盤（`is_suspended=False` 但 `timestamp` 為前日）

### 5.2 `fetchers/market_calendar.py`

```python
from datetime import datetime, time, date

class MarketCalendar:
    def is_trading_day(self, d: date) -> bool: ...
    def current_session(self, now: datetime) -> Literal[
        "pre_market",       # 08:30-09:00
        "regular",          # 09:00-13:30
        "post_market",      # 14:00-14:30（零股/盤後定價）
        "odd_lot",          # 09:00-13:30 盤中零股
        "closed"
    ]: ...
    def next_open(self, now: datetime) -> datetime: ...
```

**驗收**：2026 春節 `is_trading_day(date(2026,2,17))` 回傳 `False`。

### 5.3 `indicators/technical.py`

```python
import pandas as pd
from twadvisor.models import TechnicalIndicators

def compute_indicators(df: pd.DataFrame, symbol: str) -> TechnicalIndicators:
    """
    df: OHLCV DataFrame, index=date, cols=[open,high,low,close,volume]
    至少需 60 筆歷史資料才能算齊 MA60
    """
```

**驗收**：
- 給 120 筆模擬資料，產出的 `ma5 == df.close.tail(5).mean()`
- 資料不足 60 筆時，`ma60 is None` 但其他指標可計算

### 5.4 `portfolio/cost.py`

```python
from decimal import Decimal

def buy_cost(price: Decimal, qty: int, *, discount: float = 0.28) -> Decimal:
    """回傳買入總成本（含手續費）"""

def sell_proceeds(
    price: Decimal, qty: int, *,
    is_daytrade: bool = False,
    discount: float = 0.28,
) -> Decimal:
    """回傳賣出實收（扣手續費 + 證交稅）"""

def breakeven_price(buy_price: Decimal, *, discount: float = 0.28) -> Decimal:
    """回本價（含來回成本）"""
```

**驗收**：
- `buy_cost(Decimal("500"), 1000, discount=0.28) == Decimal("500000") + max(20, 500000*0.001425*0.28)`
- `sell_proceeds(Decimal("500"), 1000, is_daytrade=True)` 稅率用 0.0015

### 5.5 `risk/validators.py`

```python
from twadvisor.models import Recommendation, Quote, Portfolio

class ValidationError(Exception): ...

def validate_recommendation(
    rec: Recommendation,
    quote: Quote,
    portfolio: Portfolio,
    *,
    max_position_pct: float,
) -> list[str]:
    """回傳警告清單；致命錯誤丟 ValidationError"""
    # 檢查：
    # 1. symbol 必須在 quotes 中
    # 2. price 必須在漲跌停之間
    # 3. BUY: cash 足夠（含手續費）
    # 4. SELL: 持倉 qty 足夠
    # 5. qty 須為 1000 的倍數（非盤中零股時段）或 1~999（零股）
    # 6. 單檔部位上限檢查
    # 7. stop_loss < price < take_profit（BUY）
```

**驗收**：
- AI 建議買入但 cash 不足 → 丟 `ValidationError`
- AI 建議價格超過漲停 → 丟 `ValidationError`
- AI 建議股數非整張且非零股時段 → 警告
- 單檔部位將超過 20% → 警告

### 5.6 `analyzer/base.py`

```python
from abc import ABC, abstractmethod
from twadvisor.models import AnalysisRequest, AnalysisResponse

class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse: ...

    @abstractmethod
    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """回傳 (system_prompt, user_prompt)"""
```

### 5.7 `analyzer/claude.py`（範例實作）

關鍵點：
1. 使用 **structured output**（Anthropic tool use 或 JSON mode）
2. 啟用 **prompt caching**（system prompt + 策略說明快取）
3. 失敗重試（指數退避，最多 3 次）
4. Token 用量記錄到 DB

```python
import anthropic
from twadvisor.analyzer.base import BaseAnalyzer
from twadvisor.models import AnalysisRequest, AnalysisResponse, Recommendation

class ClaudeAnalyzer(BaseAnalyzer):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        system, user = self.build_prompt(req)

        # 使用 tool use 強制結構化輸出
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},  # prompt cache
                }
            ],
            tools=[RECOMMENDATION_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_recommendations"},
            messages=[{"role": "user", "content": user}],
        )
        return self._parse(response)
```

### 5.8 `analyzer/prompts/system.md`

```markdown
你是專業的台股分析助手。你的建議會被自動驗證器檢查，若違反以下規則整筆建議會被丟棄：

## 硬性規則
1. 僅能建議**台灣上市櫃**個股，代號必須在使用者 watchlist 或持倉中
2. 價格必須在當日漲跌停區間內
3. 股數：一般交易時段為 1000 股倍數（整張）；若使用零股需標註
4. 必須提供 `stop_loss` 與 `take_profit`（除非 action=hold/watch）
5. 單檔部位不得超過使用者設定的上限
6. 不保證獲利，不使用「必漲」「穩賺」等字眼
7. 輸出必須為繁體中文

## 策略對應
- daytrade：當日買賣，停損 1-2%，停利 2-3%
- swing：持有 3-10 日，停損 3-5%，停利 5-10%
- position：持有數週，關注均線與產業趨勢
- longterm：持有月~年，以基本面為主
- dividend：存股，關注殖利率與配息穩定度

## 輸出格式
使用工具 `submit_recommendations` 回傳，禁止自由文本。
```

### 5.9 `analyzer/schema.py`

```python
RECOMMENDATION_TOOL_SCHEMA = {
    "name": "submit_recommendations",
    "description": "提交台股投資建議",
    "input_schema": {
        "type": "object",
        "properties": {
            "market_view": {"type": "string", "description": "大盤看法（繁中，100字內）"},
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "pattern": "^[0-9]{4,6}$"},
                        "action": {"enum": ["buy", "sell", "hold", "watch"]},
                        "qty": {"type": "integer", "minimum": 0},
                        "order_type": {"enum": ["limit", "market"]},
                        "price": {"type": "number"},
                        "stop_loss": {"type": "number"},
                        "take_profit": {"type": "number"},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["symbol", "action", "reason", "confidence"],
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["market_view", "recommendations"],
    },
}
```

### 5.10 `scheduler/runner.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class AdvisorRunner:
    def __init__(self, settings, fetcher, analyzer, portfolio_mgr, notifier, repo):
        ...

    async def tick(self):
        """每個輪詢週期執行一次"""
        # 1. 判斷市場時段，非交易時段則跳過
        # 2. 抓取持倉 + watchlist 的 quotes
        # 3. 計算/取用快取的 indicators
        # 4. 組 AnalysisRequest
        # 5. 呼叫 analyzer
        # 6. 對每筆 recommendation 跑 validator
        # 7. 通過的存 DB，推送 notifier
        # 8. 記錄 token 用量、延遲

    def start(self, strategy: Strategy):
        interval = self._resolve_interval(strategy)
        self.scheduler.add_job(self.tick, "interval", seconds=interval)
        self.scheduler.start()
```

### 5.10.1 `notifier/discord.py`

**設計原則**：
- 使用 Discord Webhook（不需 Bot Token，使用者在頻道設定 → 整合 → 建立 Webhook 即可）
- 非同步送出（`aiohttp` 或 `httpx.AsyncClient`），避免阻塞 tick
- Token bucket 限流：30 requests / 60 秒（Discord webhook 限制）

**介面**：
```python
from twadvisor.models import Recommendation
from twadvisor.notifier.base import BaseNotifier

class DiscordWebhookNotifier(BaseNotifier):
    def __init__(self, webhook_url: str, mention_user_id: str = "", color_map: dict = None):
        ...

    async def notify(self, recs: list[Recommendation], market_view: str) -> None:
        """送出一則 Discord 訊息，含多個 Embed（每個建議一個 Embed）"""
```

**Embed 格式（每筆建議）**：
```json
{
  "title": "🟢 買進 2454 聯發科",
  "color": 3066993,
  "fields": [
    {"name": "動作", "value": "買進 1000 股", "inline": true},
    {"name": "限價", "value": "NT$ 1205", "inline": true},
    {"name": "信心", "value": "78%", "inline": true},
    {"name": "停損 / 停利", "value": "1140 / 1330", "inline": false},
    {"name": "理由", "value": "KD 黃金交叉 + 外資連 5 買超...", "inline": false}
  ],
  "footer": {"text": "策略：swing · 2026-04-23 10:15:30"}
}
```

**Payload 範例**：
```python
payload = {
    "content": f"<@{mention_user_id}> 新建議" if mention_user_id else None,
    "username": "TwStockAdvisor",
    "embeds": [...],  # 最多 10 個 embed / 則訊息
}
```

**限流處理**：
- 收到 429 時依 `Retry-After` header 退避
- 建議清單 > 10 筆時自動分多則訊息送出

### 5.11 `storage/models_orm.py`

SQLAlchemy 表：
- `recommendations`：每筆 AI 建議（含 raw prompt/response）
- `portfolio_snapshots`：每日持倉快照
- `trades`：使用者實際成交（手動記錄）
- `token_usage`：AI API 花費
- `performance_daily`：每日績效

### 5.12 CLI（`cli.py`）

```bash
# 初始化
twadvisor init

# 設定 API Key / Secret（互動式，存入 keyring）
twadvisor keys set anthropic
twadvisor keys set finmind
twadvisor keys set discord_webhook  # 貼上 Discord Webhook URL

# 匯入持倉（CSV）
twadvisor portfolio import --file portfolio.csv

# 檢視持倉
twadvisor portfolio show

# 單次分析（不排程）
twadvisor analyze --strategy swing --watchlist 2330,2317,2454

# 啟動排程
twadvisor run --strategy daytrade --interval 5

# 回測
twadvisor backtest --strategy swing --from 2025-01-01 --to 2025-12-31

# 績效報告
twadvisor report --period 30d
```

---

## 6. Prompt 範例（完整流程）

輸入給 Claude 的 `user_prompt`：
```
## 策略：短線（swing，持有 3-10 日）
## 風險偏好：moderate
## 可用餘額：NT$ 200,000
## 單檔上限：20%（即 NT$ 40,000）

## 目前持倉
| 代號 | 股數 | 均價 | 現價 | 浮動損益 |
|---|---|---|---|---|
| 2330 | 1000 | 580 | 595 | +15,000 |

## Watchlist 即時資料
### 2454 聯發科
- 現價 1205（+1.2%），昨收 1190，漲停 1309，跌停 1071
- 成交量 8500 張（5日均量 6200）
- MA5 1180，MA20 1150，MA60 1080
- KD: K=75, D=68（黃金交叉）
- RSI14=62
- 外資近5日買超 3500 張

### 2317 鴻海
- 現價 210（-0.5%）...

## 任務
請針對此持倉與 watchlist，依 swing 策略給出建議。使用 submit_recommendations 工具回傳。
```

---

## 7. 測試策略

### 7.1 單元測試原則
- 所有外部呼叫（HTTP、AI API、DB）皆用 mock
- 使用 `responses` 套件 mock HTTP
- AI 回應用 `tests/fixtures/ai_response_sample.json`

### 7.2 關鍵測試案例

**`tests/unit/test_fetchers.py`**
- [ ] `test_get_quote_success`：mock FinMind 回應，驗證 Pydantic 解析正確
- [ ] `test_get_quote_symbol_not_found`：無效代號丟錯
- [ ] `test_fallback_to_twstock`：primary 失敗自動切備援
- [ ] `test_cache_hit`：2 秒內第二次呼叫不打 API

**`tests/unit/test_indicators.py`**
- [ ] `test_ma_calculation`：給定資料驗證 MA 值
- [ ] `test_insufficient_data`：資料不足 60 筆 ma60 為 None
- [ ] `test_kd_golden_cross`：K 線上穿 D 線正確偵測

**`tests/unit/test_cost.py`**
- [ ] `test_buy_cost_includes_commission`
- [ ] `test_daytrade_tax_rate`
- [ ] `test_minimum_commission_20`

**`tests/unit/test_validators.py`**
- [ ] `test_reject_price_above_limit_up`
- [ ] `test_reject_insufficient_cash`
- [ ] `test_reject_oversold_position`
- [ ] `test_warn_position_pct_exceeded`
- [ ] `test_reject_odd_lot_during_regular_session`

**`tests/unit/test_analyzer.py`**
- [ ] `test_prompt_includes_all_portfolio`
- [ ] `test_parse_tool_use_response`
- [ ] `test_retry_on_rate_limit`
- [ ] `test_prompt_cache_enabled`

**`tests/integration/test_end_to_end.py`**
- [ ] `test_full_tick_cycle`：mock fetcher + mock analyzer，驗證 tick 完整流程
- [ ] `test_paper_trading_one_day`：跑一天的模擬交易，驗證持倉與現金變化

### 7.3 覆蓋率目標
- `fetchers/`、`indicators/`、`portfolio/`、`risk/`：**90%+**
- `analyzer/`：**80%+**（扣除真實 API 呼叫）
- 整體：**85%+**

---

## 8. 開發階段與驗收條件

### Phase 1 — 骨架（1–2 天）
**任務**：
- 建立專案結構、`pyproject.toml`、`pytest` 設定
- 實作 `models.py`、`settings.py`、`constants.py`
- CLI 骨架（`twadvisor init`、`twadvisor keys set`）
- Keyring 整合

**驗收**：
- `pip install -e .` 成功
- `python -m twadvisor --help` 顯示命令
- `pytest` 跑過（即使只有 placeholder test）

### Phase 2 — 資料層（2–3 天）
**任務**：
- `fetchers/finmind.py` + `twstock_fetcher.py` + `yahoo.py`
- `market_calendar.py`
- `cache.py`（SQLite 或 `diskcache`）
- `indicators/technical.py`

**驗收**：
- `twadvisor quote 2330` 印出即時報價
- `twadvisor indicators 2330` 印出技術指標表格
- 非交易日呼叫回傳前一交易日資料
- 單元測試覆蓋率 90%+

### Phase 3 — 持倉與風控（2 天）
**任務**：
- `portfolio/manager.py`、`cost.py`、`pnl.py`
- `risk/position_sizer.py`、`guardrails.py`、`validators.py`
- CSV 匯入（`scripts/import_portfolio.py`）

**驗收**：
- `twadvisor portfolio import --file tests/fixtures/portfolio_sample.csv` 成功
- `twadvisor portfolio show` 顯示損益表格
- 所有 validator 測試通過

### Phase 4 — AI 分析層（3–4 天）
**任務**：
- `analyzer/base.py`、`claude.py`
- Prompt 模板（五種策略）
- Tool use schema + response parsing
- 重試邏輯
- Token 用量記錄

**驗收**：
- `twadvisor analyze --strategy swing --watchlist 2330` 回傳結構化建議
- AI 回傳非法股號時被 validator 擋下
- Token 用量寫入 DB

### Phase 5 — 排程與通知（1–2 天）
**任務**：
- `scheduler/runner.py`
- `notifier/console.py`（`rich` 彩色表格）
- `notifier/discord.py`（Webhook 模式）
  - 使用 Discord Embed 格式，依 action 著色（買=綠、賣=紅、持有=灰）
  - 超過 Discord 2000 字限制時自動分段
  - 失敗時 log 但不中斷 tick（退化為僅 console）
  - 速率限制處理（Discord webhook 30 req/min）
- Ctrl+C 優雅關閉

**驗收**：
- `twadvisor run --strategy daytrade --interval 10` 每 10 秒跑一次
- 建議同時出現在 console 與 Discord 頻道
- Discord 訊息為 Embed 格式，含：標的、action（彩色）、股數、限價、停損停利、信心分數、AI 理由
- Webhook URL 錯誤或 Discord 服務掛掉時，tick 不中斷
- 休市時段自動跳過但不退出

### Phase 6 — 儲存與績效（2 天）
**任務**：
- `storage/` 完整 ORM
- `performance/metrics.py`
- `twadvisor report` 命令

**驗收**：
- 所有建議、token 用量、持倉快照寫入 SQLite
- `twadvisor report --period 30d` 顯示勝率、累計盈虧

### Phase 7 — 回測與 Paper Trading（3 天）
**任務**：
- `backtest/engine.py`：吃歷史 K 線，跑策略
- `backtest/paper_trader.py`：即時模擬交易
- 績效對照表（AI 建議 vs 買入持有）

**驗收**：
- `twadvisor backtest --strategy swing --from 2024-01-01 --to 2024-12-31` 產出報告
- 報告含：勝率、盈虧比、最大回撤、Sharpe、與大盤對比

### Phase 8 — 多 AI / Web UI（optional）
- `openai_analyzer.py`、`gemini.py`
- FastAPI + React 後台（另開 `web/` 目錄）

---

## 9. 給 Codex 的執行指引

### 9.1 開發迴圈
```
for phase in [1, 2, 3, 4, 5, 6, 7]:
    1. 閱讀 PLAN.md 該 phase 章節
    2. 依「任務」清單實作
    3. 執行 `pytest tests/ -v`
    4. 執行 phase 「驗收」清單的手動命令
    5. 所有驗收通過 → commit，進下一階段
    6. 任何失敗 → 修復，goto 3
```

### 9.2 每階段 commit 訊息格式
```
feat(phase-N): <模組> — <簡述>

- 實作 XXX
- 測試 YYY（覆蓋率 Z%）
- 通過驗收清單 1,2,3
```

### 9.3 禁止事項
- ❌ 不要寫 mock 取代真實實作
- ❌ 不要跳過測試直接 commit
- ❌ 不要引入 PLAN.md 未列出的重型依賴（需先更新本文件）
- ❌ 不要把 API Key 寫入任何 config 檔
- ❌ 不要自動下單邏輯（本專案僅建議）

### 9.4 遇到阻礙
1. FinMind 免費額度用完（每日 600 次）— 啟用 cache，並用 `twstock` / `yahoo` 作 fallback
2. 歷史資料不足 — `scripts/backfill_history.py` 補齊（FinMind `TaiwanStockPrice` dataset）
3. AI 回傳格式不穩 — 強制 tool use，不要 JSON mode
4. Windows keyring 問題 — 降級成加密 .env（AES-256 + master password）
5. Discord Webhook 2000 字限制 — 超過時拆多則送出，或改用 embed.description（4096 字）
6. Discord 速率限制（30/min/webhook）— `notifier/discord.py` 內建 token bucket

---

## 10. 免責聲明（每次 CLI 啟動顯示）

```
⚠️  本工具為 AI 輔助分析，僅供學術研究與個人參考。
⚠️  所有建議不構成投資推薦，投資決策請自行負責。
⚠️  過去績效不代表未來表現，交易有風險，入市需謹慎。
⚠️  本工具不進行自動下單，所有交易須使用者於券商端手動執行。
```

---

## 11. 未來擴充（不列入 MVP）

- 選擇權、期貨
- ETF 成分股連動分析
- LINE Bot 雙向互動（使用者回問「為什麼建議賣？」）
- 多使用者 SaaS 模式
- 券商 API 自動下單（需二階段確認）
- Backtesting 視覺化（Plotly Dash）
- 新聞情緒分析（抓 cnyes / MoneyDJ RSS → embedding → 分數）
- 同步 Notion / Google Sheets 交易日誌

---

**文件版本**：v1.0 · 2026-04-23
**維護**：此文件為單一真相來源；任何架構變更先改本文件再改碼。
