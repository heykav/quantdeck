"""Date-range handling shared by the pandas-based data feeds.

Both feeds use the same convention: ``start`` and ``end`` are inclusive. A
date-only ``end`` (a ``date`` object, or a string with no time of day such as
``"2023-12-29"``) includes every bar on that calendar day, intraday bars too.
An ``end`` given as a ``datetime`` or with a time of day is an exact,
inclusive cut-off.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


def _is_date_only(value: date | datetime | str) -> bool:
    if isinstance(value, datetime):
        return False
    if isinstance(value, date):
        return True
    return ":" not in value


def _parse(value: date | datetime | str, name: str) -> Any:
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Could not parse {name} date {value!r}: {exc}") from None
    if ts is pd.NaT:
        raise ValueError(f"Could not parse {name} date {value!r}")
    return ts


def bounds(start: date | datetime | str, end: date | datetime | str) -> tuple[Any, Any, bool]:
    """Return ``(start_ts, end_ts, end_is_exclusive)`` as pandas Timestamps.

    For a date-only ``end`` the returned bound is midnight of the *next* day
    and exclusive; otherwise it is ``end`` itself and inclusive.
    """
    start_ts = _parse(start, "start")
    end_ts = _parse(end, "end")
    if _is_date_only(end):
        return start_ts, end_ts.normalize() + timedelta(days=1), True
    return start_ts, end_ts, False


def _align_tz(ts: Any, tz: Any) -> Any:
    """Make a bound comparable with a column/index in timezone ``tz``."""
    if tz is None:
        return ts.tz_localize(None) if ts.tzinfo is not None else ts
    return ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)


def in_range(timestamps: Any, start: date | datetime | str, end: date | datetime | str) -> Any:
    """Boolean mask of ``timestamps`` (a datetime Series or Index) inside the range.

    Naive bounds are interpreted in the timestamps' own timezone, so
    ``"2023-01-03"`` means that date on the data's clock.
    """
    start_ts, end_ts, exclusive = bounds(start, end)
    tz = timestamps.dt.tz if isinstance(timestamps, pd.Series) else timestamps.tz
    start_ts, end_ts = _align_tz(start_ts, tz), _align_tz(end_ts, tz)
    upper = timestamps < end_ts if exclusive else timestamps <= end_ts
    return (timestamps >= start_ts) & upper
