"""Real daily OHLCV from Binance's public market-data endpoint, cached as CSV.

Uses ``https://data-api.binance.vision``, Binance's documented read-only mirror
for public market data. It needs no account and no API key, and it only serves
market data (no trading, no account endpoints). Candles are spot prices quoted
in USDT, with UTC day boundaries, and they are *not* adjusted for anything
(crypto has no splits or dividends). Only the standard library is used for the
download, so this module works wherever ``quantdeck`` does.

Check Binance's current terms before building anything on top of this data:
https://www.binance.com/en/terms
"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantdeck.data.base import DataFeed
from quantdeck.data.csv_feed import CSVDataFeed
from quantdeck.models import Bar

BASE_URL = "https://data-api.binance.vision"
CSV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
_MAX_PER_REQUEST = 1000
_INTERVAL_MS = {"1d": 86_400_000}

Fetcher = Callable[[str], Any]


def _to_ms(value: date | datetime | str) -> int:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _http_get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "quantdeck"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read().decode("utf-8"))


def fetch_klines(
    symbol: str,
    start: date | datetime | str,
    end: date | datetime | str,
    interval: str = "1d",
    fetcher: Fetcher | None = None,
    now_ms: int | None = None,
) -> list[list[Any]]:
    """Download raw klines for ``symbol`` (e.g. ``BTCUSDT``) from ``start`` to ``end`` inclusive.

    Pages through the endpoint 1000 candles at a time. A candle that has not
    closed yet is dropped, so a partial "today" bar never enters a backtest.
    ``fetcher`` takes a URL and returns parsed JSON; it exists so tests can run
    without the network.
    """
    if interval not in _INTERVAL_MS:
        raise ValueError(f"Unsupported interval {interval!r}; only {sorted(_INTERVAL_MS)} for now")
    get = fetcher or _http_get_json
    step = _INTERVAL_MS[interval]
    cursor = _to_ms(start)
    end_ms = _to_ms(end) + step - 1  # include the whole end day
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    rows: list[list[Any]] = []
    while cursor <= end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": _MAX_PER_REQUEST,
            }
        )
        page = get(f"{BASE_URL}/api/v3/klines?{query}")
        if not page:
            break
        rows.extend(page)
        cursor = int(page[-1][0]) + step
        if len(page) < _MAX_PER_REQUEST:
            break
    return [r for r in rows if int(r[6]) < now_ms]  # r[6] is the candle's close time


def write_csv(rows: list[list[Any]], path: str | Path) -> Path:
    """Write klines as ``timestamp,open,high,low,close,volume`` (the CSVDataFeed format)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for r in rows:
            day = datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            writer.writerow([day, r[1], r[2], r[3], r[4], r[5]])
    return target


def download_csv(
    symbol: str,
    start: date | datetime | str,
    end: date | datetime | str,
    path: str | Path,
    interval: str = "1d",
    fetcher: Fetcher | None = None,
) -> Path:
    """Download daily candles and save them to ``path`` as CSV."""
    rows = fetch_klines(symbol, start, end, interval, fetcher=fetcher)
    if not rows:
        raise ValueError(f"No candles returned for {symbol} between {start} and {end}")
    return write_csv(rows, path)


class BinanceFeed(DataFeed):
    """Daily bars from Binance public data, cached under ``cache_dir`` as CSV.

    The first request for a symbol and date range downloads it; later requests
    for the same range read the cached file, so reruns work offline.
    """

    def __init__(self, cache_dir: str | Path = ".quantdeck_cache", fetcher: Fetcher | None = None):
        self.cache_dir = Path(cache_dir)
        self._fetcher = fetcher

    def cache_path(
        self, symbol: str, start: date | datetime | str, end: date | datetime | str
    ) -> Path:
        s = str(start)[:10]
        e = str(end)[:10]
        return self.cache_dir / f"{symbol.upper()}_1d_{s}_{e}.csv"

    def get_bars(
        self,
        symbol: str,
        start: date | datetime | str,
        end: date | datetime | str,
        timeframe: str = "1d",
    ) -> list[Bar]:
        path = self.cache_path(symbol, start, end)
        if not path.exists():
            download_csv(symbol, start, end, path, timeframe, fetcher=self._fetcher)
        return CSVDataFeed(path).get_bars(symbol, start, end, timeframe)
