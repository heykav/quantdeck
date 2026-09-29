import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_api_docs  # noqa: E402
import make_synthetic_data  # noqa: E402
import offline_backtest  # noqa: E402

from quantdeck.cli import app  # noqa: E402
from quantdeck.models import OrderSide  # noqa: E402


def test_synthetic_csv_matches_its_generator():
    assert (ROOT / "examples/data/synthetic.csv").read_text() == make_synthetic_data.generate()


def test_offline_example_is_deterministic_and_pinned():
    engine, summary = offline_backtest.run()
    assert summary == {
        "bars": 500,
        "fills": 21,
        "rejected": 0,
        "total_return_pct": -9.81,
        "sharpe": -0.37,
        "max_drawdown_pct": 17.32,
        "ending_equity": 90193.14,
    }
    # Independent reconciliation: replay fills to cash and shares.
    cash, qty = 100_000.0, 0.0
    for f in engine.fills:
        sign = 1 if f.side == OrderSide.BUY else -1
        cash -= sign * f.qty * f.price + f.commission
        qty += sign * f.qty
    last_close = float(
        (ROOT / "examples/data/synthetic.csv").read_text().strip().splitlines()[-1].split(",")[4]
    )
    assert engine.cash == pytest.approx(cash)
    assert engine.equity_curve[-1].equity == pytest.approx(cash + qty * last_close)


def test_offline_example_script_runs_as_a_subprocess():
    out = subprocess.run(
        [sys.executable, str(ROOT / "examples/offline_backtest.py")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "ending_equity: 90193.14" in out


def test_cli_backtest_offline_csv(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "backtest",
            str(ROOT / "examples/sma_crossover.py"),
            "--symbol",
            "SYN",
            "--start",
            "2022-01-01",
            "--end",
            "2030-01-01",
            "--csv",
            str(ROOT / "examples/data/synthetic.csv"),
            "--db",
            str(tmp_path / "r.db"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Number of Trades" in result.output
    assert (tmp_path / "r.db").exists()


def test_api_docs_are_in_sync_with_code():
    assert gen_api_docs.OUT.read_text() == gen_api_docs.render(), (
        "manual/api.md is stale; run: python scripts/gen_api_docs.py"
    )
