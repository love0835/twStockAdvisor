const panelMeta = {
  portfolio: ["持倉", "匯入現有持倉、現金與未實現損益"],
  analyze: ["分析", "執行單次 AI 分析，或掃描全市場推薦標的"],
  report: ["績效", "讀取資料庫內的每日績效紀錄"],
  backtest: ["回測", "用歷史 K 線檢查策略表現"],
};

const actionLabels = {
  buy: "買進",
  sell: "賣出",
  hold: "持有",
  watch: "觀察",
};

let portfolioSymbols = [];
let lastScannerSource = null;
let lastScannerSymbols = [];

function showPanel(panel) {
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panel);
  });
  Object.keys(panelMeta).forEach((key) => {
    document.getElementById(`${key}-panel`).classList.toggle("hidden", key !== panel);
  });
  document.getElementById("panel-title").textContent = panelMeta[panel][0];
  document.getElementById("panel-subtitle").textContent = panelMeta[panel][1];
}

function renderStats(targetId, rows) {
  const target = document.getElementById(targetId);
  target.innerHTML = "";
  rows.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    target.appendChild(card);
  });
}

function renderTable(tableId, rows) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  tbody.innerHTML = "";
  rows.forEach((cells) => {
    const tr = document.createElement("tr");
    cells.forEach((cell) => {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function storagePath() {
  const field = document.querySelector("#analyze-form input[name='storage_path']");
  return field ? field.value : "data/portfolio.json";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "請求失敗");
  }
  return data;
}

function setButtonLoading(button, loadingText) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = loadingText;
  return () => {
    button.disabled = false;
    button.textContent = originalText;
  };
}

function renderAnalysisResult(data, metaPrefix = "") {
  document.getElementById("market-view").textContent = data.market_view;
  document.getElementById("analyze-meta").textContent = `${metaPrefix}輸入 tokens: ${data.prompt_tokens}\n輸出 tokens: ${data.completion_tokens}`;
  renderTable(
    "analyze-table",
    data.recommendations.map((row) => [
      row.symbol,
      actionLabels[row.action] || row.action,
      String(row.qty),
      row.price,
      row.warnings,
      row.reason,
    ]),
  );
}

async function loadHealth() {
  try {
    await fetchJson("/api/health");
    document.getElementById("health-pill").textContent = "API 已連線";
  } catch (error) {
    document.getElementById("health-pill").textContent = "API 無法連線";
  }
}

document.querySelectorAll(".nav-btn").forEach((button) => {
  button.addEventListener("click", () => showPanel(button.dataset.panel));
});

document.getElementById("portfolio-import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  try {
    const data = await fetchJson("/api/portfolio/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("portfolio-import-result").textContent = JSON.stringify(data, null, 2);
    await loadPortfolio();
  } catch (error) {
    document.getElementById("portfolio-import-result").textContent = error.message;
  }
});

async function loadPortfolio() {
  try {
    const data = await fetchJson("/api/portfolio");
    portfolioSymbols = data.rows.map((row) => row.symbol);
    renderStats("portfolio-stats", [
      ["現金", data.cash],
      ["持股數", String(data.position_count)],
      ["總成本", data.total_cost],
      ["更新時間", data.updated_at],
    ]);
    renderTable(
      "portfolio-table",
      data.rows.map((row) => [
        row.symbol,
        row.qty,
        row.avg_cost,
        row.current_price,
        row.unrealized_pnl,
        row.unrealized_pnl_pct,
      ]),
    );
  } catch (error) {
    portfolioSymbols = [];
    renderStats("portfolio-stats", [["錯誤", error.message]]);
    renderTable("portfolio-table", []);
  }
}

document.getElementById("refresh-portfolio").addEventListener("click", loadPortfolio);

document.getElementById("analyze-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = event.submitter;
  const form = new FormData(event.target);
  const payload = {
    strategy: form.get("strategy"),
    watchlist: String(form.get("watchlist") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    storage_path: form.get("storage_path"),
  };
  const restoreButton = submitButton ? setButtonLoading(submitButton, "分析中...") : () => {};
  document.getElementById("market-view").textContent = "正在抓取行情與技術指標，接著呼叫 AI 分析...";
  document.getElementById("analyze-meta").textContent = "";
  renderTable("analyze-table", []);
  try {
    const data = await fetchJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderAnalysisResult(data);
  } catch (error) {
    document.getElementById("market-view").textContent = error.message;
    renderTable("analyze-table", []);
  } finally {
    restoreButton();
  }
});

function scannerPayload() {
  return {
    top_n: Number(document.getElementById("scanner-top-n").value || 5),
    exclude_holdings: document.getElementById("scanner-exclude-holdings").checked,
    exclude_etf: document.getElementById("scanner-exclude-etf").checked,
    foreign_consecutive_days: Number(document.getElementById("scanner-foreign-days").value || 3),
    storage_path: storagePath(),
  };
}

function updateAiDecisionButton() {
  const button = document.getElementById("scanner-ai-decision-btn");
  const hint = document.getElementById("scanner-decision-hint");
  button.disabled = lastScannerSymbols.length === 0;
  hint.textContent =
    lastScannerSymbols.length === 0
      ? "請先掃描出候選標的，再交給 AI 參考持倉與餘額。"
      : `將 ${lastScannerSymbols.length} 檔候選標的與 ${portfolioSymbols.length} 檔持倉一起交給 AI。`;
}

async function runScanner(source, button) {
  const restoreButton = setButtonLoading(button, "掃描中...");
  const meta = document.getElementById("scanner-meta");
  lastScannerSource = source;
  lastScannerSymbols = [];
  updateAiDecisionButton();
  meta.textContent = source === "daytrade" ? "正在掃描全市場當沖候選股..." : "正在掃描全市場短線候選股...";
  try {
    const data = await fetchJson(`/api/screener/${source}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scannerPayload()),
    });
    lastScannerSymbols = data.recommendations.map((row) => row.symbol);
    meta.textContent = `全市場 ${data.candidates_total} → 規則篩選後 ${data.candidates_after_rules} → Top ${data.recommendations.length}，耗時 ${data.elapsed_sec} 秒`;
    if (data.warnings && data.warnings.length) {
      meta.textContent += `\n提醒：${data.warnings.join("；")}`;
    }
    renderTable(
      "scanner-table",
      data.recommendations.map((row) => [
        String(row.rank),
        `${row.symbol} ${row.name}`,
        row.confidence,
        row.entry_range,
        row.stop_loss,
        row.take_profit,
        row.reason,
      ]),
    );
  } catch (error) {
    meta.textContent = `掃描失敗：${error.message}`;
  } finally {
    updateAiDecisionButton();
    restoreButton();
  }
}

async function runScannerAiDecision(button) {
  if (lastScannerSymbols.length === 0) {
    document.getElementById("scanner-meta").textContent = "請先掃描出候選標的。";
    return;
  }
  const restoreButton = setButtonLoading(button, "AI 決策中...");
  const watchlist = Array.from(new Set([...lastScannerSymbols, ...portfolioSymbols]));
  const strategy = lastScannerSource === "daytrade" ? "daytrade" : "swing";
  document.getElementById("market-view").textContent = "AI 正在參考候選標的、持倉、現金與風控限制，產生交易決策...";
  document.getElementById("analyze-meta").textContent = "";
  renderTable("analyze-table", []);
  try {
    const data = await fetchJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategy,
        watchlist,
        storage_path: storagePath(),
      }),
    });
    renderAnalysisResult(data, `AI 決策標的: ${watchlist.join(", ")}\n`);
  } catch (error) {
    document.getElementById("market-view").textContent = `AI 決策失敗：${error.message}`;
    renderTable("analyze-table", []);
  } finally {
    restoreButton();
    updateAiDecisionButton();
  }
}

document.getElementById("scan-daytrade-btn").addEventListener("click", (event) => {
  runScanner("daytrade", event.currentTarget);
});

document.getElementById("scan-swing-btn").addEventListener("click", (event) => {
  runScanner("swing", event.currentTarget);
});

document.getElementById("scanner-ai-decision-btn").addEventListener("click", (event) => {
  runScannerAiDecision(event.currentTarget);
});

document.getElementById("report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const data = await fetchJson(`/api/report?period=${encodeURIComponent(form.get("period"))}`);
    renderStats("report-stats", [
      ["勝率", data.win_rate],
      ["累積損益", data.cumulative_pnl],
      ["Sharpe", data.sharpe],
      ["最大回撤", data.max_drawdown],
      ["天數", String(data.days)],
    ]);
  } catch (error) {
    renderStats("report-stats", [["錯誤", error.message]]);
  }
});

document.getElementById("backtest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = {
    strategy: form.get("strategy"),
    symbols: String(form.get("symbols") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    from_date: form.get("from_date"),
    to_date: form.get("to_date"),
    initial_cash: form.get("initial_cash"),
    storage_path: "data/portfolio.json",
  };
  try {
    const data = await fetchJson("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderStats("backtest-stats", [
      ["股票", data.symbols.join(", ")],
      ["最終權益", data.final_equity],
      ["總報酬", data.total_return],
      ["Benchmark", data.benchmark_return],
      ["勝率", data.win_rate],
      ["Profit Factor", data.profit_factor],
      ["Sharpe", data.sharpe],
      ["最大回撤", data.max_drawdown],
      ["交易數", String(data.trade_count)],
    ]);
  } catch (error) {
    renderStats("backtest-stats", [["錯誤", error.message]]);
  }
});

loadHealth();
loadPortfolio().then(updateAiDecisionButton);
