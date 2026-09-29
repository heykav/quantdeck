"""Shared deterministic fixtures for the tests (no network, no files)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from quantdeck.data.base import DataFeed
from quantdeck.models import Bar

T0 = datetime(2024, 1, 1)


class FixedFeed(DataFeed):
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self._bars


def make_bar(day: int, o: float, c: float | None = None, symbol: str = "TEST") -> Bar:
    c = o if c is None else c
    return Bar(
        symbol=symbol,
        timestamp=T0 + timedelta(days=day),
        open=o,
        high=max(o, c),
        low=min(o, c),
        close=c,
        volume=1000,
    )


def bars_from_opens_closes(opens: list[float], closes: list[float]) -> list[Bar]:
    return [make_bar(i, o, c) for i, (o, c) in enumerate(zip(opens, closes, strict=True))]


def gapless_random_walk(n: int = 200, seed: int = 7) -> list[Bar]:
    """Seeded random walk where each bar opens at the previous close."""
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    opens = np.concatenate([[100.0], closes[:-1]])
    return bars_from_opens_closes([float(x) for x in opens], [float(x) for x in closes])
