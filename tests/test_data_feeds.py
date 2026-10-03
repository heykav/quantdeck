"""CSV parsing errors and the shared inclusive date-range convention."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from quantdeck.data import yfinance_feed
from quantdeck.data.csv_feed import CSVDataFeed, CSVFormatError
from quantdeck.data.yfinance_feed import YFinanceFeed

HEADER = "timestamp,open,high,low,close,volume\n"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "bars.csv"
    path.write_text(text)
    return path


def _bars(path: Path, start="2020-01-01", end="2030-01-01"):
    return CSVDataFeed(path).get_bars("X", start, end)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "file is empty"),
        ("timestamp,open,high,low,close\n2022-01-03,1,1,1,1\n", r"missing column\(s\) volume"),
        (HEADER + "2022-01-03,1,1,1,abc,5\n", "line 2: close value 'abc' is not a number"),
        (HEADER + "2022-01-03,1,1,1,1,5\n2022-01-04,1,,1,1,5\n", "line 3: high value \\(blank\\)"),
        (HEADER + "2022-01-03,1,1,1,1,5\nnot-a-date,1,1,1,1,5\n", "line 3: could not parse"),
        (HEADER + "2022-01-03,1,1,1,1,5\n2022-01-04,nan,1,1,1,5\n", "line 3: open value 'nan'"),
    ],
)
def test_bad_csv_errors_name_the_problem_and_line(tmp_path, text, message):
    path = _write(tmp_path, text)
    with pytest.raises(CSVFormatError, match=message) as info:
        _bars(path)
    assert str(path) in str(info.value)
    assert isinstance(info.value, ValueError)  # existing `except ValueError` keeps working


def test_missing_file_names_the_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.csv"):
        _bars(tmp_path / "nope.csv")


def test_headers_are_case_and_space_insensitive_and_extra_columns_ignored(tmp_path):
    path = _write(
        tmp_path, " Timestamp ,Open,HIGH,Low,Close,Volume,Adj Close\n2022-01-03,1,2,0.5,1.5,7,9\n"
    )
    [bar] = _bars(path)
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (1, 2, 0.5, 1.5, 7)


def test_rows_are_sorted_and_range_is_inclusive(tmp_path):
    rows = ["2022-01-05,3,3,3,3,1", "2022-01-03,1,1,1,1,1", "2022-01-04,2,2,2,2,1"]
    path = _write(tmp_path, HEADER + "\n".join(rows) + "\n")
    assert [b.open for b in _bars(path)] == [1, 2, 3]
    assert [b.open for b in _bars(path, "2022-01-04", "2022-01-05")] == [2, 3]
    assert [b.open for b in _bars(path, date(2022, 1, 3), date(2022, 1, 3))] == [1]


def test_date_only_end_includes_the_whole_day_of_intraday_bars(tmp_path):
    rows = [
        "2022-01-03 09:30,1,1,1,1,1",
        "2022-01-03 15:30,2,2,2,2,1",
        "2022-01-04 09:30,3,3,3,3,1",
    ]
    path = _write(tmp_path, HEADER + "\n".join(rows) + "\n")
    assert [b.open for b in _bars(path, "2022-01-03", "2022-01-03")] == [1, 2]
    # A time of day (or a datetime) is an exact, inclusive cut-off.
    assert [b.open for b in _bars(path, "2022-01-03", "2022-01-03 12:00")] == [1]
    assert [b.open for b in _bars(path, "2022-01-03", datetime(2022, 1, 3, 15, 30))] == [1, 2]


def test_timezone_aware_timestamps_work_with_naive_bounds(tmp_path):
    rows = ["2022-01-03T14:30:00+00:00,1,1,1,1,1", "2022-01-04T14:30:00+00:00,2,2,2,2,1"]
    path = _write(tmp_path, HEADER + "\n".join(rows) + "\n")
    bars = _bars(path, "2022-01-04", "2022-01-04")
    assert [b.open for b in bars] == [2]
    assert bars[0].timestamp.tzinfo is not None


def test_unparseable_bound_is_a_clear_error(tmp_path):
    path = _write(tmp_path, HEADER + "2022-01-03,1,1,1,1,1\n")
    with pytest.raises(ValueError, match="end date 'soon'"):
        _bars(path, "2022-01-01", "soon")


def test_yfinance_end_date_is_inclusive(monkeypatch):
    # Yahoo treats `end` as exclusive; the feed asks for one more day and
    # trims, so a date-only end includes that day as it does for CSVs.
    calls = {}
    index = pd.DatetimeIndex(["2023-01-03", "2023-01-04", "2023-01-05"])
    frame = pd.DataFrame(
        {k: [1.0, 2.0, 3.0] for k in ["Open", "High", "Low", "Close", "Volume"]}, index=index
    )

    def fake_download(symbol, **kwargs):
        calls.update(kwargs, symbol=symbol)
        return frame

    monkeypatch.setattr(yfinance_feed.yf, "download", fake_download)
    bars = YFinanceFeed().get_bars("AAA", "2023-01-03", "2023-01-04")
    assert calls["start"] == "2023-01-03" and calls["end"] == "2023-01-05"
    assert [b.open for b in bars] == [1.0, 2.0]
    assert all(b.symbol == "AAA" for b in bars)


def test_yfinance_empty_range_raises(monkeypatch):
    monkeypatch.setattr(yfinance_feed.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="No data returned"):
        YFinanceFeed().get_bars("AAA", "2023-01-03", "2023-01-04")


def test_cli_reports_bad_csv_without_a_traceback(tmp_path):
    from typer.testing import CliRunner

    from quantdeck.cli import app

    root = Path(__file__).resolve().parent.parent
    path = _write(tmp_path, HEADER + "2022-01-03,1,1,1,oops,5\n")
    result = CliRunner().invoke(
        app,
        ["backtest", str(root / "examples/sma_crossover.py"), "--symbol", "X"]
        + ["--start", "2022-01-01", "--end", "2022-12-31", "--csv", str(path)]
        + ["--db", str(tmp_path / "q.db")],
    )
    assert result.exit_code == 1
    assert "line 2: close value 'oops' is not a number" in result.output
    assert "Traceback" not in result.output
