from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from quantdeck.data._dates import bounds, in_range
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
    work out of the box against real market data. Prices are split- and
    dividend-adjusted (``auto_adjust=True``).

    ``start`` and ``end`` are inclusive, as in :class:`CSVDataFeed`: Yahoo's
    own ``end`` is exclusive, so one extra day is requested and the result is
    trimmed to the range.
    """

    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe, timeframe)
        start_ts, end_ts, exclusive = bounds(start, end)
        # Yahoo's end date is exclusive and day-granular: round an inclusive
        # cut-off up to the next midnight, then trim to the exact range below.
        fetch_end = end_ts.normalize() if exclusive else end_ts.normalize() + timedelta(days=1)
        df = yf.download(
            symbol,
            start=start_ts.date().isoformat(),
            end=fetch_end.date().isoformat(),
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df is not None and not df.empty:
            df = df[in_range(df.index, start, end)]
        if df is None or df.empty:
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
