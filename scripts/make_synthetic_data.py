"""Generate the deterministic SYNTHETIC price series used by the offline example.

This is a seeded geometric random walk with regime changes. It is NOT market
data and any result computed from it says nothing about real markets.

    python scripts/make_synthetic_data.py > examples/data/synthetic.csv
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np


def generate(n: int = 500, seed: int = 42) -> str:
    rng = np.random.default_rng(seed)
    drift = np.where(np.arange(n) // 100 % 2 == 0, 0.0009, -0.0006)  # alternating regimes
    log_ret = drift + rng.normal(0.0, 0.012, n)
    close = 100.0 * np.exp(np.cumsum(log_ret))
    open_ = np.concatenate([[100.0], close[:-1]]) * np.exp(rng.normal(0.0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.0, 0.004, n)))
    vol = rng.integers(500_000, 2_000_000, n)

    lines = ["timestamp,open,high,low,close,volume"]
    day = date(2022, 1, 3)
    for i in range(n):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        lines.append(
            f"{day.isoformat()},{open_[i]:.4f},{high[i]:.4f},{low[i]:.4f},{close[i]:.4f},{vol[i]}"
        )
        day += timedelta(days=1)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(generate())
