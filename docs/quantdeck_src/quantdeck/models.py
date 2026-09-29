from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    """A market order. ``qty`` is always a positive magnitude; direction is ``side``."""

    symbol: str
    side: OrderSide
    qty: float

    def __post_init__(self) -> None:
        # A negative quantity would silently invert the trade (a "buy" of -5
        # credits cash and opens a short), so it is rejected outright.
        if not math.isfinite(self.qty) or self.qty <= 0:
            raise ValueError(f"Order qty must be a positive finite number, got {self.qty!r}")


@dataclass
class Fill:
    symbol: str
    side: OrderSide
    qty: float
    price: float
    timestamp: datetime
    commission: float = 0.0


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0


@dataclass
class RejectedOrder:
    """An order the broker refused to fill, with the reason why."""

    order: Order
    reason: str
    timestamp: datetime
