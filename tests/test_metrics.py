import math
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


def test_sharpe_matches_legacy_zero_rate_value():
    # Guards the refactor: with no risk-free rate, Sharpe must still be
    # exactly what the original mean/std formulation produced.
    metrics = compute_metrics([100, 120, 90, 110], [], periods_per_year=252)
    assert metrics.sharpe == pytest.approx(3.42, abs=0.01)


def test_risk_free_rate_reduces_sharpe():
    zero_rate = compute_metrics([100, 120, 90, 110], [], periods_per_year=252)
    with_rate = compute_metrics([100, 120, 90, 110], [], periods_per_year=252, risk_free_rate=0.05)
    assert with_rate.sharpe < zero_rate.sharpe


def test_sortino_exceeds_sharpe_when_downside_is_milder_than_total_volatility():
    metrics = compute_metrics([100, 120, 90, 110], [], periods_per_year=252)
    assert metrics.sortino > metrics.sharpe
    assert metrics.sortino == pytest.approx(6.31, abs=0.01)


def test_sortino_is_zero_when_no_period_loses_money():
    metrics = compute_metrics([100, 101, 102, 103], [], periods_per_year=252)
    assert metrics.sortino == 0.0
    assert metrics.sharpe > 0  # the curve really is trending up, not degenerate


def test_calmar_is_cagr_over_max_drawdown():
    # periods_per_year=3 makes this three-period curve exactly one year long,
    # so CAGR is the plain 10% total return and max drawdown is the 120 -> 90
    # drop. Calmar is then 0.10 / 0.25.
    metrics = compute_metrics([100, 120, 90, 110], [], periods_per_year=3)
    assert metrics.cagr_pct == pytest.approx(10.0)
    assert metrics.max_drawdown_pct == pytest.approx(25.0)
    assert metrics.calmar == pytest.approx(0.4)


def test_volatility_scales_with_square_root_of_periods_per_year():
    fast = compute_metrics([100, 120, 90, 110], [], periods_per_year=63)
    slow = compute_metrics([100, 120, 90, 110], [], periods_per_year=252)
    assert slow.volatility_pct / fast.volatility_pct == pytest.approx(2.0)


def test_profit_factor_is_gross_profit_over_gross_loss():
    metrics = compute_metrics([100, 110], trade_pnls=[10, -5, 3])
    assert metrics.profit_factor == pytest.approx(13 / 5)


def test_profit_factor_is_infinite_without_losing_trades():
    metrics = compute_metrics([100, 110], trade_pnls=[10, 5])
    assert metrics.profit_factor == math.inf


def test_profit_factor_is_zero_without_trades():
    metrics = compute_metrics([100, 110], trade_pnls=[])
    assert metrics.profit_factor == 0.0


def test_flat_curve_yields_zeroed_risk_ratios():
    metrics = compute_metrics([100, 100, 100], [], periods_per_year=252)
    assert metrics.sharpe == 0.0
    assert metrics.sortino == 0.0
    assert metrics.calmar == 0.0
    assert metrics.volatility_pct == 0.0
    assert metrics.max_drawdown_pct == 0.0
