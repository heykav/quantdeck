"""Backtest an SMA 10/30 crossover on REAL BTCUSDT daily prices, next to buy-and-hold.

The data is the committed Binance slice in examples/data (see PROVENANCE.md), so
this runs offline and is deterministic. Both runs go through the same engine with
the same costs. Whatever the numbers turn out to be is what gets printed, including
when the strategy loses to simply holding.

    python examples/real_data_backtest.py

Costs: 5 bps slippage plus about 10 bps for Binance's standard 0.1% taker fee,
modelled together as 15 bps against you on every fill (the engine's commission is a
flat amount per fill, so a percentage fee is approximated through slippage). Crypto
trades every day of the year, so metrics use 365 periods per year, not 252.
Backtest only: market orders, one symbol, no live or paper trading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sma_crossover import SmaCrossoverStrategy

from quantdeck.data.csv_feed import CSVDataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.models import Bar
from quantdeck.strategy import Strategy

DATA = Path(__file__).parent / "data" / "BTCUSDT_1d_2021-2025.csv"
SYMBOL = "BTCUSDT"
START, END = "2021-01-01", "2025-12-31"
CASH = 100_000.0
COST_BPS = 15.0
PERIODS_PER_YEAR = 365
INVEST_FRACTION = 0.99  # buy-and-hold keeps 1% back so next-open slippage cannot reject the buy


class BuyAndHold(Strategy):
    """Buy once on the first bar and never sell."""

    def on_bar(self, bar: Bar) -> None:
        if self.position == 0 and not getattr(self, "_bought", False):
            self._bought = True
            self.buy(self.cash * INVEST_FRACTION / bar.close)


def _run_one(strategy: Strategy) -> dict[str, Any]:
    engine = BacktestEngine(
        strategy=strategy,
        data_feed=CSVDataFeed(DATA),
        symbol=SYMBOL,
        start=START,
        end=END,
        starting_cash=CASH,
        slippage_bps=COST_BPS,
    )
    curve = engine.run()
    values = [p.equity for p in curve]
    m = compute_metrics(values, compute_trade_pnls(engine.fills), periods_per_year=PERIODS_PER_YEAR)
    s = COST_BPS / 10_000
    costs = sum(
        f.qty * (f.price - f.price / (1 + s))
        if f.side.value == "buy"
        else f.qty * (f.price / (1 - s) - f.price)
        for f in engine.fills
    )
    return {
        "metrics": m,
        "fills": len(engine.fills),
        "rejected": len(engine.rejected_orders),
        "costs": costs,
        "ending_equity": values[-1],
        "bars": len(curve),
        "first_day": curve[0].timestamp.date().isoformat(),
        "last_day": curve[-1].timestamp.date().isoformat(),
    }


def run() -> dict[str, dict[str, Any]]:
    sma = SmaCrossoverStrategy()
    sma.fractional = True  # whole-coin sizing is useless for BTC; the strategy invests 95% of cash
    return {"SMA 10/30": _run_one(sma), "Buy and hold": _run_one(BuyAndHold())}


def format_table(results: dict[str, dict[str, Any]]) -> str:
    names = list(results)
    rows = [
        ("Total return", lambda r: f"{r['metrics'].total_return_pct:.2f}%"),
        ("CAGR", lambda r: f"{r['metrics'].cagr_pct:.2f}%"),
        ("Volatility (ann.)", lambda r: f"{r['metrics'].volatility_pct:.2f}%"),
        ("Sharpe (rf 0)", lambda r: f"{r['metrics'].sharpe:.2f}"),
        ("Max drawdown", lambda r: f"{r['metrics'].max_drawdown_pct:.2f}%"),
        ("Round trips", lambda r: str(r["metrics"].num_trades)),
        ("Fills", lambda r: str(r["fills"])),
        ("Costs paid", lambda r: f"${r['costs']:,.2f}"),
        ("Ending equity", lambda r: f"${r['ending_equity']:,.2f}"),
    ]
    width = max(len(label) for label, _ in rows)
    lines = [f"{'':<{width}}  " + "  ".join(f"{n:>14}" for n in names)]
    for label, fmt in rows:
        lines.append(f"{label:<{width}}  " + "  ".join(f"{fmt(results[n]):>14}" for n in names))
    return "\n".join(lines)


if __name__ == "__main__":
    res = run()
    first = res["SMA 10/30"]
    print(
        f"Real data: Binance BTCUSDT daily, {first['first_day']} to {first['last_day']} "
        f"({first['bars']} bars), start cash ${CASH:,.0f}, costs {COST_BPS:g} bps per fill"
    )
    print(format_table(res))
