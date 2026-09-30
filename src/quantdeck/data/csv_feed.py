from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quantdeck.data._dates import in_range
from quantdeck.data.base import DataFeed
from quantdeck.models import Bar

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")


class CSVFormatError(ValueError):
    """A CSV file could not be turned into bars. The message names the file,
    and the line number of the first bad row where there is one."""


class CSVDataFeed(DataFeed):
    """Loads OHLCV bars from a local CSV file.

    Expects columns: ``timestamp, open, high, low, close, volume`` (header
    names are matched case-insensitively and may have surrounding spaces;
    extra columns are ignored). Rows are sorted by timestamp. ``start`` and
    ``end`` are inclusive, and a date-only ``end`` includes that whole day.
    Timezone-aware timestamps are supported; naive ``start``/``end`` are then
    read in the file's timezone.

    Problems in the file (missing columns, unparseable timestamps, blank or
    non-numeric values) raise :class:`CSVFormatError`, a ``ValueError``,
    naming the offending line. Price sanity (positive, ``low <= high``,
    strictly increasing timestamps) is checked by the engine.

    This is the escape hatch for custom or offline data when ``YFinanceFeed``
    isn't suitable.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _fail(self, message: str) -> CSVFormatError:
        return CSVFormatError(f"{self.path}: {message}")

    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        try:
            df = pd.read_csv(self.path, dtype=str, keep_default_na=False)
        except FileNotFoundError:
            raise FileNotFoundError(f"CSV file not found: {self.path}") from None
        except pd.errors.EmptyDataError:
            raise self._fail("file is empty (expected a header row)") from None

        df.columns = [str(c).strip().lower() for c in df.columns]
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise self._fail(
                f"missing column(s) {', '.join(missing)}; expected a header with "
                f"{','.join(REQUIRED_COLUMNS)} (found: {','.join(df.columns)})"
            )

        # Line numbers as a text editor shows them: the header is line 1.
        line = pd.Series(range(2, len(df) + 2), index=df.index)

        raw_ts = df["timestamp"].str.strip()
        try:
            ts = pd.to_datetime(raw_ts, errors="coerce")
        except (ValueError, TypeError) as exc:
            # e.g. naive and timezone-aware timestamps mixed in one column
            raise self._fail(f"could not parse the timestamp column: {exc}") from None
        bad = ts.isna()
        if bad.any():
            first = bad.idxmax()
            raise self._fail(
                f"line {line[first]}: could not parse timestamp {raw_ts[first]!r} "
                f"({int(bad.sum())} bad timestamp(s) in total)"
            )
        df["timestamp"] = ts

        for col in _NUMERIC_COLUMNS:
            raw = df[col].str.strip()
            values = pd.to_numeric(raw, errors="coerce")
            bad = values.isna()
            if bad.any():
                first = bad.idxmax()
                shown = repr(raw[first]) if raw[first] else "(blank)"
                raise self._fail(
                    f"line {line[first]}: {col} value {shown} is not a number "
                    f"({int(bad.sum())} bad value(s) in column {col})"
                )
            df[col] = values.astype(float)

        df = df[in_range(df["timestamp"], start, end)]
        # A stable sort keeps file order for equal timestamps, so the engine's
        # duplicate-timestamp error is reproducible.
        df = df.sort_values("timestamp", kind="stable")

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
