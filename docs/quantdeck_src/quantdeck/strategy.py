from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from quantdeck.models import Bar, Order, OrderSide

if TYPE_CHECKING:
    from quantdeck.engine import BacktestEngine


class Strategy(ABC):
    """Base class for user-defined trading strategies.

    Subclass this and implement ``on_bar()``. Use ``self.buy()`` / ``self.sell()``
    to trade, and ``self.position`` / ``self.cash`` / ``self.equity`` to inspect
    the current state. Orders placed in ``on_bar`` fill at the next bar's open.
    Only the backtest engine exists today; the class only touches a small engine
    interface, but no live/paper-trading engine is implemented.
    """

    def __init__(self) -> None:
        self._engine: BacktestEngine | None = None

    def bind(self, engine: BacktestEngine) -> None:
        self._engine = engine

    def on_start(self) -> None:
        """Called once before the first bar. Override to set up state."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> None:
        """Called once per bar. Implement your trading logic here."""

    def on_end(self) -> None:
        """Called once after the last bar. Override for teardown/reporting."""

    def buy(self, qty: float, symbol: str | None = None) -> None:
        """Queue a market buy of ``qty`` (> 0) shares; fills at the next bar's open."""
        engine = self._require_engine()
        engine.submit_order(Order(symbol=symbol or engine.symbol, side=OrderSide.BUY, qty=qty))

    def sell(self, qty: float, symbol: str | None = None) -> None:
        """Queue a market sell of ``qty`` (> 0) shares; fills at the next bar's open."""
        engine = self._require_engine()
        engine.submit_order(Order(symbol=symbol or engine.symbol, side=OrderSide.SELL, qty=qty))

    def _require_engine(self) -> BacktestEngine:
        if self._engine is None:
            raise RuntimeError("Strategy is not bound to a running engine")
        return self._engine

    @property
    def position(self) -> float:
        """Shares currently held (filled orders only; queued orders are not counted)."""
        return self._require_engine().position_qty

    @property
    def cash(self) -> float:
        """Uninvested cash after all fills so far."""
        return self._require_engine().cash

    @property
    def equity(self) -> float:
        """Cash plus the position marked at the current bar's close."""
        return self._require_engine().equity
