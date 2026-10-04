import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quantdeck.cli import app
from quantdeck.report import fingerprint, write_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    strategy = tmp_path / "strategy.py"
    csv = tmp_path / "data.csv"
    shutil.copy(ROOT / "examples/sma_crossover.py", strategy)
    shutil.copy(ROOT / "examples/data/synthetic.csv", csv)
    return strategy, csv, tmp_path / "run.db"


def run(inputs, target=None):
    strategy, csv, db = inputs
    args = [
        "backtest",
        str(strategy),
        "--symbol",
        "SYN",
        "--start",
        "2022-01-01",
        "--end",
        "2030-01-01",
        "--commission",
        "1",
        "--csv",
        str(csv),
        "--db",
        str(db),
    ]
    if target is not None:
        args += ["--report", str(target)]
    return CliRunner().invoke(app, args)


def test_report_deterministic_and_reconciles(inputs, tmp_path):
    target = tmp_path / "report.json"
    assert run(inputs, target).exit_code == 0
    first = target.read_bytes()
    assert run(inputs, target).exit_code == 0
    assert target.read_bytes() == first
    data = json.loads(first)
    assert data["schema_version"] == 1
    assert data["strategy"]["sha256"] == hashlib.sha256(inputs[0].read_bytes()).hexdigest()
    assert data["data_source"]["filename"] == "data.csv"
    assert str(tmp_path) not in first.decode()
    assert data["equity_curve"][-1]["equity"] == pytest.approx(90193.14, abs=0.01)
    assert len(data["fills"]) == 21
    cash, shares = data["parameters"]["cash"], 0.0
    for fill in data["fills"]:
        sign = 1 if fill["side"] == "buy" else -1
        shares += sign * fill["qty"]
        cash -= sign * fill["qty"] * fill["price"] + fill["commission"]
    last_close = float(inputs[1].read_text().strip().splitlines()[-1].split(",")[4])
    assert cash + shares * last_close == pytest.approx(data["equity_curve"][-1]["equity"])


def test_hash_changes_with_input(inputs):
    before = fingerprint(inputs[0])
    inputs[0].write_text(inputs[0].read_text() + "\n# different bytes\n")
    assert fingerprint(inputs[0])["sha256"] != before["sha256"]


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_refuses_input_or_database_overwrite(inputs, tmp_path, index, alias):
    source = inputs[index]
    if not source.exists():
        source.write_bytes(b"database placeholder")
    original = source.read_bytes()
    target = source
    if alias != "direct":
        target = tmp_path / "alias.json"
        if alias == "symlink":
            target.symlink_to(source)
        else:
            target.hardlink_to(source)
    result = run(inputs, target)
    assert result.exit_code == 1
    assert "Report error" in result.output
    assert source.read_bytes() == original


def test_strict_json_and_atomic_failure(tmp_path, monkeypatch):
    target = tmp_path / "out.json"
    write_report({"metrics": [float("nan"), float("inf"), -float("inf"), 3.0]}, target)
    assert json.loads(target.read_text()) == {"metrics": [None, None, None, 3.0]}
    before = target.read_bytes()

    def fail(*args):
        raise OSError("cannot replace")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        write_report({"new": True}, target)
    assert target.read_bytes() == before
    assert list(tmp_path.iterdir()) == [target]


def test_optional_and_write_error(inputs, tmp_path):
    assert run(inputs).exit_code == 0
    assert not list(tmp_path.glob("*.json"))
    result = run(inputs, tmp_path / "missing" / "out.json")
    assert result.exit_code == 1
    assert "Report error" in result.output
