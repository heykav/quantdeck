# QuantDeck

A simple, event-driven backtesting framework for algorithmic trading strategies — zero-config, real market data out of the box, no database server required.

QuantDeck was built as a modern alternative to older frameworks like [LiuAlgoTrader](https://github.com/amor71/LiuAlgoTrader): no Postgres setup, no ceremony — write a strategy class, run one command, and see real results against real historical data in seconds.

> **New to trading or Python?** This README is written for you too — skip straight to [What is this, actually?](#what-is-this-actually) below.

---

## Table of contents

- [What is this, actually?](#what-is-this-actually)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Your first backtest](#your-first-backtest)
- [Understanding the results](#understanding-the-results)
- [Writing your own strategy](#writing-your-own-strategy)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Glossary](#glossary)
- [CLI reference](#cli-reference)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Roadmap](#roadmap)
- [Important disclaimer](#important-disclaimer)
- [License](#license)

---

## What is this, actually?

**Algorithmic trading** just means: instead of a person watching a stock chart and clicking "buy" or "sell" by hand, you write a small program with rules — like *"buy 10 shares of Apple if its price rises above its 10-day average"* — and let the computer follow those rules.

Before you'd ever trust such a program with real (or even fake) money, you want to know: *if I had run this rule over the last year of real stock prices, would I have made money or lost it?* That process — replaying your rule against historical prices to see how it would have performed — is called **backtesting**. That's what QuantDeck does.

Concretely, QuantDeck gives you three things:

1. **A simple way to write a "strategy"** — a small Python class describing your buy/sell rule.
2. **A backtesting engine** that fetches real historical stock prices and plays your strategy against them, day by day, tracking exactly how much money you'd have made or lost.
3. **A results report** — plain numbers (and later, an interactive dashboard) telling you how the strategy performed.

You don't need a trading account, an API key, or any setup beyond installing Python and this package. It fetches free public data from Yahoo Finance automatically.

---

## Prerequisites

You only need one thing installed: **Python 3.10 or newer**.

To check what you have, open a terminal and run:

```bash
python3 --version
```

- If it says `Python 3.10.x`, `3.11.x`, or `3.12.x` (or newer) — you're good, skip to [Installation](#installation).
- If it says something older (like `3.9.x`) or you get a "command not found" error, install a current Python first:
  - **Mac**: `brew install python@3.12` (install [Homebrew](https://brew.sh) first if you don't have it), or download from [python.org](https://www.python.org/downloads/).
  - **Windows**: download the installer from [python.org](https://www.python.org/downloads/) and make sure to check "Add Python to PATH" during setup.
  - **Linux**: use your package manager, e.g. `sudo apt install python3.12`.

You'll also want [git](https://git-scm.com/downloads) installed to download this project (most Macs and Linux machines already have it).

---

## Installation

Open a terminal and run these commands one at a time:

```bash
# 1. Download the project
git clone https://github.com/heykav/quantdeck.git
cd quantdeck

# 2. Create an isolated Python environment just for this project
#    (this keeps QuantDeck's dependencies separate from everything else on your machine)
python3 -m venv .venv

# 3. Activate that environment
#    On Mac/Linux:
source .venv/bin/activate
#    On Windows (Command Prompt):
#    .venv\Scripts\activate.bat

# 4. Install QuantDeck and its dependencies
pip install -e ".[dev]"
```

You'll know it worked if running `quantdeck --help` prints a list of commands instead of an error.

> **Note:** every time you open a *new* terminal window to work on this project, you'll need to run step 3 (`source .venv/bin/activate`) again first — that's what tells your terminal "use QuantDeck's Python environment."

---

## Your first backtest

QuantDeck ships with a ready-made example strategy at [`examples/sma_crossover.py`](examples/sma_crossover.py). Try it right now:

```bash
quantdeck backtest examples/sma_crossover.py --symbol AAPL --start 2023-01-01 --end 2023-12-31
```

Here's what each part of that command means:

| Part | Meaning |
|---|---|
| `backtest` | the CLI command that runs a backtest |
| `examples/sma_crossover.py` | the file containing the strategy to test |
| `--symbol AAPL` | the stock ticker to test against — Apple, in this case |
| `--start 2023-01-01` | the first day of historical data to include |
| `--end 2023-12-31` | the last day of historical data to include |

Behind the scenes, QuantDeck fetches AAPL's real daily prices for 2023 from Yahoo Finance (no account or API key needed), replays the strategy's rules day-by-day, and prints a results table. It takes a few seconds.

---

## Understanding the results

Running a backtest prints a table like this:

```
         Backtest Results
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Metric           ┃       Value ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ Total Return     │      13.88% │
│ CAGR             │      14.06% │
│ Sharpe Ratio     │        1.00 │
│ Max Drawdown     │      12.02% │
│ Win Rate         │      75.00% │
│ Number of Trades │           4 │
│ Ending Equity    │ $113,883.39 │
└──────────────────┴─────────────┘
```

Here's what each row means, in plain English:

| Metric | What it tells you |
|---|---|
| **Total Return** | How much your money grew (or shrank) over the whole period, as a percentage. `13.88%` means $100,000 became about $113,880. |
| **CAGR** | "Compound Annual Growth Rate" — the return re-stated as *"if this rate continued for a full year, every year"*. Useful for comparing strategies tested over different time spans. |
| **Sharpe Ratio** | A measure of return *relative to how bumpy the ride was*. Roughly: above 1 is decent, above 2 is very good, below 0 means you'd have been better off not trading. It rewards steady gains and penalizes wild swings. |
| **Max Drawdown** | The single worst drop from a peak to a low point during the test, as a percentage. `12.02%` means at some point your account fell 12% below its previous high before recovering. This is a key measure of "how bad could it get." |
| **Win Rate** | Of all the completed trades (a buy followed by a matching sell), what percentage made money. `75%` means 3 out of 4 trades were profitable. |
| **Number of Trades** | How many completed round-trip trades the strategy made. |
| **Ending Equity** | The final dollar value of the account, starting from $100,000 by default. |

Results are also saved to a local file, `quantdeck.db`, so you can keep a history of every backtest you've run (a SQLite database — just a single file, no server needed; you can even open it with a free tool like [DB Browser for SQLite](https://sqlitebrowser.org/) if you want to poke around).

---

## Writing your own strategy

A strategy is just a Python class. Generate a starter template:

```bash
quantdeck init my_strategy.py
```

This creates:

```python
"""A starter QuantDeck strategy — edit this to build your own."""
from quantdeck.strategy import Strategy


class MyStrategy(Strategy):
    def on_bar(self, bar):
        # Example: buy 10 shares if we have no position yet.
        if self.position == 0:
            self.buy(10)
```

A few things to know:

- **`on_bar(self, bar)`** is called once for every day (or "bar") of historical data, in order. This is the only method you *must* implement — it's where your trading logic goes.
- **`bar`** is the current day's price data. It has `bar.open`, `bar.high`, `bar.low`, `bar.close`, `bar.volume`, and `bar.timestamp`.
- **`self.buy(qty)`** and **`self.sell(qty)`** place orders. Orders fill at the *next* day's opening price — never the price of the day you decided to trade, since in real life you can't buy at a price you've already seen close.
- **`self.position`** tells you how many shares you currently hold (0 if none).
- **`self.cash`** is how much uninvested cash you have; **`self.equity`** is your total account value (cash + the current value of anything you're holding).
- **`on_start(self)`** and **`on_end(self)`** are optional — override them to set up variables before the backtest begins, or to do something after it ends.

Once you've edited it, run it just like the example:

```bash
quantdeck backtest my_strategy.py --symbol AAPL --start 2023-01-01 --end 2023-12-31
```

Want a slightly more advanced example? Look at [`examples/sma_crossover.py`](examples/sma_crossover.py) — it tracks a rolling average of recent prices to decide when to buy and sell, with comments explaining each step.

---

## How it works under the hood

```
Strategy (your code)
    │  on_bar(bar) → buy()/sell()
    ▼
BacktestEngine  ──drives──▶  DataFeed (YFinanceFeed / CSVDataFeed)
    │
    ▼
PaperBroker (simulated fills, slippage, commission)
    │
    ▼
Storage (SQLite) + Metrics (return, CAGR, Sharpe, drawdown, win rate)
```

In plain words: the **engine** is a loop that hands your strategy one day of prices at a time. Whenever your strategy calls `buy()` or `sell()`, the engine passes that order to a simulated **broker**, which fills it at a realistic price (accounting for typical trading costs) and updates your account. After every day, the engine records your total account value, building up an **equity curve** — and at the end, the **metrics** module turns that curve into the summary table you saw above.

The `Strategy` interface is deliberately broker-agnostic: the same strategy code that runs in a backtest is designed to run against a live paper-trading broker in a later phase, without any changes to your strategy.

---

## Glossary

Terms you'll see throughout this project:

- **Bar** — one unit of price data (e.g., one day's open/high/low/close/volume). QuantDeck currently uses daily bars.
- **Backtest** — simulating a strategy against historical data to see how it would have performed.
- **Paper trading** — trading with fake money against real, live prices (as opposed to a backtest, which uses past data). This is a later-phase feature.
- **Slippage** — the small difference between the price you expected to pay and the price you actually got, which happens in real trading. QuantDeck simulates this so backtest results aren't unrealistically perfect.
- **Commission** — a fee charged per trade by a broker.
- **Look-ahead bias** — a common backtesting mistake where a strategy accidentally "sees the future" (e.g., trading at a price it couldn't have known yet). QuantDeck avoids this by filling orders at the *next* bar's price.
- **Equity curve** — a graph (or list) of your total account value over time.
- **OHLCV** — Open, High, Low, Close, Volume: the standard five numbers describing one bar of price data.

---

## CLI reference

| Command | What it does |
|---|---|
| `quantdeck init [path]` | Creates a starter strategy file (defaults to `strategy.py`). |
| `quantdeck backtest <file> --symbol <TICKER> --start <YYYY-MM-DD> --end <YYYY-MM-DD>` | Runs a backtest. Optional: `--cash <amount>` (starting cash, default $100,000) and `--db <path>` (where to save results, default `quantdeck.db`). |
| `quantdeck --help` | Lists all commands. |

---

## Troubleshooting

- **`command not found: quantdeck`** — you probably haven't activated the virtual environment in this terminal. Run `source .venv/bin/activate` (Mac/Linux) from inside the `quantdeck` folder.
- **`No data returned for '<SYMBOL>' between ...`** — check the ticker symbol is correct and that the date range includes trading days (e.g., not entirely a weekend or a date range in the future).
- **`No Strategy subclass found in <file>`** — your strategy file needs a class that inherits from `Strategy` (e.g., `class MyStrategy(Strategy):`).
- **Install fails with a Python version error** — re-check `python3 --version` is 3.10 or newer (see [Prerequisites](#prerequisites)), and make sure you created the virtual environment with that version.

---

## Development

```bash
pip install -e ".[dev]"
pytest          # run the test suite
ruff check .    # run the linter
```

---

## Roadmap

- [x] **Phase 1** — event-driven backtest engine, strategy interface, SQLite storage, metrics, CLI
- [ ] **Phase 2** — interactive Streamlit dashboard (equity curve, trade log, positions)
- [ ] **Phase 3** — live paper trading via Alpaca, using the same `Strategy` interface

---

## Important disclaimer

QuantDeck is an educational and research tool. Backtested performance does **not** guarantee future results — real markets involve costs, risks, and behavior that a simulation can't fully capture. Nothing in this project is financial advice. If you ever move from backtesting to trading with real money, start with a broker's paper-trading (fake money) mode first, and only risk money you can afford to lose.

---

## License

MIT
