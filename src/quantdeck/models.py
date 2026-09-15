from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Order(BaseModel):
    symbol: str
    side: OrderSide
    qty: float


class Fill(BaseModel):
    symbol: str
    side: OrderSide
    qty: float
    price: float
    timestamp: datetime
    commission: float = 0.0


class Position(BaseModel):
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
