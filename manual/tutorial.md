# QuantDeck tutorial (no notebook needed)

Everything here runs offline on the bundled synthetic data. Commands assume the repo root and an activated virtualenv with `pip install .` (or `pip install -e ".[dev]"`).

The data in `examples/data/synthetic.csv` is a seeded random walk (`scripts/make_synthetic_data.py`). It is not market data, so no result below says anything about real markets.

## 1. Run the bundled example

```bash
python examples/offline_backtest.py
```

```
              bars: 500
             fills: 21
          rejected: 0
  total_return_pct: -9.81
            sharpe: -0.37
  max_drawdown_pct: 17.32
     ending_equity: 90193.14
```

This uses a flat commission of 1.0 per fill, which is why it differs slightly from the zero-commission CLI run in the README. A test pins these numbers.

## 2. Write a strategy

```python
from quantdeck.models import Bar
from quantdeck.strategy import Strategy


class BuyTheDip(Strategy):
    def on_start(self) -> None:
        self.prev_close: float | None = None

    def on_bar(self, bar: Bar) -> None:
        # Everything up to bar.close is known here. Orders fill at the NEXT open.
        if self.prev_close is not None:
            if bar.close < 0.98 * self.prev_close and self.position == 0:
                self.buy(int(self.cash * 0.95 // bar.close))  # 5% buffer, see below
            elif bar.close > 1.02 * self.prev_close and self.position > 0:
                self.sell(self.position)
        self.prev_close = bar.close
```

Timing rules:

| Moment | What you can see | What happens |
|---|---|---|
| `on_bar(bar_t)` | bars up to and including `t` (open, high, low, close) | `buy()` / `sell()` queue a market order |
| start of bar `t+1` | | queued orders fill at `open[t+1]` +/- slippage |
| `on_bar(bar_t+1)` | the fill is already reflected in `position` / `cash` | equity point for `t+1` = cash + position at `close[t+1]` |

Consequences:

- An order placed on the last bar never fills.
- `cash // bar.close` can be too much: the fill price is the next open plus slippage. A buy that costs more than your cash is **rejected**, not resized. The bundled SMA example originally sized with 100% of cash and had 7 buy orders rejected on the synthetic series; it now keeps a 5% buffer. Check `engine.rejected_orders` when results look too quiet.
- Selling more than you hold is rejected unless `allow_short=True`.
- `buy(0)`, negative or NaN quantities raise `ValueError`.

## 3. Run it and look at the results

```python
from quantdeck.data.csv_feed import CSVDataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls

engine = BacktestEngine(
    BuyTheDip(), CSVDataFeed("examples/data/synthetic.csv"),
    symbol="SYN", start="2022-01-01", end="2030-01-01",
    starting_cash=100_000, slippage_bps=5, commission=1.0,
)
curve = engine.run()                      # one EquityPoint per bar; run() works once per engine
metrics = compute_metrics([p.equity for p in curve], compute_trade_pnls(engine.fills))
print(metrics.total_return_pct, metrics.max_drawdown_pct)
print(len(engine.fills), "fills;", len(engine.rejected_orders), "rejected")
```

Or via the CLI, which also stores the run in SQLite:

```bash
quantdeck backtest my_strategy.py --symbol SYN --start 2022-01-01 --end 2030-01-01 \
    --csv examples/data/synthetic.csv --slippage-bps 5 --commission 1.0
```

## 4. Check your own strategy for look-ahead bias

The engine prevents the usual mistakes, but a strategy can still cheat through its own code (e.g. loading the whole CSV and indexing into the future). A cheap sanity test: run it on a series where every bar opens at the same price and closes alternately up and down. A strategy that only uses information available at bar close cannot earn a systematic profit there. `tests/test_engine_correctness.py::test_peeking_style_strategy_earns_nothing` shows the pattern.

## 5. Metric conventions

| Metric | Definition |
|---|---|
| returns | simple period returns of the equity curve |
| volatility, Sharpe | sample std (ddof=1) x sqrt(periods_per_year); `risk_free_rate` is annual |
| Sortino | downside deviation about the risk-free rate, dividing by all periods |
| CAGR | `(end/start) ** (periods_per_year/(n-1)) - 1` |
| max drawdown | largest (peak - value) / peak |
| Calmar | CAGR / max drawdown |
| win rate, profit factor | from FIFO-matched round trips, net of commission |

Edge cases: zero-variance curves give 0.0 for the ratios; a curve that reaches zero or negative equity is treated as ruin (-100% return, 100% drawdown); zero drawdown gives Calmar 0.0; no losing trades gives an infinite profit factor. `periods_per_year` defaults to 252, so pass it explicitly for non-daily data.

See [api.md](api.md) for every public signature.
