"""A classic fast/slow SMA crossover strategy.

Buys when the fast moving average crosses above the slow one, and sells when
it crosses back below. Run it with:

    quantdeck backtest examples/sma_crossover.py --symbol AAPL --start 2023-01-01 --end 2023-12-31
"""
from collections import deque

from quantdeck.models import Bar
from quantdeck.strategy import Strategy


class SmaCrossoverStrategy(Strategy):
    fast_window = 10
    slow_window = 30

    def on_start(self) -> None:
        self._closes: deque[float] = deque(maxlen=self.slow_window)
        self._prev_signal: int | None = None

    def on_bar(self, bar: Bar) -> None:
        self._closes.append(bar.close)
        if len(self._closes) < self.slow_window:
            return

        fast_avg = sum(list(self._closes)[-self.fast_window :]) / self.fast_window
        slow_avg = sum(self._closes) / self.slow_window
        signal = 1 if fast_avg > slow_avg else -1

        if signal == 1 and self._prev_signal != 1 and self.position == 0:
            qty = int(self.cash // bar.close)
            if qty > 0:
                self.buy(qty)
        elif signal == -1 and self._prev_signal != -1 and self.position > 0:
            self.sell(self.position)

        self._prev_signal = signal
