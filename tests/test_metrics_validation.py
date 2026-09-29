"""Metrics checked against independent numpy/pandas calculations."""

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.models import Fill, OrderSide


def reference(curve, ppy=252, rf=0.0):
    """Independent implementation using numpy / pandas idioms."""
    s = pd.Series(curve, dtype=float)
    r = s.pct_change().dropna().to_numpy()
    rf_p = rf / ppy
    ex = r - rf_p
    std = r.std(ddof=1)
    dd = np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))
    years = (len(s) - 1) / ppy
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1
    maxdd = float(((s.cummax() - s) / s.cummax()).max())
    return {
        "total": (s.iloc[-1] / s.iloc[0] - 1) * 100,
        "cagr": cagr * 100,
        "vol": std * np.sqrt(ppy) * 100,
        "sharpe": ex.mean() / std * np.sqrt(ppy),
        "sortino": ex.mean() / dd * np.sqrt(ppy),
        "maxdd": maxdd * 100,
        "calmar": cagr / maxdd,
    }


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("rf", [0.0, 0.03])
def test_all_metrics_match_numpy_pandas_reference(seed, rf):
    rng = np.random.default_rng(seed)
    curve = list(100_000 * np.cumprod(1 + rng.normal(0.0005, 0.012, 300)))
    m = compute_metrics(curve, [], periods_per_year=252, risk_free_rate=rf)
    ref = reference(curve, 252, rf)
    assert m.total_return_pct == pytest.approx(ref["total"])
    assert m.cagr_pct == pytest.approx(ref["cagr"])
    assert m.volatility_pct == pytest.approx(ref["vol"])
    assert m.sharpe == pytest.approx(ref["sharpe"])
    assert m.sortino == pytest.approx(ref["sortino"])
    assert m.max_drawdown_pct == pytest.approx(ref["maxdd"])
    assert m.calmar == pytest.approx(ref["calmar"])


def test_hand_computed_small_curve():
    # returns: +0.2, -0.25, +0.222...  Peak 120 -> trough 90 => 25% drawdown.
    m = compute_metrics([100, 120, 90, 110], [], periods_per_year=3)
    r = np.array([0.2, -0.25, 110 / 90 - 1])
    assert m.volatility_pct == pytest.approx(r.std(ddof=1) * math.sqrt(3) * 100)
    assert m.cagr_pct == pytest.approx(10.0)  # 3 periods / 3 per year = 1 year
    assert m.calmar == pytest.approx(0.10 / 0.25)


def test_drawdown_is_worst_peak_to_trough_not_last():
    m = compute_metrics([100, 200, 100, 150, 140], [])
    assert m.max_drawdown_pct == pytest.approx(50.0)


def test_monotone_rising_curve_has_zero_drawdown_and_zero_calmar():
    m = compute_metrics([100, 101, 103, 104], [])
    assert m.max_drawdown_pct == 0.0 and m.calmar == 0.0


def test_constant_growth_is_not_infinite_sharpe():
    curve = [100 * 1.01**i for i in range(60)]
    m = compute_metrics(curve, [])
    assert m.sharpe == 0.0 and m.volatility_pct == 0.0 and m.sortino == 0.0
    assert m.total_return_pct == pytest.approx((1.01**59 - 1) * 100)


def test_two_point_curve_single_return():
    m = compute_metrics([100, 110], [])
    assert m.total_return_pct == pytest.approx(10.0)
    assert m.sharpe == 0.0 and m.volatility_pct == 0.0
    assert math.isfinite(m.cagr_pct)


def test_all_losing_curve_signs():
    m = compute_metrics([100, 95, 90, 85, 80], [])
    assert m.total_return_pct == pytest.approx(-20.0)
    assert m.sharpe < 0 and m.sortino < 0 and m.cagr_pct < 0 and m.calmar < 0
    assert m.max_drawdown_pct == pytest.approx(20.0)


def test_negative_equity_is_treated_as_ruin():
    m = compute_metrics([100, 50, -10, 20], [])
    assert m.total_return_pct == pytest.approx(-100.0)
    assert m.cagr_pct == pytest.approx(-100.0)
    assert m.max_drawdown_pct == pytest.approx(100.0)
    assert all(math.isfinite(x) for x in (m.sharpe, m.sortino, m.calmar, m.volatility_pct))


def test_exactly_zero_equity_is_ruin_too():
    m = compute_metrics([100, 0, 0], [])
    assert m.max_drawdown_pct == pytest.approx(100.0)
    assert m.total_return_pct == pytest.approx(-100.0)


@pytest.mark.parametrize("bad", [[0, 10], [-5, 10], [100, float("nan")], [100, math.inf]])
def test_invalid_curves_raise_value_error(bad):
    with pytest.raises(ValueError):
        compute_metrics(bad, [])


def test_single_trade_stats():
    m = compute_metrics([100, 110], trade_pnls=[10.0])
    assert m.num_trades == 1 and m.win_rate_pct == 100.0 and m.profit_factor == math.inf
    m = compute_metrics([100, 90], trade_pnls=[-10.0])
    assert m.win_rate_pct == 0.0 and m.profit_factor == 0.0


def test_zero_pnl_trade_is_not_a_win():
    m = compute_metrics([100, 100], trade_pnls=[0.0])
    assert m.win_rate_pct == 0.0 and m.num_trades == 1


def _fill(side, qty, price, day, commission=0.0):
    return Fill("T", side, qty, price, datetime(2024, 1, day), commission)


def test_trade_pnl_is_net_of_commission():
    fills = [_fill(OrderSide.BUY, 10, 100, 1, 5.0), _fill(OrderSide.SELL, 10, 105, 2, 5.0)]
    assert compute_trade_pnls(fills) == [pytest.approx(50.0 - 10.0)]


def test_trade_pnl_commission_prorated_over_partial_closes():
    fills = [
        _fill(OrderSide.BUY, 10, 100, 1, 10.0),  # 1.0 per share
        _fill(OrderSide.SELL, 4, 110, 2, 2.0),  # 0.5 per share
        _fill(OrderSide.SELL, 6, 110, 3, 3.0),  # 0.5 per share
    ]
    assert compute_trade_pnls(fills) == [
        pytest.approx(40 - 4 * 1.5),
        pytest.approx(60 - 6 * 1.5),
    ]
    # Total realized P&L reconciles with cash: 100 gross - 15 total commission.
    assert sum(compute_trade_pnls(fills)) == pytest.approx(100 - 15)


def test_trade_pnls_short_round_trip_and_flip():
    fills = [_fill(OrderSide.SELL, 5, 100, 1), _fill(OrderSide.BUY, 8, 90, 2)]
    # covers the 5-share short for +50 and opens a 3-share long (no closed trade yet)
    assert compute_trade_pnls(fills) == [50.0]
