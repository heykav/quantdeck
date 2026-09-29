import math

import pytest
from helpers import FixedFeed, bars_from_opens_closes, gapless_random_walk, make_bar

from quantdeck.engine import BacktestEngine
from quantdeck.models import Bar, Order, OrderSide
from quantdeck.strategy import Strategy


def _engine(strategy, bars, **kw):
    kw.setdefault("slippage_bps", 0)
    return BacktestEngine(
        strategy, FixedFeed(bars), symbol="TEST", start="2024-01-01", end="2030-01-01", **kw
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


def test_hand_computed_pnl_with_slippage_and_commission():
    # Decide on bar 0 -> buy fills at bar 1 open 110 (+10 bps). Decide on bar 2
    # -> sell fills at bar 3 open 130 (-10 bps). Flat commission 1 per fill.
    opens = [100, 110, 120, 130, 140]
    bars = bars_from_opens_closes(opens, [105, 115, 125, 135, 145])
    eng = _engine(
        _Scripted({0: ("buy", 10), 2: ("sell", 10)}),
        bars,
        starting_cash=10_000,
        slippage_bps=10,
        commission=1.0,
    )
    curve = eng.run()

    buy_px, sell_px = 110 * 1.001, 130 * 0.999  # 110.11, 129.87
    assert [f.price for f in eng.fills] == pytest.approx([buy_px, sell_px])
    expected_cash = 10_000 - (buy_px * 10 + 1) + (sell_px * 10 - 1)
    assert expected_cash == pytest.approx(10_000 + (129.87 - 110.11) * 10 - 2)  # 10195.6
    assert eng.cash == pytest.approx(expected_cash)
    assert eng.position_qty == 0
    assert curve[-1].equity == pytest.approx(expected_cash)
    # Mid-trade point (bar 1 close 115): cash after buy + 10 shares at 115.
    assert curve[1].equity == pytest.approx(10_000 - (buy_px * 10 + 1) + 10 * 115)
    # Bar 0: nothing has filled yet, so equity is exactly starting cash.
    assert curve[0].equity == 10_000


def test_zero_cost_buy_and_hold_equals_price_ratio():
    bars = gapless_random_walk(250)
    cash0 = 50_000.0

    class AllIn(Strategy):
        done = False

        def on_bar(self, bar):
            if not self.done:
                self.buy(self.cash / bar.close)  # bar.close == next open (gapless)
                self.done = True

    eng = _engine(AllIn(), bars, starting_cash=cash0)
    curve = eng.run()
    assert curve[-1].equity / cash0 == pytest.approx(bars[-1].close / bars[0].close, rel=1e-12)
    # Every point tracks the price path, not just the end.
    for p, b in zip(curve, bars, strict=True):
        assert p.equity == pytest.approx(cash0 * b.close / bars[0].close, rel=1e-12)
    assert eng.rejected_orders == []


def test_peeking_style_strategy_earns_nothing():
    # Every bar opens at 100 and closes alternately +10 / -10. A strategy that
    # could buy at the open of a bar it already saw close up would earn +10 per
    # up bar. Here it can only act on the *next* open, so it earns exactly 0.
    n = 40
    opens = [100.0] * n
    closes = [110.0 if i % 2 == 0 else 90.0 for i in range(n)]
    bars = bars_from_opens_closes(opens, closes)

    class ChaseTheCloseThenFlatten(Strategy):
        def on_bar(self, bar):
            if self.position > 0:
                self.sell(self.position)
            elif bar.close > bar.open:
                self.buy(1)

    eng = _engine(ChaseTheCloseThenFlatten(), bars, starting_cash=1_000)
    eng.run()
    assert eng.fills, "strategy should have traded"
    assert all(f.price == 100 for f in eng.fills)
    # Every round trip is bought at 100 and sold at 100, so realized P&L is 0:
    # final equity differs from the start only by the open position's mark.
    final_equity = eng.cash + eng.position_qty * bars[-1].close
    assert final_equity - 1_000 == pytest.approx(eng.position_qty * (bars[-1].close - 100))
    completed = [f for f in eng.fills if f.side == OrderSide.SELL]
    assert completed and all(f.price == 100 for f in completed)


def test_fills_always_strictly_after_decision_bar_at_next_open():
    bars = gapless_random_walk(121, seed=3)
    decisions = {}

    class Recorder(Strategy):
        i = -1

        def on_bar(self, bar):
            self.i += 1
            if self.i % 7 == 0 and self.position == 0:
                self.buy(1)
                decisions[self.i] = bar.timestamp
            elif self.i % 7 == 3 and self.position > 0:
                self.sell(self.position)
                decisions[self.i] = bar.timestamp

    eng = _engine(Recorder(), bars, starting_cash=10_000)
    eng.run()
    ts_index = {b.timestamp: i for i, b in enumerate(bars)}
    decided = sorted(decisions)
    assert len(eng.fills) == len(decided)
    for idx, fill in zip(decided, eng.fills, strict=True):
        assert ts_index[fill.timestamp] == idx + 1
        assert fill.price == bars[idx + 1].open


def test_order_on_last_bar_never_fills():
    bars = bars_from_opens_closes([100, 100, 100], [100, 100, 100])
    eng = _engine(_Scripted({2: ("buy", 5)}), bars, starting_cash=1_000)
    eng.run()
    assert eng.fills == [] and eng.cash == 1_000 and eng.position_qty == 0


def test_insufficient_cash_is_rejected_and_recorded():
    bars = bars_from_opens_closes([100, 200, 200], [100, 200, 200])
    # Sized off the close of 100 (10 shares = 1000) but fills at the 200 gap-up open.
    eng = _engine(_Scripted({0: ("buy", 10)}), bars, starting_cash=1_000)
    eng.run()
    assert eng.fills == [] and eng.cash == 1_000
    assert [r.reason for r in eng.rejected_orders] == ["insufficient cash"]


def test_cannot_sell_more_than_held_by_default():
    bars = bars_from_opens_closes([100] * 4, [100] * 4)
    eng = _engine(_Scripted({0: ("sell", 10)}), bars, starting_cash=1_000)
    eng.run()
    assert eng.position_qty == 0 and eng.cash == 1_000
    assert "shorting disabled" in eng.rejected_orders[0].reason


def test_double_sell_before_fill_does_not_create_short():
    bars = bars_from_opens_closes([100] * 5, [100] * 5)
    eng = _engine(
        _Scripted({0: ("buy", 10), 2: ("sell", 10), 3: ("sell", 10)}), bars, starting_cash=5_000
    )
    eng.run()
    assert eng.position_qty == 0
    assert len(eng.rejected_orders) == 1


def test_short_selling_only_when_enabled():
    bars = bars_from_opens_closes([100, 100, 80, 80], [100, 100, 80, 80])
    eng = _engine(
        _Scripted({0: ("sell", 10), 2: ("buy", 10)}), bars, starting_cash=1_000, allow_short=True
    )
    eng.run()
    assert eng.position_qty == 0
    assert eng.cash == pytest.approx(1_000 + (100 - 80) * 10)


@pytest.mark.parametrize("qty", [0, -5, math.nan, math.inf])
def test_invalid_order_quantity_rejected(qty):
    with pytest.raises(ValueError):
        Order("TEST", OrderSide.BUY, qty)


def test_negative_buy_cannot_be_used_to_conjure_cash():
    eng = _engine(_Scripted({0: ("buy", -5)}), bars_from_opens_closes([100] * 3, [100] * 3))
    with pytest.raises(ValueError):
        eng.run()


def test_order_for_other_symbol_is_rejected_loudly():
    class Wrong(Strategy):
        def on_bar(self, bar):
            self.buy(1, symbol="OTHER")

    with pytest.raises(ValueError, match="OTHER"):
        _engine(Wrong(), bars_from_opens_closes([100] * 3, [100] * 3)).run()


def test_run_twice_is_an_error():
    eng = _engine(_Scripted({}), bars_from_opens_closes([100] * 3, [100] * 3))
    eng.run()
    with pytest.raises(RuntimeError):
        eng.run()


@pytest.mark.parametrize(
    "bars",
    [
        [make_bar(1, 100), make_bar(0, 100)],  # out of order
        [make_bar(0, 100), make_bar(0, 100)],  # duplicate timestamp
        [make_bar(0, 100), make_bar(1, float("nan"))],
        [make_bar(0, 100), make_bar(1, -5)],
    ],
)
def test_bad_bar_data_is_rejected(bars):
    with pytest.raises(ValueError):
        _engine(_Scripted({}), bars).run()


def test_equity_identity_cash_plus_position_value():
    bars = gapless_random_walk(150, seed=11)
    eng = _engine(
        _Scripted({5: ("buy", 20), 40: ("sell", 5), 70: ("buy", 3), 120: ("sell", 18)}),
        bars,
        starting_cash=20_000,
        slippage_bps=5,
        commission=2.5,
    )
    curve = eng.run()
    # Replay the fills independently and rebuild cash / qty at the end.
    cash, qty = 20_000.0, 0.0
    for f in eng.fills:
        sign = 1 if f.side == OrderSide.BUY else -1
        cash -= sign * f.qty * f.price + f.commission
        qty += sign * f.qty
    assert eng.cash == pytest.approx(cash)
    assert eng.position_qty == pytest.approx(qty)
    assert curve[-1].equity == pytest.approx(cash + qty * bars[-1].close)
