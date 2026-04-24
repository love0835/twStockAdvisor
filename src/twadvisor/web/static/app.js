const panelMeta = {
  portfolio: ["持倉", "管理持倉、現金、手續費折讓與未實現損益"],
  analyze: ["分析", "執行單次 AI 分析，或掃描全市場推薦標的"],
  report: ["績效", "讀取資料庫內的每日績效紀錄"],
  backtest: ["回測", "用歷史 K 線檢查策略表現"],
  admin: ["Usage", "查看家庭會員 AI 使用量"],
};

const actionLabels = { buy: "買進", sell: "賣出", hold: "持有", watch: "觀察" };

let currentUser = null;
let portfolioSymbols = [];
let selectedHoldingSymbols = new Set();
let hasLoadedPortfolio = false;
let lastScannerSource = null;
let lastScannerSymbols = [];

function $(id) {
  return document.getElementById(id);
}

function showPanel(panel) {
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panel);
  });
  Object.keys(panelMeta).forEach((key) => {
    const el = $(`${key}-panel`);
    if (el) el.classList.toggle("hidden", key !== panel);
  });
  $("panel-title").textContent = panelMeta[panel][0];
  $("panel-subtitle").textContent = panelMeta[panel][1];
  if (panel === "admin") loadUsage();
}

function renderStats(targetId, rows) {
  const target = $(targetId);
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
      if (cell instanceof Node) td.appendChild(cell);
      else td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function parseSymbolList(value) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function storagePath() {
  const field = document.querySelector("#analyze-form input[name='storage_path']");
  return field ? field.value : "data/portfolio.json";
}

function commissionDiscount() {
  const value = $("commission-discount").value.trim();
  return value ? Number(value) : null;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "請求失敗");
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

function showApp(user) {
  currentUser = user;
  $("auth-screen").classList.add("hidden");
  $("app-shell").classList.remove("hidden");
  $("current-user-pill").textContent = `${user.display_name} (${user.role})`;
  $("admin-nav-btn").classList.toggle("hidden", user.role !== "admin");
  showPanel("portfolio");
  loadHealth();
  loadPortfolio();
}

function showAuth(needsAdmin) {
  $("auth-screen").classList.remove("hidden");
  $("app-shell").classList.add("hidden");
  $("login-form").classList.toggle("hidden", needsAdmin);
  $("initial-admin-form").classList.toggle("hidden", !needsAdmin);
  $("auth-subtitle").textContent = needsAdmin ? "第一次使用，請建立管理員" : "家庭會員登入";
}

async function initAuth() {
  const bootstrap = await fetchJson("/api/auth/bootstrap");
  if (bootstrap.needs_admin) {
    showAuth(true);
    return;
  }
  try {
    const data = await fetchJson("/api/auth/me");
    showApp(data.user);
  } catch {
    showAuth(false);
  }
}

async function loadHealth() {
  try {
    await fetchJson("/api/health");
    $("health-pill").textContent = "API 已連線";
  } catch {
    $("health-pill").textContent = "API 無法連線";
  }
}

function selectedHoldings() {
  return portfolioSymbols.filter((symbol) => selectedHoldingSymbols.has(symbol));
}

function updatePortfolioSelectionHint() {
  const selected = selectedHoldings();
  $("portfolio-ai-hint").textContent = `已選 ${selected.length} 檔`;
  $("portfolio-ai-btn").disabled = selected.length === 0;
}

function holdingToggle(symbol) {
  const label = document.createElement("label");
  label.className = "switch";
  label.title = `選取 ${symbol}`;
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = selectedHoldingSymbols.has(symbol);
  input.addEventListener("change", () => {
    if (input.checked) selectedHoldingSymbols.add(symbol);
    else selectedHoldingSymbols.delete(symbol);
    updatePortfolioSelectionHint();
  });
  label.appendChild(input);
  label.appendChild(document.createElement("span"));
  return label;
}

function rowActions(row) {
  const wrap = document.createElement("div");
  wrap.className = "row-actions";
  const editButton = document.createElement("button");
  editButton.className = "secondary-btn compact-btn";
  editButton.textContent = "編輯";
  editButton.addEventListener("click", () => editPosition(row));
  const deleteButton = document.createElement("button");
  deleteButton.className = "danger-btn compact-btn";
  deleteButton.textContent = "刪除";
  deleteButton.addEventListener("click", () => deletePosition(row.symbol));
  wrap.appendChild(editButton);
  wrap.appendChild(deleteButton);
  return wrap;
}

function renderPortfolio(data) {
  const previousSelection = new Set(selectedHoldingSymbols);
  portfolioSymbols = data.rows.map((row) => row.symbol);
  selectedHoldingSymbols = new Set(portfolioSymbols.filter((symbol) => !hasLoadedPortfolio || previousSelection.has(symbol)));
  hasLoadedPortfolio = true;
  $("portfolio-cash-input").value = data.cash;
  $("commission-discount").value = data.commission_discount || "0.28";
  renderStats("portfolio-stats", [
    ["現金", data.cash],
    ["持股數", String(data.position_count)],
    ["總成本", data.total_cost],
    ["更新時間", data.updated_at],
  ]);
  renderTable("portfolio-table", data.rows.map((row) => [
    holdingToggle(row.symbol),
    row.symbol,
    row.qty,
    row.avg_cost,
    row.cost_basis || "-",
    row.current_price,
    row.unrealized_pnl,
    row.unrealized_pnl_pct,
    rowActions(row),
  ]));
  updatePortfolioSelectionHint();
  updateAiDecisionButton();
}

function renderAnalysisResult(data, metaPrefix = "", target = {}) {
  const viewId = target.viewId || "market-view";
  const metaId = target.metaId || "analyze-meta";
  const tableId = target.tableId || "analyze-table";
  $(viewId).textContent = data.market_view;
  $(metaId).textContent = `${metaPrefix}輸入 tokens: ${data.prompt_tokens}\n輸出 tokens: ${data.completion_tokens}`;
  renderTable(tableId, data.recommendations.map((row) => [
    row.symbol,
    actionLabels[row.action] || row.action,
    row.lots ? `${row.lots} / ${row.qty} 股` : String(row.qty),
    row.price,
    row.stop_loss || "-",
    row.take_profit || "-",
    row.warnings,
    row.reason,
  ]));
}

async function runAiAnalysis({ strategy, watchlist, includePortfolio, holdingSymbols, metaPrefix, button, target = {}, switchToAnalyze = true }) {
  const restoreButton = button ? setButtonLoading(button, "AI 分析中...") : () => {};
  const viewId = target.viewId || "market-view";
  const metaId = target.metaId || "analyze-meta";
  const tableId = target.tableId || "analyze-table";
  $(viewId).textContent = "正在抓取行情與技術指標，接著呼叫 AI 分析...";
  $(metaId).textContent = "";
  renderTable(tableId, []);
  try {
    const data = await fetchJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, watchlist, include_portfolio: includePortfolio, holding_symbols: holdingSymbols, storage_path: storagePath() }),
    });
    renderAnalysisResult(data, metaPrefix, target);
    if (switchToAnalyze) showPanel("analyze");
  } catch (error) {
    $(viewId).textContent = error.message;
    renderTable(tableId, []);
    if (switchToAnalyze) showPanel("analyze");
  } finally {
    restoreButton();
  }
}

async function loadPortfolio() {
  try {
    const data = await fetchJson("/api/portfolio");
    renderPortfolio(data);
    $("portfolio-action-result").textContent = "持倉已載入，現價與損益尚未更新。";
  } catch (error) {
    if (error.message === "Not authenticated") return showAuth(false);
    renderStats("portfolio-stats", [["錯誤", error.message]]);
    renderTable("portfolio-table", []);
  }
}

async function editPosition(row) {
  const qty = window.prompt(`${row.symbol} 股數`, row.qty);
  if (qty === null) return;
  const avgCost = window.prompt(`${row.symbol} 均價`, row.avg_cost);
  if (avgCost === null) return;
  try {
    const data = await fetchJson(`/api/portfolio/positions/${encodeURIComponent(row.symbol)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: row.symbol, qty: Number(qty), avg_cost: avgCost, storage_path: storagePath() }),
    });
    renderPortfolio(data);
    $("portfolio-action-result").textContent = `已更新 ${row.symbol}。`;
  } catch (error) {
    $("portfolio-action-result").textContent = error.message;
  }
}

async function deletePosition(symbol) {
  if (!window.confirm(`確定刪除 ${symbol} 持倉？`)) return;
  try {
    const data = await fetchJson(`/api/portfolio/positions/${encodeURIComponent(symbol)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ storage_path: storagePath() }),
    });
    selectedHoldingSymbols.delete(symbol);
    renderPortfolio(data);
    $("portfolio-action-result").textContent = `已刪除 ${symbol}。`;
  } catch (error) {
    $("portfolio-action-result").textContent = error.message;
  }
}

async function loadUsage() {
  if (!currentUser || currentUser.role !== "admin") return;
  try {
    const data = await fetchJson("/api/admin/usage");
    renderTable("usage-table", data.rows.map((row) => [
      row.username,
      row.display_name,
      row.provider,
      String(row.runs),
      String(row.prompt_tokens),
      String(row.completion_tokens),
    ]));
    $("usage-result").textContent = `共 ${data.rows.length} 筆彙總`;
  } catch (error) {
    $("usage-result").textContent = error.message;
  }
}

function scannerPayload() {
  return {
    top_n: Number($("scanner-top-n").value || 5),
    exclude_holdings: $("scanner-exclude-holdings").checked,
    exclude_etf: $("scanner-exclude-etf").checked,
    foreign_consecutive_days: Number($("scanner-foreign-days").value || 3),
    storage_path: storagePath(),
  };
}

function updateAiDecisionButton() {
  const button = $("scanner-ai-decision-btn");
  const hint = $("scanner-decision-hint");
  if (!button || !hint) return;
  const includePortfolio = $("scanner-include-portfolio").checked;
  button.disabled = lastScannerSymbols.length === 0;
  hint.textContent = lastScannerSymbols.length === 0
    ? "請先掃描出候選標的"
    : includePortfolio
      ? `將 ${lastScannerSymbols.length} 檔候選標的交給 AI，並參考目前持倉與現金。`
      : `將 ${lastScannerSymbols.length} 檔候選標的交給 AI。`;
}

async function runScanner(source, button) {
  const restoreButton = setButtonLoading(button, "掃描中...");
  lastScannerSource = source;
  lastScannerSymbols = [];
  updateAiDecisionButton();
  $("scanner-meta").textContent = source === "daytrade" ? "正在掃描全市場當沖候選股..." : "正在掃描全市場短線候選股...";
  try {
    const data = await fetchJson(`/api/screener/${source}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scannerPayload()),
    });
    lastScannerSymbols = data.recommendations.map((row) => row.symbol);
    $("scanner-meta").textContent = `全市場 ${data.candidates_total} → 規則篩選後 ${data.candidates_after_rules} → Top ${data.recommendations.length}，耗時 ${data.elapsed_sec} 秒`;
    if (data.warnings && data.warnings.length) $("scanner-meta").textContent += `\n提醒：${data.warnings.join("；")}`;
    renderTable("scanner-table", data.recommendations.map((row) => [
      String(row.rank),
      `${row.symbol} ${row.name}`,
      row.confidence,
      row.entry_range,
      row.stop_loss,
      row.take_profit,
      row.reason,
    ]));
  } catch (error) {
    $("scanner-meta").textContent = `掃描失敗：${error.message}`;
  } finally {
    updateAiDecisionButton();
    restoreButton();
  }
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((button) => button.addEventListener("click", () => showPanel(button.dataset.panel)));

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      showApp(data.user);
    } catch (error) {
      $("auth-result").textContent = error.message;
    }
  });

  $("initial-admin-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/auth/initial-admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password"), display_name: form.get("display_name") }),
      });
      showApp(data.user);
    } catch (error) {
      $("auth-result").textContent = error.message;
    }
  });

  $("logout-btn").addEventListener("click", async () => {
    await fetchJson("/api/auth/logout", { method: "POST" });
    currentUser = null;
    showAuth(false);
  });

  $("change-password-btn").addEventListener("click", async () => {
    const current = window.prompt("目前密碼");
    if (current === null) return;
    const next = window.prompt("新密碼（至少 8 碼）");
    if (next === null) return;
    try {
      await fetchJson("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      $("portfolio-action-result").textContent = "密碼已更新。";
    } catch (error) {
      $("portfolio-action-result").textContent = error.message;
    }
  });

  $("refresh-portfolio").addEventListener("click", loadPortfolio);
  $("cash-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/portfolio/cash", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cash: String(form.get("cash") || "").trim(), storage_path: storagePath() }),
      });
      renderPortfolio(data);
      $("portfolio-action-result").textContent = "現金已更新。";
    } catch (error) {
      $("portfolio-action-result").textContent = error.message;
    }
  });

  $("commission-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/portfolio/commission", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commission_discount: String(form.get("commission_discount") || "").trim(), storage_path: storagePath() }),
      });
      renderPortfolio(data);
      $("portfolio-action-result").textContent = "手續費折讓已儲存。";
    } catch (error) {
      $("portfolio-action-result").textContent = error.message;
    }
  });

  $("portfolio-import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    try {
      const data = await fetchJson("/api/portfolio/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("portfolio-import-result").textContent = JSON.stringify(data, null, 2);
      hasLoadedPortfolio = false;
      await loadPortfolio();
    } catch (error) {
      $("portfolio-import-result").textContent = error.message;
    }
  });

  $("position-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = { symbol: String(form.get("symbol") || "").trim(), qty: Number(form.get("qty")), avg_cost: String(form.get("avg_cost") || "").trim(), storage_path: storagePath() };
    try {
      const data = await fetchJson("/api/portfolio/positions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      event.target.reset();
      renderPortfolio(data);
      $("portfolio-action-result").textContent = `已新增 ${payload.symbol}。`;
    } catch (error) {
      $("portfolio-action-result").textContent = error.message;
    }
  });

  $("update-quotes-btn").addEventListener("click", async (event) => {
    const restoreButton = setButtonLoading(event.currentTarget, "更新中...");
    try {
      const data = await fetchJson("/api/portfolio/quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storage_path: storagePath(), commission_discount: commissionDiscount() }),
      });
      renderPortfolio(data);
      const failed = data.failed_symbols || [];
      $("portfolio-action-result").textContent = failed.length === 0 ? "現價與損益已更新。" : `部分更新失敗：${failed.join(", ")}`;
    } catch (error) {
      $("portfolio-action-result").textContent = error.message;
    } finally {
      restoreButton();
    }
  });

  $("select-all-holdings").addEventListener("click", () => {
    selectedHoldingSymbols = new Set(portfolioSymbols);
    document.querySelectorAll("#portfolio-table input[type='checkbox']").forEach((input) => { input.checked = true; });
    updatePortfolioSelectionHint();
  });
  $("clear-all-holdings").addEventListener("click", () => {
    selectedHoldingSymbols = new Set();
    document.querySelectorAll("#portfolio-table input[type='checkbox']").forEach((input) => { input.checked = false; });
    updatePortfolioSelectionHint();
  });
  $("portfolio-ai-btn").addEventListener("click", (event) => {
    const holdings = selectedHoldings();
    if (holdings.length === 0) return updatePortfolioSelectionHint();
    runAiAnalysis({
      strategy: "position",
      watchlist: [],
      includePortfolio: true,
      holdingSymbols: holdings,
      metaPrefix: `持倉分析: ${holdings.join(", ")}\n`,
      button: event.currentTarget,
      target: { viewId: "portfolio-ai-view", metaId: "portfolio-ai-meta", tableId: "portfolio-ai-table" },
      switchToAnalyze: false,
    });
  });

  $("analyze-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const includePortfolio = Boolean(form.get("include_portfolio"));
    runAiAnalysis({
      strategy: form.get("strategy"),
      watchlist: parseSymbolList(form.get("watchlist")),
      includePortfolio,
      holdingSymbols: includePortfolio ? portfolioSymbols : [],
      metaPrefix: includePortfolio ? `已參考持倉: ${portfolioSymbols.join(", ")}\n` : "",
      button: event.submitter,
    });
  });

  $("scan-daytrade-btn").addEventListener("click", (event) => runScanner("daytrade", event.currentTarget));
  $("scan-swing-btn").addEventListener("click", (event) => runScanner("swing", event.currentTarget));
  $("scanner-ai-decision-btn").addEventListener("click", (event) => {
    if (lastScannerSymbols.length === 0) {
      $("scanner-meta").textContent = "請先掃描出候選標的。";
      return;
    }
    const strategy = lastScannerSource === "daytrade" ? "daytrade" : "swing";
    const includePortfolio = $("scanner-include-portfolio").checked;
    runAiAnalysis({
      strategy,
      watchlist: lastScannerSymbols,
      includePortfolio,
      holdingSymbols: includePortfolio ? portfolioSymbols : [],
      metaPrefix: includePortfolio ? `AI 決策標的: ${lastScannerSymbols.join(", ")}\n已參考持倉: ${portfolioSymbols.join(", ")}\n` : `AI 決策標的: ${lastScannerSymbols.join(", ")}\n`,
      button: event.currentTarget,
    });
  });
  $("scanner-include-portfolio").addEventListener("change", updateAiDecisionButton);

  $("report-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson(`/api/report?period=${encodeURIComponent(form.get("period"))}`);
      renderStats("report-stats", [["勝率", data.win_rate], ["累積損益", data.cumulative_pnl], ["Sharpe", data.sharpe], ["最大回撤", data.max_drawdown], ["天數", String(data.days)]]);
    } catch (error) {
      renderStats("report-stats", [["錯誤", error.message]]);
    }
  });

  $("backtest-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: form.get("strategy"), symbols: parseSymbolList(form.get("symbols")), from_date: form.get("from_date"), to_date: form.get("to_date"), initial_cash: form.get("initial_cash"), storage_path: "data/portfolio.json" }),
      });
      renderStats("backtest-stats", [["股票", data.symbols.join(", ")], ["最終權益", data.final_equity], ["總報酬", data.total_return], ["Benchmark", data.benchmark_return], ["勝率", data.win_rate], ["Profit Factor", data.profit_factor], ["Sharpe", data.sharpe], ["最大回撤", data.max_drawdown], ["交易數", String(data.trade_count)]]);
    } catch (error) {
      renderStats("backtest-stats", [["錯誤", error.message]]);
    }
  });

  $("refresh-usage-btn").addEventListener("click", loadUsage);
  $("admin-create-user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await fetchJson("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), display_name: form.get("display_name"), password: form.get("password"), role: "member" }),
      });
      $("admin-user-result").textContent = `已新增會員 ${data.user.username}`;
      event.target.reset();
    } catch (error) {
      $("admin-user-result").textContent = error.message;
    }
  });
}

bindEvents();
initAuth();
