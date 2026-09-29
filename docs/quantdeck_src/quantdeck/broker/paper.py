from __future__ import annotations

from quantdeck.broker.base import Broker
from quantdeck.models import Bar, Fill, Order, OrderSide, Position, RejectedOrder


class PaperBroker(Broker):
    """Simulated broker for backtesting.

    Fill rules (all market orders):

    * A pending order fills at the *next* bar's open price (never the bar the
      strategy decided on, which would be look-ahead bias).
    * Slippage is ``slippage_bps`` basis points against you: buys fill above
      the open, sells below it.
    * ``commission`` is a flat amount charged per fill (not per share).
    * A buy that the cash balance cannot cover (notional + commission) is
      rejected, not partially filled.
    * Unless ``allow_short`` is set, a sell larger than the current position
      is rejected, so a strategy cannot accidentally go short.

    Rejected orders are kept in :attr:`rejected` with a reason instead of
    disappearing silently. Orders still pending when the data ends never fill.
    """

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        slippage_bps: float = 5.0,
        commission: float = 0.0,
        allow_short: bool = False,
    ) -> None:
        if starting_cash < 0 or slippage_bps < 0 or commission < 0:
            raise ValueError("starting_cash, slippage_bps and commission must be >= 0")
        self._cash = starting_cash
        self.slippage_bps = slippage_bps
        self.commission = commission
        self.allow_short = allow_short
        self._positions: dict[str, Position] = {}
        self._pending: list[Order] = []
        self.rejected: list[RejectedOrder] = []

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
                    self._reject(order, bar, "insufficient cash")
                    continue
                self._cash -= cost + self.commission
            else:
                if not self.allow_short and order.qty > self.position_qty(order.symbol) + 1e-9:
                    self._reject(order, bar, "sell exceeds position (shorting disabled)")
                    continue
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

    def _reject(self, order: Order, bar: Bar, reason: str) -> None:
        self.rejected.append(RejectedOrder(order=order, reason=reason, timestamp=bar.timestamp))

    def _apply_fill(self, order: Order, price: float) -> None:
        pos = self._positions.setdefault(order.symbol, Position(symbol=order.symbol))
        signed_qty = order.qty if order.side == OrderSide.BUY else -order.qty
        new_qty = pos.qty + signed_qty

        if abs(new_qty) < 1e-12:
            new_qty = 0.0
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
        """Cash plus positions marked at ``mark_prices`` (cost basis if unmarked)."""
        value = self._cash
        for symbol, pos in self._positions.items():
            value += pos.qty * mark_prices.get(symbol, pos.avg_price)
        return value
