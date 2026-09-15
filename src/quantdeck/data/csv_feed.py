from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quantdeck.data.base import DataFeed
from quantdeck.models import Bar


class CSVDataFeed(DataFeed):
    """Loads OHLCV bars from a local CSV file.

    Expects columns: ``timestamp, open, high, low, close, volume``. This is the
    escape hatch for custom or offline data when ``YFinanceFeed`` isn't suitable.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        df = pd.read_csv(self.path, parse_dates=["timestamp"])
        df = df[(df["timestamp"] >= pd.Timestamp(start)) & (df["timestamp"] <= pd.Timestamp(end))]
        df = df.sort_values("timestamp")

        return [
            Bar(
                symbol=symbol,
                timestamp=row.timestamp.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            for row in df.itertuples()
        ]
