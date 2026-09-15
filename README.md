# QuantDeck

A simple, event-driven backtesting framework for algorithmic trading strategies — zero-config, real market data out of the box, no database server required.

QuantDeck was built as a modern alternative to older frameworks like [LiuAlgoTrader](https://github.com/amor71/LiuAlgoTrader): no Postgres setup, no ceremony — write a strategy class, run `quantdeck backtest`, and see real results against real historical data in seconds.

## Quickstart

```bash
pip install -e ".[dev]"

quantdeck backtest examples/sma_crossover.py --symbol AAPL --start 2023-01-01 --end 2023-12-31
```

That's it — no API keys, no database, no config files. Historical data is pulled live from Yahoo Finance via `yfinance`, and results are printed as a metrics table and saved to a local `quantdeck.db` SQLite file.

## Writing a strategy

```python
from quantdeck.strategy import Strategy

class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.position == 0:
            self.buy(10)
```

Every strategy is a subclass of `Strategy` implementing `on_bar()`. Inside it you get:

- `self.buy(qty)` / `self.sell(qty)` — submit orders (filled at the next bar's open, to avoid look-ahead bias)
- `self.position` — current share quantity held
- `self.cash` / `self.equity` — current cash and total portfolio value
- `on_start()` / `on_end()` — optional lifecycle hooks for setup/teardown

Scaffold a new strategy file with:

```bash
quantdeck init my_strategy.py
```

## Architecture

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

The `Strategy` interface is deliberately broker-agnostic: the same strategy code that runs in a backtest will run against a live paper-trading broker in a later phase, without changes.

## Roadmap

- [x] **Phase 1** — event-driven backtest engine, strategy interface, SQLite storage, metrics, CLI
- [ ] **Phase 2** — interactive Streamlit dashboard (equity curve, trade log, positions)
- [ ] **Phase 3** — live paper trading via Alpaca, using the same `Strategy` interface

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
