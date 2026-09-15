from __future__ import annotations

import sqlite3
from pathlib import Path

from quantdeck.engine import EquityPoint
from quantdeck.models import Fill

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    equity REAL NOT NULL
);
"""


class Storage:
    """Lightweight SQLite persistence for backtest results.

    No ORM, no server to run — just a local file, so there's nothing extra to
    install or configure to get started.
    """

    def __init__(self, db_path: str | Path = "quantdeck.db") -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_run(self, run_id: str, fills: list[Fill], equity_curve: list[EquityPoint]) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT INTO trades (run_id, symbol, side, qty, price, commission, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        f.symbol,
                        f.side.value,
                        f.qty,
                        f.price,
                        f.commission,
                        f.timestamp.isoformat(),
                    )
                    for f in fills
                ],
            )
            self._conn.executemany(
                "INSERT INTO equity_curve (run_id, timestamp, equity) VALUES (?, ?, ?)",
                [(run_id, p.timestamp.isoformat(), p.equity) for p in equity_curve],
            )

    def load_equity_curve(self, run_id: str) -> list[tuple[str, float]]:
        cur = self._conn.execute(
            "SELECT timestamp, equity FROM equity_curve WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()
