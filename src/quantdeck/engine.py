from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from quantdeck.broker.paper import PaperBroker
from quantdeck.data.base import DataFeed
from quantdeck.models import Fill, Order
from quantdeck.strategy import Strategy


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float


class BacktestEngine:
    """Event-driven backtest loop.

    Feeds bars to the strategy one at a time in chronological order, routes any
    orders the strategy places to the broker, and records the equity curve
    after each bar. The same ``Strategy`` code will run unchanged against a
    live broker/data feed in a later phase — only this class differs.
    """

    def __init__(
        self,
        strategy: Strategy,
        data_feed: DataFeed,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
        starting_cash: float = 100_000.0,
        slippage_bps: float = 5.0,
        commission: float = 0.0,
    ) -> None:
        self.strategy = strategy
        self.data_feed = data_feed
        self.symbol = symbol
        self.start = start
        self.end = end
        self.timeframe = timeframe
        self.broker = PaperBroker(
            starting_cash=starting_cash, slippage_bps=slippage_bps, commission=commission
        )
        self.equity_curve: list[EquityPoint] = []
        self.fills: list[Fill] = []
        self._last_price: float = 0.0
        strategy.bind(self)

    def submit_order(self, order: Order) -> None:
        self.broker.submit_order(order)

    @property
    def cash(self) -> float:
        return self.broker.cash

    @property
    def position_qty(self) -> float:
        return self.broker.position_qty(self.symbol)

    @property
    def equity(self) -> float:
        return self.broker.equity({self.symbol: self._last_price})

    def run(self) -> list[EquityPoint]:
        bars = self.data_feed.get_bars(self.symbol, self.start, self.end, self.timeframe)
        if not bars:
            raise ValueError(f"No bars returned for {self.symbol}")

        self.strategy.on_start()
        for bar in bars:
            # Fill orders placed on the *previous* bar at this bar's open,
            # then hand the bar to the strategy — this keeps the strategy from
            # ever trading on a price it couldn't have known yet.
            self.fills.extend(self.broker.process_bar(bar))
            self._last_price = bar.close
            self.strategy.on_bar(bar)
            self.equity_curve.append(EquityPoint(timestamp=bar.timestamp, equity=self.equity))
        self.strategy.on_end()

        return self.equity_curve
