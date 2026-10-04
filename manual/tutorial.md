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
- Selling more than you hold is rejected unless `allow_short=True`. A sell that overshoots the position only by float rounding (e.g. fractional sizes such as `0.1 + 0.2`) sells exactly what you hold, and a position left with only rounding dust is set to exactly 0.
- With `allow_short=True` there is no margin requirement and no borrow cost. A short that runs against you can push equity below zero, and buying back is rejected if cash cannot cover it.
- Nothing is liquidated at the end of the data: an open position is marked at the last close in the equity curve, but it is not a completed trade, so it does not count towards win rate, profit factor or the number of trades.
- `buy(0)`, negative or NaN quantities raise `ValueError`.
- The data feed must return bars labelled with the engine's `symbol`; a mismatch raises `ValueError` (previously every order silently stayed unfilled).

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

The engine prevents the usual mistakes, but a strategy can still cheat through its own code (e.g. loading the whole CSV and indexing into the future). Two cheap checks:

- **Change the future, compare the past.** Run the strategy twice, the second time with every bar after some index `k` replaced by unrelated prices. The orders placed on bars `0..k`, the fills up to bar `k` and the equity curve up to bar `k` must be identical. `tests/test_lookahead_and_edges.py::test_changing_the_future_does_not_change_the_past` does this for the bundled strategies; it fails if the engine hands `on_bar` the next bar instead of the current one.
- **A series with nothing to predict.** Every bar opens at the same price and closes alternately up and down. A strategy that only uses information available at bar close cannot earn a systematic profit there. `tests/test_engine_correctness.py::test_peeking_style_strategy_earns_nothing` shows the pattern.

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

Annualisation: every annualised figure uses `periods_per_year`, which defaults to 252 (daily bars), so pass it explicitly for other bar sizes. CAGR counts `n - 1` periods for an `n`-point curve, so 253 daily equity points are exactly one year. There is no simple-return ("non-compounded") CAGR option.

Edge cases: zero-variance curves give 0.0 for the ratios; a curve that reaches zero or negative equity is treated as ruin (-100% return, -100% CAGR, 100% drawdown; later points are ignored); zero drawdown gives Calmar 0.0; no losing trades gives an infinite profit factor. Very short samples annualise to extreme CAGRs; one that overflows a float (e.g. +9,900% in one daily bar) is reported as `inf` instead of raising. `periods_per_year <= 0` or a non-finite `risk_free_rate` raise `ValueError`.

## 6. Data files and date ranges

`CSVDataFeed` needs the columns `timestamp,open,high,low,close,volume` (header case and surrounding spaces do not matter; extra columns are ignored). A missing column, an unparseable timestamp or a blank / non-numeric value raises `CSVFormatError` (a `ValueError`) naming the file and line, for example:

```
bars.csv: line 3: high value (blank) is not a number (1 bad value(s) in column high)
```

`start` and `end` are inclusive for both `CSVDataFeed` and `YFinanceFeed`. A date-only `end` such as `"2023-12-29"` includes every bar on that day; an `end` with a time of day is an exact cut-off. (Yahoo's own `end` is exclusive; the feed requests one extra day and trims.)

See [api.md](api.md) for every public signature.
