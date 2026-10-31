const LIGHT = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
const ACCENT = LIGHT ? "#00A84A" : "#00FF66", MUTED = LIGHT ? "#54564f" : "#9a9c96", BORDER = LIGHT ? "#c4c7c0" : "#2a2c29", TEXT = LIGHT ? "#111211" : "#F4F5F2", GREEN = ACCENT, RED = LIGHT ? "#c62828" : "#ff5c5c";
Chart.defaults.color = MUTED;
Chart.defaults.borderColor = BORDER;
Chart.defaults.font.family = "ui-monospace, Menlo, Consolas, monospace";

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

// Real data, two ways. "BTCUSDT_LIVE" asks Binance's public market-data host straight
// from the browser (it allows cross-origin reads, needs no key) for the last ~5 years of
// closed daily candles. If that fails (offline, blocked) it falls back to the committed
// snapshot and says so. Crypto trades every day, so metrics use 365 periods per year,
// and costs are 15 bps per fill (5 bps slippage + about 10 bps taker fee).
const BINANCE = "https://data-api.binance.vision/api/v3/klines";
const DAY_MS = 86400000;
const CRYPTO = { symbol: "BTCUSDT", slippage: 15, periods: 365, fractional: true };
const SNAPSHOT_NOTE = "Real data: Binance BTCUSDT daily, 2021-01-01 to 2025-12-31, snapshot retrieved 2026-10-29 (committed file, no network needed).";
const STOCK_NOTE = "Bundled daily prices, 2015-2024, a static snapshot (no live fetch for stocks).";

async function fetchBinanceCsv() {
  const end = Math.floor(Date.now() / DAY_MS) * DAY_MS; // start of today UTC; today's candle is still open
  let cursor = end - 1826 * DAY_MS;
  const lines = ["timestamp,open,high,low,close,volume"];
  let first = null, last = null;
  while (cursor < end) {
    const url = `${BINANCE}?symbol=BTCUSDT&interval=1d&startTime=${cursor}&endTime=${end - 1}&limit=1000`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("Binance answered " + resp.status);
    const page = await resp.json();
    if (!page.length) break;
    for (const k of page) {
      const day = new Date(k[0]).toISOString().slice(0, 10);
      first = first || day;
      last = day;
      lines.push([day, k[1], k[2], k[3], k[4], k[5]].join(","));
    }
    cursor = page[page.length - 1][0] + DAY_MS;
    if (page.length < 1000) break;
  }
  if (lines.length < 100) throw new Error("too few candles returned");
  return { csv: lines.join("\n") + "\n", label: `Real data, live from Binance BTCUSDT daily, ${first} to ${last}, fetched ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC in your browser.` };
}

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
    const wanted = new URLSearchParams(location.search).get("symbol");
    const select = document.getElementById("symbol");
    if (new URLSearchParams(location.search).get("tab") === "trades") {
      document.querySelector('.tabs button[data-tab="trades"]').click();
    }
    if (wanted && [...select.options].some((o) => o.value === wanted)) select.value = wanted;
    document.getElementById("run").disabled = false;
    document.getElementById("run").textContent = "Run backtest";
    setStatus("Ready.");
    runBacktest();
  } catch (e) {
    setStatus("Failed to load: " + e, true);
  }
}

async function getBundled(file, label) {
  if (!csvCache[file]) {
    const resp = await fetch("data/" + file + ".csv");
    if (!resp.ok) throw new Error("failed to fetch data for " + file + " (" + resp.status + ")");
    csvCache[file] = await resp.text();
  }
  return { csv: csvCache[file], label };
}

// Returns { csv, label, symbol, opts } for the dropdown choice.
async function getData(choice) {
  if (choice === "BTCUSDT_LIVE") {
    try {
      if (!csvCache.live) csvCache.live = await fetchBinanceCsv();
      return { ...csvCache.live, symbol: "BTCUSDT", opts: CRYPTO };
    } catch (e) {
      const snap = await getBundled("BTCUSDT", SNAPSHOT_NOTE);
      return { ...snap, label: "Live fetch from Binance failed (" + e.message + "), showing the snapshot instead. " + SNAPSHOT_NOTE, symbol: "BTCUSDT", opts: CRYPTO };
    }
  }
  if (choice === "BTCUSDT") {
    return { ...(await getBundled("BTCUSDT", SNAPSHOT_NOTE)), symbol: "BTCUSDT", opts: CRYPTO };
  }
  return { ...(await getBundled(choice, STOCK_NOTE)), symbol: choice, opts: { slippage: 5, periods: 252, fractional: false } };
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
    const data0 = await getData(symbol);

    // Yield one frame so "Running…" actually paints before the
    // synchronous Pyodide call blocks the thread.
    await new Promise(requestAnimationFrame);

    const fn = pyodide.globals.get("run_web_backtest");
    const raw = fn(data0.symbol, data0.csv, fastWindow, slowWindow, cash, riskFreeRate, data0.opts.slippage, data0.opts.periods, data0.opts.fractional);
    const data = JSON.parse(raw);
    if (data.error) {
      setStatus(data.error, true);
    } else {
      setStatus("Ready.");
      document.getElementById("datasource").textContent = data0.label + " Costs: " + data0.opts.slippage + " bps per fill.";
      renderEquity(data.dates, data.equity_curve, data.benchmark_curve);
      renderTrades(data.trades);
      renderSummary(data.metrics, data.benchmark);
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

function renderEquity(dates, curve, bench) {
  destroyIfExists("equity");
  const ctx = document.getElementById("chartEquity");
  charts.equity = new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: [{
        label: "SMA strategy",
        data: curve, borderColor: ACCENT, backgroundColor: "rgba(58,160,255,0.12)",
        fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2,
      }, {
        label: "Buy and hold",
        data: bench, borderColor: MUTED, borderDash: [6, 4],
        fill: false, tension: 0.1, pointRadius: 0, borderWidth: 1.5,
      }],
    },
    options: {
      plugins: { legend: { display: true, labels: { color: MUTED } }, title: { display: true, text: "Equity Curve", color: TEXT } },
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
    const cells = [t.date, t.side.toUpperCase(), Number(t.qty.toFixed(6)), "$" + t.price.toFixed(2)];
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

function renderSummary(m, b) {
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
    ["Buy and hold: Total Return", b.total_return_pct.toFixed(2) + "%"],
    ["Buy and hold: Max Drawdown", b.max_drawdown_pct.toFixed(2) + "%"],
    ["Buy and hold: Ending Equity", "$" + b.ending_equity.toLocaleString(undefined, { maximumFractionDigits: 2 })],
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
