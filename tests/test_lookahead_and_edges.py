"""Look-ahead invariance, gaps, shorts, end of data and float-noise settlement."""

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest
from helpers import FixedFeed, bars_from_opens_closes, gapless_random_walk, make_bar

from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.models import Bar, Order, OrderSide
from quantdeck.strategy import Strategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
from sma_crossover import SmaCrossoverStrategy  # noqa: E402


def _engine(strategy, bars, symbol="TEST", **kw):
    kw.setdefault("slippage_bps", 0)
    return BacktestEngine(
        strategy, FixedFeed(bars), symbol=symbol, start="2024-01-01", end="2030-01-01", **kw
    )


class _Scripted(Strategy):
    """Places orders on given bar indices: {index: ("buy"|"sell", qty)}."""

    def __init__(self, script):
        super().__init__()
        self.script = script
        self.i = -1

    def on_bar(self, bar: Bar) -> None:
        self.i += 1
        if self.i in self.script:
            side, qty = self.script[self.i]
            getattr(self, side)(qty)


class _MeanReversion(Strategy):
    """Trades on every bar's close vs a short average, so any leak of future
    prices into decisions changes its trades."""

    def on_start(self) -> None:
        self.closes: list[float] = []

    def on_bar(self, bar: Bar) -> None:
        self.closes.append(bar.close)
        if len(self.closes) < 5:
            return
        avg = sum(self.closes[-5:]) / 5
        if bar.close < avg and self.position == 0:
            self.buy(10)
        elif bar.close > avg and self.position > 0:
            self.sell(self.position)


def _perturb_from(bars: list[Bar], k: int, seed: int) -> list[Bar]:
    """Replace every bar after index k with an unrelated random path."""
    rng = np.random.default_rng(seed)
    out = list(bars[: k + 1])
    for b in bars[k + 1 :]:
        o, c = (float(x) for x in rng.uniform(50, 150, 2))
        out.append(dataclasses.replace(b, open=o, close=c, high=max(o, c), low=min(o, c)))
    return out


def _record_orders(eng: BacktestEngine) -> list[tuple[int, Order]]:
    """Log every order with the index of the bar whose on_bar placed it."""
    log: list[tuple[int, Order]] = []
    submit = eng.submit_order

    def recording_submit(order: Order) -> None:
        log.append((len(eng.equity_curve), order))  # the point for bar t is appended after on_bar
        submit(order)

    eng.submit_order = recording_submit  # type: ignore[method-assign]
    return log


@pytest.mark.parametrize("strategy_cls", [_MeanReversion, SmaCrossoverStrategy])
@pytest.mark.parametrize("k", [70, 125, 170])
def test_changing_the_future_does_not_change_the_past(strategy_cls, k):
    # The core look-ahead test: decisions made on bars 0..k, and the equity
    # and fills up to bar k, may depend only on bars 0..k. Rewrite every bar
    # after k and they must be bit-for-bit identical. (Verified to fail if the
    # engine hands on_bar the next bar instead of the current one.)
    bars = gapless_random_walk(200, seed=5)
    costs = {"starting_cash": 100_000, "slippage_bps": 5, "commission": 1}
    a = _engine(strategy_cls(), bars, **costs)
    b = _engine(strategy_cls(), _perturb_from(bars, k, seed=k), **costs)
    orders_a, orders_b = _record_orders(a), _record_orders(b)
    ca, cb = a.run(), b.run()
    assert [p.equity for p in ca[: k + 1]] == [p.equity for p in cb[: k + 1]]
    assert [o for o in orders_a if o[0] <= k] == [o for o in orders_b if o[0] <= k]
    cutoff = bars[k].timestamp
    past_a = [f for f in a.fills if f.timestamp <= cutoff]
    past_b = [f for f in b.fills if f.timestamp <= cutoff]
    assert past_a == past_b
    assert past_a, "the strategy should have traded before bar k"


def test_fills_on_a_bar_ignore_that_bars_close_high_and_low():
    # A fill on bar t happens at its open, before the bar is known. Changing
    # bar t's close/high/low must leave the fill (price and whether it
    # happened) untouched; only the mark-to-market of that bar may move.
    bars = gapless_random_walk(40, seed=9)
    t = 11
    altered = list(bars)
    o = bars[t].open
    altered[t] = dataclasses.replace(bars[t], close=o * 3, high=o * 3, low=o)
    script = {t - 1: ("buy", 5)}
    a = _engine(_Scripted(script), bars, starting_cash=10_000)
    b = _engine(_Scripted(dict(script)), altered, starting_cash=10_000)
    a.run()
    b.run()
    assert a.fills == b.fills
    assert a.fills[0].timestamp == bars[t].timestamp and a.fills[0].price == bars[t].open


def test_gap_fills_at_the_gapped_open_not_the_previous_close():
    # Decide at close 100; the next bar gaps down to open 70 (and there are
    # missing calendar days in between). The sell fills at 70 - slippage.
    bars = [make_bar(0, 100, 100), make_bar(1, 100, 100), make_bar(9, 70, 72)]
    eng = _engine(
        _Scripted({0: ("buy", 10), 1: ("sell", 10)}),
        bars,
        starting_cash=5_000,
        slippage_bps=10,
    )
    eng.run()
    assert [f.price for f in eng.fills] == pytest.approx([100 * 1.001, 70 * 0.999])
    assert eng.fills[1].timestamp == bars[2].timestamp


def test_open_position_at_end_is_marked_not_liquidated():
    bars = bars_from_opens_closes([100, 100, 110, 120], [100, 105, 115, 125])
    eng = _engine(_Scripted({0: ("buy", 10)}), bars, starting_cash=5_000)
    curve = eng.run()
    assert eng.position_qty == 10  # still held: no forced liquidation
    assert curve[-1].equity == pytest.approx(5_000 - 100 * 10 + 125 * 10)
    # The unrealised trade is in the equity curve but not in the trade list.
    assert compute_trade_pnls(eng.fills) == []


def test_short_that_runs_away_can_go_negative_and_metrics_call_it_ruin():
    # Short 10 at 100 with 100 cash, then the price triples. There is no
    # margin model, so equity goes negative and buying back is rejected for
    # lack of cash; the metrics treat the negative equity as a total loss.
    bars = bars_from_opens_closes([100, 100, 300, 300], [100, 100, 300, 300])
    eng = _engine(
        _Scripted({0: ("sell", 10), 2: ("buy", 10)}), bars, starting_cash=100, allow_short=True
    )
    curve = eng.run()
    assert eng.cash == pytest.approx(1_100)
    assert eng.position_qty == -10
    assert curve[-1].equity == pytest.approx(1_100 - 3_000)
    assert [r.reason for r in eng.rejected_orders] == ["insufficient cash"]
    m = compute_metrics([p.equity for p in curve], [])
    assert m.total_return_pct == -100 and m.max_drawdown_pct == 100 and m.cagr_pct == -100


def test_flip_long_to_short_in_one_order():
    bars = bars_from_opens_closes([100, 100, 90, 80], [100, 100, 90, 80])
    eng = _engine(
        _Scripted({0: ("buy", 5), 1: ("sell", 15)}), bars, starting_cash=1_000, allow_short=True
    )
    curve = eng.run()
    assert eng.position_qty == -10
    assert eng.broker._positions["TEST"].avg_price == 90
    assert eng.cash == pytest.approx(1_000 - 500 + 15 * 90)
    assert curve[-1].equity == pytest.approx(eng.cash - 10 * 80)


def test_bars_for_another_symbol_are_rejected_instead_of_never_filling():
    # Regression: the broker only fills orders on bars of the same symbol, so
    # a feed returning bars labelled differently used to leave every order
    # pending forever, silently producing a flat equity curve.
    bars = bars_from_opens_closes([100] * 3, [100] * 3)  # labelled "TEST"
    with pytest.raises(ValueError, match="'TEST'.*'OTHER'"):
        _engine(_Scripted({0: ("buy", 1)}), bars, symbol="OTHER").run()


def test_float_noise_oversell_is_settled_to_exactly_flat():
    # Regression: holding 725781.9604 shares, selling 722027.273 and then the
    # 3754.6874 that is left on paper overshoots the float position by
    # ~1e-10 shares. That used to leave a microscopic *short* position with
    # shorting disabled (so `position == 0` never became true again).
    held, first = 725781.9604, 722027.273
    rest = round(held - first, 6)
    assert rest > held - first  # the overshoot this test is about
    bars = bars_from_opens_closes([1.0] * 5, [1.0] * 5)
    eng = _engine(
        _Scripted({0: ("buy", held), 1: ("sell", first), 2: ("sell", rest)}),
        bars,
        starting_cash=1_000_000,
    )
    eng.run()
    assert eng.rejected_orders == []
    assert eng.position_qty == 0.0
    assert eng.fills[-1].qty == pytest.approx(rest)
    assert eng.cash == pytest.approx(1_000_000)


def test_real_oversell_is_still_rejected():
    bars = bars_from_opens_closes([100] * 4, [100] * 4)
    eng = _engine(_Scripted({0: ("buy", 1), 1: ("sell", 1.001)}), bars, starting_cash=1_000)
    eng.run()
    assert eng.position_qty == 1
    assert len(eng.rejected_orders) == 1


def test_tiny_sell_with_no_position_is_rejected_not_filled_as_zero():
    bars = bars_from_opens_closes([100] * 3, [100] * 3)
    eng = _engine(_Scripted({0: ("sell", 1e-12)}), bars, starting_cash=1_000)
    eng.run()
    assert eng.fills == [] and len(eng.rejected_orders) == 1


def test_fractional_partial_closes_book_no_phantom_trade():
    # Regression: 0.3 - 0.1 - 0.1 - 0.1 leaves ~3e-17 in float arithmetic.
    # The trade matcher used to keep that as an open short lot, then book it
    # as an extra (winning) round trip on the next buy.
    bars = bars_from_opens_closes([10, 10, 11, 11, 11, 10, 12, 12], [10] * 8)
    eng = _engine(
        _Scripted(
            {0: ("buy", 0.3), 1: ("sell", 0.1), 2: ("sell", 0.1), 3: ("sell", 0.1)}
            | {4: ("buy", 1), 5: ("sell", 1)}
        ),
        bars,
        starting_cash=1_000,
    )
    eng.run()
    assert eng.rejected_orders == []
    assert [f.side for f in eng.fills] == [OrderSide.BUY] + [OrderSide.SELL] * 3 + [
        OrderSide.BUY,
        OrderSide.SELL,
    ]
    pnls = compute_trade_pnls(eng.fills)
    assert pnls == pytest.approx([0.1, 0.1, 0.1, 2.0])
