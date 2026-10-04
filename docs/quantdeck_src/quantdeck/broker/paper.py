from __future__ import annotations

from quantdeck.broker.base import Broker
from quantdeck.models import (
    Bar,
    Fill,
    Order,
    OrderSide,
    Position,
    RejectedOrder,
    qty_tolerance,
)


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
      is rejected, so a strategy cannot accidentally go short. A sell that
      exceeds the position only by float noise (see :func:`quantdeck.models.qty_tolerance`)
      is filled for exactly the shares held instead.
    * A position left with only float-noise shares after a fill is set to
      exactly zero, so ``position == 0`` checks in strategies work.
    * With ``allow_short`` there is no margin requirement or borrow cost: a
      short sale credits the full proceeds to cash, and buying back is only
      limited by the cash balance, like any other buy.

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
            qty = order.qty

            if order.side == OrderSide.BUY:
                if price * qty + self.commission > self._cash:
                    self._reject(order, bar, "insufficient cash")
                    continue
                self._cash -= price * qty + self.commission
            else:
                held = self.position_qty(order.symbol)
                if not self.allow_short and qty > held:
                    if held <= 0 or qty - held > qty_tolerance(qty, held):
                        self._reject(order, bar, "sell exceeds position (shorting disabled)")
                        continue
                    qty = held  # only float noise over the position: sell exactly what is held
                self._cash += price * qty - self.commission

            self._apply_fill(order.symbol, order.side, qty, price)
            fills.append(
                Fill(
                    symbol=order.symbol,
                    side=order.side,
                    qty=qty,
                    price=price,
                    timestamp=bar.timestamp,
                    commission=self.commission,
                )
            )

        return fills

    def _reject(self, order: Order, bar: Bar, reason: str) -> None:
        self.rejected.append(RejectedOrder(order=order, reason=reason, timestamp=bar.timestamp))

    def _apply_fill(self, symbol: str, side: OrderSide, qty: float, price: float) -> None:
        pos = self._positions.setdefault(symbol, Position(symbol=symbol))
        signed_qty = qty if side == OrderSide.BUY else -qty
        new_qty = pos.qty + signed_qty

        if abs(new_qty) <= qty_tolerance(pos.qty, qty):
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
