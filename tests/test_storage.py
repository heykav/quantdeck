from datetime import datetime

from quantdeck.engine import EquityPoint
from quantdeck.models import Fill, OrderSide
from quantdeck.storage import Storage


def test_save_and_load_equity_curve(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(db_path)

    fills = [
        Fill(symbol="TEST", side=OrderSide.BUY, qty=10, price=100.0, timestamp=datetime(2024, 1, 1))
    ]
    curve = [
        EquityPoint(timestamp=datetime(2024, 1, 1), equity=1000.0),
        EquityPoint(timestamp=datetime(2024, 1, 2), equity=1050.0),
    ]

    storage.save_run("run-1", fills, curve)
    loaded = storage.load_equity_curve("run-1")
    storage.close()

    assert len(loaded) == 2
    assert loaded[-1][1] == 1050.0
