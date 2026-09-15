from datetime import datetime

import pytest

from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.models import Fill, OrderSide


def test_total_return_and_max_drawdown():
    curve = [100, 120, 90, 110]
    metrics = compute_metrics(curve, trade_pnls=[], periods_per_year=252)
    assert metrics.total_return_pct == pytest.approx(10.0)
    assert metrics.max_drawdown_pct == pytest.approx(25.0)  # drop from 120 to 90


def test_win_rate():
    metrics = compute_metrics([100, 110], trade_pnls=[10, -5, 3], periods_per_year=252)
    assert metrics.win_rate_pct == pytest.approx(200 / 3)


def test_compute_metrics_requires_two_points():
    with pytest.raises(ValueError):
        compute_metrics([100], [])


def _fill(side: OrderSide, qty: float, price: float, day: int) -> Fill:
    return Fill(symbol="TEST", side=side, qty=qty, price=price, timestamp=datetime(2024, 1, day))


def test_compute_trade_pnls_fifo_round_trip():
    fills = [
        _fill(OrderSide.BUY, 10, 100, 1),
        _fill(OrderSide.SELL, 10, 110, 2),
    ]
    pnls = compute_trade_pnls(fills)
    assert pnls == [100.0]  # (110 - 100) * 10


def test_compute_trade_pnls_partial_fills():
    fills = [
        _fill(OrderSide.BUY, 10, 100, 1),
        _fill(OrderSide.SELL, 4, 110, 2),
        _fill(OrderSide.SELL, 6, 90, 3),
    ]
    pnls = compute_trade_pnls(fills)
    assert pnls == [pytest.approx(40.0), pytest.approx(-60.0)]
