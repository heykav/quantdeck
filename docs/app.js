const ACCENT = "#3aa0ff", MUTED = "#9a9cac", BORDER = "#2a2c34", TEXT = "#F4F5F2", GREEN = "#3ddc84", RED = "#ff5c5c";
Chart.defaults.color = MUTED;
Chart.defaults.borderColor = BORDER;
Chart.defaults.font.family = "-apple-system, sans-serif";

const SRC_FILES = [
  "quantdeck/__init__.py",
  "quantdeck/models.py",
  "quantdeck/strategy.py",
  "quantdeck/engine.py",
  "quantdeck/metrics.py",
  "quantdeck/broker/__init__.py",
  "quantdeck/broker/base.py",
  "quantdeck/broker/paper.py",
  "quantdeck/data/__init__.py",
  "quantdeck/data/base.py",
  "sma_crossover.py",
  "web_glue.py",
];

// Mirrors the validation the CLI itself would eventually hit (a bad
// window size just makes the strategy never trade) - checking here first
// means an immediate, specific, in-place message instead of a silent
// "0 trades" result with no explanation.
const FIELD_RULES = {
  fastWindow: { label: "Fast SMA window", min: 1, max: 200, integer: true },
  slowWindow: { label: "Slow SMA window", min: 2, max: 400, integer: true },
  cash: { label: "Starting cash", min: 100, max: 100_000_000, finite: true },
  riskFreeRate: { label: "Risk-free rate", min: -5, max: 25, finite: true },
};

let pyodide;
let charts = {};
let booted = false;
let running = false;
const csvCache = {};

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = isError ? "error" : "";
}

function clearFieldErrors() {
  Object.keys(FIELD_RULES).forEach((id) => document.getElementById(id).classList.remove("invalid"));
}

function validateFields() {
  let firstMessage = null;
  for (const [id, rule] of Object.entries(FIELD_RULES)) {
    const el = document.getElementById(id);
    const raw = el.value.trim();
    const value = rule.integer ? parseInt(raw, 10) : parseFloat(raw);
    let message = null;
    if (raw === "" || Number.isNaN(value)) {
      message = `${rule.label} must be a number.`;
    } else if (!Number.isFinite(value)) {
      message = `${rule.label} must be finite.`;
    } else if (value < rule.min || value > rule.max) {
      message = `${rule.label} must be between ${rule.min} and ${rule.max}.`;
    }
    el.classList.toggle("invalid", !!message);
    if (message && !firstMessage) firstMessage = message;
  }

  const fast = parseInt(document.getElementById("fastWindow").value, 10);
  const slow = parseInt(document.getElementById("slowWindow").value, 10);
  if (Number.isFinite(fast) && Number.isFinite(slow) && fast >= slow) {
    document.getElementById("fastWindow").classList.add("invalid");
    document.getElementById("slowWindow").classList.add("invalid");
    firstMessage = firstMessage || "Fast window must be smaller than the slow window.";
  }

  return firstMessage;
}

async function boot() {
  try {
    pyodide = await loadPyodide();

    pyodide.FS.mkdirTree("/quantdeck_pkg/quantdeck/broker");
    pyodide.FS.mkdirTree("/quantdeck_pkg/quantdeck/data");
    for (const f of SRC_FILES) {
      const resp = await fetch("quantdeck_src/" + f);
      if (!resp.ok) throw new Error("failed to fetch " + f + " (" + resp.status + ")");
      const text = await resp.text();
      pyodide.FS.writeFile("/quantdeck_pkg/" + f, text);
    }
    pyodide.runPython(`
import sys
sys.path.insert(0, "/quantdeck_pkg")
from web_glue import run_web_backtest
`);

    booted = true;
    document.getElementById("run").disabled = false;
    document.getElementById("run").textContent = "Run backtest";
    setStatus("Ready.");
    runBacktest();
  } catch (e) {
    setStatus("Failed to load: " + e, true);
  }
}

async function getCsv(symbol) {
  if (csvCache[symbol]) return csvCache[symbol];
  const resp = await fetch("data/" + symbol + ".csv");
  if (!resp.ok) throw new Error("failed to fetch data for " + symbol + " (" + resp.status + ")");
  const text = await resp.text();
  csvCache[symbol] = text;
  return text;
}

async function runBacktest() {
  if (!booted || running) return;

  clearFieldErrors();
  const problem = validateFields();
  if (problem) {
    setStatus(problem, true);
    return;
  }

  const symbol = document.getElementById("symbol").value;
  const fastWindow = parseInt(document.getElementById("fastWindow").value, 10);
  const slowWindow = parseInt(document.getElementById("slowWindow").value, 10);
  const cash = parseFloat(document.getElementById("cash").value);
  const riskFreeRate = parseFloat(document.getElementById("riskFreeRate").value) / 100;

  running = true;
  const runBtn = document.getElementById("run");
  runBtn.disabled = true;
  runBtn.textContent = "Running…";
  setStatus("Running backtest…");

  try {
    const csvText = await getCsv(symbol);

    // Yield one frame so "Running…" actually paints before the
    // synchronous Pyodide call blocks the thread.
    await new Promise(requestAnimationFrame);

    const fn = pyodide.globals.get("run_web_backtest");
    const raw = fn(symbol, csvText, fastWindow, slowWindow, cash, riskFreeRate);
    const data = JSON.parse(raw);
    if (data.error) {
      setStatus(data.error, true);
    } else {
      setStatus("Ready.");
      renderEquity(data.dates, data.equity_curve);
      renderTrades(data.trades);
      renderSummary(data.metrics);
    }
  } catch (e) {
    setStatus("Backtest error: " + e, true);
  } finally {
    running = false;
    runBtn.disabled = false;
    runBtn.textContent = "Run backtest";
  }
}

function destroyIfExists(key) {
  if (charts[key]) { charts[key].destroy(); }
}

function renderEquity(dates, curve) {
  destroyIfExists("equity");
  const ctx = document.getElementById("chartEquity");
  charts.equity = new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: [{
        data: curve, borderColor: ACCENT, backgroundColor: "rgba(58,160,255,0.12)",
        fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      plugins: { legend: { display: false }, title: { display: true, text: "Equity Curve", color: TEXT } },
      scales: {
        x: { title: { display: true, text: "Date" }, grid: { color: BORDER }, ticks: { maxTicksLimit: 10 } },
        y: { title: { display: true, text: "Account Value ($)" }, grid: { color: BORDER } },
      },
    },
  });
}

function renderTrades(trades) {
  const tbody = document.querySelector("#trades tbody");
  tbody.textContent = "";
  for (const t of trades) {
    const tr = document.createElement("tr");
    const cells = [t.date, t.side.toUpperCase(), t.qty, "$" + t.price.toFixed(2)];
    cells.forEach((val, i) => {
      const td = document.createElement("td");
      td.textContent = val;
      if (i === 1) td.classList.add(t.side === "buy" ? "buy" : "sell");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  if (trades.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.textContent = "No trades — try a smaller fast/slow window gap.";
    td.style.color = MUTED;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

function renderSummary(m) {
  const rows = [
    ["Total Return", m.total_return_pct.toFixed(2) + "%"],
    ["CAGR", m.cagr_pct.toFixed(2) + "%"],
    ["Volatility (ann.)", m.volatility_pct.toFixed(2) + "%"],
    ["Sharpe Ratio", m.sharpe.toFixed(2)],
    ["Sortino Ratio", m.sortino.toFixed(2)],
    ["Calmar Ratio", m.calmar.toFixed(2)],
    ["Max Drawdown", m.max_drawdown_pct.toFixed(2) + "%"],
    ["Win Rate", m.win_rate_pct.toFixed(2) + "%"],
    ["Profit Factor", m.profit_factor],
    ["Number of Trades", m.num_trades],
    ["Ending Equity", "$" + m.ending_equity.toLocaleString(undefined, { maximumFractionDigits: 2 })],
  ];
  const tbody = document.querySelector("#summary tbody");
  tbody.textContent = "";
  for (const [k, v] of rows) {
    const tr = document.createElement("tr");
    const tdK = document.createElement("td");
    tdK.textContent = k;
    const tdV = document.createElement("td");
    tdV.textContent = v;
    tr.append(tdK, tdV);
    tbody.appendChild(tr);
  }
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tabpage").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    const chart = charts[btn.dataset.tab];
    if (chart) chart.resize();
  });
});

document.getElementById("run").addEventListener("click", runBacktest);
document.getElementById("symbol").addEventListener("change", runBacktest);
document.getElementById("controls").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runBacktest();
});
boot();
