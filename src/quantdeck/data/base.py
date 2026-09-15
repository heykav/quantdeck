from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from quantdeck.models import Bar


class DataFeed(ABC):
    """Source of historical OHLCV bars for a symbol."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        ...
