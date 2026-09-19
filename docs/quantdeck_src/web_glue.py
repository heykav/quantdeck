"""Web-only glue between the real `quantdeck` package and the browser demo.

Deliberately kept out of the `quantdeck` package itself: this is JSON-shaping
for the JS/Chart.js frontend, plus a stdlib-only CSV loader (so the browser
demo needs no `pandas`/`yfinance` download), not part of the library.
`BacktestEngine`, `SmaCrossoverStrategy`, `PaperBroker`, and the metrics
functions are the exact same code the CLI and the test suite use — the
browser demo runs the real engine, not a reimplementation of it.
"""
import csv
import io
import json
import math
from datetime import datetime

from sma_crossover import SmaCrossoverStrategy

from quantdeck.data.base import DataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.models import Bar


class _StaticFeed(DataFeed):
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self._bars


def _parse_bars(symbol: str, csv_text: str) -> list[Bar]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [
        Bar(
            symbol=symbol,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for row in reader
    ]


def run_web_backtest(symbol, csv_text, fast_window, slow_window, starting_cash, risk_free_rate=0.0):
    try:
        bars = _parse_bars(symbol, csv_text)
        if not bars:
            return json.dumps({"error": f"No bundled data for {symbol}."})

        strategy = SmaCrossoverStrategy()
        strategy.fast_window = int(fast_window)
        strategy.slow_window = int(slow_window)
        if strategy.fast_window >= strategy.slow_window:
            return json.dumps({"error": "Fast window must be smaller than the slow window."})

        engine = BacktestEngine(
            strategy=strategy,
            data_feed=_StaticFeed(bars),
            symbol=symbol,
            start=bars[0].timestamp,
            end=bars[-1].timestamp,
            starting_cash=float(starting_cash),
        )
        equity_curve = engine.run()
    except Exception as e:  # noqa: BLE001 - surfaced to the UI as a message, not a crash
        return json.dumps({"error": str(e)})

    values = [p.equity for p in equity_curve]
    trade_pnls = compute_trade_pnls(engine.fills)
    metrics = compute_metrics(values, trade_pnls, risk_free_rate=float(risk_free_rate))

    return json.dumps(
        {
            "dates": [p.timestamp.strftime("%Y-%m-%d") for p in equity_curve],
            "equity_curve": values,
            "trades": [
                {
                    "date": f.timestamp.strftime("%Y-%m-%d"),
                    "side": f.side.value,
                    "qty": f.qty,
                    "price": f.price,
                }
                for f in engine.fills
            ],
            "metrics": {
                "total_return_pct": metrics.total_return_pct,
                "cagr_pct": metrics.cagr_pct,
                "volatility_pct": metrics.volatility_pct,
                "sharpe": metrics.sharpe,
                "sortino": metrics.sortino,
                "calmar": metrics.calmar,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "win_rate_pct": metrics.win_rate_pct,
                # profit_factor can be math.inf (zero losing trades) - JSON has no
                # Infinity token, and JS's JSON.parse rejects Python's json.dumps
                # output for it outright, so it's pre-formatted here the same way
                # the CLI's _format_ratio renders it.
                "profit_factor": "∞" if math.isinf(metrics.profit_factor) else f"{metrics.profit_factor:.2f}",
                "num_trades": metrics.num_trades,
                "ending_equity": values[-1],
            },
        }
    )
