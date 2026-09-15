from __future__ import annotations

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
    symbol: str
    side: OrderSide
    qty: float


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
