from __future__ import annotations

from abc import ABC, abstractmethod

from quantdeck.models import Bar, Fill, Order


class Broker(ABC):
    """Executes orders and tracks cash/positions."""

    @abstractmethod
    def submit_order(self, order: Order) -> None:
        ...

    @abstractmethod
    def process_bar(self, bar: Bar) -> list[Fill]:
        """Called once per bar by the engine; returns any fills that occurred."""

    @property
    @abstractmethod
    def cash(self) -> float:
        ...

    @abstractmethod
    def position_qty(self, symbol: str) -> float:
        ...
