---
name: twstockadvisor
description: Work on the TwStockAdvisor Taiwan stock AI advisor repo. Use when Codex needs project-local guidance for modifying, validating, operating, documenting, or reporting status for this repository, including CLI, FastAPI Web UI, portfolio import, AI analysis, data fetchers, storage, performance reports, backtesting, provider keys, and Git workflow.
---

# TwStockAdvisor

## Project Anchor

Use this skill for this repository:

```powershell
cd E:\TwStockAdvisor
```

Remote:

```text
https://github.com/love0835/twStockAdvisor.git
```

This project is a local Taiwan stock AI advisor with CLI and FastAPI Web UI. It supports portfolio import, quotes/K-line data, indicators, AI analysis, validation, notifications, SQLite persistence, performance reports, backtests, and optional OpenAI/Gemini analyzer providers.

## Current State

Completed phases:

- Phase 1: project skeleton, Typer CLI, settings, keyring, Pydantic models
- Phase 2: data fetchers, market calendar, cache, technical indicators
- Phase 3: portfolio import/show, costs, PnL, risk validators
- Phase 4: Claude analyzer, prompts, structured output, token usage
- Phase 5: scheduler and console/Discord notification flow
- Phase 6: SQLAlchemy/SQLite storage and performance report
- Phase 7: backtest engine and paper trader
- Phase 8: OpenAI/Gemini analyzer support and FastAPI Web UI

Recent delivered behavior:

- Web strategy labels are Traditional Chinese.
- Web analysis action labels are localized: `buy` -> `買進`, `sell` -> `賣出`, `hold` -> `持有`, `watch` -> `觀察`.
- Web analysis shows progress while running.
- Web analysis caches analysis inputs for 10 minutes and avoids unnecessary K-line fetches.
- `twstock` history fetch avoids repeated yearly/monthly duplication.

## Security Rules

Never write API keys, broker credentials, account numbers, or private portfolio data into Git-tracked files.

Use the OS keyring through:

```powershell
uv run --python 3.11 python -m twadvisor keys set anthropic
uv run --python 3.11 python -m twadvisor keys set openai
uv run --python 3.11 python -m twadvisor keys set gemini
uv run --python 3.11 python -m twadvisor keys set finmind
```

Private runtime data belongs under `data/`, which is ignored by Git. Treat `data/portfolio.json`, `data/twadvisor.db`, and broker-derived CSV files as private local files and do not commit them.

Before committing changes that touch config, storage, web forms, or examples, check:

```powershell
git status --short
git ls-files
git check-ignore -v data/portfolio.json data/twadvisor.db
```

## Common Commands

Run all tests:

```powershell
uv run --python 3.11 pytest tests -v --cov=src/twadvisor --cov-report=term-missing
```

Start Web UI:

```powershell
uv run --python 3.11 python -m uvicorn twadvisor.web.app:create_app --factory --host 127.0.0.1 --port 8010
```

Web URLs:

```text
http://127.0.0.1:8010/
http://127.0.0.1:8010/docs
```

Import portfolio:

```powershell
uv run --python 3.11 python -m twadvisor portfolio import --file data/taishin_portfolio.csv --cash 260576.0
```

Show portfolio:

```powershell
uv run --python 3.11 python -m twadvisor portfolio show
```

Analyze:

```powershell
uv run --python 3.11 python -m twadvisor analyze --strategy swing --watchlist 2330
```

Report:

```powershell
uv run --python 3.11 python -m twadvisor report --period 30d
```

Backtest:

```powershell
uv run --python 3.11 python -m twadvisor backtest --strategy swing --from 2024-01-01 --to 2024-12-31
```

## Web UI Notes

Web UI files:

```text
src/twadvisor/web/
src/twadvisor/web/static/index.html
src/twadvisor/web/static/app.js
src/twadvisor/web/static/styles.css
```

User-facing text should be Traditional Chinese. Preserve backend enum values in API payloads and translate for display unless a backend schema change is explicitly requested.

Strategy labels:

- `daytrade`: 當沖 / 日內交易
- `swing`: 短線波段
- `position`: 中期波段 / 部位交易
- `longterm`: 長期投資
- `dividend`: 存股 / 股息策略

Action labels:

- `buy`: 買進
- `sell`: 賣出
- `hold`: 持有
- `watch`: 觀察

If the user says the Web UI has no response, test the HTTP endpoint directly and add visible loading/error state before changing deeper logic.

## Portfolio Import Format

Use this standard CSV shape:

```csv
symbol,qty,avg_cost,account_type,opened_at
2330,1000,580,cash,2025-01-02
```

Meanings:

- `symbol`: stock symbol
- `qty`: shares, not lots
- `avg_cost`: average cost
- `account_type`: usually `cash`
- `opened_at`: ISO date; use an approximate/import date if the broker does not provide the original opened date

For broker screenshots or exports, convert into this schema and place private output under `data/`.

## Implementation Pointers

Key modules:

- `src/twadvisor/cli.py`: Typer commands
- `src/twadvisor/models.py`: core Pydantic models and enums
- `src/twadvisor/settings.py`: TOML settings loader
- `src/twadvisor/fetchers/`: FinMind, twstock, Yahoo fetchers
- `src/twadvisor/analyzer/`: Claude/OpenAI/Gemini analyzers
- `src/twadvisor/portfolio/`: CSV import, cost, PnL
- `src/twadvisor/risk/`: validators and guardrails
- `src/twadvisor/storage/`: SQLAlchemy models and repository
- `src/twadvisor/performance/metrics.py`: metrics
- `src/twadvisor/backtest/`: historical simulation and paper trader
- `src/twadvisor/web/`: FastAPI routes and static UI

Prefer existing patterns over new frameworks. Keep CLI and Web behavior aligned by reusing core modules rather than duplicating finance logic in frontend code.

## Validation Workflow

For small Web-only changes:

```powershell
uv run --python 3.11 pytest tests/test_web.py -v
```

For data fetcher changes:

```powershell
uv run --python 3.11 pytest tests/test_fetchers.py -v
```

For release-ready changes:

```powershell
uv run --python 3.11 pytest tests -v --cov=src/twadvisor --cov-report=term-missing
```

When changing live Web behavior, restart the local server and verify:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/health
```

## Git Workflow

Before committing:

1. Run relevant tests.
2. Check `git status --short`.
3. Ensure no private files under `data/` are staged.
4. Commit with concise conventional messages.
5. Push to `origin main`.
