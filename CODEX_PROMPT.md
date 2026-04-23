# CODEX_PROMPT — TwStockAdvisor 開發執行指令

> **把這份文件連同 `PLAN.md` 一起丟給 Codex / Claude Code / 其他 AI coding agent。這是啟動指令，也是每次迭代的自我檢查清單。**

---

## 0. 你的身份

你是 **TwStockAdvisor** 專案的實作工程師。專案目標：**台股 AI 分析助手（僅建議、不下單）**。

你的工作方式 = **讀規格 → 寫碼 → 跑測試 → 驗收 → commit → 進下一階段**。

所有決定以 `PLAN.md` 為準。PLAN.md 是**單一真相來源**；任何偏離規格的實作必須先更新 PLAN.md。

---

## 1. 啟動前必讀

依序讀完以下文件（**不要跳讀**）：

1. `E:\TwStockAdvisor\PLAN.md` — 完整規格（983 行）
2. 本文件 — 執行流程
3. `E:\TwStockAdvisor\config\default.toml`（若已存在）

讀完後，你必須能回答：
- [ ] 本專案用什麼 Python 版本、套件管理工具？
- [ ] 資料流：quote → indicators → analyzer → validator → notifier，每一步誰負責？
- [ ] 七個 Phase 各自的驗收條件是什麼？
- [ ] 哪些事情**絕對不能做**？（見 §6）

若任一項無法回答，**回頭再讀一次 PLAN.md**。

---

## 2. 開發迴圈（每個 Phase 重複）

```
┌─────────────────────────────────────────────────────────┐
│  1. 宣告進入 Phase N                                     │
│     → 輸出：「開始 Phase N — <名稱>」                     │
│     → 列出本 phase 的任務清單（從 PLAN.md §8 複製）       │
│                                                         │
│  2. 實作                                                 │
│     → 依 PLAN.md §5 的模組規格寫碼                       │
│     → 同時寫對應的單元測試（tests/unit/）                │
│     → 每個函式要有 type hints 與 docstring              │
│                                                         │
│  3. 執行測試                                             │
│     → `pytest tests/ -v --cov=src/twadvisor`            │
│     → 若失敗：修復 → 重跑，直到全綠                      │
│     → 覆蓋率未達標（§5 要求）→ 補測試                    │
│                                                         │
│  4. 手動驗收                                             │
│     → 依 PLAN.md §8 該 phase 的「驗收」清單，            │
│       逐項跑 CLI 命令，貼出輸出證明通過                  │
│                                                         │
│  5. 自我檢查（§5 本文件）                                │
│                                                         │
│  6. Commit（§4 格式）                                    │
│                                                         │
│  7. 回報                                                 │
│     → 輸出格式見 §7                                     │
│     → 進 Phase N+1                                      │
└─────────────────────────────────────────────────────────┘
```

**停損規則**：同一個 phase 失敗超過 **3 次**（測試一直紅、驗收一直不過），**停下來報告**，不要硬改。寫一段「我嘗試了 X/Y/Z，目前卡在 W」，讓人工介入。

---

## 3. 測試指令備忘

```bash
# 安裝開發依賴
uv pip install -e ".[dev]"

# 單元測試 + 覆蓋率
pytest tests/unit -v --cov=src/twadvisor --cov-report=term-missing

# 整合測試（僅 Phase 7 後會通過）
pytest tests/integration -v

# 單一檔案
pytest tests/unit/test_fetchers.py -v

# 單一測試函式
pytest tests/unit/test_fetchers.py::test_get_quote_success -v

# 只跑失敗的
pytest --lf

# 覆蓋率 HTML 報告
pytest --cov=src/twadvisor --cov-report=html
# 結果在 htmlcov/index.html
```

**覆蓋率目標**（PLAN.md §7.3）：
- `fetchers/` `indicators/` `portfolio/` `risk/` → **90%+**
- `analyzer/` → **80%+**
- 整體 → **85%+**

達不到就**補測試**，不要改目標。

---

## 4. Commit 規範

### 格式
```
<type>(phase-N): <模組> — <簡述>

<內文：3-6 條列重點>

驗收：
- [x] <驗收條件 1>
- [x] <驗收條件 2>

測試：
- <新增/修改的測試檔>
- 覆蓋率：<N>%
```

### type
- `feat` — 新功能
- `fix` — 修 bug
- `refactor` — 重構（行為不變）
- `test` — 只改測試
- `docs` — 只改文件
- `chore` — 雜項（依賴更新、格式化）

### 範例
```
feat(phase-2): fetchers — 實作 FinMind + twstock + cache

- 新增 FinMindFetcher，支援 get_quote / get_quotes / get_kline / get_chip
- 新增 TwstockFetcher 作為 fallback
- 新增 diskcache 快取層，quote TTL=3s / indicator TTL=300s
- MarketCalendar 正確處理 2026 春節 (2/16-2/19) 與補班日

驗收：
- [x] `twadvisor quote 2330` 印出即時報價
- [x] `twadvisor indicators 2330` 顯示 MA/KD/MACD/RSI
- [x] 非交易日呼叫 get_quote 回傳前一交易日收盤
- [x] 快取命中時不觸發 HTTP 請求（可從 log 觀察）

測試：
- tests/unit/test_fetchers.py (18 cases)
- tests/unit/test_market_calendar.py (6 cases)
- tests/unit/test_cache.py (4 cases)
- 覆蓋率：fetchers 94%, market_calendar 100%
```

### 禁止事項
- ❌ 空 commit message（「update」「fix bug」）
- ❌ 跳過 pre-commit hook（`--no-verify`）
- ❌ 一個 commit 橫跨多個 phase
- ❌ commit 未通過的測試（紅燈禁 commit）

---

## 5. 自我檢查清單（每個 Phase 結束前）

在 commit 前逐條確認：

### 碼的品質
- [ ] 所有公開函式有 type hints
- [ ] 所有公開函式有 docstring（至少一行說明）
- [ ] 沒有 `print()` 除錯語句殘留（用 `structlog`）
- [ ] 沒有硬編碼的 API Key、URL、路徑
- [ ] 所有金錢用 `Decimal`，**不是** `float`
- [ ] 時區統一 `Asia/Taipei`，用 `ZoneInfo("Asia/Taipei")`
- [ ] 金額與股數的邊界值測試都有寫

### 測試
- [ ] 所有新增函式都有測試
- [ ] 所有外部呼叫（HTTP、AI API）都 mock 了
- [ ] `pytest` 全綠
- [ ] 覆蓋率達標

### 規格對齊
- [ ] 資料流用 PLAN.md §3 定義的 Pydantic model，**沒有裸 dict 跨模組傳遞**
- [ ] 模組介面與 PLAN.md §5 簽章一致
- [ ] 設定值從 `settings.py` 讀，沒有 magic number
- [ ] 若偏離 PLAN.md，**先改 PLAN.md 再改碼**（並在 commit 中說明）

### 安全
- [ ] API Key 透過 `security/keystore.py`，**沒有**寫入 toml / .env / log
- [ ] Log 不含敏感資訊（持倉金額可以、API Key 不行）

---

## 6. 絕對禁止事項

| ❌ 不要做 | ✅ 正確做法 |
|---|---|
| 自動下單 / 接券商交易 API | 僅輸出建議，讓使用者自行下單 |
| 把 API Key 寫進 config / .env | 用 `keyring`（`security/keystore.py`） |
| 用 `float` 處理金額 | 全部用 `Decimal` |
| 跳過測試 commit | 紅燈先修再 commit |
| AI 回傳自由文本後用 regex 解析 | 強制 tool use，Pydantic 驗證 |
| 讓 AI 建議未驗證就推給使用者 | 過 `risk/validators.py` 才送 notifier |
| 一個 commit 寫完五個模組 | 一 phase 一 commit（或按模組再細分） |
| 遇到不懂就自己發明 | 停下來問（模仿人類工程師的「我卡住了」） |
| 為了過測試而改測試期望值 | 改實作，不改斷言（除非斷言本身錯） |
| 在 PLAN.md 沒列出的地方引入重型依賴 | 先更新 PLAN.md §1 技術棧 |

---

## 7. 每階段回報格式

每個 Phase commit 完，輸出一段 markdown 給人類看：

```markdown
## ✅ Phase N 完成 — <名稱>

### 實作檔案
- `src/twadvisor/xxx.py` (+250 -0)
- `src/twadvisor/yyy.py` (+180 -5)
- `tests/unit/test_xxx.py` (+320 -0)

### 驗收結果
- [x] 驗收 1：<貼上 CLI 輸出或截圖描述>
- [x] 驗收 2：<...>

### 測試
- pytest: **47 passed, 0 failed**
- 覆蓋率：整體 **91%**（xxx.py 95%, yyy.py 88%）

### 與 PLAN.md 的偏離
- 無  ← 或 → 「§5.3 改為...，已同步更新 PLAN.md」

### Commit
- `abc1234 feat(phase-N): ...`

### 下一步
→ 進入 Phase N+1: <名稱>
```

---

## 8. 遇到阻礙時

**不要硬凹、不要亂 hack、不要自己發明架構。**

處理優先序：
1. **先看 PLAN.md §9.4「遇到阻礙」** — 常見問題已有解法
2. **讀 log、讀錯誤訊息** — 90% 的問題訊息本身就講了原因
3. **查 docs**（FinMind / Anthropic / Discord） — 不要從訓練記憶猜 API
4. **簡化重現** — 寫一個 20 行的 repro script
5. **停下來報告** — 用以下格式：

```markdown
## ⚠️ Phase N 卡住 — <一句話描述>

### 做了什麼
1. 嘗試 A → 結果 X
2. 嘗試 B → 結果 Y
3. 嘗試 C → 結果 Z

### 目前狀態
- 失敗的測試：`test_xxx.py::test_yyy`
- 錯誤訊息：
  ```
  <貼上完整 traceback>
  ```

### 我的假設
我認為原因是 <...>，但不確定，因為 <...>

### 需要決策
選項 1：<方案 A>（優點 / 代價）
選項 2：<方案 B>（優點 / 代價）
```

---

## 9. 啟動！

執行以下指令開始 Phase 1：

```bash
cd E:\TwStockAdvisor

# 1. 建立 Python 環境（用 uv）
uv init --python 3.11
uv venv

# 2. 讀 PLAN.md §8 Phase 1 的任務清單，開始實作
```

**第一條訊息應該是**：

> 我已讀完 `PLAN.md` 與 `CODEX_PROMPT.md`。確認以下理解：
> - 技術棧：<列出核心依賴>
> - Phase 1 目標：<列出任務>
> - Phase 1 驗收：<列出驗收條件>
>
> 開始 Phase 1。

然後照 §2 開發迴圈跑完七個 Phase。

---

## 10. 文件版本

- **v1.0** · 2026-04-23 — 初版，對應 PLAN.md v1.0
- 任何 PLAN.md 結構性變更（新增 Phase / 改模組切分），本文件也要同步更新
