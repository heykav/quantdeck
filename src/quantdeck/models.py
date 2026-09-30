from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


def qty_tolerance(*quantities: float) -> float:
    """Float noise allowed when comparing share quantities.

    Fractional sizes rarely sum exactly (``0.1 + 0.2 != 0.3``), and the
    rounding residue grows with the size of the position, so the tolerance is
    relative (1e-12 of the largest quantity involved) with an absolute floor
    of 1e-9 shares.
    """
    return max(1e-9, 1e-12 * max((abs(q) for q in quantities), default=0.0))


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
