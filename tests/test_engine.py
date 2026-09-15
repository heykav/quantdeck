from datetime import datetime

from quantdeck.data.base import DataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.models import Bar
from quantdeck.strategy import Strategy


class _FixedFeed(DataFeed):
    def __init__(self, bars):
        self._bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self._bars


def _bar(o: float, ts: datetime) -> Bar:
    return Bar(symbol="TEST", timestamp=ts, open=o, high=o, low=o, close=o, volume=1000)


class BuyThenSellStrategy(Strategy):
    def on_bar(self, bar: Bar) -> None:
        if bar.timestamp.day == 1 and self.position == 0:
            self.buy(10)
        elif bar.timestamp.day == 3 and self.position > 0:
            self.sell(self.position)


def test_orders_fill_at_next_bar_open_not_current_bar():
    bars = [
        _bar(100, datetime(2024, 1, 1)),
        _bar(110, datetime(2024, 1, 2)),
        _bar(120, datetime(2024, 1, 3)),
        _bar(130, datetime(2024, 1, 4)),
    ]
    engine = BacktestEngine(
        BuyThenSellStrategy(),
        _FixedFeed(bars),
        symbol="TEST",
        start="2024-01-01",
        end="2024-01-04",
        slippage_bps=0,
    )
    engine.run()

    buy_fill = engine.fills[0]
    assert buy_fill.price == 110  # filled at the NEXT bar's open, not bar 1's open of 100


def test_cash_round_trips_with_no_slippage_or_commission():
    bars = [_bar(100, datetime(2024, 1, i + 1)) for i in range(4)]
    engine = BacktestEngine(
        BuyThenSellStrategy(),
        _FixedFeed(bars),
        symbol="TEST",
        start="2024-01-01",
        end="2024-01-04",
        starting_cash=1000,
        slippage_bps=0,
    )
    engine.run()
    assert engine.cash == 1000  # bought 10 @ 100, sold 10 @ 100 -> back to start


def test_equity_curve_has_one_point_per_bar():
    bars = [_bar(100, datetime(2024, 1, i + 1)) for i in range(4)]
    engine = BacktestEngine(
        BuyThenSellStrategy(), _FixedFeed(bars), symbol="TEST", start="2024-01-01", end="2024-01-04"
    )
    curve = engine.run()
    assert len(curve) == len(bars)
