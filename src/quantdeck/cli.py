from __future__ import annotations

import importlib.util
import inspect
import math
import sys
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantdeck.data.yfinance_feed import YFinanceFeed
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls
from quantdeck.storage import Storage
from quantdeck.strategy import Strategy

app = typer.Typer(help="QuantDeck — a simple, event-driven backtesting framework.")
console = Console()

_STARTER_STRATEGY = '''"""A starter QuantDeck strategy — edit this to build your own."""
from quantdeck.strategy import Strategy


class MyStrategy(Strategy):
    def on_bar(self, bar):
        # Example: buy 10 shares if we have no position yet.
        if self.position == 0:
            self.buy(10)
'''


@app.command()
def init(
    path: str = typer.Argument("strategy.py", help="Where to write the starter strategy file."),
) -> None:
    """Scaffold a starter strategy file."""
    target = Path(path)
    if target.exists():
        typer.confirm(f"{target} already exists. Overwrite?", abort=True)
    target.write_text(_STARTER_STRATEGY)
    console.print(f"[green]Created[/green] {target}")


def _load_strategy(strategy_file: Path) -> type[Strategy]:
    spec = importlib.util.spec_from_file_location(strategy_file.stem, strategy_file)
    if spec is None or spec.loader is None:
        raise typer.BadParameter(f"Could not load {strategy_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    candidates = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, Strategy) and obj is not Strategy
    ]
    if not candidates:
        raise typer.BadParameter(f"No Strategy subclass found in {strategy_file}")
    return candidates[0]


def _format_ratio(value: float) -> str:
    """Ratios are unbounded — a run with no losing trades has an infinite
    profit factor, which reads better as ∞ than as 'inf'."""
    return "∞" if math.isinf(value) else f"{value:.2f}"


@app.command()
def backtest(
    strategy_file: Path = typer.Argument(
        ..., help="Path to a .py file containing a Strategy subclass."
    ),
    symbol: str = typer.Option(..., "--symbol", "-s", help="Ticker symbol, e.g. AAPL."),
    start: str = typer.Option(..., "--start", help="Start date, YYYY-MM-DD."),
    end: str = typer.Option(..., "--end", help="End date, YYYY-MM-DD."),
    cash: float = typer.Option(100_000.0, "--cash", help="Starting cash."),
    risk_free_rate: float = typer.Option(
        0.0,
        "--risk-free-rate",
        "--rf",
        help="Annualized risk-free rate, e.g. 0.04 for 4%. Drives Sharpe and Sortino.",
    ),
    db: str = typer.Option("quantdeck.db", "--db", help="SQLite file to save results to."),
) -> None:
    """Run a backtest for STRATEGY_FILE against real historical data."""
    strategy_cls = _load_strategy(strategy_file)
    strategy = strategy_cls()

    engine = BacktestEngine(
        strategy=strategy,
        data_feed=YFinanceFeed(),
        symbol=symbol,
        start=start,
        end=end,
        starting_cash=cash,
    )

    console.print(
        f"Running backtest: [bold]{strategy_cls.__name__}[/bold] on {symbol} ({start} → {end})"
    )
    equity_curve = engine.run()

    values = [p.equity for p in equity_curve]
    trade_pnls = compute_trade_pnls(engine.fills)
    metrics = compute_metrics(values, trade_pnls, risk_free_rate=risk_free_rate)

    table = Table(title="Backtest Results")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total Return", f"{metrics.total_return_pct:.2f}%")
    table.add_row("CAGR", f"{metrics.cagr_pct:.2f}%")
    table.add_row("Volatility (ann.)", f"{metrics.volatility_pct:.2f}%")
    table.add_row("Sharpe Ratio", f"{metrics.sharpe:.2f}")
    table.add_row("Sortino Ratio", f"{metrics.sortino:.2f}")
    table.add_row("Calmar Ratio", f"{metrics.calmar:.2f}")
    table.add_row("Max Drawdown", f"{metrics.max_drawdown_pct:.2f}%")
    table.add_row("Win Rate", f"{metrics.win_rate_pct:.2f}%")
    table.add_row("Profit Factor", _format_ratio(metrics.profit_factor))
    table.add_row("Number of Trades", str(metrics.num_trades))
    table.add_row("Ending Equity", f"${values[-1]:,.2f}")
    console.print(table)

    run_id = f"{strategy_cls.__name__}-{symbol}-{uuid.uuid4().hex[:8]}"
    storage = Storage(db)
    storage.save_run(run_id, engine.fills, equity_curve)
    storage.close()
    console.print(f"[dim]Saved run '{run_id}' to {db}[/dim]")


if __name__ == "__main__":
    app()
