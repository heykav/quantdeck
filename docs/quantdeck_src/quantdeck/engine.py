from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from quantdeck.broker.paper import PaperBroker
from quantdeck.data.base import DataFeed
from quantdeck.models import Bar, Fill, Order, RejectedOrder
from quantdeck.strategy import Strategy


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float


class BacktestEngine:
    """Event-driven backtest loop.

    Feeds bars to the strategy one at a time in chronological order, routes any
    orders the strategy places to the broker, and records the equity curve
    after each bar.

    Timing contract: ``on_bar(bar)`` runs after bar ``t`` has closed, so it may
    use anything up to and including ``bar.close``. Orders it places are filled
    at the open of bar ``t+1`` (plus slippage), and that fill is visible to the
    strategy from the start of ``on_bar`` for bar ``t+1``. Each equity point is
    cash plus positions marked at that bar's close.

    Note: only this backtest path exists. There is no live or paper-trading
    engine in this repository yet; ``Strategy`` is written against the engine's
    small surface (``submit_order``, ``cash``, ``position_qty``, ``equity``) so
    one could be added, but that is not implemented.
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
        allow_short: bool = False,
    ) -> None:
        self.strategy = strategy
        self.data_feed = data_feed
        self.symbol = symbol
        self.start = start
        self.end = end
        self.timeframe = timeframe
        self.broker = PaperBroker(
            starting_cash=starting_cash,
            slippage_bps=slippage_bps,
            commission=commission,
            allow_short=allow_short,
        )
        self.equity_curve: list[EquityPoint] = []
        self.fills: list[Fill] = []
        self._last_price: float = 0.0
        self._has_run = False
        strategy.bind(self)

    def submit_order(self, order: Order) -> None:
        if order.symbol != self.symbol:
            raise ValueError(
                f"Engine trades {self.symbol!r} only; cannot place an order for {order.symbol!r}"
            )
        self.broker.submit_order(order)

    @property
    def rejected_orders(self) -> list[RejectedOrder]:
        """Orders the broker refused (insufficient cash, unauthorised short)."""
        return self.broker.rejected

    @property
    def cash(self) -> float:
        return self.broker.cash

    @property
    def position_qty(self) -> float:
        return self.broker.position_qty(self.symbol)

    @property
    def equity(self) -> float:
        return self.broker.equity({self.symbol: self._last_price})

    @staticmethod
    def _validate_bars(bars: list[Bar]) -> None:
        prev = None
        for bar in bars:
            prices = (bar.open, bar.high, bar.low, bar.close)
            if not all(math.isfinite(x) and x > 0 for x in prices) or bar.low > bar.high:
                raise ValueError(f"Invalid prices in bar at {bar.timestamp}: {bar}")
            if prev is not None and bar.timestamp <= prev:
                raise ValueError(
                    f"Bars must be in strictly increasing time order: {bar.timestamp} "
                    f"does not follow {prev}"
                )
            prev = bar.timestamp

    def run(self) -> list[EquityPoint]:
        if self._has_run:
            raise RuntimeError("BacktestEngine.run() can only be called once; build a new engine")
        self._has_run = True
        bars = self.data_feed.get_bars(self.symbol, self.start, self.end, self.timeframe)
        if not bars:
            raise ValueError(f"No bars returned for {self.symbol}")
        self._validate_bars(bars)

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
