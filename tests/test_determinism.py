"""Same data + same configuration must give identical results."""

import re
import sqlite3
import sys
from pathlib import Path

from helpers import FixedFeed, gapless_random_walk
from typer.testing import CliRunner

from quantdeck.cli import app
from quantdeck.data.csv_feed import CSVDataFeed
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import compute_metrics, compute_trade_pnls

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))
from sma_crossover import SmaCrossoverStrategy  # noqa: E402

CSV = ROOT / "examples/data/synthetic.csv"


def _run(feed):
    eng = BacktestEngine(
        SmaCrossoverStrategy(),
        feed,
        symbol="SYN",
        start="2022-01-01",
        end="2030-01-01",
        slippage_bps=5,
        commission=1,
    )
    curve = eng.run()
    metrics = compute_metrics([p.equity for p in curve], compute_trade_pnls(eng.fills))
    return curve, eng.fills, eng.rejected_orders, metrics


def test_repeated_runs_are_bit_for_bit_identical():
    first = _run(CSVDataFeed(CSV))
    for _ in range(3):
        assert _run(CSVDataFeed(CSV)) == first  # dataclass equality: exact floats


def test_in_memory_and_csv_feeds_agree():
    bars = CSVDataFeed(CSV).get_bars("SYN", "2022-01-01", "2030-01-01")
    assert _run(FixedFeed(bars)) == _run(CSVDataFeed(CSV))


def test_seeded_helper_data_is_reproducible():
    assert gapless_random_walk(50, seed=1) == gapless_random_walk(50, seed=1)


def test_cli_runs_are_identical_apart_from_the_run_id(tmp_path):
    db = tmp_path / "r.db"
    args = ["backtest", str(ROOT / "examples/sma_crossover.py"), "--symbol", "SYN"]
    args += ["--start", "2022-01-01", "--end", "2030-01-01", "--csv", str(CSV), "--db", str(db)]
    outputs = []
    for _ in range(2):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        outputs.append(re.sub(r"-[0-9a-f]{8}'", "-<id>'", result.output))
    assert outputs[0] == outputs[1]

    with sqlite3.connect(db) as conn:
        runs = [r for (r,) in conn.execute("SELECT DISTINCT run_id FROM equity_curve")]
        assert len(runs) == 2
        curves = [
            conn.execute(
                "SELECT timestamp, equity FROM equity_curve WHERE run_id = ? ORDER BY id", (r,)
            ).fetchall()
            for r in runs
        ]
        trades = [
            conn.execute(
                "SELECT symbol, side, qty, price, commission, timestamp FROM trades "
                "WHERE run_id = ? ORDER BY id",
                (r,),
            ).fetchall()
            for r in runs
        ]
    assert curves[0] == curves[1] and len(curves[0]) == 500
    assert trades[0] == trades[1] and trades[0]
