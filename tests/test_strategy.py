from datetime import datetime

import pytest

from quantdeck.data.base import DataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.models import Bar
from quantdeck.strategy import Strategy


class _FixedFeed(DataFeed):
    def __init__(self, bars):
        self._bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self._bars


def _bar(close: float, ts: datetime) -> Bar:
    return Bar(
        symbol="TEST", timestamp=ts, open=close, high=close, low=close, close=close, volume=1000
    )


class BuyOnceStrategy(Strategy):
    def on_start(self) -> None:
        self.bought = False

    def on_bar(self, bar: Bar) -> None:
        if not self.bought:
            self.buy(10)
            self.bought = True


def test_strategy_can_buy_and_track_position():
    bars = [_bar(100 + i, datetime(2024, 1, 1 + i)) for i in range(5)]
    engine = BacktestEngine(
        BuyOnceStrategy(), _FixedFeed(bars), symbol="TEST", start="2024-01-01", end="2024-01-05"
    )
    engine.run()
    assert engine.position_qty == 10


def test_strategy_raises_if_not_bound():
    strategy = BuyOnceStrategy()
    with pytest.raises(RuntimeError):
        _ = strategy.position
