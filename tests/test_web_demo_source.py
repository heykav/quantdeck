"""The browser demo runs a copy of the engine in docs/quantdeck_src.

`.github/workflows/sync-web-demo.yml` refreshes that copy after merges to
main; these tests make drift (or a copy that no longer runs) a CI failure on
the pull request itself instead of something noticed later.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "docs" / "quantdeck_src"
COPIED = [
    "__init__.py",
    "models.py",
    "strategy.py",
    "engine.py",
    "metrics.py",
    "broker/__init__.py",
    "broker/base.py",
    "broker/paper.py",
    "data/__init__.py",
    "data/base.py",
]


@pytest.mark.parametrize("rel", COPIED)
def test_demo_copy_matches_package_source(rel):
    assert (DEMO / "quantdeck" / rel).read_text() == (ROOT / "src/quantdeck" / rel).read_text()


def test_demo_strategy_copy_matches_example():
    assert (DEMO / "sma_crossover.py").read_text() == (
        ROOT / "examples/sma_crossover.py"
    ).read_text()


def test_demo_copy_runs_without_pandas_on_bundled_data():
    # Runs the demo's own copy (not src/) the way the page does, with pandas
    # and yfinance import blocked, on a bundled dataset.
    code = (
        "import sys, json\n"
        "sys.modules['pandas'] = None; sys.modules['yfinance'] = None\n"
        "import quantdeck, web_glue\n"
        "assert quantdeck.__file__.startswith(sys.argv[1]), quantdeck.__file__\n"
        "text = open(sys.argv[2]).read()\n"
        "print(web_glue.run_web_backtest('SPY', text, 10, 30, 100000))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(DEMO)}
    out = subprocess.run(
        [sys.executable, "-c", code, str(DEMO), str(ROOT / "docs/data/SPY.csv")],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout
    result = json.loads(out)
    assert "error" not in result
    assert len(result["equity_curve"]) == len(result["dates"]) > 100
    assert result["trades"]
