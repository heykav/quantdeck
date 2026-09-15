from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import yfinance as yf

from quantdeck.data.base import DataFeed
from quantdeck.models import Bar

_TIMEFRAME_TO_INTERVAL = {
    "1d": "1d",
    "1h": "1h",
    "1m": "1m",
}


class YFinanceFeed(DataFeed):
    """Fetches real historical OHLCV data from Yahoo Finance.

    No API key or account required — this is what makes ``quantdeck backtest``
    work out of the box against real market data.
    """

    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe, timeframe)
        df = yf.download(
            symbol, start=start, end=end, interval=interval, progress=False, auto_adjust=True
        )
        if df.empty:
            raise ValueError(f"No data returned for {symbol!r} between {start} and {end}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        bars: list[Bar] = []
        for ts, row in df.iterrows():
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=ts.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        return bars
