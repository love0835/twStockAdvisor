const panelMeta = {
  portfolio: ["持倉", "載入現有持倉、現金與未實現損益"],
  analyze: ["分析", "執行單次 AI 分析並檢視建議"],
  report: ["績效", "讀取資料庫內的日績效彙總"],
  backtest: ["回測", "用歷史 K 線檢查策略表現"],
};

const actionLabels = {
  buy: "買進",
  sell: "賣出",
  hold: "持有",
  watch: "觀察",
};

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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
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
  const originalButtonText = submitButton ? submitButton.textContent : "";
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "分析中...";
  }
  document.getElementById("market-view").textContent = "正在抓取行情與技術指標，接著呼叫 AI 分析...";
  document.getElementById("analyze-meta").textContent = "";
  renderTable("analyze-table", []);
  try {
    const data = await fetchJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("market-view").textContent = data.market_view;
    document.getElementById("analyze-meta").textContent = `輸入 tokens: ${data.prompt_tokens}\n輸出 tokens: ${data.completion_tokens}`;
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
  } catch (error) {
    document.getElementById("market-view").textContent = error.message;
    renderTable("analyze-table", []);
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalButtonText;
    }
  }
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
loadPortfolio();
