from __future__ import annotations

from quantdeck.broker.base import Broker
from quantdeck.models import Bar, Fill, Order, OrderSide, Position


class PaperBroker(Broker):
    """Simulated broker for backtesting.

    Pending orders fill at the *next* bar's open price (never the bar the
    strategy decided on, which would be look-ahead bias), with a fixed
    slippage in basis points plus a flat commission per fill.
    """

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        slippage_bps: float = 5.0,
        commission: float = 0.0,
    ) -> None:
        self._cash = starting_cash
        self.slippage_bps = slippage_bps
        self.commission = commission
        self._positions: dict[str, Position] = {}
        self._pending: list[Order] = []

    def submit_order(self, order: Order) -> None:
        self._pending.append(order)

    def process_bar(self, bar: Bar) -> list[Fill]:
        fills: list[Fill] = []
        orders, self._pending = self._pending, []

        for order in orders:
            if order.symbol != bar.symbol:
                self._pending.append(order)
                continue

            slip = bar.open * (self.slippage_bps / 10_000)
            price = bar.open + slip if order.side == OrderSide.BUY else bar.open - slip
            cost = price * order.qty

            if order.side == OrderSide.BUY:
                if cost + self.commission > self._cash:
                    continue  # insufficient cash, drop the order
                self._cash -= cost + self.commission
            else:
                self._cash += cost - self.commission

            self._apply_fill(order, price)
            fills.append(
                Fill(
                    symbol=order.symbol,
                    side=order.side,
                    qty=order.qty,
                    price=price,
                    timestamp=bar.timestamp,
                    commission=self.commission,
                )
            )

        return fills

    def _apply_fill(self, order: Order, price: float) -> None:
        pos = self._positions.setdefault(order.symbol, Position(symbol=order.symbol))
        signed_qty = order.qty if order.side == OrderSide.BUY else -order.qty
        new_qty = pos.qty + signed_qty

        if new_qty == 0:
            pos.avg_price = 0.0
        elif pos.qty == 0 or (pos.qty > 0) != (new_qty > 0):
            # opening a fresh position, or flipping from long to short (or vice versa)
            pos.avg_price = price
        elif (pos.qty > 0) == (signed_qty > 0):
            # adding to the position in the same direction: weighted-average cost
            pos.avg_price = (pos.avg_price * pos.qty + price * signed_qty) / new_qty
        # else: partially reducing the position — cost basis of the remainder is unchanged

        pos.qty = new_qty

    @property
    def cash(self) -> float:
        return self._cash

    def position_qty(self, symbol: str) -> float:
        return self._positions.get(symbol, Position(symbol=symbol)).qty

    def equity(self, mark_prices: dict[str, float]) -> float:
        value = self._cash
        for symbol, pos in self._positions.items():
            value += pos.qty * mark_prices.get(symbol, pos.avg_price)
        return value
